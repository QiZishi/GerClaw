"""Encrypted conversation lifecycle and idempotent turn persistence."""

from __future__ import annotations

import uuid
from typing import Literal, cast

from pydantic import TypeAdapter, ValidationError

from gerclaw_api.database.models import AnswerVersion, ConversationSession, Message
from gerclaw_api.domain.chat_schemas import ChatMessageRead
from gerclaw_api.modules.agent_harness.protocols import ConversationHistoryMessage
from gerclaw_api.modules.contracts import AgentResponse, SafetyDecision
from gerclaw_api.repositories.conversation import (
    ConversationConflictError,
    ConversationRepository,
)
from gerclaw_api.services.message_content import (
    StoredMessageContentError,
    read_message_citations,
    read_message_text,
)


class ConversationNotFoundError(LookupError):
    """Raised without disclosing whether another principal owns a session."""


class ConversationDataError(RuntimeError):
    """Raised when encrypted persisted content fails its schema boundary."""


_SAFETY = TypeAdapter(SafetyDecision)


class ConversationService:
    """Own sessions and messages while keeping free text out of telemetry."""

    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    async def create_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession:
        conversation = await self._repository.ensure_session(
            session_id, tenant_id=tenant_id, actor_id=actor_id
        )
        await self._repository.commit()
        return conversation

    async def require_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession:
        conversation = await self._repository.get_session(
            session_id, tenant_id=tenant_id, actor_id=actor_id
        )
        if conversation is None or conversation.status != "active":
            raise ConversationNotFoundError(str(session_id))
        return conversation

    async def list_sessions(
        self, *, tenant_id: str, actor_id: str, limit: int
    ) -> list[ConversationSession]:
        """List only this verified account's active conversation records."""

        return await self._repository.list_sessions(
            tenant_id=tenant_id, actor_id=actor_id, limit=limit
        )

    async def ensure_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession:
        return await self._repository.ensure_session(
            session_id, tenant_id=tenant_id, actor_id=actor_id
        )

    async def delete_session(self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str) -> None:
        """Erase an idle caller-owned session and its database-cascaded session data."""

        conversation = await self._repository.get_session(
            session_id, tenant_id=tenant_id, actor_id=actor_id
        )
        if conversation is None:
            raise ConversationNotFoundError(str(session_id))
        await self._repository.delete_session(session_id, tenant_id=tenant_id, actor_id=actor_id)
        await self._repository.commit()

    async def load_history(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
        exclude_trace_id: str | None = None,
    ) -> list[ConversationHistoryMessage]:
        await self.require_session(session_id, tenant_id=tenant_id, actor_id=actor_id)
        messages = await self._repository.list_messages(
            session_id,
            tenant_id=tenant_id,
            limit=limit,
            context_only=True,
        )
        return [
            ConversationHistoryMessage(
                role=cast(Literal["user", "assistant"], message.role),
                text=self._message_text(message),
                stable_id=f"message:{message.id}",
            )
            for message in messages
            if message.role in {"user", "assistant"} and message.trace_id != exclude_trace_id
        ]

    async def next_fencing_token(self) -> int:
        """Allocate a non-reusable token from PostgreSQL, not Redis state."""

        return await self._repository.next_fencing_token()

    async def claim_fencing_token(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        trace_id: str,
    ) -> ConversationSession:
        conversation = await self._repository.claim_fencing_token(
            session_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            fencing_token=fencing_token,
            trace_id=trace_id,
        )
        await self._repository.commit()
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
        """Lock and verify the current owner before staging terminal writes."""

        return await self._repository.assert_fencing_token(
            session_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            fencing_token=fencing_token,
            trace_id=trace_id,
        )

    async def lock_trace_failure_fence(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        trace_id: str,
    ) -> bool:
        """Return false when a newer owner adopted the same running Trace."""

        return await self._repository.lock_trace_failure_fence(
            session_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            fencing_token=fencing_token,
            trace_id=trace_id,
        )

    async def list_messages(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[ChatMessageRead]:
        await self.require_session(session_id, tenant_id=tenant_id, actor_id=actor_id)
        messages = await self._repository.list_messages(
            session_id, tenant_id=tenant_id, limit=limit
        )
        result: list[ChatMessageRead] = []
        for message in messages:
            version = (
                await self._repository.get_answer_version_by_message(
                    message.id,
                    tenant_id=tenant_id,
                )
                if message.role == "assistant"
                else None
            )
            if version is not None and not version.is_current:
                continue
            result.append(self.to_public_message(message, answer_version=version))
        return result

    async def get_replayed_assistant(
        self, *, tenant_id: str, trace_id: str, session_id: uuid.UUID
    ) -> Message | None:
        message = await self._repository.get_message_by_trace(
            tenant_id=tenant_id, trace_id=trace_id, role="assistant"
        )
        if message is not None and message.session_id != session_id:
            raise ConversationConflictError("trace belongs to another session")
        return message

    async def store_user_message(
        self,
        *,
        tenant_id: str,
        conversation: ConversationSession,
        session_id: uuid.UUID,
        trace_id: str,
        text: str,
        channel: str,
    ) -> Message:
        existing = await self._repository.get_message_by_trace(
            tenant_id=tenant_id, trace_id=trace_id, role="user"
        )
        if existing is not None:
            if existing.session_id != session_id or self._message_text(existing) != text:
                raise ConversationConflictError("trace user message conflicts with stored data")
            return existing
        if conversation.title is None:
            conversation.title = " ".join(text.split())[:120] or "新对话"
        message = Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            trace_id=trace_id,
            role="user",
            content=[{"type": "text", "text": text}],
            message_metadata={"channel": channel},
        )
        await self._repository.add_message(message)
        await self._repository.commit()
        return message

    async def store_assistant_message(
        self,
        *,
        tenant_id: str,
        session: ConversationSession,
        trace_id: str,
        response: AgentResponse,
        commit: bool = True,
    ) -> Message:
        existing = await self._repository.get_message_by_trace(
            tenant_id=tenant_id, trace_id=trace_id, role="assistant"
        )
        if existing is not None:
            if existing.session_id != session.id or self._message_text(existing) != response.text:
                raise ConversationConflictError(
                    "trace assistant message conflicts with stored data"
                )
            return existing
        metadata = {
            "citations": [item.model_dump(mode="json") for item in response.citations],
            "safety": response.safety.model_dump(mode="json"),
            "medical_content": response.medical_content,
            "emergency_short_circuit": response.emergency_short_circuit,
            "model_preference": response.structured.get("model_preference"),
        }
        message = Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            session_id=session.id,
            trace_id=trace_id,
            role="assistant",
            content=[{"type": "text", "text": response.text}],
            message_metadata=metadata,
        )
        await self._repository.add_message(message)
        await self._repository.touch(session)
        if commit:
            await self._repository.commit()
        return message

    async def store_failure_message(
        self,
        *,
        tenant_id: str,
        session_id: uuid.UUID,
        trace_id: str,
        text: str,
        commit: bool = True,
    ) -> Message:
        """Persist a concise failed-turn notice while keeping the Trace non-contextual."""

        existing = await self._repository.get_message_by_trace(
            tenant_id=tenant_id, trace_id=trace_id, role="assistant"
        )
        if existing is not None:
            if existing.session_id != session_id or self._message_text(existing) != text:
                raise ConversationConflictError(
                    "trace failure message conflicts with stored data"
                )
            return existing
        message = Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            trace_id=trace_id,
            role="assistant",
            content=[{"type": "text", "text": text}],
            message_metadata={"failed_turn_notice": True},
        )
        await self._repository.add_message(message)
        if commit:
            await self._repository.commit()
        return message

    async def rollback(self) -> None:
        """Discard a failed atomic turn finalization on the shared DB session."""

        await self._repository.rollback()

    def to_public_message(
        self,
        message: Message,
        *,
        answer_version: AnswerVersion | None = None,
    ) -> ChatMessageRead:
        try:
            citations = read_message_citations(message)
        except StoredMessageContentError as error:
            raise ConversationDataError(str(error)) from error
        return ChatMessageRead(
            id=message.id,
            trace_id=message.trace_id,
            role=cast(Literal["user", "assistant"], message.role),
            text=self._message_text(message),
            citations=citations,
            answer_group_run_id=(answer_version.run_id if answer_version is not None else None),
            answer_version_id=(answer_version.id if answer_version is not None else None),
            answer_version=(answer_version.version if answer_version is not None else None),
            created_at=message.created_at,
        )

    def to_agent_response(self, message: Message) -> AgentResponse:
        """Rebuild a validated response for same-trace idempotent SSE replay."""

        public = self.to_public_message(message)
        try:
            safety = _SAFETY.validate_python(message.message_metadata.get("safety"))
        except ValidationError as error:
            raise ConversationDataError("stored message safety decision is invalid") from error
        medical_content = message.message_metadata.get("medical_content")
        if not isinstance(medical_content, bool):
            raise ConversationDataError("stored message medical-content flag is invalid")
        emergency_short_circuit = message.message_metadata.get("emergency_short_circuit", False)
        if not isinstance(emergency_short_circuit, bool):
            raise ConversationDataError("stored emergency short-circuit flag is invalid")
        model_preference = message.message_metadata.get("model_preference")
        if model_preference not in {"primary", "backup1", "backup2", None}:
            raise ConversationDataError("stored model preference is invalid")
        return AgentResponse(
            text=public.text,
            citations=public.citations,
            safety=safety,
            medical_content=medical_content,
            emergency_short_circuit=emergency_short_circuit,
            structured={"model_preference": model_preference, "replayed": True},
        )

    @staticmethod
    def _message_text(message: Message) -> str:
        try:
            return read_message_text(message)
        except StoredMessageContentError as error:
            raise ConversationDataError(str(error)) from error
