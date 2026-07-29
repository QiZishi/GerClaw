"""Actor-owned answer-version persistence boundary."""

from __future__ import annotations

import uuid
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import AgentRun, AnswerVersion, Message


class AnswerVersionRepository(Protocol):
    """Persistence operations used while the owning run row is locked."""

    async def get_owned_run_for_update(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        """Lock one run only when the principal owns it."""

    async def get_assistant_message(
        self,
        message_id: uuid.UUID,
        *,
        tenant_id: str,
        conversation_id: uuid.UUID,
    ) -> Message | None:
        """Return an assistant message from the run's conversation."""

    async def get_owned_producer_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        conversation_id: uuid.UUID,
    ) -> AgentRun | None:
        """Return the generation Run only within the same owned conversation."""

    async def get_by_message(
        self,
        run_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
    ) -> AnswerVersion | None:
        """Return an idempotently registered message version."""

    async def get_by_producer_run(
        self,
        producer_run_id: uuid.UUID,
    ) -> AnswerVersion | None:
        """Return the one answer version produced by an execution Run."""

    async def get_version(
        self,
        run_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> AnswerVersion | None:
        """Return one version belonging to the locked run."""

    async def get_current(self, run_id: uuid.UUID) -> AnswerVersion | None:
        """Return the unique current answer version."""

    async def list_versions(self, run_id: uuid.UUID, *, limit: int) -> list[AnswerVersion]:
        """Return versions in ascending version order."""

    async def add_version(self, version: AnswerVersion) -> None:
        """Stage one immutable version."""

    async def flush(self) -> None:
        """Flush staged state changes in dependency order."""

    async def commit(self) -> None:
        """Commit the current transaction."""

    async def rollback(self) -> None:
        """Release the run lock and discard staged changes."""


class SqlAlchemyAnswerVersionRepository:
    """PostgreSQL implementation using the AgentRun row as the write mutex."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owned_run_for_update(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        statement = (
            select(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.tenant_id == tenant_id,
                AgentRun.actor_id == actor_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return cast(AgentRun | None, await self._session.scalar(statement))

    async def get_assistant_message(
        self,
        message_id: uuid.UUID,
        *,
        tenant_id: str,
        conversation_id: uuid.UUID,
    ) -> Message | None:
        statement = select(Message).where(
            Message.id == message_id,
            Message.tenant_id == tenant_id,
            Message.session_id == conversation_id,
            Message.role == "assistant",
        )
        return cast(Message | None, await self._session.scalar(statement))

    async def get_owned_producer_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        conversation_id: uuid.UUID,
    ) -> AgentRun | None:
        statement = select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == tenant_id,
            AgentRun.actor_id == actor_id,
            AgentRun.conversation_id == conversation_id,
        )
        return cast(AgentRun | None, await self._session.scalar(statement))

    async def get_by_message(
        self,
        run_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
    ) -> AnswerVersion | None:
        statement = select(AnswerVersion).where(
            AnswerVersion.run_id == run_id,
            AnswerVersion.assistant_message_id == assistant_message_id,
        )
        return cast(AnswerVersion | None, await self._session.scalar(statement))

    async def get_by_producer_run(
        self,
        producer_run_id: uuid.UUID,
    ) -> AnswerVersion | None:
        statement = select(AnswerVersion).where(
            AnswerVersion.producer_run_id == producer_run_id
        )
        return cast(AnswerVersion | None, await self._session.scalar(statement))

    async def get_version(
        self,
        run_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> AnswerVersion | None:
        statement = select(AnswerVersion).where(
            AnswerVersion.id == version_id,
            AnswerVersion.run_id == run_id,
        )
        return cast(AnswerVersion | None, await self._session.scalar(statement))

    async def get_current(self, run_id: uuid.UUID) -> AnswerVersion | None:
        statement = select(AnswerVersion).where(
            AnswerVersion.run_id == run_id,
            AnswerVersion.is_current.is_(True),
        )
        return cast(AnswerVersion | None, await self._session.scalar(statement))

    async def list_versions(self, run_id: uuid.UUID, *, limit: int) -> list[AnswerVersion]:
        statement = (
            select(AnswerVersion)
            .where(AnswerVersion.run_id == run_id)
            .order_by(AnswerVersion.version)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def add_version(self, version: AnswerVersion) -> None:
        self._session.add(version)

    async def flush(self) -> None:
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
