"""Actor-owned durable Agent run persistence boundary."""

from __future__ import annotations

import uuid
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import AgentRun, RunEvent


class DuplicateAgentRunError(RuntimeError):
    """Raised when a run identity or event sequence loses a uniqueness race."""


class AgentRunRepository(Protocol):
    """Storage operations that never return another principal's run."""

    async def get_owned_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> AgentRun | None:
        """Return one actor-owned run, optionally acquiring its row lock."""

    async def get_owned_run_by_trace(
        self,
        trace_id: str,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> AgentRun | None:
        """Return an idempotently created actor-owned run."""

    async def add_run(self, run: AgentRun) -> None:
        """Stage one run."""

    async def add_event(self, event: RunEvent) -> None:
        """Stage one monotonically sequenced event."""

    async def list_events(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int,
        limit: int,
    ) -> list[RunEvent]:
        """Return a bounded replay page after verifying run ownership."""

    async def flush(self) -> None:
        """Flush staged writes and translate uniqueness races."""

    async def commit(self) -> None:
        """Commit the current transaction."""

    async def rollback(self) -> None:
        """Release locks and discard staged writes."""


class SqlAlchemyAgentRunRepository:
    """PostgreSQL implementation backed by one request-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owned_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> AgentRun | None:
        statement = select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == tenant_id,
            AgentRun.actor_id == actor_id,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(AgentRun | None, await self._session.scalar(statement))

    async def get_owned_run_by_trace(
        self,
        trace_id: str,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> AgentRun | None:
        statement = select(AgentRun).where(
            AgentRun.trace_id == trace_id,
            AgentRun.tenant_id == tenant_id,
            AgentRun.actor_id == actor_id,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(AgentRun | None, await self._session.scalar(statement))

    async def add_run(self, run: AgentRun) -> None:
        self._session.add(run)

    async def add_event(self, event: RunEvent) -> None:
        self._session.add(event)

    async def list_events(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int,
        limit: int,
    ) -> list[RunEvent]:
        owned_run = await self.get_owned_run(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if owned_run is None:
            return []
        statement = (
            select(RunEvent)
            .where(
                RunEvent.run_id == run_id,
                RunEvent.sequence > after_sequence,
            )
            .order_by(RunEvent.sequence)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def flush(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise DuplicateAgentRunError from error
            raise

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise DuplicateAgentRunError from error
            raise

    async def rollback(self) -> None:
        await self._session.rollback()
