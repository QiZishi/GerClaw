"""System-only scan boundary for unfinished Agent runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import AgentRun


@dataclass(frozen=True, slots=True)
class RunRecoveryCandidate:
    """Content-free identity needed to verify whether a Run still has a lease."""

    run_id: uuid.UUID
    tenant_id: str
    actor_id: str
    conversation_id: uuid.UUID


class SqlAlchemyRunRecoveryRepository:
    """Read unfinished identities in deterministic UUID pages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_candidates(
        self,
        *,
        after_run_id: uuid.UUID | None,
        limit: int,
    ) -> list[RunRecoveryCandidate]:
        statement = (
            select(
                AgentRun.id,
                AgentRun.tenant_id,
                AgentRun.actor_id,
                AgentRun.conversation_id,
            )
            .where(AgentRun.status.in_(("running", "waiting_for_user")))
            .order_by(AgentRun.id)
            .limit(limit)
        )
        if after_run_id is not None:
            statement = statement.where(AgentRun.id > after_run_id)
        rows = (await self._session.execute(statement)).all()
        return [
            RunRecoveryCandidate(
                run_id=row.id,
                tenant_id=row.tenant_id,
                actor_id=row.actor_id,
                conversation_id=row.conversation_id,
            )
            for row in rows
        ]
