"""Tenant-scoped encrypted Memory persistence and profile row locking."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import (
    ConversationSession,
    HealthProfile,
    MemoryFact,
    MemoryFactRevision,
    Message,
    User,
)


class MemoryRepositoryError(RuntimeError):
    """Safe base error for invalid or unavailable persisted Memory state."""


class MemoryNotFoundError(LookupError):
    """Raised without revealing whether another tenant owns a resource."""


class MemoryConflictError(RuntimeError):
    """Raised on stale fact revisions or conflicting profile mutations."""


class MemoryRepository(Protocol):
    """Storage boundary whose lookups always include verified ownership."""

    async def get_user(self, *, tenant_id: str, actor_id: str) -> User | None: ...

    async def require_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession: ...

    async def list_messages(
        self, session_id: uuid.UUID, *, tenant_id: str, limit: int
    ) -> list[Message]: ...

    async def add_message(self, message: Message) -> None: ...

    async def get_profile(self, *, tenant_id: str, user_id: uuid.UUID) -> HealthProfile | None: ...

    async def lock_or_create_profile(
        self, *, tenant_id: str, user_id: uuid.UUID
    ) -> HealthProfile: ...

    async def get_fact_by_key_for_update(
        self, *, tenant_id: str, user_id: uuid.UUID, fact_key: str
    ) -> MemoryFact | None: ...

    async def get_fact_for_update(
        self, *, tenant_id: str, user_id: uuid.UUID, fact_id: uuid.UUID
    ) -> MemoryFact | None: ...

    async def get_fact(
        self, *, tenant_id: str, user_id: uuid.UUID, fact_id: uuid.UUID
    ) -> MemoryFact | None: ...

    async def list_facts(
        self,
        *,
        tenant_id: str,
        user_id: uuid.UUID,
        statuses: Sequence[str] | None = None,
        fact_ids: Sequence[uuid.UUID] | None = None,
        limit: int = 200,
    ) -> list[MemoryFact]: ...

    async def add_fact(self, fact: MemoryFact) -> None: ...

    async def add_fact_revision(self, revision: MemoryFactRevision) -> None: ...

    async def list_fact_revisions(
        self, *, tenant_id: str, user_id: uuid.UUID, fact_id: uuid.UUID, limit: int
    ) -> list[MemoryFactRevision]: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class SqlAlchemyMemoryRepository:
    """PostgreSQL Memory implementation over one request-owned session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user(self, *, tenant_id: str, actor_id: str) -> User | None:
        statement = select(User).where(
            User.tenant_id == tenant_id,
            User.external_id == actor_id,
            User.is_active.is_(True),
        )
        return cast(User | None, await self._session.scalar(statement))

    async def require_session(
        self, session_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ConversationSession:
        statement = (
            select(ConversationSession)
            .join(User, User.id == ConversationSession.user_id)
            .where(
                ConversationSession.id == session_id,
                ConversationSession.tenant_id == tenant_id,
                ConversationSession.status == "active",
                User.tenant_id == tenant_id,
                User.external_id == actor_id,
                User.is_active.is_(True),
            )
            .execution_options(populate_existing=True)
        )
        session = cast(ConversationSession | None, await self._session.scalar(statement))
        if session is None:
            raise MemoryNotFoundError("memory session not found")
        return session

    async def list_messages(
        self, session_id: uuid.UUID, *, tenant_id: str, limit: int
    ) -> list[Message]:
        statement = (
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.session_id == session_id,
                Message.role.in_(("user", "assistant", "system", "tool")),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        messages = list((await self._session.scalars(statement)).all())
        messages.reverse()
        return messages

    async def add_message(self, message: Message) -> None:
        self._session.add(message)
        await self._session.flush()

    async def get_profile(self, *, tenant_id: str, user_id: uuid.UUID) -> HealthProfile | None:
        statement = select(HealthProfile).where(
            HealthProfile.tenant_id == tenant_id,
            HealthProfile.user_id == user_id,
        )
        return cast(HealthProfile | None, await self._session.scalar(statement))

    async def lock_or_create_profile(self, *, tenant_id: str, user_id: uuid.UUID) -> HealthProfile:
        await self._session.execute(
            pg_insert(HealthProfile)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                schema_version=1,
                version=1,
                profile={},
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "user_id"])
        )
        statement = (
            select(HealthProfile)
            .where(
                HealthProfile.tenant_id == tenant_id,
                HealthProfile.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        profile = cast(HealthProfile | None, await self._session.scalar(statement))
        if profile is None:
            raise MemoryRepositoryError("health profile could not be locked")
        return profile

    async def get_fact_by_key_for_update(
        self, *, tenant_id: str, user_id: uuid.UUID, fact_key: str
    ) -> MemoryFact | None:
        statement = (
            select(MemoryFact)
            .where(
                MemoryFact.tenant_id == tenant_id,
                MemoryFact.user_id == user_id,
                MemoryFact.fact_key == fact_key,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return cast(MemoryFact | None, await self._session.scalar(statement))

    async def get_fact_for_update(
        self, *, tenant_id: str, user_id: uuid.UUID, fact_id: uuid.UUID
    ) -> MemoryFact | None:
        statement = (
            select(MemoryFact)
            .where(
                MemoryFact.id == fact_id,
                MemoryFact.tenant_id == tenant_id,
                MemoryFact.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return cast(MemoryFact | None, await self._session.scalar(statement))

    async def get_fact(
        self, *, tenant_id: str, user_id: uuid.UUID, fact_id: uuid.UUID
    ) -> MemoryFact | None:
        statement = select(MemoryFact).where(
            MemoryFact.id == fact_id,
            MemoryFact.tenant_id == tenant_id,
            MemoryFact.user_id == user_id,
        )
        return cast(MemoryFact | None, await self._session.scalar(statement))

    async def list_facts(
        self,
        *,
        tenant_id: str,
        user_id: uuid.UUID,
        statuses: Sequence[str] | None = None,
        fact_ids: Sequence[uuid.UUID] | None = None,
        limit: int = 200,
    ) -> list[MemoryFact]:
        statement = select(MemoryFact).where(
            MemoryFact.tenant_id == tenant_id,
            MemoryFact.user_id == user_id,
        )
        if statuses is not None:
            statement = statement.where(MemoryFact.status.in_(tuple(statuses)))
        if fact_ids is not None:
            if not fact_ids:
                return []
            statement = statement.where(MemoryFact.id.in_(tuple(fact_ids)))
        statement = statement.order_by(MemoryFact.updated_at.desc(), MemoryFact.id).limit(limit)
        return list((await self._session.scalars(statement)).all())

    async def add_fact(self, fact: MemoryFact) -> None:
        self._session.add(fact)
        await self._session.flush()

    async def add_fact_revision(self, revision: MemoryFactRevision) -> None:
        self._session.add(revision)

    async def list_fact_revisions(
        self, *, tenant_id: str, user_id: uuid.UUID, fact_id: uuid.UUID, limit: int
    ) -> list[MemoryFactRevision]:
        statement = (
            select(MemoryFactRevision)
            .where(
                MemoryFactRevision.tenant_id == tenant_id,
                MemoryFactRevision.user_id == user_id,
                MemoryFactRevision.fact_id == fact_id,
            )
            .order_by(MemoryFactRevision.revision.desc(), MemoryFactRevision.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def flush(self) -> None:
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
