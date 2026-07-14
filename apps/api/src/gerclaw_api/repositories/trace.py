"""Trace persistence boundary and SQLAlchemy implementation."""

from __future__ import annotations

from typing import Protocol, cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import (
    BadCase,
    ExecutionTrace,
    TraceEvent,
    UserFeedback,
)


class DuplicateKeyError(RuntimeError):
    """Raised after a unique-key race has been rolled back safely."""


class TraceRepository(Protocol):
    """Storage contract used by the trace service."""

    async def get_trace(
        self, tenant_id: str, trace_id: str, *, for_update: bool = False
    ) -> ExecutionTrace | None:
        """Return a trace, optionally locking it for a state transition."""

    async def add_trace(self, trace: ExecutionTrace) -> None:
        """Stage a new trace."""

    async def next_event_sequence(self, tenant_id: str, trace_id: str) -> int:
        """Return the next ordered event sequence number."""

    async def add_event(self, event: TraceEvent) -> None:
        """Stage an event."""

    async def get_event_by_id(
        self, tenant_id: str, trace_id: str, event_id: str
    ) -> TraceEvent | None:
        """Return an idempotently accepted event."""

    async def count_events(self, tenant_id: str, trace_id: str) -> int:
        """Count events to enforce a per-Trace resource ceiling."""

    async def list_events(
        self, tenant_id: str, trace_id: str, *, after_sequence: int, limit: int
    ) -> list[TraceEvent]:
        """List one bounded page in deterministic sequence order."""

    async def get_feedback_by_key(
        self, tenant_id: str, idempotency_key: str
    ) -> UserFeedback | None:
        """Return feedback previously accepted for an idempotency key."""

    async def add_feedback(self, feedback: UserFeedback) -> None:
        """Stage user feedback."""

    async def get_bad_case(self, tenant_id: str, trace_id: str, source: str) -> BadCase | None:
        """Return an existing bad-case queue item."""

    async def add_bad_case(self, bad_case: BadCase) -> None:
        """Stage a new bad-case queue item."""

    async def flush(self) -> None:
        """Flush staged objects, rolling back unique-key races safely."""

    async def commit(self) -> None:
        """Commit the current transaction."""


class SqlAlchemyTraceRepository:
    """PostgreSQL-backed trace repository scoped to one request transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_trace(
        self, tenant_id: str, trace_id: str, *, for_update: bool = False
    ) -> ExecutionTrace | None:
        statement = select(ExecutionTrace).where(
            ExecutionTrace.tenant_id == tenant_id,
            ExecutionTrace.trace_id == trace_id,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(ExecutionTrace | None, await self._session.scalar(statement))

    async def add_trace(self, trace: ExecutionTrace) -> None:
        self._session.add(trace)

    async def next_event_sequence(self, tenant_id: str, trace_id: str) -> int:
        statement = select(func.coalesce(func.max(TraceEvent.sequence), 0) + 1).where(
            TraceEvent.tenant_id == tenant_id, TraceEvent.trace_id == trace_id
        )
        return int(await self._session.scalar(statement) or 1)

    async def add_event(self, event: TraceEvent) -> None:
        self._session.add(event)

    async def get_event_by_id(
        self, tenant_id: str, trace_id: str, event_id: str
    ) -> TraceEvent | None:
        statement = select(TraceEvent).where(
            TraceEvent.tenant_id == tenant_id,
            TraceEvent.trace_id == trace_id,
            TraceEvent.event_id == event_id,
        )
        return cast(TraceEvent | None, await self._session.scalar(statement))

    async def count_events(self, tenant_id: str, trace_id: str) -> int:
        statement = (
            select(func.count())
            .select_from(TraceEvent)
            .where(
                TraceEvent.tenant_id == tenant_id,
                TraceEvent.trace_id == trace_id,
            )
        )
        return int(await self._session.scalar(statement) or 0)

    async def list_events(
        self, tenant_id: str, trace_id: str, *, after_sequence: int, limit: int
    ) -> list[TraceEvent]:
        statement = (
            select(TraceEvent)
            .where(
                TraceEvent.tenant_id == tenant_id,
                TraceEvent.trace_id == trace_id,
                TraceEvent.sequence > after_sequence,
            )
            .order_by(TraceEvent.sequence)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_feedback_by_key(
        self, tenant_id: str, idempotency_key: str
    ) -> UserFeedback | None:
        statement = select(UserFeedback).where(
            UserFeedback.tenant_id == tenant_id,
            UserFeedback.idempotency_key == idempotency_key,
        )
        return cast(UserFeedback | None, await self._session.scalar(statement))

    async def add_feedback(self, feedback: UserFeedback) -> None:
        self._session.add(feedback)

    async def get_bad_case(self, tenant_id: str, trace_id: str, source: str) -> BadCase | None:
        statement = select(BadCase).where(
            BadCase.tenant_id == tenant_id,
            BadCase.trace_id == trace_id,
            BadCase.source == source,
        )
        return cast(BadCase | None, await self._session.scalar(statement))

    async def add_bad_case(self, bad_case: BadCase) -> None:
        self._session.add(bad_case)

    async def flush(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise DuplicateKeyError from error
            raise

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise DuplicateKeyError from error
            raise
