"""Current-value feedback reconciliation persistence boundary."""

from __future__ import annotations

import uuid
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import (
    AgentRun,
    RunFeedbackRevision,
    RunFeedbackState,
)


class RunFeedbackRepository(Protocol):
    """Serialize feedback writes on the actor-owned AgentRun row."""

    async def get_owned_run_for_update(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        """Lock one run only when the caller owns it."""

    async def get_state(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunFeedbackState | None:
        """Return the current state for the already locked run."""

    async def add_state(self, state: RunFeedbackState) -> None:
        """Stage a first feedback state."""

    async def add_revision(self, revision: RunFeedbackRevision) -> None:
        """Stage one accepted, decontented evolution signal."""

    async def flush(self) -> None:
        """Flush staged writes."""

    async def commit(self) -> None:
        """Commit the reconciliation."""

    async def rollback(self) -> None:
        """Release locks and discard staged changes."""


class SqlAlchemyRunFeedbackRepository:
    """PostgreSQL implementation with run-level serialization."""

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
        )
        return cast(AgentRun | None, await self._session.scalar(statement))

    async def get_state(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunFeedbackState | None:
        statement = select(RunFeedbackState).where(
            RunFeedbackState.run_id == run_id,
            RunFeedbackState.tenant_id == tenant_id,
            RunFeedbackState.actor_id == actor_id,
        )
        return cast(RunFeedbackState | None, await self._session.scalar(statement))

    async def add_state(self, state: RunFeedbackState) -> None:
        self._session.add(state)

    async def add_revision(self, revision: RunFeedbackRevision) -> None:
        self._session.add(revision)

    async def flush(self) -> None:
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
