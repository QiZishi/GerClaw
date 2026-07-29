"""Owner-scoped source facts required to authorize answer regeneration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import AgentRun, AnswerVersion, Message


@dataclass(frozen=True, slots=True)
class RegenerationSource:
    run: AgentRun
    input_message: Message
    current_version: AnswerVersion | None


class RunRegenerationRepository(Protocol):
    async def get_owned_source(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RegenerationSource | None:
        """Return only a fully owner-scoped source Run and its immutable input."""

    async def rollback(self) -> None:
        """Release the source read transaction without mutation."""


class SqlAlchemyRunRegenerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owned_source(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RegenerationSource | None:
        run = cast(
            AgentRun | None,
            await self._session.scalar(
                select(AgentRun).where(
                    AgentRun.id == run_id,
                    AgentRun.tenant_id == tenant_id,
                    AgentRun.actor_id == actor_id,
                )
            ),
        )
        if run is None:
            return None
        message = cast(
            Message | None,
            await self._session.scalar(
                select(Message).where(
                    Message.id == run.input_message_id,
                    Message.tenant_id == tenant_id,
                    Message.session_id == run.conversation_id,
                    Message.role == "user",
                )
            ),
        )
        if message is None:
            return None
        current = cast(
            AnswerVersion | None,
            await self._session.scalar(
                select(AnswerVersion).where(
                    AnswerVersion.run_id == run.id,
                    AnswerVersion.is_current.is_(True),
                )
            ),
        )
        return RegenerationSource(
            run=run,
            input_message=message,
            current_version=current,
        )

    async def rollback(self) -> None:
        await self._session.rollback()
