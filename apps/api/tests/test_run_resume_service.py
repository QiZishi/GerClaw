"""Explicit Run resume reconstruction and trust-boundary validation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.config import Settings
from gerclaw_api.database.models import AgentRun, ExecutionTrace, Message
from gerclaw_api.modules.agent_harness.clinical_state import ClinicalState
from gerclaw_api.modules.agent_harness.config import ResolvedHarnessConfig
from gerclaw_api.modules.agent_harness.context_snapshot import (
    AgentContext,
    ContextProjectionManifest,
    ConversationHistoryMessage,
    FrozenToolContract,
    PersistedContextSnapshot,
    PersistedRunPlan,
)
from gerclaw_api.modules.agent_harness.planning import (
    ClinicalDecisionCoordinator,
    DeterministicPlanner,
    PlanRequest,
)
from gerclaw_api.modules.agent_harness.routing import RouteDecision, RouteKind
from gerclaw_api.modules.contracts import ExecutionContext
from gerclaw_api.modules.runtime.models import ExecutionBudget
from gerclaw_api.modules.workflows import get_default_workflow_registry
from gerclaw_api.repositories.run_resume import RunResumeRecord
from gerclaw_api.services.run_resume_service import (
    RunResumeConflictError,
    RunResumeDataError,
    RunResumeNotFoundError,
    RunResumeService,
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_unit0001"


class _Repository:
    def __init__(self, record: RunResumeRecord | None) -> None:
        self.record = record
        self.rollbacks = 0
        self.controlled_successor_id: uuid.UUID | None = None
        self.active_steer_directive_id: uuid.UUID | None = None

    async def get_owned_context(
        self,
        _run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunResumeRecord | None:
        assert (tenant_id, actor_id) == (TENANT, ACTOR)
        return self.record

    async def get_latest_recoverable(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        assert (tenant_id, actor_id) == (TENANT, ACTOR)
        if self.record is None or self.record.run.conversation_id != conversation_id:
            return None
        return self.record.run

    async def get_controlled_successor_id(
        self,
        _run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> uuid.UUID | None:
        assert (tenant_id, actor_id) == (TENANT, ACTOR)
        return self.controlled_successor_id

    async def get_active_steer_directive_id(
        self,
        _run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> uuid.UUID | None:
        assert (tenant_id, actor_id) == (TENANT, ACTOR)
        return self.active_steer_directive_id

    async def rollback(self) -> None:
        self.rollbacks += 1


def _record() -> RunResumeRecord:
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()
    message_id = uuid.uuid4()
    trace_id = "trace_resume_unit_0001"
    request_id = "request_resume_unit_0001"
    now = datetime.now(UTC)
    settings = Settings()
    resolved = ResolvedHarnessConfig.from_settings(settings)
    budget = ExecutionBudget(
        max_steps=resolved.max_react_iterations,
        max_output_bytes=resolved.max_output_bytes,
    )
    route = RouteDecision(
        route=RouteKind.STANDARD,
        reason_code="test_standard",
    )
    clinical_decision = ClinicalDecisionCoordinator(
        minimum_score=resolved.savi_minimum_score
    ).prepare(state=ClinicalState(), message="请恢复这次回答", has_attachments=False)
    dynamic_plan = DeterministicPlanner(
        execution_budget=budget,
        output_reserve_tokens=resolved.model_output_reserve_tokens,
    ).build(
        PlanRequest(
            route=RouteKind.STANDARD,
            selected_action="answer",
        )
    )
    workflow = get_default_workflow_registry().resolve("standard")
    context = AgentContext(
        execution=ExecutionContext(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            session_id=session_id,
        ),
        system_instructions=(
            "medical_safety_v1",
            "traceable_evidence_required_v1",
            "no_raw_chain_of_thought_v1",
        ),
        tool_names=("search_knowledge", "search_memory"),
        conversation_history=(
            ConversationHistoryMessage(
                role="assistant",
                text="这是冻结的历史。",
            ),
        ),
        projection=ContextProjectionManifest(
            model_context_tokens=32_768,
            trigger_tokens=27_852,
            target_tokens=21_299,
            output_reserve_tokens=2_048,
            estimated_tokens_before=1_024,
            estimated_tokens_after=1_024,
            history_budget_tokens=1_000,
            history_message_count=1,
            retained_history_message_count=1,
            compression_state="not_needed",
            compression_strategy="none",
            source_hash="0" * 64,
            sections=(),
        ),
    )
    snapshot = PersistedContextSnapshot(
        input_message_id=message_id,
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
        workflow_version=workflow.version,
        workflow_owner_module=workflow.owner_module,
        search_enabled=workflow.search_enabled,
        route_decision=route,
        dynamic_plan=dynamic_plan,
        clinical_decision=clinical_decision,
        resolved_config=resolved,
        execution_budget=budget,
    )
    run = AgentRun(
        id=run_id,
        tenant_id=TENANT,
        actor_id=ACTOR,
        conversation_id=session_id,
        input_message_id=message_id,
        trace_id=trace_id,
        route="standard",
        status="interrupted",
        context_snapshot=snapshot.model_dump(mode="json"),
        plan=plan.model_dump(mode="json"),
        warnings=[],
        fencing_token=7,
        last_sequence=2,
        revision=2,
        started_at=now,
        interrupted_at=now,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    message = Message(
        id=message_id,
        tenant_id=TENANT,
        session_id=session_id,
        trace_id=trace_id,
        role="user",
        content=[{"type": "text", "text": " 请恢复这次回答 "}],
        message_metadata={"channel": "web"},
        created_at=now,
    )
    trace = ExecutionTrace(
        trace_id=trace_id,
        request_id=request_id,
        tenant_id=TENANT,
        actor_id=ACTOR,
        session_id=session_id,
        execution_type="agent.chat",
        status="running",
        attributes={},
        private_input_artifacts={},
        started_at=now,
    )
    return RunResumeRecord(run=run, input_message=message, trace=trace)


@pytest.mark.asyncio
async def test_prepare_reconstructs_only_server_persisted_input() -> None:
    record = _record()
    repository = _Repository(record)
    command = await RunResumeService(repository).prepare(
        record.run.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert command.trace_id == record.run.trace_id
    assert command.request.message == "请恢复这次回答"
    assert command.request.loaded_skills == []
    assert command.request.uploaded_files == []
    assert command.request.images == []
    assert command.request_id == record.trace.request_id
    assert command.state.snapshot.agent_context.conversation_history[0].text == ("这是冻结的历史。")
    projection = command.state.snapshot.agent_context.projection
    assert projection is not None
    assert projection.source_hash == "0" * 64
    assert repository.rollbacks == 1


@pytest.mark.asyncio
async def test_prepare_preserves_server_validated_regeneration_identity() -> None:
    record = _record()
    source_run_id = uuid.uuid4()
    current_version_id = uuid.uuid4()
    record.run.plan = {
        **record.run.plan,
        "regenerate_from_run_id": str(source_run_id),
        "expected_current_answer_version_id": str(current_version_id),
    }
    command = await RunResumeService(_Repository(record)).prepare(
        record.run.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert command.request.regenerate_from_run_id == source_run_id
    assert command.request.expected_current_answer_version_id == current_version_id


@pytest.mark.asyncio
async def test_prepare_rejects_run_replaced_by_controlled_successor() -> None:
    record = _record()
    repository = _Repository(record)
    directive_id = uuid.uuid4()
    repository.active_steer_directive_id = directive_id
    repository.controlled_successor_id = uuid.uuid4()

    with pytest.raises(
        RunResumeConflictError,
        match="replaced by a controlled successor",
    ):
        await RunResumeService(repository).prepare(
            record.run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    command = await RunResumeService(repository).prepare(
        record.run.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
        controlled_directive_id=directive_id,
    )
    assert command.run_id == record.run.id


@pytest.mark.asyncio
async def test_pending_steer_reserves_source_from_public_resume() -> None:
    record = _record()
    repository = _Repository(record)
    directive_id = uuid.uuid4()
    repository.active_steer_directive_id = directive_id

    with pytest.raises(RunResumeConflictError, match="reserved"):
        await RunResumeService(repository).prepare(
            record.run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )

    command = await RunResumeService(repository).prepare(
        record.run.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
        controlled_directive_id=directive_id,
    )
    assert command.run_id == record.run.id


@pytest.mark.asyncio
async def test_prepare_rejects_non_interrupted_or_corrupt_material() -> None:
    record = _record()
    record.run.status = "completed"
    repository = _Repository(record)
    with pytest.raises(RunResumeConflictError):
        await RunResumeService(repository).prepare(
            record.run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    record.run.status = "cancelled"
    with pytest.raises(RunResumeConflictError):
        await RunResumeService(repository).prepare(
            record.run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    record.run.status = "interrupted"
    record.run.plan = {**record.run.plan, "loaded_skill_count": 2}
    with pytest.raises(RunResumeDataError):
        await RunResumeService(repository).prepare(
            record.run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_prepare_rejects_legacy_snapshot_without_context_projection() -> None:
    record = _record()
    agent_context = dict(record.run.context_snapshot["agent_context"])
    agent_context.pop("projection")
    record.run.context_snapshot = {
        **record.run.context_snapshot,
        "schema_version": "context-snapshot-v1",
        "agent_context": agent_context,
    }

    with pytest.raises(RunResumeDataError):
        await RunResumeService(_Repository(record)).prepare(
            record.run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_prepare_rejects_cross_actor_or_unknown_snapshot_material() -> None:
    record = _record()
    agent_context = record.run.context_snapshot["agent_context"]
    assert isinstance(agent_context, dict)
    execution = agent_context["execution"]
    assert isinstance(execution, dict)
    execution["actor_id"] = "usr_patient_foreign0001"
    with pytest.raises(RunResumeDataError):
        await RunResumeService(_Repository(record)).prepare(
            record.run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )

    record = _record()
    record.run.context_snapshot["unexpected"] = True
    with pytest.raises(RunResumeDataError):
        await RunResumeService(_Repository(record)).prepare(
            record.run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_prepare_hides_missing_or_foreign_run() -> None:
    repository = _Repository(None)
    with pytest.raises(RunResumeNotFoundError):
        await RunResumeService(repository).prepare(
            uuid.uuid4(),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    assert repository.rollbacks == 1


@pytest.mark.asyncio
async def test_latest_interrupted_returns_public_run_without_contents() -> None:
    record = _record()
    repository = _Repository(record)
    latest = await RunResumeService(repository).latest_recoverable(
        record.run.conversation_id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert latest is not None
    assert latest.id == record.run.id
    assert latest.status.value == "interrupted"
    assert repository.rollbacks == 1
