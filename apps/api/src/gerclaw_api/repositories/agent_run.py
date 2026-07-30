"""Actor-owned durable Agent run persistence boundary."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import (
    AgentRun,
    AgentRunAttempt,
    AgentRunAttemptEvent,
    AgentRunPlanNodeEvent,
    ConversationSession,
    RunDirective,
    RunEvent,
)


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

    async def get_latest_owned_run_for_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        """Return the latest actor-owned snapshot for one conversation."""

    async def add_run(self, run: AgentRun) -> None:
        """Stage one run."""

    async def add_event(self, event: RunEvent) -> None:
        """Stage one monotonically sequenced event."""

    async def get_attempt(
        self,
        attempt_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> AgentRunAttempt | None:
        """Return one private attempt, optionally locked."""

    async def next_attempt_number(
        self,
        run_id: uuid.UUID,
        public_operation_id: uuid.UUID,
    ) -> int:
        """Return the next monotonic attempt number for an operation."""

    async def add_attempt(self, attempt: AgentRunAttempt) -> None:
        """Stage private attempt metadata."""

    async def add_attempt_event(self, event: AgentRunAttemptEvent) -> None:
        """Stage one private event that is not replayable."""

    async def add_plan_node_event(self, event: AgentRunPlanNodeEvent) -> None:
        """Stage one append-only content-free plan transition."""

    async def list_attempt_events(
        self,
        attempt_id: uuid.UUID,
    ) -> list[AgentRunAttemptEvent]:
        """Return private staged events in ordinal order."""

    async def invalidate_staging_attempts(
        self,
        run_id: uuid.UUID,
        *,
        completed_at: datetime,
    ) -> None:
        """Invalidate every uncommitted attempt for a terminal/interrupted run."""

    async def bind_deferred_directives(
        self,
        run_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> None:
        """Bind actor-owned deferred requirements to a newly created Run."""

    async def defer_unconsumed_directives(
        self,
        run_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> None:
        """Defer requirements or bind them to an already active successor."""

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

    async def get_latest_owned_run_for_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        statement = (
            select(AgentRun)
            .where(
                AgentRun.conversation_id == conversation_id,
                AgentRun.tenant_id == tenant_id,
                AgentRun.actor_id == actor_id,
            )
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(1)
        )
        return cast(AgentRun | None, await self._session.scalar(statement))

    async def add_run(self, run: AgentRun) -> None:
        self._session.add(run)

    async def add_event(self, event: RunEvent) -> None:
        self._session.add(event)

    async def get_attempt(
        self,
        attempt_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> AgentRunAttempt | None:
        statement = select(AgentRunAttempt).where(AgentRunAttempt.id == attempt_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(AgentRunAttempt | None, await self._session.scalar(statement))

    async def next_attempt_number(
        self,
        run_id: uuid.UUID,
        public_operation_id: uuid.UUID,
    ) -> int:
        latest = await self._session.scalar(
            select(func.max(AgentRunAttempt.attempt)).where(
                AgentRunAttempt.run_id == run_id,
                AgentRunAttempt.public_operation_id == public_operation_id,
            )
        )
        return int(latest or 0) + 1

    async def add_attempt(self, attempt: AgentRunAttempt) -> None:
        self._session.add(attempt)

    async def add_attempt_event(self, event: AgentRunAttemptEvent) -> None:
        self._session.add(event)

    async def add_plan_node_event(self, event: AgentRunPlanNodeEvent) -> None:
        self._session.add(event)

    async def list_attempt_events(
        self,
        attempt_id: uuid.UUID,
    ) -> list[AgentRunAttemptEvent]:
        statement = (
            select(AgentRunAttemptEvent)
            .where(AgentRunAttemptEvent.attempt_id == attempt_id)
            .order_by(AgentRunAttemptEvent.ordinal)
        )
        return list((await self._session.scalars(statement)).all())

    async def invalidate_staging_attempts(
        self,
        run_id: uuid.UUID,
        *,
        completed_at: datetime,
    ) -> None:
        attempts = list(
            (
                await self._session.scalars(
                    select(AgentRunAttempt).where(
                        AgentRunAttempt.run_id == run_id,
                        AgentRunAttempt.status == "staging",
                    )
                )
            ).all()
        )
        for attempt in attempts:
            attempt.status = "invalidated"
            attempt.completed_at = completed_at

    async def _lock_directive_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
    ) -> ConversationSession:
        conversation = await self._session.scalar(
            select(ConversationSession)
            .where(
                ConversationSession.id == conversation_id,
                ConversationSession.tenant_id == tenant_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if conversation is None:
            raise RuntimeError("directive conversation disappeared")
        return conversation

    async def bind_deferred_directives(
        self,
        run_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> None:
        await self._lock_directive_conversation(
            conversation_id,
            tenant_id=tenant_id,
        )
        directives = list(
            (
                await self._session.scalars(
                    select(RunDirective)
                    .where(
                        RunDirective.conversation_id == conversation_id,
                        RunDirective.tenant_id == tenant_id,
                        RunDirective.actor_id == actor_id,
                        RunDirective.status == "pending_next_run",
                        RunDirective.successor_run_id.is_(None),
                    )
                    .order_by(RunDirective.sequence)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        for directive in directives:
            directive.status = "pending"
            directive.successor_run_id = run_id
            directive.revision += 1

    async def defer_unconsumed_directives(
        self,
        run_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> None:
        conversation = await self._lock_directive_conversation(
            conversation_id,
            tenant_id=tenant_id,
        )
        successor_run_id: uuid.UUID | None = None
        if conversation.active_fencing_trace_id is not None:
            successor_run_id = cast(
                uuid.UUID | None,
                await self._session.scalar(
                    select(AgentRun.id)
                    .where(
                        AgentRun.conversation_id == conversation_id,
                        AgentRun.tenant_id == tenant_id,
                        AgentRun.actor_id == actor_id,
                        AgentRun.id != run_id,
                        AgentRun.trace_id == conversation.active_fencing_trace_id,
                        AgentRun.status == "running",
                    )
                    .limit(1)
                ),
            )
        statement = (
            select(RunDirective)
            .where(
                RunDirective.tenant_id == tenant_id,
                RunDirective.actor_id == actor_id,
                RunDirective.status.in_(("pending", "claimed")),
                (
                    (RunDirective.successor_run_id == run_id)
                    | (
                        (RunDirective.successor_run_id.is_(None))
                        & (RunDirective.target_run_id == run_id)
                    )
                ),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        directives = list((await self._session.scalars(statement)).all())
        for directive in directives:
            directive.status = "pending" if successor_run_id is not None else "pending_next_run"
            directive.successor_run_id = successor_run_id
            directive.claimed_by_fencing_token = None
            directive.claim_boundary_id = None
            directive.claimed_at = None
            directive.revision += 1

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
