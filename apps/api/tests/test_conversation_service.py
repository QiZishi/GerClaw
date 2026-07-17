"""Conversation service tests over an in-memory persistence boundary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import ConversationSession, Message
from gerclaw_api.modules.contracts import AgentResponse, Citation, SafetyDecision
from gerclaw_api.repositories.conversation import ConversationConflictError
from gerclaw_api.services.conversation_service import (
    ConversationDataError,
    ConversationNotFoundError,
    ConversationService,
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_unit0001"


class _ConversationRepository:
    def __init__(self) -> None:
        self.sessions: dict[uuid.UUID, tuple[ConversationSession, str, str]] = {}
        self.messages: list[Message] = []
        self.commits = 0
        self.rollbacks = 0
        self.fencing_token = 0
        self.running_sessions: set[uuid.UUID] = set()

    async def ensure_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession:
        stored = self.sessions.get(session_id)
        if stored is not None:
            conversation, owner_tenant, owner_actor = stored
            if (owner_tenant, owner_actor) != (tenant_id, actor_id):
                raise ConversationConflictError("other owner")
            return conversation
        now = datetime.now(UTC)
        conversation = ConversationSession(
            id=session_id,
            user_id=uuid.uuid4(),
            tenant_id=tenant_id,
            agent_id="gerclaw-geriatric-specialist",
            status="active",
            active_fencing_token=0,
            context_summary={},
            created_at=now,
            updated_at=now,
        )
        self.sessions[session_id] = (conversation, tenant_id, actor_id)
        return conversation

    async def get_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession | None:
        stored = self.sessions.get(session_id)
        if stored is None or stored[1:] != (tenant_id, actor_id):
            return None
        return stored[0]

    async def list_sessions(
        self, *, tenant_id: str, actor_id: str, limit: int
    ) -> list[ConversationSession]:
        owned_active_sessions = [
            conversation
            for conversation, owner_tenant, owner_actor in self.sessions.values()
            if (owner_tenant, owner_actor) == (tenant_id, actor_id)
            and conversation.status == "active"
        ]
        return sorted(
            owned_active_sessions,
            key=lambda conversation: (conversation.updated_at, str(conversation.id)),
            reverse=True,
        )[:limit]

    async def delete_session(self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str) -> bool:
        if session_id in self.running_sessions:
            raise ConversationConflictError("conversation has a running execution")
        stored = self.sessions.get(session_id)
        if stored is None or stored[1:] != (tenant_id, actor_id):
            return False
        del self.sessions[session_id]
        self.messages = [message for message in self.messages if message.session_id != session_id]
        return True

    async def list_messages(
        self, session_id: uuid.UUID, *, tenant_id: str, limit: int
    ) -> list[Message]:
        return [
            message
            for message in self.messages
            if message.session_id == session_id and message.tenant_id == tenant_id
        ][-limit:]

    async def next_fencing_token(self) -> int:
        self.fencing_token += 1
        return self.fencing_token

    async def claim_fencing_token(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        trace_id: str,
    ) -> ConversationSession:
        conversation = await self.ensure_session(session_id, tenant_id=tenant_id, actor_id=actor_id)
        if fencing_token <= conversation.active_fencing_token:
            raise ConversationConflictError("stale")
        conversation.active_fencing_token = fencing_token
        conversation.active_fencing_trace_id = trace_id
        return conversation

    async def assert_fencing_token(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        trace_id: str,
    ) -> ConversationSession:
        conversation = await self.ensure_session(session_id, tenant_id=tenant_id, actor_id=actor_id)
        if (
            conversation.active_fencing_token != fencing_token
            or conversation.active_fencing_trace_id != trace_id
        ):
            raise ConversationConflictError("superseded")
        return conversation

    async def lock_trace_failure_fence(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        trace_id: str,
    ) -> bool:
        conversation = await self.ensure_session(session_id, tenant_id=tenant_id, actor_id=actor_id)
        return not (
            conversation.active_fencing_trace_id == trace_id
            and conversation.active_fencing_token > fencing_token
        )

    async def get_message_by_trace(
        self, *, tenant_id: str, trace_id: str, role: str
    ) -> Message | None:
        return next(
            (
                message
                for message in self.messages
                if message.tenant_id == tenant_id
                and message.trace_id == trace_id
                and message.role == role
            ),
            None,
        )

    async def add_message(self, message: Message) -> None:
        message.created_at = datetime.now(UTC)
        self.messages.append(message)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def touch(self, conversation: ConversationSession) -> None:
        conversation.updated_at = datetime.now(UTC)


def _response() -> AgentResponse:
    return AgentResponse(
        text="建议请医生进一步评估。\n\n内容由 AI 生成，仅供参考。身体不适请及时就医。",
        citations=[
            Citation(
                source_id="chunk-unit-001",
                title="老年医学指南",
                locator="指南.md | 评估 | chunk 1/2",
                excerpt="需要综合评估。",
                score=0.8,
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


@pytest.mark.asyncio
async def test_conversation_lifecycle_history_and_replay() -> None:
    repository = _ConversationRepository()
    service = ConversationService(repository)
    session_id = uuid.uuid4()
    conversation = await service.create_session(session_id, tenant_id=TENANT, actor_id=ACTOR)
    assert (
        await service.ensure_session(session_id, tenant_id=TENANT, actor_id=ACTOR) is conversation
    )
    assert (
        await service.require_session(session_id, tenant_id=TENANT, actor_id=ACTOR) is conversation
    )
    assert await service.load_history(session_id, tenant_id=TENANT, actor_id=ACTOR, limit=10) == []
    fencing_token = await service.next_fencing_token()
    assert fencing_token == 1
    assert (
        await service.claim_fencing_token(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=fencing_token,
            trace_id="trace_conversation_unit001",
        )
        is conversation
    )
    assert (
        await service.assert_fencing_token(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=fencing_token,
            trace_id="trace_conversation_unit001",
        )
        is conversation
    )
    assert await service.lock_trace_failure_fence(
        session_id,
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=fencing_token,
        trace_id="trace_conversation_unit001",
    )

    user = await service.store_user_message(
        tenant_id=TENANT,
        conversation=conversation,
        session_id=session_id,
        trace_id="trace_conversation_unit001",
        text="老年高血压如何管理?",
        channel="web",
    )
    assistant = await service.store_assistant_message(
        tenant_id=TENANT,
        session=conversation,
        trace_id="trace_conversation_unit001",
        response=_response(),
    )
    assert (
        await service.store_user_message(
            tenant_id=TENANT,
            conversation=conversation,
            session_id=session_id,
            trace_id="trace_conversation_unit001",
            text="老年高血压如何管理?",
            channel="web",
        )
    ) is user
    assert conversation.title == "老年高血压如何管理?"
    assert (
        await service.store_assistant_message(
            tenant_id=TENANT,
            session=conversation,
            trace_id="trace_conversation_unit001",
            response=_response(),
        )
    ) is assistant

    history = await service.load_history(session_id, tenant_id=TENANT, actor_id=ACTOR, limit=10)
    public = await service.list_messages(session_id, tenant_id=TENANT, actor_id=ACTOR, limit=10)
    replayed = service.to_agent_response(
        await service.get_replayed_assistant(
            tenant_id=TENANT,
            trace_id="trace_conversation_unit001",
            session_id=session_id,
        )
    )
    assert [item.role for item in history] == ["user", "assistant"]
    assert (
        await service.load_history(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            limit=10,
            exclude_trace_id="trace_conversation_unit001",
        )
        == []
    )
    assert [item.role for item in public] == ["user", "assistant"]
    assert public[1].citations[0].source_id == "chunk-unit-001"
    assert replayed.text == _response().text
    assert replayed.structured == {"model_preference": "primary", "replayed": True}

    with pytest.raises(ConversationConflictError):
        await service.store_user_message(
            tenant_id=TENANT,
            conversation=conversation,
            session_id=session_id,
            trace_id="trace_conversation_unit001",
            text="different",
            channel="web",
        )
    with pytest.raises(ConversationConflictError):
        await service.get_replayed_assistant(
            tenant_id=TENANT,
            trace_id="trace_conversation_unit001",
            session_id=uuid.uuid4(),
        )
    with pytest.raises(ConversationNotFoundError):
        await service.require_session(session_id, tenant_id=TENANT, actor_id="usr_other00000001")
    with pytest.raises(ConversationConflictError):
        await service.claim_fencing_token(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=fencing_token,
            trace_id="trace_conversation_unit001",
        )
    with pytest.raises(ConversationConflictError):
        await service.assert_fencing_token(
            session_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=fencing_token + 1,
            trace_id="trace_conversation_unit001",
        )
    await service.rollback()
    assert repository.rollbacks == 1


@pytest.mark.asyncio
async def test_list_sessions_is_owned_active_and_newest_first() -> None:
    repository = _ConversationRepository()
    service = ConversationService(repository)
    older_id = uuid.uuid4()
    newer_id = uuid.uuid4()
    other_id = uuid.uuid4()
    older = await service.create_session(older_id, tenant_id=TENANT, actor_id=ACTOR)
    newer = await service.create_session(newer_id, tenant_id=TENANT, actor_id=ACTOR)
    other = await service.create_session(other_id, tenant_id=TENANT, actor_id="usr_other00000001")
    older.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    newer.updated_at = datetime(2026, 1, 2, tzinfo=UTC)
    other.updated_at = datetime(2026, 1, 3, tzinfo=UTC)

    assert await service.list_sessions(tenant_id=TENANT, actor_id=ACTOR, limit=50) == [newer, older]
    assert await service.list_sessions(tenant_id=TENANT, actor_id=ACTOR, limit=1) == [newer]


@pytest.mark.asyncio
async def test_delete_session_erases_only_an_idle_owned_session() -> None:
    repository = _ConversationRepository()
    service = ConversationService(repository)
    session_id = uuid.uuid4()
    await service.create_session(session_id, tenant_id=TENANT, actor_id=ACTOR)

    await service.delete_session(session_id, tenant_id=TENANT, actor_id=ACTOR)

    assert session_id not in repository.sessions
    assert repository.commits == 2
    with pytest.raises(ConversationNotFoundError):
        await service.require_session(session_id, tenant_id=TENANT, actor_id=ACTOR)
    with pytest.raises(ConversationNotFoundError):
        await service.delete_session(session_id, tenant_id=TENANT, actor_id=ACTOR)


@pytest.mark.asyncio
async def test_delete_session_rejects_running_or_other_principal_sessions() -> None:
    repository = _ConversationRepository()
    service = ConversationService(repository)
    session_id = uuid.uuid4()
    await service.create_session(session_id, tenant_id=TENANT, actor_id=ACTOR)
    repository.running_sessions.add(session_id)

    with pytest.raises(ConversationConflictError, match="running execution"):
        await service.delete_session(session_id, tenant_id=TENANT, actor_id=ACTOR)
    assert session_id in repository.sessions
    with pytest.raises(ConversationNotFoundError):
        await service.delete_session(session_id, tenant_id=TENANT, actor_id="usr_other00000001")


def test_persisted_message_schema_failures_are_closed() -> None:
    service = ConversationService(_ConversationRepository())
    now = datetime.now(UTC)
    base = Message(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        session_id=uuid.uuid4(),
        trace_id="trace_invalid_message001",
        role="assistant",
        content=[{"type": "text", "text": "safe text"}],
        message_metadata={
            "citations": [],
            "safety": _response().safety.model_dump(mode="json"),
            "medical_content": False,
            "model_preference": None,
        },
        created_at=now,
    )
    assert service.to_public_message(base).text == "safe text"

    invalid_content = base
    invalid_content.content = [{"type": "html", "text": "unsafe"}]
    with pytest.raises(ConversationDataError):
        service.to_public_message(invalid_content)
    invalid_content.content = []
    with pytest.raises(ConversationDataError):
        service.to_public_message(invalid_content)
    invalid_content.content = [{"type": "text", "text": "safe text"}]

    invalid_content.message_metadata["citations"] = [{"source_id": "missing fields"}]
    with pytest.raises(ConversationDataError):
        service.to_public_message(invalid_content)
    invalid_content.message_metadata["citations"] = []
    invalid_content.message_metadata["safety"] = {"reviewed": False}
    with pytest.raises(ConversationDataError):
        service.to_agent_response(invalid_content)
    invalid_content.message_metadata["safety"] = _response().safety.model_dump(mode="json")
    invalid_content.message_metadata["medical_content"] = "yes"
    with pytest.raises(ConversationDataError):
        service.to_agent_response(invalid_content)
    invalid_content.message_metadata["medical_content"] = False
    invalid_content.message_metadata["model_preference"] = "provider-secret-name"
    with pytest.raises(ConversationDataError):
        service.to_agent_response(invalid_content)
