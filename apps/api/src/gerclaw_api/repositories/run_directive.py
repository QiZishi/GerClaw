"""Actor-owned persistence boundary for execution-time user directives."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, cast

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import AgentRun, ConversationSession, Message, RunDirective


class DuplicateRunDirectiveError(RuntimeError):
    """Raised when an idempotency key or conversation sequence loses a race."""


class RunDirectiveRepository(Protocol):
    async def get_owned_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> AgentRun | None: ...

    async def get_owned_run_by_trace(
        self,
        trace_id: str,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> AgentRun | None: ...

    async def get_owned(
        self,
        directive_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> RunDirective | None: ...

    async def get_owned_by_idempotency(
        self,
        idempotency_key: str,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirective | None: ...

    async def get_bound_steer_for_source(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirective | None: ...

    async def lock_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
    ) -> ConversationSession | None: ...

    async def list_consumable(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunDirective]: ...

    async def transfer_consumable(
        self,
        source_run_id: uuid.UUID,
        successor_run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        updated_at: datetime,
    ) -> None: ...

    async def list_applied_for_execution(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int,
        limit: int,
    ) -> list[RunDirective]: ...

    async def list_recent_applied_for_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunDirective]: ...

    async def list_for_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunDirective]: ...

    async def get_projected_message(
        self,
        trace_id: str,
        *,
        tenant_id: str,
    ) -> Message | None: ...

    async def get_run_input_message(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> Message | None: ...

    async def add_projected_message(self, message: Message) -> None: ...

    async def add(self, directive: RunDirective) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class SqlAlchemyRunDirectiveRepository:
    """PostgreSQL ledger with row locking and actor-scoped reads."""

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

    async def get_owned(
        self,
        directive_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> RunDirective | None:
        statement = select(RunDirective).where(
            RunDirective.id == directive_id,
            RunDirective.tenant_id == tenant_id,
            RunDirective.actor_id == actor_id,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(RunDirective | None, await self._session.scalar(statement))

    async def get_owned_by_idempotency(
        self,
        idempotency_key: str,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirective | None:
        return cast(
            RunDirective | None,
            await self._session.scalar(
                select(RunDirective).where(
                    RunDirective.tenant_id == tenant_id,
                    RunDirective.actor_id == actor_id,
                    RunDirective.idempotency_key == idempotency_key,
                )
            ),
        )

    async def get_bound_steer_for_source(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirective | None:
        return cast(
            RunDirective | None,
            await self._session.scalar(
                select(RunDirective)
                .where(
                    RunDirective.tenant_id == tenant_id,
                    RunDirective.actor_id == actor_id,
                    RunDirective.target_run_id == run_id,
                    RunDirective.mode == "interrupt_and_steer",
                    RunDirective.status == "applied",
                    RunDirective.successor_run_id.is_not(None),
                )
                .order_by(RunDirective.sequence.desc())
                .limit(1)
            ),
        )

    async def lock_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
    ) -> ConversationSession | None:
        return cast(
            ConversationSession | None,
            await self._session.scalar(
                select(ConversationSession)
                .where(
                    ConversationSession.id == conversation_id,
                    ConversationSession.tenant_id == tenant_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            ),
        )

    async def list_consumable(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunDirective]:
        execution_target = or_(
            RunDirective.successor_run_id == run_id,
            and_(
                RunDirective.successor_run_id.is_(None),
                RunDirective.target_run_id == run_id,
                RunDirective.mode == "queue_for_next_boundary",
            ),
        )
        statement = (
            select(RunDirective)
            .where(
                RunDirective.tenant_id == tenant_id,
                RunDirective.actor_id == actor_id,
                RunDirective.status.in_(("pending", "claimed")),
                execution_target,
            )
            .order_by(RunDirective.sequence)
            .limit(limit)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list((await self._session.scalars(statement)).all())

    async def transfer_consumable(
        self,
        source_run_id: uuid.UUID,
        successor_run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        updated_at: datetime,
    ) -> None:
        """Move every still-consumable queue item while the source Run is locked."""

        await self._session.execute(
            update(RunDirective)
            .where(
                RunDirective.tenant_id == tenant_id,
                RunDirective.actor_id == actor_id,
                RunDirective.status.in_(("pending", "claimed")),
                or_(
                    RunDirective.successor_run_id == source_run_id,
                    and_(
                        RunDirective.successor_run_id.is_(None),
                        RunDirective.target_run_id == source_run_id,
                        RunDirective.mode == "queue_for_next_boundary",
                    ),
                ),
            )
            .values(
                successor_run_id=successor_run_id,
                status="pending",
                claimed_by_fencing_token=None,
                claim_boundary_id=None,
                claimed_at=None,
                revision=RunDirective.revision + 1,
                updated_at=updated_at,
            )
        )

    async def list_applied_for_execution(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int,
        limit: int,
    ) -> list[RunDirective]:
        execution_target = or_(
            RunDirective.successor_run_id == run_id,
            and_(
                RunDirective.successor_run_id.is_(None),
                RunDirective.target_run_id == run_id,
                RunDirective.mode == "queue_for_next_boundary",
            ),
        )
        statement = (
            select(RunDirective)
            .where(
                RunDirective.tenant_id == tenant_id,
                RunDirective.actor_id == actor_id,
                RunDirective.status == "applied",
                RunDirective.sequence > after_sequence,
                execution_target,
            )
            .order_by(RunDirective.sequence)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def list_recent_applied_for_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunDirective]:
        statement = (
            select(RunDirective)
            .where(
                RunDirective.conversation_id == conversation_id,
                RunDirective.tenant_id == tenant_id,
                RunDirective.actor_id == actor_id,
                RunDirective.status == "applied",
            )
            .order_by(RunDirective.sequence.desc())
            .limit(limit)
        )
        newest_first = list((await self._session.scalars(statement)).all())
        return list(reversed(newest_first))

    async def list_for_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunDirective]:
        statement = (
            select(RunDirective)
            .where(
                RunDirective.tenant_id == tenant_id,
                RunDirective.actor_id == actor_id,
                or_(
                    RunDirective.target_run_id == run_id,
                    RunDirective.successor_run_id == run_id,
                ),
            )
            .order_by(RunDirective.sequence)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_projected_message(
        self,
        trace_id: str,
        *,
        tenant_id: str,
    ) -> Message | None:
        return cast(
            Message | None,
            await self._session.scalar(
                select(Message).where(
                    Message.tenant_id == tenant_id,
                    Message.trace_id == trace_id,
                    Message.role == "user",
                )
            ),
        )

    async def get_run_input_message(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> Message | None:
        return cast(
            Message | None,
            await self._session.scalar(
                select(Message)
                .join(
                    AgentRun,
                    and_(
                        AgentRun.input_message_id == Message.id,
                        AgentRun.tenant_id == Message.tenant_id,
                        AgentRun.conversation_id == Message.session_id,
                    ),
                )
                .where(
                    AgentRun.id == run_id,
                    AgentRun.tenant_id == tenant_id,
                    AgentRun.actor_id == actor_id,
                    Message.role == "user",
                )
            ),
        )

    async def add_projected_message(self, message: Message) -> None:
        self._session.add(message)

    async def add(self, directive: RunDirective) -> None:
        self._session.add(directive)

    async def flush(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise DuplicateRunDirectiveError from error
            raise

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise DuplicateRunDirectiveError from error
            raise

    async def rollback(self) -> None:
        await self._session.rollback()
