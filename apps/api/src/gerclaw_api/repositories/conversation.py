"""Tenant- and actor-scoped conversation persistence boundary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol, cast

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import ConversationSession, Message, User


class ConversationConflictError(RuntimeError):
    """Raised when an idempotent conversation write conflicts."""


class ConversationRepository(Protocol):
    """Storage operations whose every lookup includes verified ownership."""

    async def ensure_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession:
        """Return or create the caller-owned active session."""

    async def get_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession | None:
        """Return a session only when both tenant and actor own it."""

    async def list_messages(
        self, session_id: uuid.UUID, *, tenant_id: str, limit: int
    ) -> list[Message]:
        """Return the most recent messages in chronological order."""

    async def next_fencing_token(self) -> int:
        """Allocate a database-monotonic token for one lease attempt."""

    async def claim_fencing_token(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        trace_id: str,
    ) -> ConversationSession:
        """Publish a newer owner token before it begins the turn."""

    async def assert_fencing_token(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        trace_id: str,
    ) -> ConversationSession:
        """Lock the session row and reject a stale writer."""

    async def lock_trace_failure_fence(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        trace_id: str,
    ) -> bool:
        """Lock the session row and reject a stale same-Trace owner."""

    async def get_message_by_trace(
        self, *, tenant_id: str, trace_id: str, role: str
    ) -> Message | None:
        """Return an idempotently stored turn message."""

    async def add_message(self, message: Message) -> None:
        """Stage and flush one message."""

    async def commit(self) -> None:
        """Commit all staged conversation changes."""

    async def rollback(self) -> None:
        """Discard all staged conversation and Trace changes in the shared session."""

    async def touch(self, conversation: ConversationSession) -> None:
        """Advance session ordering after a completed durable turn."""


class SqlAlchemyConversationRepository:
    """PostgreSQL implementation backed by one request-owned session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession:
        existing = await self.get_session(session_id, tenant_id=tenant_id, actor_id=actor_id)
        if existing is not None:
            if existing.status != "active":
                raise ConversationConflictError("conversation session is not active")
            return existing

        any_owner = await self._session.scalar(
            select(ConversationSession).where(ConversationSession.id == session_id)
        )
        if any_owner is not None:
            raise ConversationConflictError("conversation session belongs to another principal")

        user = await self._get_or_create_user(tenant_id=tenant_id, actor_id=actor_id)
        created = ConversationSession(
            id=session_id,
            user_id=user.id,
            tenant_id=tenant_id,
            agent_id="gerclaw-geriatric-specialist",
            status="active",
            context_summary={},
        )
        try:
            async with self._session.begin_nested():
                self._session.add(created)
                await self._session.flush()
        except IntegrityError:
            existing = await self.get_session(session_id, tenant_id=tenant_id, actor_id=actor_id)
            if existing is None:
                raise ConversationConflictError(
                    "conversation session was concurrently claimed"
                ) from None
            return existing
        return created

    async def get_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession | None:
        statement = (
            select(ConversationSession)
            .join(User, User.id == ConversationSession.user_id)
            .where(
                ConversationSession.id == session_id,
                ConversationSession.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
                User.external_id == actor_id,
                User.is_active.is_(True),
            )
            .execution_options(populate_existing=True)
        )
        return cast(ConversationSession | None, await self._session.scalar(statement))

    async def list_messages(
        self, session_id: uuid.UUID, *, tenant_id: str, limit: int
    ) -> list[Message]:
        statement = (
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.session_id == session_id,
                Message.role.in_(("user", "assistant")),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        messages = list((await self._session.scalars(statement)).all())
        messages.reverse()
        return messages

    async def next_fencing_token(self) -> int:
        value = await self._session.scalar(text("SELECT nextval('chat_session_fencing_seq')"))
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise RuntimeError("database returned an invalid chat fencing token")
        return value

    async def claim_fencing_token(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        trace_id: str,
    ) -> ConversationSession:
        conversation = await self._locked_owned_session(
            session_id, tenant_id=tenant_id, actor_id=actor_id
        )
        if fencing_token <= conversation.active_fencing_token:
            raise ConversationConflictError("chat fencing token is stale")
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
        conversation = await self._locked_owned_session(
            session_id, tenant_id=tenant_id, actor_id=actor_id
        )
        if (
            conversation.active_fencing_token != fencing_token
            or conversation.active_fencing_trace_id != trace_id
        ):
            raise ConversationConflictError("chat lease ownership was superseded")
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
        conversation = await self._locked_owned_session(
            session_id, tenant_id=tenant_id, actor_id=actor_id
        )
        return not (
            conversation.active_fencing_trace_id == trace_id
            and conversation.active_fencing_token > fencing_token
        )

    async def get_message_by_trace(
        self, *, tenant_id: str, trace_id: str, role: str
    ) -> Message | None:
        statement = select(Message).where(
            Message.tenant_id == tenant_id,
            Message.trace_id == trace_id,
            Message.role == role,
        )
        return cast(Message | None, await self._session.scalar(statement))

    async def add_message(self, message: Message) -> None:
        try:
            async with self._session.begin_nested():
                self._session.add(message)
                await self._session.flush()
        except IntegrityError as error:
            raise ConversationConflictError("message was already stored") from error

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def _locked_owned_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession:
        statement = (
            select(ConversationSession)
            .join(User, User.id == ConversationSession.user_id)
            .where(
                ConversationSession.id == session_id,
                ConversationSession.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
                User.external_id == actor_id,
                User.is_active.is_(True),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        conversation = cast(ConversationSession | None, await self._session.scalar(statement))
        if conversation is None or conversation.status != "active":
            raise ConversationConflictError("conversation session is unavailable")
        return conversation

    async def _get_or_create_user(self, *, tenant_id: str, actor_id: str) -> User:
        statement = select(User).where(
            User.tenant_id == tenant_id,
            User.external_id == actor_id,
        )
        existing = cast(User | None, await self._session.scalar(statement))
        if existing is not None:
            if not existing.is_active:
                raise ConversationConflictError("conversation principal is inactive")
            return existing

        created = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            external_id=actor_id,
            role="patient",
            is_active=True,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(created)
                await self._session.flush()
        except IntegrityError:
            existing = cast(User | None, await self._session.scalar(statement))
            if existing is None:
                raise ConversationConflictError(
                    "conversation principal creation conflicted"
                ) from None
            return existing
        return created

    async def touch(self, conversation: ConversationSession) -> None:
        """Advance session ordering after a completed durable turn."""

        conversation.updated_at = datetime.now(UTC)
