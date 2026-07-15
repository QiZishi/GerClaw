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
from gerclaw_api.database.models import BadCase, Message
from gerclaw_api.domain.enums import TraceStatus
from gerclaw_api.domain.trace_schemas import TraceFinishRequest
from gerclaw_api.modules.agent_harness import StreamEvent
from gerclaw_api.modules.contracts import AgentResponse, Citation, SafetyDecision
from gerclaw_api.repositories.conversation import (
    ConversationConflictError,
    SqlAlchemyConversationRepository,
)
from gerclaw_api.services import chat_service as chat_service_module
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


class _EmptyRAG:
    async def retrieve(self, *_args: object, **_kwargs: object) -> list[object]:
        return []


class _SafeHarness:
    def __init__(self, **_kwargs: object) -> None:
        pass

    async def assemble_context(self, *_args: object, **_kwargs: object) -> object:
        return object()

    async def process_message(self, *_args: object, **_kwargs: object) -> AgentResponse:
        return _safe_response()


class _BlockingSkillHarness:
    entered = asyncio.Event()

    def __init__(self, **_kwargs: object) -> None:
        type(self).entered.clear()

    async def assemble_context(self, *_args: object, **_kwargs: object) -> object:
        return object()

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
    assert replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]
    assert history.status_code == 200
    assert history.json() == {"session_id": str(session_id), "messages": []}

    other_token = create_access_token(
        app.state.settings,
        actor_id="usr_patient_integration0002",
        tenant_id=TENANT,
        scopes={"chat:read", "chat:write"},
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
async def test_chat_missing_evidence_fails_trace_without_assistant_message(
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
    runtime.module = _EmptyRAG()
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

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "CHAT_EVIDENCE_UNAVAILABLE" in response.text
    assert "event: done" not in response.text
    trace = await client.get(f"/api/v1/traces/{trace_id}")
    assert trace.status_code == 200
    assert trace.json()["status"] == "failed"
    assert trace.json()["error_code"] == "chat_evidence_unavailable"

    async with app.state.database.session() as session:
        assistant_count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.trace_id == trace_id, Message.role == "assistant")
        )
        bad_case_count = await session.scalar(
            select(func.count()).select_from(BadCase).where(BadCase.trace_id == trace_id)
        )
    assert assistant_count == 0
    assert bad_case_count == 1


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
async def test_explicit_cancel_keeps_sse_open_until_tool_and_trace_are_terminal(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cancel control request must acknowledge only after durable cleanup is visible."""

    client, _app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_chat_cancel_route_0001"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
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
