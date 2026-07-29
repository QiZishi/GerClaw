"""Transactional source of truth for Agent runs and public replay events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from gerclaw_api.database.models import AgentRun, RunEvent
from gerclaw_api.domain.run_schemas import (
    TERMINAL_RUN_STATUSES,
    AgentRunCreate,
    AgentRunRead,
    AgentRunStatus,
    RunEventRead,
    RunEventWrite,
)
from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.modules.agent_harness.run_lifecycle import (
    AgentRunStateMachine,
    RunFenceConflictError,
    RunLifecycleState,
    RunTerminalConflictError,
)
from gerclaw_api.repositories.agent_run import (
    AgentRunRepository,
    DuplicateAgentRunError,
)


class AgentRunNotFoundError(LookupError):
    """Raised without revealing whether another principal owns the run."""


class AgentRunConflictError(RuntimeError):
    """Raised when an idempotent run identity conflicts with durable state."""


class AgentRunService:
    """Persist run state and its ordered public events in one transaction."""

    def __init__(
        self,
        repository: AgentRunRepository,
        *,
        state_machine: AgentRunStateMachine | None = None,
    ) -> None:
        self._repository = repository
        self._state_machine = state_machine or AgentRunStateMachine()

    async def create_run(
        self,
        request: AgentRunCreate,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRunRead:
        existing = await self._repository.get_owned_run_by_trace(
            request.trace_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if existing is not None:
            self._validate_replayed_create(existing, request)
            return self.to_public_run(existing)

        now = datetime.now(UTC)
        run = AgentRun(
            id=request.id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=request.conversation_id,
            input_message_id=request.input_message_id,
            trace_id=request.trace_id,
            route=request.route.value,
            status=AgentRunStatus.RUNNING.value,
            context_snapshot=request.context_snapshot,
            plan=request.plan,
            warnings=[],
            fencing_token=request.fencing_token,
            last_sequence=0,
            revision=1,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        await self._repository.add_run(run)
        try:
            await self._repository.flush()
            await self._repository.commit()
        except DuplicateAgentRunError:
            existing = await self._repository.get_owned_run_by_trace(
                request.trace_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
            if existing is None:
                raise AgentRunConflictError("run trace belongs to another principal") from None
            self._validate_replayed_create(existing, request)
            return self.to_public_run(existing)
        return self.to_public_run(run)

    async def get_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRunRead:
        run = await self._repository.get_owned_run(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if run is None:
            raise AgentRunNotFoundError(str(run_id))
        return self.to_public_run(run)

    async def append_event(
        self,
        run_id: uuid.UUID,
        request: RunEventWrite,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunEventRead:
        run = await self._locked_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        if run.fencing_token != fencing_token:
            await self._repository.rollback()
            raise RunFenceConflictError("agent run fencing token is stale")
        if AgentRunStatus(run.status) in TERMINAL_RUN_STATUSES:
            await self._repository.rollback()
            raise RunTerminalConflictError("terminal agent run cannot accept events")
        event = await self._stage_event(run, request)
        try:
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public_event(event)

    async def list_events(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> list[RunEventRead]:
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        run = await self._repository.get_owned_run(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if run is None:
            raise AgentRunNotFoundError(str(run_id))
        events = await self._repository.list_events(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        return [self.to_public_event(event) for event in events]

    async def transition(
        self,
        run_id: uuid.UUID,
        target: AgentRunStatus,
        *,
        tenant_id: str,
        actor_id: str,
        expected_revision: int,
        fencing_token: int,
        warnings: tuple[str, ...] = (),
        public_summary: str | None = None,
        occurred_at: datetime | None = None,
    ) -> AgentRunRead:
        run = await self._locked_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        current = self._lifecycle_state(run)
        try:
            updated = self._state_machine.transition(
                current,
                target,
                expected_revision=expected_revision,
                fencing_token=fencing_token,
                warnings=warnings,
                occurred_at=occurred_at,
            )
            if updated is current:
                result = self.to_public_run(run)
                await self._repository.rollback()
                return result
            run.status = updated.status.value
            run.revision = updated.revision
            run.warnings = list(updated.warnings)
            run.completed_at = updated.completed_at
            event_request = RunEventWrite(
                event_type="run.status",
                status=updated.status.value,
                public_summary=public_summary,
            )
            await self._stage_event(run, event_request, occurred_at=occurred_at)
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public_run(run)

    async def cancel_owned(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        occurred_at: datetime | None = None,
    ) -> AgentRunRead:
        """Cancel with the stored fence without exposing that worker token to clients."""

        run = await self._locked_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        current = self._lifecycle_state(run)
        try:
            updated = self._state_machine.transition(
                current,
                AgentRunStatus.CANCELLED,
                expected_revision=current.revision,
                fencing_token=current.fencing_token,
                occurred_at=occurred_at,
            )
            if updated is current:
                result = self.to_public_run(run)
                await self._repository.rollback()
                return result
            run.status = updated.status.value
            run.revision = updated.revision
            run.warnings = list(updated.warnings)
            run.completed_at = updated.completed_at
            await self._stage_event(
                run,
                RunEventWrite(
                    event_type="run.status",
                    status=AgentRunStatus.CANCELLED.value,
                    public_summary="已停止生成",
                ),
                occurred_at=occurred_at,
            )
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public_run(run)

    async def interrupt_owned(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        occurred_at: datetime | None = None,
    ) -> AgentRunRead:
        """Mark a lease-orphaned unfinished run as recoverable interrupted state."""

        run = await self._locked_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        current = self._lifecycle_state(run)
        try:
            updated = self._state_machine.transition(
                current,
                AgentRunStatus.INTERRUPTED,
                expected_revision=current.revision,
                fencing_token=current.fencing_token,
                occurred_at=occurred_at,
            )
            run.status = updated.status.value
            run.revision = updated.revision
            run.warnings = list(updated.warnings)
            run.completed_at = updated.completed_at
            await self._stage_event(
                run,
                RunEventWrite(
                    event_type="run.status",
                    status=AgentRunStatus.INTERRUPTED.value,
                    public_summary="服务中断, 可稍后恢复",
                ),
                occurred_at=occurred_at,
            )
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public_run(run)

    async def _locked_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun:
        run = await self._repository.get_owned_run(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if run is None:
            raise AgentRunNotFoundError(str(run_id))
        return run

    async def _stage_event(
        self,
        run: AgentRun,
        request: RunEventWrite,
        *,
        occurred_at: datetime | None = None,
    ) -> RunEvent:
        run.last_sequence += 1
        event = RunEvent(
            run_id=run.id,
            sequence=run.last_sequence,
            event_type=request.event_type,
            status=request.status,
            public_summary=request.public_summary,
            payload=request.payload,
            duration_ms=request.duration_ms,
            created_at=occurred_at or datetime.now(UTC),
        )
        await self._repository.add_event(event)
        return event

    @staticmethod
    def _lifecycle_state(run: AgentRun) -> RunLifecycleState:
        return RunLifecycleState(
            run_id=run.id,
            status=AgentRunStatus(run.status),
            revision=run.revision,
            fencing_token=run.fencing_token,
            warnings=tuple(run.warnings),
            completed_at=run.completed_at,
        )

    @staticmethod
    def _validate_replayed_create(run: AgentRun, request: AgentRunCreate) -> None:
        if (
            run.conversation_id != request.conversation_id
            or run.input_message_id != request.input_message_id
            or run.route != request.route.value
            or run.context_snapshot != request.context_snapshot
            or run.plan != request.plan
            or run.fencing_token != request.fencing_token
        ):
            raise AgentRunConflictError("run trace conflicts with stored identity")

    @staticmethod
    def to_public_run(run: AgentRun) -> AgentRunRead:
        return AgentRunRead(
            id=run.id,
            conversation_id=run.conversation_id,
            input_message_id=run.input_message_id,
            trace_id=run.trace_id,
            route=RouteKind(run.route),
            status=AgentRunStatus(run.status),
            current_answer_version_id=run.current_answer_version_id,
            warnings=tuple(run.warnings),
            last_sequence=run.last_sequence,
            revision=run.revision,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )

    @staticmethod
    def to_public_event(event: RunEvent) -> RunEventRead:
        return RunEventRead(
            run_id=event.run_id,
            sequence=event.sequence,
            event_type=event.event_type,
            status=event.status,
            public_summary=event.public_summary,
            payload=event.payload,
            duration_ms=event.duration_ms,
            created_at=event.created_at,
        )
