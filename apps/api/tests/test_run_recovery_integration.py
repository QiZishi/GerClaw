"""Lease-aware Agent run recovery against real PostgreSQL and Redis."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import suppress

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from gerclaw_api.database.models import (
    AgentRun,
    AgentRunPlanNodeEvent,
    AnswerVersion,
    EvolutionSignalRecord,
    RunEvent,
)
from gerclaw_api.domain.chat_schemas import ChatRequest
from gerclaw_api.domain.run_schemas import AgentRunCreate
from gerclaw_api.domain.trace_schemas import TraceStartRequest
from gerclaw_api.modules.agent_harness.clinical_state import ClinicalState
from gerclaw_api.modules.agent_harness.config import ResolvedHarnessConfig
from gerclaw_api.modules.agent_harness.context_snapshot import (
    AgentContext,
    ContextProjectionManifest,
    FrozenToolContract,
    PersistedContextSnapshot,
    PersistedRunPlan,
)
from gerclaw_api.modules.agent_harness.planning import (
    ClinicalDecisionCoordinator,
    DeterministicPlanner,
    DynamicPlan,
    DynamicPlanExecutor,
    PlanExecutionSnapshot,
    PlanNode,
    PlanRequest,
)
from gerclaw_api.modules.agent_harness.plugin_runtime import (
    CapabilityEntrypoint,
    CapabilityResult,
    CapabilitySelection,
    CapabilitySelectionMode,
    SelectedCapability,
)
from gerclaw_api.modules.agent_harness.routing import RouteDecision, RouteKind
from gerclaw_api.modules.agent_harness.safety import MEDICAL_DISCLAIMER
from gerclaw_api.modules.contracts import (
    AgentResponse,
    ExecutionContext,
    SafetyDecision,
)
from gerclaw_api.modules.runtime.models import ExecutionBudget
from gerclaw_api.modules.workflows import get_default_workflow_registry
from gerclaw_api.repositories.agent_run import SqlAlchemyAgentRunRepository
from gerclaw_api.repositories.conversation import SqlAlchemyConversationRepository
from gerclaw_api.repositories.trace import SqlAlchemyTraceRepository
from gerclaw_api.services import chat_service as chat_service_module
from gerclaw_api.services.agent_run_service import (
    AgentRunConflictError,
    AgentRunService,
)
from gerclaw_api.services.chat_service import _fingerprint
from gerclaw_api.services.conversation_service import ConversationService
from gerclaw_api.services.run_recovery_service import StaleAgentRunReconciler
from gerclaw_api.services.session_lease import SessionBusyError, SessionLease
from gerclaw_api.services.trace_service import TraceService

TENANT = "tenant_public0001"
ACTOR = "usr_patient_integration0001"


def _frozen_run_material(
    *,
    settings: object,
    payload: ChatRequest,
    input_message_id: uuid.UUID,
    trace_id: str,
    request_id: str,
    regenerate_from_run_id: uuid.UUID | None = None,
    expected_current_answer_version_id: uuid.UUID | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    resolved = ResolvedHarnessConfig.from_settings(settings)  # type: ignore[arg-type]
    budget = ExecutionBudget(
        max_steps=resolved.max_react_iterations,
        max_output_bytes=resolved.max_output_bytes,
    )
    route = RouteDecision(
        route=RouteKind.STANDARD,
        reason_code="integration_resume_fixture",
    )
    clinical_decision = ClinicalDecisionCoordinator(
        minimum_score=resolved.savi_minimum_score
    ).prepare(
        state=ClinicalState(),
        message=payload.message,
        has_attachments=False,
    )
    dynamic_plan = DeterministicPlanner(
        execution_budget=budget,
        output_reserve_tokens=resolved.model_output_reserve_tokens,
    ).build(PlanRequest(route=RouteKind.STANDARD))
    workflow = get_default_workflow_registry().resolve(payload.workflow)
    context = AgentContext(
        execution=ExecutionContext(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            session_id=payload.session_id,
        ),
        system_instructions=(
            "medical_safety_v1",
            "traceable_evidence_required_v1",
            "no_raw_chain_of_thought_v1",
        ),
        tool_names=("search_knowledge", "search_memory"),
        projection=ContextProjectionManifest(
            model_context_tokens=32_768,
            trigger_tokens=27_852,
            target_tokens=21_299,
            output_reserve_tokens=2_048,
            estimated_tokens_before=1_024,
            estimated_tokens_after=1_024,
            history_budget_tokens=0,
            history_message_count=0,
            retained_history_message_count=0,
            compression_state="not_needed",
            compression_strategy="none",
            source_hash="0" * 64,
            sections=(),
        ),
    )
    snapshot = PersistedContextSnapshot(
        input_message_id=input_message_id,
        agent_context=context,
        prompt_policy_ids=context.system_instructions,
        tool_contracts=tuple(
            FrozenToolContract(name=name, version="1.0.0") for name in context.tool_names
        ),
    )
    plan = PersistedRunPlan(
        loaded_skill_count=0,
        requested_capability_count=0,
        uploaded_document_count=0,
        uploaded_image_count=0,
        workflow=workflow.workflow_id,
        workflow_definition=workflow,
        channel=payload.channel,
        workflow_version=workflow.version,
        workflow_owner_module=workflow.owner_module,
        search_enabled=workflow.search_enabled,
        route_decision=route,
        dynamic_plan=dynamic_plan,
        plan_execution=PlanExecutionSnapshot.initial(dynamic_plan),
        clinical_decision=clinical_decision,
        resolved_config=resolved,
        execution_budget=budget,
        regenerate_from_run_id=regenerate_from_run_id,
        expected_current_answer_version_id=expected_current_answer_version_id,
    )
    return (
        snapshot.model_dump(mode="json"),
        plan.model_dump(mode="json"),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_plan_node_transitions_are_fenced_persisted_and_append_audited(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    response = await client.post(
        "/api/v1/sessions",
        json={"session_id": str(session_id)},
    )
    assert response.status_code == 201, response.text

    payload = ChatRequest(session_id=session_id, message="计划节点持久化测试")
    trace_id = "trace_plan_node_integration_0001"
    async with app.state.database.session() as session:
        conversation_service = ConversationService(SqlAlchemyConversationRepository(session))
        conversation = await conversation_service.require_session(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        message = await conversation_service.store_user_message(
            tenant_id=TENANT,
            conversation=conversation,
            session_id=session_id,
            trace_id=trace_id,
            text=payload.message,
            channel="web",
        )
        context, plan_payload = _frozen_run_material(
            settings=app.state.settings,
            payload=payload,
            input_message_id=message.id,
            trace_id=trace_id,
            request_id="req_plan_node_integration_0001",
        )
        service = AgentRunService(SqlAlchemyAgentRunRepository(session))
        created = await service.create_run(
            AgentRunCreate(
                conversation_id=session_id,
                input_message_id=message.id,
                trace_id=trace_id,
                route=RouteKind.STANDARD,
                fencing_token=23,
                context_snapshot=context,
                plan=plan_payload,
            ),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )

    persisted = PersistedRunPlan.model_validate(plan_payload)
    executor = DynamicPlanExecutor(
        persisted.dynamic_plan,
        snapshot=persisted.effective_plan_execution(),
    )
    first_node = persisted.dynamic_plan.nodes[0]
    node_id = executor.start_capability(first_node.capability)
    async with app.state.database.session() as session:
        service = AgentRunService(SqlAlchemyAgentRunRepository(session))
        running = await service.update_plan_execution(
            created.id,
            executor.snapshot(),
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=23,
        )
    executor.complete(node_id)
    async with app.state.database.session() as session:
        service = AgentRunService(SqlAlchemyAgentRunRepository(session))
        completed = await service.update_plan_execution(
            created.id,
            executor.snapshot(),
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=23,
        )
        with pytest.raises(AgentRunConflictError):
            await service.update_plan_execution(
                created.id,
                completed,
                tenant_id=TENANT,
                actor_id=ACTOR,
                fencing_token=23,
            )

    async with app.state.database.session() as session:
        stored = await session.get(AgentRun, created.id)
        events = list(
            (
                await session.scalars(
                    select(AgentRunPlanNodeEvent)
                    .where(AgentRunPlanNodeEvent.run_id == created.id)
                    .order_by(AgentRunPlanNodeEvent.id.asc())
                )
            ).all()
        )
    assert stored is not None
    stored_plan = PersistedRunPlan.model_validate(stored.plan)
    assert stored_plan.plan_execution == completed
    assert running.statuses[node_id].value == "running"
    assert completed.statuses[node_id].value == "completed"
    assert [
        (event.node_id, event.attempt, event.status, event.fencing_token) for event in events
    ] == [
        (node_id, 1, "running", 23),
        (node_id, 1, "completed", 23),
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_capability_result_and_completion_commit_atomically_in_postgres(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    response = await client.post(
        "/api/v1/sessions",
        json={"session_id": str(session_id)},
    )
    assert response.status_code == 201, response.text

    payload = ChatRequest(session_id=session_id, message="能力结果原子持久化测试")
    trace_id = "trace_capability_result_integration_0001"
    dynamic_plan = DynamicPlan(
        route=RouteKind.STANDARD,
        nodes=(
            PlanNode(
                node_id="capability",
                required=False,
                capability="gerclaw.cga",
                public_summary="正在执行老年综合评估",
            ),
            PlanNode(
                node_id="answer",
                capability="answer.standard",
                public_summary="正在整理回答",
            ),
        ),
    )
    selection = CapabilitySelection(
        selected=(
            SelectedCapability(
                capability_id="gerclaw.cga",
                source=CapabilitySelectionMode.MANUAL,
                entrypoint=CapabilityEntrypoint.CGA_ASSESSMENT,
                owner_module="cga",
            ),
        )
    )
    async with app.state.database.session() as session:
        conversation_service = ConversationService(SqlAlchemyConversationRepository(session))
        conversation = await conversation_service.require_session(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        message = await conversation_service.store_user_message(
            tenant_id=TENANT,
            conversation=conversation,
            session_id=session_id,
            trace_id=trace_id,
            text=payload.message,
            channel="web",
        )
        context, base_plan_payload = _frozen_run_material(
            settings=app.state.settings,
            payload=payload,
            input_message_id=message.id,
            trace_id=trace_id,
            request_id="req_capability_result_integration_0001",
        )
        plan = PersistedRunPlan.model_validate(
            base_plan_payload
            | {
                "capability_selection": selection.model_dump(mode="json"),
                "dynamic_plan": dynamic_plan.model_dump(mode="json"),
                "plan_execution": PlanExecutionSnapshot.initial(dynamic_plan).model_dump(
                    mode="json"
                ),
            }
        )
        service = AgentRunService(SqlAlchemyAgentRunRepository(session))
        created = await service.create_run(
            AgentRunCreate(
                conversation_id=session_id,
                input_message_id=message.id,
                trace_id=trace_id,
                route=RouteKind.STANDARD,
                fencing_token=29,
                context_snapshot=context,
                plan=plan.model_dump(mode="json"),
            ),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )

    executor = DynamicPlanExecutor(
        dynamic_plan,
        snapshot=plan.effective_plan_execution(),
    )
    node_id = executor.start_capability("gerclaw.cga")
    async with app.state.database.session() as session:
        service = AgentRunService(SqlAlchemyAgentRunRepository(session))
        await service.update_plan_execution(
            created.id,
            executor.snapshot(),
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=29,
        )

    executor.complete(node_id)
    result = CapabilityResult(
        capability_id="gerclaw.cga",
        result_ref="cga:assessment:integration",
        public_summary="老年综合评估已完成。",
    )
    async with app.state.database.session() as session:
        service = AgentRunService(SqlAlchemyAgentRunRepository(session))
        completed = await service.update_plan_execution(
            created.id,
            executor.snapshot(),
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=29,
            capability_result=result,
        )

    async with app.state.database.session() as session:
        stored = await session.get(AgentRun, created.id)
        events = list(
            (
                await session.scalars(
                    select(AgentRunPlanNodeEvent)
                    .where(AgentRunPlanNodeEvent.run_id == created.id)
                    .order_by(AgentRunPlanNodeEvent.id.asc())
                )
            ).all()
        )
    assert stored is not None
    stored_plan = PersistedRunPlan.model_validate(stored.plan)
    assert stored_plan.plan_execution == completed
    assert stored_plan.capability_results == (result,)
    assert [(event.node_id, event.status, event.fencing_token) for event in events] == [
        (node_id, "running", 29),
        (node_id, "completed", 29),
    ]


class _ResumeHarness:
    def __init__(self, **kwargs: object) -> None:
        preassembled = kwargs.get("preassembled_context")
        self.context = (
            preassembled
            if isinstance(preassembled, AgentContext)
            else AgentContext(
                execution=kwargs["execution"],
                system_instructions=(
                    "medical_safety_v1",
                    "traceable_evidence_required_v1",
                    "no_raw_chain_of_thought_v1",
                ),
                tool_names=("search_knowledge", "search_memory"),
            )
        )

    async def assemble_context(self, *_args: object, **_kwargs: object) -> object:
        return self.context

    async def process_message(self, *_args: object, **_kwargs: object) -> AgentResponse:
        return AgentResponse(
            text=f"恢复后的安全回答。\n\n{MEDICAL_DISCLAIMER}",
            safety=SafetyDecision(
                reviewed=True,
                disclaimer_applied=True,
                deterministic_diagnosis_blocked=False,
                high_risk_escalation_checked=True,
                notices=[
                    "medical_disclaimer_applied",
                    "deterministic_diagnosis_checked",
                    "high_risk_escalation_checked",
                ],
            ),
            medical_content=False,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recovery_interrupts_only_runs_without_cross_replica_lease(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    orphan_session_id = uuid.uuid4()
    active_session_id = uuid.uuid4()
    for session_id in (orphan_session_id, active_session_id):
        response = await client.post(
            "/api/v1/sessions",
            json={"session_id": str(session_id)},
        )
        assert response.status_code == 201, response.text

    async def create_run(session_id: uuid.UUID, trace_id: str, fence: int) -> uuid.UUID:
        async with app.state.database.session() as session:
            conversation_service = ConversationService(SqlAlchemyConversationRepository(session))
            conversation = await conversation_service.require_session(
                session_id,
                tenant_id=TENANT,
                actor_id=ACTOR,
            )
            message = await conversation_service.store_user_message(
                tenant_id=TENANT,
                conversation=conversation,
                session_id=session_id,
                trace_id=trace_id,
                text="恢复测试",
                channel="web",
            )
            run = await AgentRunService(SqlAlchemyAgentRunRepository(session)).create_run(
                AgentRunCreate(
                    conversation_id=session_id,
                    input_message_id=message.id,
                    trace_id=trace_id,
                    route=RouteKind.STANDARD,
                    fencing_token=fence,
                ),
                tenant_id=TENANT,
                actor_id=ACTOR,
            )
            return run.id

    orphan_run_id = await create_run(
        orphan_session_id,
        "trace_recovery_orphan_0001",
        101,
    )
    active_run_id = await create_run(
        active_session_id,
        "trace_recovery_active_0001",
        102,
    )
    active_lease_key = SessionLease.key_for(
        tenant_id=TENANT,
        session_id=active_session_id,
    )
    await app.state.redis.set(active_lease_key, "102:other-replica", ex=60)
    try:
        interrupted_count = await StaleAgentRunReconciler(
            app.state.database,
            app.state.redis,
            batch_size=1,
            guard_ttl_seconds=30,
            evolution_signal_collector=app.state.evolution_signal_collector,
        ).reconcile()
    finally:
        await app.state.redis.delete(active_lease_key)
    await app.state.evolution_signal_collector.wait_pending()

    async with app.state.database.session() as session:
        orphan = await session.get(AgentRun, orphan_run_id)
        active = await session.get(AgentRun, active_run_id)
        orphan_events = list(
            (await session.scalars(select(RunEvent).where(RunEvent.run_id == orphan_run_id))).all()
        )
        signals = list((await session.scalars(select(EvolutionSignalRecord))).all())
    assert interrupted_count == 1
    assert orphan is not None and orphan.status == "interrupted"
    assert orphan.completed_at is None
    assert orphan.interrupted_at is not None
    assert active is not None and active.status == "running"
    assert [event.status for event in orphan_events] == ["interrupted"]
    assert [signal.run_status for signal in signals] == ["interrupted"]
    active_recoverable = await client.get(
        f"/api/v1/conversations/{active_session_id}/recoverable-run"
    )
    assert active_recoverable.status_code == 200, active_recoverable.text
    assert active_recoverable.json()["run"]["id"] == str(active_run_id)
    assert active_recoverable.json()["run"]["status"] == "running"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recovery_guard_closes_lease_check_to_interrupt_window(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    async with app.state.database.session() as session:
        conversation_service = ConversationService(SqlAlchemyConversationRepository(session))
        conversation = await conversation_service.require_session(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        message = await conversation_service.store_user_message(
            tenant_id=TENANT,
            conversation=conversation,
            session_id=session_id,
            trace_id="trace_recovery_guard_0001",
            text="恢复互斥测试",
            channel="web",
        )
        run = await AgentRunService(SqlAlchemyAgentRunRepository(session)).create_run(
            AgentRunCreate(
                conversation_id=session_id,
                input_message_id=message.id,
                trace_id="trace_recovery_guard_0001",
                route=RouteKind.STANDARD,
                fencing_token=301,
            ),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )

    entered_interrupt = asyncio.Event()
    release_interrupt = asyncio.Event()
    original_interrupt = AgentRunService.interrupt_owned

    async def delayed_interrupt(
        service: AgentRunService,
        run_id: uuid.UUID,
        **kwargs: object,
    ) -> object:
        entered_interrupt.set()
        await release_interrupt.wait()
        return await original_interrupt(service, run_id, **kwargs)

    monkeypatch.setattr(AgentRunService, "interrupt_owned", delayed_interrupt)
    reconcile_task = asyncio.create_task(
        StaleAgentRunReconciler(
            app.state.database,
            app.state.redis,
            batch_size=10,
            guard_ttl_seconds=1,
        ).reconcile()
    )
    await asyncio.wait_for(entered_interrupt.wait(), timeout=3)
    # Exceed the old fixed TTL. Renewal must keep excluding a worker for the
    # entire PostgreSQL transition.
    await asyncio.sleep(1.2)
    lease = SessionLease(app.state.redis, ttl_seconds=60)
    with pytest.raises(SessionBusyError):
        async with lease.acquire(
            tenant_id=TENANT,
            session_id=session_id,
            fencing_token=302,
        ):
            pytest.fail("new worker cannot enter the recovery transition window")
    release_interrupt.set()
    try:
        assert await asyncio.wait_for(reconcile_task, timeout=3) == 1
    finally:
        if not reconcile_task.done():
            reconcile_task.cancel()
            with suppress(asyncio.CancelledError):
                await reconcile_task

    async with app.state.database.session() as session:
        recovered = await session.get(AgentRun, run.id)
    assert recovered is not None and recovered.status == "interrupted"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_explicit_resume_adopts_interrupted_run_and_completes_it(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_recovery_retry_0001"
    payload = ChatRequest(session_id=session_id, message="请恢复这次回答")
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    workflow = get_default_workflow_registry().validate_context(
        payload.workflow,
        loaded_skill_count=0,
        uploaded_file_count=0,
        uploaded_image_count=0,
    )
    async with app.state.database.session() as session:
        conversation_service = ConversationService(SqlAlchemyConversationRepository(session))
        conversation = await conversation_service.require_session(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        message = await conversation_service.store_user_message(
            tenant_id=TENANT,
            conversation=conversation,
            session_id=session_id,
            trace_id=trace_id,
            text=payload.message,
            channel=payload.channel,
        )
        old_fence = await conversation_service.next_fencing_token()
        await TraceService(SqlAlchemyTraceRepository(session)).start_trace(
            TraceStartRequest(
                session_id=session_id,
                execution_type="agent.chat",
                attributes={
                    "channel": payload.channel,
                    "feature": "medical_chat",
                    "module": "agent_harness",
                    "operation": "process_message",
                    "request_fingerprint": _fingerprint(payload, app.state.settings),
                    "workflow": workflow.workflow_id.value,
                    "workflow_version": workflow.version,
                    "workflow_owner_module": workflow.owner_module,
                },
            ),
            "request_recovery_retry_0001",
            trace_id=trace_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        context_snapshot, persisted_plan = _frozen_run_material(
            settings=app.state.settings,
            payload=payload,
            input_message_id=message.id,
            trace_id=trace_id,
            request_id="request_recovery_retry_0001",
        )
        run_service = AgentRunService(SqlAlchemyAgentRunRepository(session))
        run = await run_service.create_run(
            AgentRunCreate(
                conversation_id=session_id,
                input_message_id=message.id,
                trace_id=trace_id,
                route=RouteKind.STANDARD,
                context_snapshot=context_snapshot,
                plan=persisted_plan,
                fencing_token=old_fence,
            ),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        frozen_plan = PersistedRunPlan.model_validate(persisted_plan)
        plan_executor = DynamicPlanExecutor(
            frozen_plan.dynamic_plan,
            snapshot=frozen_plan.effective_plan_execution(),
        )
        in_flight_node_id = plan_executor.start_capability(
            frozen_plan.dynamic_plan.nodes[0].capability
        )
        await run_service.update_plan_execution(
            run.id,
            plan_executor.snapshot(),
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=old_fence,
        )
        await run_service.interrupt_owned(
            run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        run_id = run.id

    monkeypatch.setattr(chat_service_module, "ProductionAgentHarness", _ResumeHarness)
    recoverable = await client.get(f"/api/v1/conversations/{session_id}/recoverable-run")
    assert recoverable.status_code == 200, recoverable.text
    assert recoverable.json()["run"]["id"] == str(run_id)
    response = await client.post(f"/api/v1/runs/{run_id}/resume")

    assert response.status_code == 200, response.text
    assert "event: done" in response.text
    assert response.headers["x-trace-id"] == trace_id
    async with app.state.database.session() as session:
        resumed = await session.get(AgentRun, run_id)
        events = list(
            (
                await session.scalars(
                    select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.sequence)
                )
            ).all()
        )
        node_events = list(
            (
                await session.scalars(
                    select(AgentRunPlanNodeEvent)
                    .where(AgentRunPlanNodeEvent.run_id == run_id)
                    .order_by(AgentRunPlanNodeEvent.id)
                )
            ).all()
        )
    assert resumed is not None and resumed.status == "completed"
    assert resumed.current_answer_version_id is not None
    resumed_plan = PersistedRunPlan.model_validate(resumed.plan)
    assert resumed_plan.effective_plan_execution().statuses[in_flight_node_id].value == "failed"
    assert [(event.status, event.error_code) for event in node_events] == [
        ("running", None),
        ("failed", "RUN_INTERRUPTED_BEFORE_NODE_COMMIT"),
    ]
    assert "run.resumed" in [event.event_type for event in events]
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    replay_stream = await client.get(
        f"/api/v1/runs/{run_id}/stream",
        params={"after_sequence": 0},
    )
    assert replay_stream.status_code == 200, replay_stream.text
    assert "id: 1" in replay_stream.text
    assert "event: done" in replay_stream.text
    assert f'"run_id":"{run_id}"' in replay_stream.text
    assert f'"sequence":{events[-1].sequence}' in replay_stream.text
    no_longer_recoverable = await client.get(f"/api/v1/conversations/{session_id}/recoverable-run")
    assert no_longer_recoverable.json()["run"] is None
    replayed_resume = await client.post(f"/api/v1/runs/{run_id}/resume")
    assert replayed_resume.status_code == 409
    assert replayed_resume.json()["error"]["code"] == "RUN_RESOURCE_CONFLICT"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_explicit_resume_reuses_source_input_for_interrupted_regeneration(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    source_trace_id = "trace_resume_regeneration_source_0001"
    interrupted_trace_id = "trace_resume_regeneration_retry_0001"
    message_text = "请给我一般健康建议"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    monkeypatch.setattr(chat_service_module, "ProductionAgentHarness", _ResumeHarness)
    source_response = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": source_trace_id},
        json={
            "session_id": str(session_id),
            "message": message_text,
            "channel": "web",
        },
    )
    assert source_response.status_code == 200, source_response.text
    assert "event: done" in source_response.text

    async with app.state.database.session() as session:
        source_run = await session.scalar(
            select(AgentRun).where(AgentRun.trace_id == source_trace_id)
        )
        assert source_run is not None
        assert source_run.current_answer_version_id is not None
        source_run_id = source_run.id
        source_input_message_id = source_run.input_message_id
        source_answer_version_id = source_run.current_answer_version_id

    regeneration = ChatRequest(
        session_id=session_id,
        message=message_text,
        regenerate_from_run_id=source_run_id,
        expected_current_answer_version_id=source_answer_version_id,
    )
    workflow = get_default_workflow_registry().validate_context(
        regeneration.workflow,
        loaded_skill_count=0,
        uploaded_file_count=0,
        uploaded_image_count=0,
    )
    async with app.state.database.session() as session:
        conversation_service = ConversationService(SqlAlchemyConversationRepository(session))
        old_fence = await conversation_service.next_fencing_token()
        await TraceService(SqlAlchemyTraceRepository(session)).start_trace(
            TraceStartRequest(
                session_id=session_id,
                execution_type="agent.chat",
                attributes={
                    "channel": regeneration.channel,
                    "feature": "medical_chat",
                    "module": "agent_harness",
                    "operation": "process_message",
                    "request_fingerprint": _fingerprint(regeneration, app.state.settings),
                    "workflow": workflow.workflow_id.value,
                    "workflow_version": workflow.version,
                    "workflow_owner_module": workflow.owner_module,
                },
            ),
            "request_resume_regeneration_retry_0001",
            trace_id=interrupted_trace_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        context_snapshot, persisted_plan = _frozen_run_material(
            settings=app.state.settings,
            payload=regeneration,
            input_message_id=source_input_message_id,
            trace_id=interrupted_trace_id,
            request_id="request_resume_regeneration_retry_0001",
            regenerate_from_run_id=source_run_id,
            expected_current_answer_version_id=source_answer_version_id,
        )
        run_service = AgentRunService(SqlAlchemyAgentRunRepository(session))
        interrupted_run = await run_service.create_run(
            AgentRunCreate(
                conversation_id=session_id,
                input_message_id=source_input_message_id,
                trace_id=interrupted_trace_id,
                route=RouteKind.STANDARD,
                context_snapshot=context_snapshot,
                plan=persisted_plan,
                fencing_token=old_fence,
            ),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        await run_service.interrupt_owned(
            interrupted_run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        interrupted_run_id = interrupted_run.id

    resumed = await client.post(
        f"/api/v1/runs/{interrupted_run_id}/resume",
    )
    assert resumed.status_code == 200, resumed.text
    assert "event: done" in resumed.text
    assert resumed.headers["x-trace-id"] == interrupted_trace_id
    assert f'"answer_group_run_id":"{source_run_id}"' in resumed.text

    async with app.state.database.session() as session:
        completed_run = await session.get(AgentRun, interrupted_run_id)
        versions = list(
            (
                await session.scalars(
                    select(AnswerVersion)
                    .where(AnswerVersion.run_id == source_run_id)
                    .order_by(AnswerVersion.version)
                )
            ).all()
        )
    assert completed_run is not None and completed_run.status == "completed"
    assert len(versions) == 2
    assert [version.is_current for version in versions] == [False, True]
    assert versions[1].producer_run_id == interrupted_run_id
