"""Independent transactions for durable Chat-to-AgentRun journaling."""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.session import Database
from gerclaw_api.domain.chat_schemas import ChatRequest
from gerclaw_api.domain.run_schemas import (
    AgentRunCreate,
    AgentRunRead,
    AgentRunStatus,
    AnswerVersionRead,
    AnswerVersionRegister,
    RunAnswerContext,
    RunEventRead,
    RunEventWrite,
    RunRegenerationContext,
)
from gerclaw_api.repositories.agent_run import SqlAlchemyAgentRunRepository
from gerclaw_api.repositories.answer_version import SqlAlchemyAnswerVersionRepository
from gerclaw_api.repositories.run_regeneration import (
    SqlAlchemyRunRegenerationRepository,
)
from gerclaw_api.security import JsonValue
from gerclaw_api.services.agent_run_service import AgentRunService
from gerclaw_api.services.answer_version_service import AnswerVersionService
from gerclaw_api.services.run_regeneration_service import RunRegenerationService


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

    async def resolve_regeneration(
        self,
        request: ChatRequest,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunRegenerationContext | None:
        """Validate a replacement request against the immutable source Run."""

    async def read_answer_context(
        self,
        trace_id: str,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunAnswerContext | None:
        """Restore version metadata for a completed same-Trace replay."""

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

    async def complete_answer(
        self,
        run_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        done_payload: dict[str, JsonValue],
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        answer_group_run_id: uuid.UUID | None = None,
        expected_current_version_id: uuid.UUID | None = None,
    ) -> tuple[AnswerVersionRead, AgentRunRead]:
        """Atomically register the answer and publish the single completed terminal event."""

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

    def __init__(
        self,
        database: Database,
        *,
        completion_session: AsyncSession | None = None,
    ) -> None:
        self._database = database
        self._completion_session = completion_session

    async def resolve_regeneration(
        self,
        request: ChatRequest,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunRegenerationContext | None:
        async with self._database.session() as session:
            return await RunRegenerationService(
                SqlAlchemyRunRegenerationRepository(session)
            ).resolve(
                request,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )

    async def read_answer_context(
        self,
        trace_id: str,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunAnswerContext | None:
        async with self._database.session() as session:
            run_repository = SqlAlchemyAgentRunRepository(session)
            run = await run_repository.get_owned_run_by_trace(
                trace_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
            if run is None:
                await run_repository.rollback()
                return None
            version_repository = SqlAlchemyAnswerVersionRepository(session)
            version = await version_repository.get_by_producer_run(run.id)
            if version is None:
                await version_repository.rollback()
                return None
            result = RunAnswerContext(
                run_id=run.id,
                answer_group_run_id=version.run_id,
                answer_version_id=version.id,
                answer_version=version.version,
            )
            await version_repository.rollback()
            return result

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

    async def complete_answer(
        self,
        run_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        done_payload: dict[str, JsonValue],
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        answer_group_run_id: uuid.UUID | None = None,
        expected_current_version_id: uuid.UUID | None = None,
    ) -> tuple[AnswerVersionRead, AgentRunRead]:
        if self._completion_session is not None:
            return await self._complete_answer_in_session(
                self._completion_session,
                run_id,
                assistant_message_id,
                done_payload,
                tenant_id=tenant_id,
                actor_id=actor_id,
                fencing_token=fencing_token,
                answer_group_run_id=answer_group_run_id,
                expected_current_version_id=expected_current_version_id,
                commit=False,
            )
        async with self._database.session() as session:
            return await self._complete_answer_in_session(
                session,
                run_id,
                assistant_message_id,
                done_payload,
                tenant_id=tenant_id,
                actor_id=actor_id,
                fencing_token=fencing_token,
                answer_group_run_id=answer_group_run_id,
                expected_current_version_id=expected_current_version_id,
                commit=True,
            )

    @staticmethod
    async def _complete_answer_in_session(
        session: AsyncSession,
        run_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        done_payload: dict[str, JsonValue],
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        answer_group_run_id: uuid.UUID | None,
        expected_current_version_id: uuid.UUID | None,
        commit: bool,
    ) -> tuple[AnswerVersionRead, AgentRunRead]:
        answer = await AnswerVersionService(
            SqlAlchemyAnswerVersionRepository(session)
        ).register(
            answer_group_run_id or run_id,
            AnswerVersionRegister(
                assistant_message_id=assistant_message_id,
                producer_run_id=run_id,
                expected_current_version_id=expected_current_version_id,
            ),
            tenant_id=tenant_id,
            actor_id=actor_id,
            commit=False,
        )
        completed_payload = {
            **done_payload,
            "run_id": str(run_id),
            "answer_group_run_id": str(answer_group_run_id or run_id),
            "answer_version_id": str(answer.id),
            "answer_version": answer.version,
        }
        run = await AgentRunService(
            SqlAlchemyAgentRunRepository(session)
        ).transition(
            run_id,
            AgentRunStatus.COMPLETED,
            tenant_id=tenant_id,
            actor_id=actor_id,
            expected_revision=None,
            fencing_token=fencing_token,
            terminal_event=RunEventWrite(
                event_type="done",
                status=AgentRunStatus.COMPLETED.value,
                public_summary="回答已完成",
                payload=completed_payload,
            ),
            commit=commit,
        )
        return answer, run

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
