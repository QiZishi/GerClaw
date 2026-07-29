"""Owner-scoped persistence boundary for reconstructing an interrupted Run."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, cast

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import AgentRun, ExecutionTrace, Message


@dataclass(frozen=True, slots=True)
class RunResumeRecord:
    """Encrypted-at-rest records needed to validate one resume command."""

    run: AgentRun
    input_message: Message
    trace: ExecutionTrace


class RunResumeRepository(Protocol):
    async def get_owned_context(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunResumeRecord | None:
        """Return a Run only with its same-owner input and Trace."""

    async def get_latest_recoverable(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        """Return the newest running or resumable Run in one owned conversation."""

    async def rollback(self) -> None:
        """End the read transaction without retaining a snapshot."""


class SqlAlchemyRunResumeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owned_context(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunResumeRecord | None:
        statement = (
            select(AgentRun, Message, ExecutionTrace)
            .join(
                Message,
                and_(
                    Message.id == AgentRun.input_message_id,
                    Message.tenant_id == AgentRun.tenant_id,
                    Message.session_id == AgentRun.conversation_id,
                ),
            )
            .join(
                ExecutionTrace,
                and_(
                    ExecutionTrace.tenant_id == AgentRun.tenant_id,
                    ExecutionTrace.trace_id == AgentRun.trace_id,
                    ExecutionTrace.actor_id == AgentRun.actor_id,
                    ExecutionTrace.session_id == AgentRun.conversation_id,
                ),
            )
            .where(
                AgentRun.id == run_id,
                AgentRun.tenant_id == tenant_id,
                AgentRun.actor_id == actor_id,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        run, input_message, trace = row._tuple()
        return RunResumeRecord(
            run=run,
            input_message=input_message,
            trace=trace,
        )

    async def get_latest_recoverable(
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
                AgentRun.status.in_(("running", "interrupted")),
            )
            .order_by(AgentRun.updated_at.desc(), AgentRun.id.desc())
            .limit(1)
        )
        return cast(AgentRun | None, await self._session.scalar(statement))

    async def rollback(self) -> None:
        await self._session.rollback()
