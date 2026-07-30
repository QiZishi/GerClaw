"""Conversation persistence and Redis serialization against real dependencies."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from gerclaw_api.auth import create_access_token
from gerclaw_api.database.models import (
    AgentRun,
    AnswerVersion,
    BadCase,
    Message,
    RunEvent,
)
from gerclaw_api.domain.enums import TraceStatus
from gerclaw_api.domain.run_schemas import AgentRunStatus
from gerclaw_api.domain.trace_schemas import TraceFinishRequest
from gerclaw_api.modules.agent_harness import AgentContext, StreamEvent
from gerclaw_api.modules.agent_harness.run_lifecycle import RunFenceConflictError
from gerclaw_api.modules.contracts import AgentResponse, Citation, SafetyDecision
from gerclaw_api.repositories.conversation import (
    ConversationConflictError,
    SqlAlchemyConversationRepository,
)
from gerclaw_api.services import chat_service as chat_service_module
from gerclaw_api.services.agent_run_service import AgentRunService
from gerclaw_api.services.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
)
from gerclaw_api.services.session_lease import (
    SessionBusyError,
    SessionLease,
    SessionLeaseLostError,
)
from gerclaw_api.services.trace_service import TraceService

TENANT = "tenant_public0001"
ACTOR = "usr_patient_integration0001"


def _fake_agent_context(kwargs: dict[str, object]) -> AgentContext:
    preassembled = kwargs.get("preassembled_context")
    if isinstance(preassembled, AgentContext):
        return preassembled
    documents = kwargs.get("uploaded_documents")
    document_ids = tuple(
        str(item.document_id)
        for item in documents
        if hasattr(item, "document_id")
    ) if isinstance(documents, list) else ()
    loaded_skill_ids = kwargs.get("loaded_skill_ids")
    return AgentContext(
        execution=kwargs["execution"],
        system_instructions=(
            "medical_safety_v1",
            "traceable_evidence_required_v1",
            "no_raw_chain_of_thought_v1",
        ),
        tool_names=(),
        clinical_state=kwargs.get("clinical_state", {}),
        loaded_skills=(
            tuple(loaded_skill_ids)
            if isinstance(loaded_skill_ids, list)
            else ()
        ),
        uploaded_files=document_ids,
        conversation_history=(
            tuple(kwargs["history"])
            if isinstance(kwargs.get("history"), list)
            else ()
        ),
    )


class _EmptyRAG:
    async def retrieve(self, *_args: object, **_kwargs: object) -> list[object]:
        return []


class _SafeHarness:
    def __init__(self, **kwargs: object) -> None:
        self.context = _fake_agent_context(kwargs)

    async def assemble_context(self, *_args: object, **_kwargs: object) -> object:
        return self.context

    async def process_message(self, *_args: object, **_kwargs: object) -> AgentResponse:
        return _safe_response()


class _BlockingSkillHarness:
    entered = asyncio.Event()

    def __init__(self, **_kwargs: object) -> None:
        type(self).entered.clear()
        self.context = _fake_agent_context(_kwargs)

    async def assemble_context(self, *_args: object, **_kwargs: object) -> object:
        return self.context

    async def process_message(
        self,
        _message: str,
        _session_id: str,
        _context: object,
        callback: Callable[[StreamEvent], Awaitable[None]],
    ) -> AgentResponse:
        await callback(
            StreamEvent(
                event_type="tool_call",
                data={
                    "tool_call_id": "tool_call_cancel_route_001",
                    "tool_name": "Skill",
                    "status": "running",
                },
                timestamp=datetime.now(UTC),
            )
        )
        self.entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await callback(
                StreamEvent(
                    event_type="tool_result",
                    data={
                        "tool_call_id": "tool_call_cancel_route_001",
                        "tool_name": "Skill",
                        "status": "cancelled",
                        "duration_ms": 1,
                    },
                    timestamp=datetime.now(UTC),
                )
            )
            raise


class _GateFirstHarness(_SafeHarness):
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def process_message(self, *_args: object, **_kwargs: object) -> AgentResponse:
        type(self).calls += 1
        if type(self).calls == 1:
            type(self).entered.set()
            await type(self).release.wait()
        return _safe_response()


def _safe_response() -> AgentResponse:
    return AgentResponse(
        text=(
            "建议由医生结合血压记录、合并症和用药情况进一步评估。\n\n"
            "内容由 AI 生成，仅供参考。身体不适请及时就医。"
        ),
        citations=[
            Citation(
                source_id="chunk-integration-001",
                title="老年高血压管理指南",
                locator="高血压/指南.md#综合评估",
                excerpt="老年高血压管理需要综合评估。",
                score=0.91,
                corpus="local_knowledge_base",
            )
        ],
        safety=SafetyDecision(
            reviewed=True,
            disclaimer_applied=True,
            deterministic_diagnosis_blocked=True,
            high_risk_escalation_checked=True,
            notices=["medical_disclaimer_applied"],
        ),
        medical_content=True,
        structured={"model_preference": "primary"},
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_api_enforces_actor_ownership(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    created = await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    replay = await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    history = await client.get(f"/api/v1/sessions/{session_id}/messages")

    assert created.status_code == 201, created.text
    assert created.json()["has_prescription_draft"] is False
    assert replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]
    assert history.status_code == 200
    assert history.json() == {"session_id": str(session_id), "messages": []}

    other_token = create_access_token(
        app.state.settings,
        actor_id="usr_patient_integration0002",
        tenant_id=TENANT,
        scopes={"chat:read", "chat:write"},
        role="patient",
        account_role="patient",
    )
    headers = {"Authorization": f"Bearer {other_token}"}
    hidden = await client.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)
    conflict = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"session_id": str(session_id)},
    )
    assert hidden.status_code == 404
    assert conflict.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guest_session_history_is_denied_but_the_session_can_be_created(
    integration_client: tuple[AsyncClient, object],
) -> None:
    """Visitors receive patient service, never a replayable history endpoint."""

    client, app = integration_client
    session_id = uuid.uuid4()
    guest_token = create_access_token(
        app.state.settings,
        actor_id="usr_guest_" + "a" * 32,
        tenant_id=TENANT,
        scopes={"chat:read", "chat:write"},
        role="guest",
        account_role="guest",
    )
    headers = {"Authorization": f"Bearer {guest_token}"}

    created = await client.post(
        "/api/v1/sessions", headers=headers, json={"session_id": str(session_id)}
    )
    listed = await client.get("/api/v1/sessions", headers=headers)
    history = await client.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)

    assert created.status_code == 201, created.text
    assert listed.status_code == 403
    assert listed.json()["detail"]["code"] == "GUEST_SESSION_HISTORY_DISABLED"
    assert history.status_code == 403
    assert history.json()["detail"]["code"] == "GUEST_SESSION_HISTORY_DISABLED"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_conversation_turn_is_idempotent_encrypted_and_actor_scoped(
    integration_client: tuple[AsyncClient, object],
) -> None:
    _client, app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_chat_storage_0001"
    response = _safe_response()

    async with app.state.database.session() as database_session:
        service = ConversationService(SqlAlchemyConversationRepository(database_session))
        conversation = await service.create_session(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        user = await service.store_user_message(
            tenant_id=TENANT,
            conversation=conversation,
            session_id=session_id,
            trace_id=trace_id,
            text="老年高血压需要注意什么?",
            channel="web",
        )
        assistant = await service.store_assistant_message(
            tenant_id=TENANT,
            session=conversation,
            trace_id=trace_id,
            response=response,
        )
        assert (
            await service.store_user_message(
                tenant_id=TENANT,
                conversation=conversation,
                session_id=session_id,
                trace_id=trace_id,
                text="老年高血压需要注意什么?",
                channel="web",
            )
        ).id == user.id
        assert (
            await service.store_assistant_message(
                tenant_id=TENANT,
                session=conversation,
                trace_id=trace_id,
                response=response,
            )
        ).id == assistant.id
        messages = await service.list_messages(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            limit=10,
        )
        assert [message.role for message in messages] == ["user", "assistant"]
        assert messages[1].citations[0].source_id == "chunk-integration-001"
        with pytest.raises(ConversationConflictError):
            await service.store_user_message(
                tenant_id=TENANT,
                conversation=conversation,
                session_id=session_id,
                trace_id=trace_id,
                text="冲突内容",
                channel="web",
            )
        with pytest.raises(ConversationNotFoundError):
            await service.list_messages(
                session_id,
                tenant_id=TENANT,
                actor_id="usr_patient_integration0002",
                limit=10,
            )

    async with app.state.database.engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT content, metadata FROM messages "
                    "WHERE tenant_id=:tenant AND session_id=:session ORDER BY created_at"
                ),
                {"tenant": TENANT, "session": session_id},
            )
        ).all()
    assert len(rows) == 2
    assert all(row.content.startswith("enc:v1:") for row in rows)
    assert all(row.metadata.startswith("enc:v1:") for row in rows)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_lease_serializes_and_never_deletes_successor(
    integration_client: tuple[AsyncClient, object],
) -> None:
    _client, app = integration_client
    session_id = uuid.uuid4()
    lease = SessionLease(app.state.redis, ttl_seconds=60)
    key = f"gerclaw:chat:lease:{TENANT}:{session_id}"

    async with lease.acquire(tenant_id=TENANT, session_id=session_id, fencing_token=1):
        with pytest.raises(SessionBusyError):
            async with lease.acquire(tenant_id=TENANT, session_id=session_id, fencing_token=2):
                pytest.fail("a second lease owner must never enter")
        await app.state.redis.set(key, "successor-owner", ex=60)

    assert await app.state.redis.get(key) == "successor-owner"
    await app.state.redis.delete(key)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lost_session_lease_cancels_active_owner(
    integration_client: tuple[AsyncClient, object],
) -> None:
    _client, app = integration_client
    session_id = uuid.uuid4()
    key = f"gerclaw:chat:lease:{TENANT}:{session_id}"
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    never_finish = asyncio.Event()

    async def worker() -> None:
        try:
            async with SessionLease(app.state.redis, ttl_seconds=1).acquire(
                tenant_id=TENANT, session_id=session_id, fencing_token=1
            ):
                entered.set()
                await never_finish.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(worker())
    await asyncio.wait_for(entered.wait(), timeout=2)
    await app.state.redis.set(key, "replacement-owner", ex=60)
    await asyncio.wait_for(cancelled.wait(), timeout=2)
    result = (await asyncio.gather(task, return_exceptions=True))[0]
    assert isinstance(result, asyncio.CancelledError)
    assert await app.state.redis.get(key) == "replacement-owner"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_successor_fencing_token_rejects_stale_database_writer(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    key = f"gerclaw:chat:lease:{TENANT}:{session_id}"
    lease = SessionLease(app.state.redis, ttl_seconds=60)

    async with (
        app.state.database.session() as first_session,
        app.state.database.session() as second_session,
    ):
        first = ConversationService(SqlAlchemyConversationRepository(first_session))
        second = ConversationService(SqlAlchemyConversationRepository(second_session))
        first_token = await first.next_fencing_token()
        async with lease.acquire(
            tenant_id=TENANT,
            session_id=session_id,
            fencing_token=first_token,
        ) as first_guard:
            await first.claim_fencing_token(
                session_id,
                tenant_id=TENANT,
                actor_id=ACTOR,
                fencing_token=first_token,
                trace_id="trace_fencing_adoption_0001",
            )
            await app.state.redis.delete(key)
            second_token = await second.next_fencing_token()
            assert second_token > first_token
            async with lease.acquire(
                tenant_id=TENANT,
                session_id=session_id,
                fencing_token=second_token,
            ) as second_guard:
                await second.claim_fencing_token(
                    session_id,
                    tenant_id=TENANT,
                    actor_id=ACTOR,
                    fencing_token=second_token,
                    trace_id="trace_fencing_adoption_0001",
                )
                with pytest.raises(SessionLeaseLostError):
                    await first_guard.assert_owned()
                with pytest.raises(ConversationConflictError, match="superseded"):
                    await first.assert_fencing_token(
                        session_id,
                        tenant_id=TENANT,
                        actor_id=ACTOR,
                        fencing_token=first_token,
                        trace_id="trace_fencing_adoption_0001",
                    )
                await first.rollback()
                await second_guard.assert_owned()
                await second.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_missing_evidence_persists_safe_clarification_without_bad_case(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_chat_no_evidence_0001"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    runtime = app.state.rag_runtime
    working_module = runtime.module
    search_runtime = app.state.search_runtime
    working_search_module = search_runtime.module
    runtime.module = _EmptyRAG()
    search_runtime.module = None
    try:
        response = await client.post(
            "/api/v1/chat",
            headers={"X-Trace-ID": trace_id},
            json={
                "session_id": str(session_id),
                "message": "请评估老年患者的用药风险",
                "channel": "web",
            },
        )
    finally:
        runtime.module = working_module
        search_runtime.module = working_search_module

    assert response.status_code == 200
    assert "event: error" not in response.text
    assert "event: done" in response.text
    assert "请先补充" in response.text
    trace = await client.get(f"/api/v1/traces/{trace_id}")
    assert trace.status_code == 200
    assert trace.json()["status"] == "completed"
    assert trace.json()["error_code"] is None

    async with app.state.database.session() as session:
        assistant_count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.trace_id == trace_id, Message.role == "assistant")
        )
        bad_case_count = await session.scalar(
            select(func.count()).select_from(BadCase).where(BadCase.trace_id == trace_id)
        )
        run = await session.scalar(select(AgentRun).where(AgentRun.trace_id == trace_id))
        assert run is not None
        answer_versions = list(
            (
                await session.scalars(
                    select(AnswerVersion).where(AnswerVersion.run_id == run.id)
                )
            ).all()
        )
        run_events = list(
            (
                await session.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run.id)
                    .order_by(RunEvent.sequence)
                )
            ).all()
        )
    assert assistant_count == 1
    assert bad_case_count == 0
    assert run.status == "completed"
    assert run.current_answer_version_id == answer_versions[0].id
    assert answer_versions[0].is_current is True
    assert [event.sequence for event in run_events] == list(
        range(1, len(run_events) + 1)
    )
    assert run_events[-1].status == "completed"
    terminal_events = [
        event
        for event in run_events
        if event.status
        in {
            "completed",
            "completed_with_warnings",
            "failed",
            "cancelled",
            "interrupted",
        }
    ]
    assert [(event.event_type, event.status) for event in terminal_events] == [
        ("done", "completed")
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_terminal_trace_failure_atomically_rolls_back_assistant(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_chat_atomic_failure_0001"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    monkeypatch.setattr(chat_service_module, "ProductionAgentHarness", _SafeHarness)
    original_finish = TraceService.finish_trace

    async def fail_completed_finish(
        service: TraceService,
        tenant_id: str,
        current_trace_id: str,
        request: TraceFinishRequest,
        *,
        commit: bool = True,
    ) -> Any:
        if request.status is TraceStatus.COMPLETED:
            raise RuntimeError("injected completed Trace persistence failure")
        return await original_finish(
            service,
            tenant_id,
            current_trace_id,
            request,
            commit=commit,
        )

    monkeypatch.setattr(TraceService, "finish_trace", fail_completed_finish)
    response = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": trace_id},
        json={
            "session_id": str(session_id),
            "message": "您好!",
            "channel": "web",
        },
    )
    assert response.status_code == 200
    assert "event: error" in response.text
    assert "event: done" not in response.text

    async with app.state.database.session() as session:
        assistant_count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.trace_id == trace_id, Message.role == "assistant")
        )
        bad_case_count = await session.scalar(
            select(func.count()).select_from(BadCase).where(BadCase.trace_id == trace_id)
        )
    trace = await client.get(f"/api/v1/traces/{trace_id}")
    assert assistant_count == 0
    assert bad_case_count == 1
    assert trace.json()["status"] == TraceStatus.FAILED.value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_completion_failure_rolls_back_answer_and_never_emits_done(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_run_completion_atomic_0001"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    monkeypatch.setattr(chat_service_module, "ProductionAgentHarness", _SafeHarness)
    original_transition = AgentRunService.transition

    async def fail_completed_run(
        service: AgentRunService,
        run_id: uuid.UUID,
        target: AgentRunStatus,
        **kwargs: Any,
    ) -> Any:
        if target is AgentRunStatus.COMPLETED:
            raise RunFenceConflictError("injected stale completion fence")
        return await original_transition(service, run_id, target, **kwargs)

    monkeypatch.setattr(AgentRunService, "transition", fail_completed_run)
    response = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": trace_id},
        json={
            "session_id": str(session_id),
            "message": "您好!",
            "channel": "web",
        },
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "event: done" not in response.text
    async with app.state.database.session() as session:
        run = await session.scalar(select(AgentRun).where(AgentRun.trace_id == trace_id))
        assert run is not None
        assistant_count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.trace_id == trace_id, Message.role == "assistant")
        )
        answer_count = await session.scalar(
            select(func.count())
            .select_from(AnswerVersion)
            .where(AnswerVersion.producer_run_id == run.id)
        )
        terminal_events = list(
            (
                await session.scalars(
                    select(RunEvent).where(
                        RunEvent.run_id == run.id,
                        RunEvent.status.in_(
                            [
                                "completed",
                                "completed_with_warnings",
                                "failed",
                                "cancelled",
                                "interrupted",
                            ]
                        ),
                    )
                )
            ).all()
        )

    assert assistant_count == 0
    assert answer_count == 0
    assert run.status == "failed"
    assert [(event.event_type, event.status) for event in terminal_events] == [
        ("run.status", "failed")
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_explicit_cancel_keeps_sse_open_until_tool_and_trace_are_terminal(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cancel control request must acknowledge only after durable cleanup is visible."""

    client, app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_chat_cancel_route_0001"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    _BlockingSkillHarness.entered = asyncio.Event()
    monkeypatch.setattr(chat_service_module, "ProductionAgentHarness", _BlockingSkillHarness)

    chat_task = asyncio.create_task(
        client.post(
            "/api/v1/chat",
            headers={"X-Trace-ID": trace_id},
            json={
                "session_id": str(session_id),
                "message": "请按已加载技能准备随访",
                "loaded_skills": ["risk-assessment"],
                "channel": "web",
            },
            timeout=15,
        )
    )
    await asyncio.wait_for(_BlockingSkillHarness.entered.wait(), timeout=3)

    cancel = await client.post(f"/api/v1/chat/{trace_id}/cancel")
    response = await asyncio.wait_for(chat_task, timeout=10)

    assert cancel.status_code == 202, cancel.text
    assert cancel.json() == {"trace_id": trace_id, "status": "cancellation_requested"}
    assert response.status_code == 200, response.text
    assert "event: tool_call" in response.text
    assert "event: tool_result" in response.text
    assert '"status":"cancelled"' in response.text
    assert "event: cancelled" in response.text
    assert response.text.index("event: tool_result") < response.text.index("event: cancelled")
    assert "event: done" not in response.text

    trace = await client.get(f"/api/v1/traces/{trace_id}?limit=100")
    assert trace.status_code == 200, trace.text
    trace_payload = trace.json()
    assert trace_payload["status"] == TraceStatus.CANCELLED.value
    skill_event = next(
        event for event in trace_payload["events"] if event["event_type"] == "skill.execute"
    )
    assert skill_event["status"] == "cancelled"
    assert skill_event["payload"]["skill"] == "risk-assessment"
    assert skill_event["payload"]["outcome"] == "cancelled"
    async with app.state.database.session() as session:
        run = await session.scalar(select(AgentRun).where(AgentRun.trace_id == trace_id))
        assert run is not None
        terminal_events = list(
            (
                await session.scalars(
                    select(RunEvent).where(
                        RunEvent.run_id == run.id,
                        RunEvent.event_type == "run.status",
                    )
                )
            ).all()
        )
    assert run.status == "cancelled"
    assert run.completed_at is not None
    assert [event.status for event in terminal_events] == ["cancelled"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_api_replays_and_reconciles_owned_resources(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_run_api_resources_0001"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    monkeypatch.setattr(chat_service_module, "ProductionAgentHarness", _SafeHarness)
    chat = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": trace_id},
        json={
            "session_id": str(session_id),
            "message": "请给我一般健康建议",
            "channel": "web",
        },
    )
    assert chat.status_code == 200
    assert "event: done" in chat.text
    async with app.state.database.session() as session:
        run = await session.scalar(select(AgentRun).where(AgentRun.trace_id == trace_id))
        assert run is not None
        run_id = run.id

    run_response = await client.get(f"/api/v1/runs/{run_id}")
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "completed"
    page = await client.get(f"/api/v1/runs/{run_id}/events?after_sequence=0&limit=100")
    assert page.status_code == 200, page.text
    page_payload = page.json()
    sequences = [event["sequence"] for event in page_payload["events"]]
    assert sequences == list(range(1, len(sequences) + 1))
    replay = await client.get(
        f"/api/v1/runs/{run_id}/events?after_sequence={sequences[0]}&limit=100"
    )
    assert all(
        event["sequence"] > sequences[0] for event in replay.json()["events"]
    )

    versions = await client.get(f"/api/v1/runs/{run_id}/answer-versions")
    assert versions.status_code == 200, versions.text
    version = versions.json()["versions"][0]
    assert version["producer_run_id"] == str(run_id)
    selected = await client.put(
        f"/api/v1/runs/{run_id}/answer-versions/{version['id']}/current",
        json={"expected_current_version_id": version["id"]},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["is_current"] is True

    assert (await client.get(f"/api/v1/runs/{run_id}/feedback")).json() is None
    liked = await client.put(
        f"/api/v1/runs/{run_id}/feedback",
        json={"value": 1, "expected_revision": 0},
    )
    assert liked.status_code == 200, liked.text
    duplicate = await client.put(
        f"/api/v1/runs/{run_id}/feedback",
        json={"value": 1, "expected_revision": 1},
    )
    assert duplicate.json()["revision"] == 1
    stale_feedback = await client.put(
        f"/api/v1/runs/{run_id}/feedback",
        json={"value": -1, "expected_revision": 0},
    )
    assert stale_feedback.status_code == 409

    created = await client.post(
        f"/api/v1/runs/{run_id}/artifacts",
        json={"title": "随访文档", "markdown": "版本 1", "kind": "markdown"},
    )
    assert created.status_code == 201, created.text
    artifact = created.json()
    updated = await client.put(
        f"/api/v1/artifacts/{artifact['id']}",
        json={
            "title": "随访文档",
            "markdown": "版本 2",
            "kind": "markdown",
            "expected_revision": 1,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    stale_artifact = await client.put(
        f"/api/v1/artifacts/{artifact['id']}",
        json={
            "title": "随访文档",
            "markdown": "过期版本",
            "kind": "markdown",
            "expected_revision": 1,
        },
    )
    assert stale_artifact.status_code == 409
    listed = await client.get(f"/api/v1/conversations/{session_id}/artifacts")
    assert [item["id"] for item in listed.json()["artifacts"]] == [artifact["id"]]

    other_token = create_access_token(
        app.state.settings,
        actor_id="usr_patient_integration0002",
        tenant_id=TENANT,
        scopes={"chat:read", "chat:write", "feedback:write"},
        role="patient",
        account_role="patient",
    )
    hidden = await client.get(
        f"/api/v1/runs/{run_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert hidden.status_code == 404
    deleted = await client.delete(
        f"/api/v1/artifacts/{artifact['id']}?expected_revision=2"
    )
    assert deleted.status_code == 200, deleted.text
    assert (await client.get(f"/api/v1/artifacts/{artifact['id']}")).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_regeneration_replaces_current_version_without_duplicate_user_message(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    source_trace_id = "trace_regeneration_source_0001"
    replacement_trace_id = "trace_regeneration_replace_0001"
    message = "请给我一般健康建议"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    monkeypatch.setattr(chat_service_module, "ProductionAgentHarness", _SafeHarness)
    first = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": source_trace_id},
        json={"session_id": str(session_id), "message": message, "channel": "web"},
    )
    assert first.status_code == 200 and "event: done" in first.text
    async with app.state.database.session() as session:
        source_run = await session.scalar(
            select(AgentRun).where(AgentRun.trace_id == source_trace_id)
        )
        assert source_run is not None and source_run.current_answer_version_id is not None
        source_run_id = source_run.id
        first_version_id = source_run.current_answer_version_id

    replacement = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": replacement_trace_id},
        json={
            "session_id": str(session_id),
            "message": message,
            "channel": "web",
            "regenerate_from_run_id": str(source_run_id),
            "expected_current_answer_version_id": str(first_version_id),
        },
    )

    assert replacement.status_code == 200, replacement.text
    assert "event: done" in replacement.text
    assert f'"answer_group_run_id":"{source_run_id}"' in replacement.text
    async with app.state.database.session() as session:
        replacement_run = await session.scalar(
            select(AgentRun).where(AgentRun.trace_id == replacement_trace_id)
        )
        assert replacement_run is not None
        versions = list(
            (
                await session.scalars(
                    select(AnswerVersion)
                    .where(AnswerVersion.run_id == source_run_id)
                    .order_by(AnswerVersion.version)
                )
            ).all()
        )
        user_messages = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.session_id == session_id,
                Message.role == "user",
            )
        )
        refreshed_source = await session.get(AgentRun, source_run_id)
    assert len(versions) == 2
    assert [version.is_current for version in versions] == [False, True]
    assert versions[1].producer_run_id == replacement_run.id
    assert refreshed_source is not None
    assert refreshed_source.current_answer_version_id == versions[1].id
    assert user_messages == 1
    history = await client.get(f"/api/v1/sessions/{session_id}/messages")
    assert history.status_code == 200, history.text
    assistant_history = [
        item for item in history.json()["messages"] if item["role"] == "assistant"
    ]
    assert len(assistant_history) == 1
    assert assistant_history[0]["answer_group_run_id"] == str(source_run_id)
    assert assistant_history[0]["answer_version_id"] == str(versions[1].id)
    assert assistant_history[0]["answer_version"] == 2

    replay = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": replacement_trace_id},
        json={
            "session_id": str(session_id),
            "message": message,
            "channel": "web",
            "regenerate_from_run_id": str(source_run_id),
            "expected_current_answer_version_id": str(first_version_id),
        },
    )
    assert '"replayed":true' in replay.text
    assert f'"answer_group_run_id":"{source_run_id}"' in replay.text
    assert f'"answer_version_id":"{versions[1].id}"' in replay.text

    stale = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": "trace_regeneration_stale_0001"},
        json={
            "session_id": str(session_id),
            "message": message,
            "channel": "web",
            "regenerate_from_run_id": str(source_run_id),
            "expected_current_answer_version_id": str(first_version_id),
        },
    )
    assert "CHAT_REGENERATION_CONFLICT" in stale.text
    assert "event: done" not in stale.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_slow_regeneration_cannot_replace_a_newer_current_version(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    message = "请给我一般健康建议"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    monkeypatch.setattr(chat_service_module, "ProductionAgentHarness", _SafeHarness)
    source = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": "trace_regeneration_race_source_0001"},
        json={"session_id": str(session_id), "message": message, "channel": "web"},
    )
    assert "event: done" in source.text
    async with app.state.database.session() as session:
        source_run = await session.scalar(
            select(AgentRun).where(
                AgentRun.trace_id == "trace_regeneration_race_source_0001"
            )
        )
        assert source_run is not None
        assert source_run.current_answer_version_id is not None
        source_run_id = source_run.id
        first_version_id = source_run.current_answer_version_id

    second = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": "trace_regeneration_race_second_0001"},
        json={
            "session_id": str(session_id),
            "message": message,
            "channel": "web",
            "regenerate_from_run_id": str(source_run_id),
            "expected_current_answer_version_id": str(first_version_id),
        },
    )
    assert "event: done" in second.text
    version_response = await client.get(f"/api/v1/runs/{source_run_id}/answer-versions")
    versions_before_race = version_response.json()["versions"]
    second_version_id = versions_before_race[1]["id"]
    selected_first = await client.put(
        f"/api/v1/runs/{source_run_id}/answer-versions/{first_version_id}/current",
        json={"expected_current_version_id": second_version_id},
    )
    assert selected_first.status_code == 200, selected_first.text

    _GateFirstHarness.entered = asyncio.Event()
    _GateFirstHarness.release = asyncio.Event()
    _GateFirstHarness.calls = 0
    monkeypatch.setattr(chat_service_module, "ProductionAgentHarness", _GateFirstHarness)
    stale_task = asyncio.create_task(
        client.post(
            "/api/v1/chat",
            headers={"X-Trace-ID": "trace_regeneration_race_stale_0001"},
            json={
                "session_id": str(session_id),
                "message": message,
                "channel": "web",
                "regenerate_from_run_id": str(source_run_id),
                "expected_current_answer_version_id": str(first_version_id),
            },
            timeout=15,
        )
    )
    await asyncio.wait_for(_GateFirstHarness.entered.wait(), timeout=3)
    selected_second = await client.put(
        f"/api/v1/runs/{source_run_id}/answer-versions/{second_version_id}/current",
        json={"expected_current_version_id": str(first_version_id)},
    )
    assert selected_second.status_code == 200, selected_second.text
    _GateFirstHarness.release.set()
    stale = await asyncio.wait_for(stale_task, timeout=10)

    assert "event: error" in stale.text
    assert "CHAT_REGENERATION_CONFLICT" in stale.text
    assert "event: done" not in stale.text
    async with app.state.database.session() as session:
        versions = list(
            (
                await session.scalars(
                    select(AnswerVersion)
                    .where(AnswerVersion.run_id == source_run_id)
                    .order_by(AnswerVersion.version)
                )
            ).all()
        )
        refreshed_source = await session.get(AgentRun, source_run_id)
        stale_run = await session.scalar(
            select(AgentRun).where(
                AgentRun.trace_id == "trace_regeneration_race_stale_0001"
            )
        )

    assert len(versions) == 2
    assert refreshed_source is not None
    assert refreshed_source.current_answer_version_id == versions[1].id
    assert stale_run is not None and stale_run.status == "failed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_cancel_endpoint_fences_and_notifies_active_worker(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_run_cancel_route_0001"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    _BlockingSkillHarness.entered = asyncio.Event()
    monkeypatch.setattr(chat_service_module, "ProductionAgentHarness", _BlockingSkillHarness)
    chat_task = asyncio.create_task(
        client.post(
            "/api/v1/chat",
            headers={"X-Trace-ID": trace_id},
            json={
                "session_id": str(session_id),
                "message": "请按已加载技能准备随访",
                "loaded_skills": ["risk-assessment"],
                "channel": "web",
            },
            timeout=15,
        )
    )
    await asyncio.wait_for(_BlockingSkillHarness.entered.wait(), timeout=3)
    async with app.state.database.session() as session:
        run = await session.scalar(select(AgentRun).where(AgentRun.trace_id == trace_id))
        assert run is not None
        run_id = run.id

    cancelled = await client.post(f"/api/v1/runs/{run_id}/cancel")
    chat = await asyncio.wait_for(chat_task, timeout=10)

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert "event: cancelled" in chat.text
    assert "event: done" not in chat.text
    replay = await client.get(f"/api/v1/runs/{run_id}/events?limit=100")
    terminal_events = [
        event
        for event in replay.json()["events"]
        if event["event_type"] == "run.status"
    ]
    assert [event["status"] for event in terminal_events] == ["cancelled"]
