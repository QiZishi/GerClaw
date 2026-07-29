"""Independent transactions for durable Chat-to-AgentRun journaling."""

from __future__ import annotations

import uuid
from typing import Protocol

from gerclaw_api.database.session import Database
from gerclaw_api.domain.run_schemas import (
    AgentRunCreate,
    AgentRunRead,
    AgentRunStatus,
    AnswerVersionRead,
    AnswerVersionRegister,
    RunEventRead,
    RunEventWrite,
)
from gerclaw_api.repositories.agent_run import SqlAlchemyAgentRunRepository
from gerclaw_api.repositories.answer_version import SqlAlchemyAnswerVersionRepository
from gerclaw_api.services.agent_run_service import AgentRunService
from gerclaw_api.services.answer_version_service import AnswerVersionService


class ChatRunJournal(Protocol):
    """Durable Run operations isolated from the Chat turn unit of work."""

    async def start(
        self,
        request: AgentRunCreate,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRunRead:
        """Create or replay the Run after the input message is durable."""

    async def append(
        self,
        run_id: uuid.UUID,
        event: RunEventWrite,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunEventRead:
        """Persist one fenced public SSE event immediately."""

    async def register_answer(
        self,
        run_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        answer_group_run_id: uuid.UUID | None = None,
    ) -> AnswerVersionRead:
        """Register the committed assistant message as a new answer version."""

    async def transition(
        self,
        run_id: uuid.UUID,
        target: AgentRunStatus,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        warnings: tuple[str, ...] = (),
        public_summary: str | None = None,
    ) -> AgentRunRead:
        """Apply a fenced transition against the latest durable revision."""


class DatabaseChatRunJournal:
    """Open a short PostgreSQL transaction for each replayable Run fact."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def start(
        self,
        request: AgentRunCreate,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRunRead:
        async with self._database.session() as session:
            return await AgentRunService(
                SqlAlchemyAgentRunRepository(session)
            ).adopt_for_worker(
                request,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )

    async def append(
        self,
        run_id: uuid.UUID,
        event: RunEventWrite,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunEventRead:
        async with self._database.session() as session:
            return await AgentRunService(
                SqlAlchemyAgentRunRepository(session)
            ).append_event(
                run_id,
                event,
                tenant_id=tenant_id,
                actor_id=actor_id,
                fencing_token=fencing_token,
            )

    async def register_answer(
        self,
        run_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        answer_group_run_id: uuid.UUID | None = None,
    ) -> AnswerVersionRead:
        async with self._database.session() as session:
            return await AnswerVersionService(
                SqlAlchemyAnswerVersionRepository(session)
            ).register(
                answer_group_run_id or run_id,
                AnswerVersionRegister(
                    assistant_message_id=assistant_message_id,
                    producer_run_id=run_id,
                ),
                tenant_id=tenant_id,
                actor_id=actor_id,
            )

    async def transition(
        self,
        run_id: uuid.UUID,
        target: AgentRunStatus,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        warnings: tuple[str, ...] = (),
        public_summary: str | None = None,
    ) -> AgentRunRead:
        async with self._database.session() as session:
            service = AgentRunService(SqlAlchemyAgentRunRepository(session))
            run = await service.get_run(
                run_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
            return await service.transition(
                run_id,
                target,
                tenant_id=tenant_id,
                actor_id=actor_id,
                expected_revision=run.revision,
                fencing_token=fencing_token,
                warnings=warnings,
                public_summary=public_summary,
            )
