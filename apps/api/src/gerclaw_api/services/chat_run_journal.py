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
    RunAttemptCreate,
    RunAttemptRead,
    RunDirectiveClaim,
    RunDirectiveRead,
    RunEventRead,
    RunEventWrite,
    RunRegenerationContext,
    ValidationFeedback,
)
from gerclaw_api.modules.agent_harness.clinical_state import (
    ClinicalState,
    ClinicalStateError,
)
from gerclaw_api.modules.agent_harness.evolution_signals import EvolutionSignalCollector
from gerclaw_api.modules.agent_harness.planning import PlanExecutionSnapshot
from gerclaw_api.repositories.agent_run import SqlAlchemyAgentRunRepository
from gerclaw_api.repositories.answer_version import SqlAlchemyAnswerVersionRepository
from gerclaw_api.repositories.run_directive import SqlAlchemyRunDirectiveRepository
from gerclaw_api.repositories.run_regeneration import (
    SqlAlchemyRunRegenerationRepository,
)
from gerclaw_api.security import JsonValue
from gerclaw_api.services.agent_run_service import AgentRunService
from gerclaw_api.services.answer_version_service import AnswerVersionService
from gerclaw_api.services.run_directive_service import RunDirectiveService
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

    async def read_clinical_state(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> ClinicalState:
        """Restore the latest encrypted, actor-owned clinical snapshot."""

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

    async def begin_attempt(
        self,
        run_id: uuid.UUID,
        request: RunAttemptCreate,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        """Create a private staging attempt for one stable public operation."""

    async def update_plan_execution(
        self,
        run_id: uuid.UUID,
        updated: PlanExecutionSnapshot,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> PlanExecutionSnapshot:
        """Persist exactly one fenced PlanNode transition."""

    async def stage_attempt_event(
        self,
        attempt_id: uuid.UUID,
        event: RunEventWrite,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        """Persist an event privately without allocating a public sequence."""

    async def reject_attempt(
        self,
        attempt_id: uuid.UUID,
        feedback: ValidationFeedback,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        """Close a failed attempt with bounded content-free repair metadata."""

    async def complete_answer(
        self,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        done_payload: dict[str, JsonValue],
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        answer_group_run_id: uuid.UUID | None = None,
        expected_current_version_id: uuid.UUID | None = None,
    ) -> tuple[AnswerVersionRead, AgentRunRead, tuple[RunEventRead, ...]]:
        """Atomically register the answer and CAS-promote the validated attempt."""

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

class RunDirectiveJournal(Protocol):
    """Optional execution-time directive boundary kept separate from base Run journaling."""

    async def list_applied_directives(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]: ...

    async def list_recent_applied_directives(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]: ...

    async def bind_successor_input(
        self,
        directive_id: uuid.UUID,
        successor_run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunDirectiveRead: ...

    async def claim_directives(
        self,
        run_id: uuid.UUID,
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]: ...

    async def mark_directives_applied(
        self,
        run_id: uuid.UUID,
        directive_ids: tuple[uuid.UUID, ...],
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> tuple[RunDirectiveRead, ...]: ...


class DatabaseChatRunJournal:
    """Open a short PostgreSQL transaction for each replayable Run fact."""

    def __init__(
        self,
        database: Database,
        *,
        completion_session: AsyncSession | None = None,
        evolution_signal_collector: EvolutionSignalCollector | None = None,
    ) -> None:
        self._database = database
        self._completion_session = completion_session
        self._evolution_signal_collector = evolution_signal_collector

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

    async def list_applied_directives(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        async with self._database.session() as session:
            return await RunDirectiveService(
                SqlAlchemyRunDirectiveRepository(session)
            ).list_applied_for_execution(
                run_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                after_sequence=after_sequence,
                limit=limit,
            )

    async def list_recent_applied_directives(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        async with self._database.session() as session:
            return await RunDirectiveService(
                SqlAlchemyRunDirectiveRepository(session)
            ).list_recent_applied_for_conversation(
                conversation_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                limit=limit,
            )

    async def bind_successor_input(
        self,
        directive_id: uuid.UUID,
        successor_run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunDirectiveRead:
        async with self._database.session() as session:
            return await RunDirectiveService(
                SqlAlchemyRunDirectiveRepository(session)
            ).bind_successor_input(
                directive_id,
                successor_run_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                fencing_token=fencing_token,
            )

    async def claim_directives(
        self,
        run_id: uuid.UUID,
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        async with self._database.session() as session:
            return await RunDirectiveService(
                SqlAlchemyRunDirectiveRepository(session)
            ).claim_batch(
                run_id,
                claim,
                tenant_id=tenant_id,
                actor_id=actor_id,
                limit=limit,
            )

    async def mark_directives_applied(
        self,
        run_id: uuid.UUID,
        directive_ids: tuple[uuid.UUID, ...],
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> tuple[RunDirectiveRead, ...]:
        async with self._database.session() as session:
            return await RunDirectiveService(
                SqlAlchemyRunDirectiveRepository(session)
            ).mark_many_applied(
                run_id,
                directive_ids,
                claim,
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

    async def read_clinical_state(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> ClinicalState:
        async with self._database.session() as session:
            repository = SqlAlchemyAgentRunRepository(session)
            run = await repository.get_latest_owned_run_for_conversation(
                conversation_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
            if run is None:
                await repository.rollback()
                return ClinicalState()
            raw_state = run.context_snapshot.get("clinical_state")
            if raw_state is None:
                agent_context = run.context_snapshot.get("agent_context")
                if isinstance(agent_context, dict):
                    raw_state = agent_context.get("clinical_state")
            await repository.rollback()
            if raw_state is None:
                return ClinicalState()
            try:
                return ClinicalState.model_validate(raw_state)
            except ValueError as exc:
                raise ClinicalStateError("PERSISTED_CLINICAL_STATE_INVALID") from exc

    async def start(
        self,
        request: AgentRunCreate,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRunRead:
        async with self._database.session() as session:
            return await AgentRunService(SqlAlchemyAgentRunRepository(session)).adopt_for_worker(
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
            return await AgentRunService(SqlAlchemyAgentRunRepository(session)).append_event(
                run_id,
                event,
                tenant_id=tenant_id,
                actor_id=actor_id,
                fencing_token=fencing_token,
            )

    async def begin_attempt(
        self,
        run_id: uuid.UUID,
        request: RunAttemptCreate,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        async with self._database.session() as session:
            return await AgentRunService(SqlAlchemyAgentRunRepository(session)).begin_attempt(
                run_id,
                request,
                tenant_id=tenant_id,
                actor_id=actor_id,
                fencing_token=fencing_token,
            )

    async def update_plan_execution(
        self,
        run_id: uuid.UUID,
        updated: PlanExecutionSnapshot,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> PlanExecutionSnapshot:
        async with self._database.session() as session:
            return await AgentRunService(
                SqlAlchemyAgentRunRepository(session)
            ).update_plan_execution(
                run_id,
                updated,
                tenant_id=tenant_id,
                actor_id=actor_id,
                fencing_token=fencing_token,
            )

    async def stage_attempt_event(
        self,
        attempt_id: uuid.UUID,
        event: RunEventWrite,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        async with self._database.session() as session:
            return await AgentRunService(SqlAlchemyAgentRunRepository(session)).stage_attempt_event(
                attempt_id,
                event,
                tenant_id=tenant_id,
                actor_id=actor_id,
                fencing_token=fencing_token,
            )

    async def reject_attempt(
        self,
        attempt_id: uuid.UUID,
        feedback: ValidationFeedback,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        async with self._database.session() as session:
            return await AgentRunService(SqlAlchemyAgentRunRepository(session)).reject_attempt(
                attempt_id,
                feedback,
                tenant_id=tenant_id,
                actor_id=actor_id,
                fencing_token=fencing_token,
            )

    async def complete_answer(
        self,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        done_payload: dict[str, JsonValue],
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        answer_group_run_id: uuid.UUID | None = None,
        expected_current_version_id: uuid.UUID | None = None,
    ) -> tuple[AnswerVersionRead, AgentRunRead, tuple[RunEventRead, ...]]:
        if self._completion_session is not None:
            return await self._complete_answer_in_session(
                self._completion_session,
                run_id,
                attempt_id,
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
            result = await self._complete_answer_in_session(
                session,
                run_id,
                attempt_id,
                assistant_message_id,
                done_payload,
                tenant_id=tenant_id,
                actor_id=actor_id,
                fencing_token=fencing_token,
                answer_group_run_id=answer_group_run_id,
                expected_current_version_id=expected_current_version_id,
                commit=True,
            )
        if self._evolution_signal_collector is not None:
            self._evolution_signal_collector.schedule(run_id)
        return result

    @staticmethod
    async def _complete_answer_in_session(
        session: AsyncSession,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        done_payload: dict[str, JsonValue],
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        answer_group_run_id: uuid.UUID | None,
        expected_current_version_id: uuid.UUID | None,
        commit: bool,
    ) -> tuple[AnswerVersionRead, AgentRunRead, tuple[RunEventRead, ...]]:
        answer = await AnswerVersionService(SqlAlchemyAnswerVersionRepository(session)).register(
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
        run, events = await AgentRunService(SqlAlchemyAgentRunRepository(session)).commit_attempt(
            attempt_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            fencing_token=fencing_token,
            target=AgentRunStatus.COMPLETED,
            terminal_event=RunEventWrite(
                event_type="done",
                status=AgentRunStatus.COMPLETED.value,
                public_summary="回答已完成",
                payload=completed_payload,
            ),
            commit=commit,
        )
        return answer, run, events

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
            transitioned = await service.transition(
                run_id,
                target,
                tenant_id=tenant_id,
                actor_id=actor_id,
                expected_revision=run.revision,
                fencing_token=fencing_token,
                warnings=warnings,
                public_summary=public_summary,
            )
        if self._evolution_signal_collector is not None:
            self._evolution_signal_collector.schedule(run_id)
        return transitioned
