"""Encrypted conversation lifecycle and idempotent turn persistence."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from gerclaw_api.database.models import ConversationSession, Message
from gerclaw_api.domain.chat_schemas import ChatMessageRead
from gerclaw_api.modules.agent_harness.protocols import ConversationHistoryMessage
from gerclaw_api.modules.contracts import AgentResponse, Citation, SafetyDecision
from gerclaw_api.repositories.conversation import (
    ConversationConflictError,
    ConversationRepository,
)


class ConversationNotFoundError(LookupError):
    """Raised without disclosing whether another principal owns a session."""


class ConversationDataError(RuntimeError):
    """Raised when encrypted persisted content fails its schema boundary."""


class _StoredTextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=50_000)


_CITATIONS = TypeAdapter(list[Citation])
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

    async def ensure_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession:
        return await self._repository.ensure_session(
            session_id, tenant_id=tenant_id, actor_id=actor_id
        )

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
            session_id, tenant_id=tenant_id, limit=limit
        )
        return [
            ConversationHistoryMessage(role=message.role, text=self._message_text(message))
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
        return [self.to_public_message(message) for message in messages]

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

    async def rollback(self) -> None:
        """Discard a failed atomic turn finalization on the shared DB session."""

        await self._repository.rollback()

    def to_public_message(self, message: Message) -> ChatMessageRead:
        citations_value = message.message_metadata.get("citations", [])
        try:
            citations = _CITATIONS.validate_python(citations_value)
        except ValidationError as error:
            raise ConversationDataError("stored message citations are invalid") from error
        return ChatMessageRead(
            id=message.id,
            trace_id=message.trace_id,
            role=message.role,
            text=self._message_text(message),
            citations=citations[:50],
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
        model_preference = message.message_metadata.get("model_preference")
        if model_preference not in {"primary", "backup1", "backup2", None}:
            raise ConversationDataError("stored model preference is invalid")
        return AgentResponse(
            text=public.text,
            citations=public.citations,
            safety=safety,
            medical_content=medical_content,
            structured={"model_preference": model_preference, "replayed": True},
        )

    @staticmethod
    def _message_text(message: Message) -> str:
        try:
            blocks = [_StoredTextBlock.model_validate(item) for item in message.content]
        except (ValidationError, TypeError) as error:
            raise ConversationDataError("stored message content is invalid") from error
        text = "\n".join(block.text for block in blocks).strip()
        if not text:
            raise ConversationDataError("stored message text is empty")
        return text
