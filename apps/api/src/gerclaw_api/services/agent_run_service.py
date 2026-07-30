"""Transactional source of truth for Agent runs and public replay events."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from gerclaw_api.database.models import (
    AgentRun,
    AgentRunAttempt,
    AgentRunAttemptEvent,
    AgentRunPlanNodeEvent,
    RunEvent,
)
from gerclaw_api.domain.run_schemas import (
    RUN_EVENT_CLOSED_STATUSES,
    TERMINAL_RUN_STATUSES,
    AgentRunCreate,
    AgentRunRead,
    AgentRunStatus,
    RunAttemptCreate,
    RunAttemptRead,
    RunAttemptStatus,
    RunEventRead,
    RunEventWrite,
    ValidationFeedback,
)
from gerclaw_api.modules.agent_harness.context_snapshot import PersistedRunPlan
from gerclaw_api.modules.agent_harness.planning import (
    PlanExecutionSnapshot,
    PlanningError,
    PlanNodeStatus,
    validate_plan_execution_transition,
)
from gerclaw_api.modules.agent_harness.plugin_runtime import CapabilityResult
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


class RunAttemptConflictError(RuntimeError):
    """Raised when a private attempt loses fencing or current-pointer CAS."""


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
            interrupted_at=None,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        await self._repository.add_run(run)
        try:
            await self._repository.flush()
            await self._repository.bind_deferred_directives(
                run.id,
                run.conversation_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
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

    async def adopt_for_worker(
        self,
        request: AgentRunCreate,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRunRead:
        """Create a Run or fence an orphaned same-Trace Run to the new lease owner."""

        existing = await self._repository.get_owned_run_by_trace(
            request.trace_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if existing is None:
            return await self.create_run(
                request,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
        self._validate_replayed_create(
            existing,
            request,
            compare_context=False,
            compare_fence=False,
        )
        current = self._lifecycle_state(existing)
        if (
            current.status is AgentRunStatus.RUNNING
            and current.fencing_token == request.fencing_token
        ):
            result = self.to_public_run(existing)
            await self._repository.rollback()
            return result
        if request.fencing_token <= current.fencing_token:
            await self._repository.rollback()
            raise AgentRunConflictError("run adoption fencing token is stale")
        if current.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.COMPLETED_WITH_WARNINGS,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }:
            await self._repository.rollback()
            raise AgentRunConflictError("terminal run cannot be adopted")
        try:
            if current.status in {
                AgentRunStatus.INTERRUPTED,
                AgentRunStatus.WAITING_FOR_USER,
            }:
                updated = self._state_machine.transition(
                    current,
                    AgentRunStatus.RUNNING,
                    expected_revision=current.revision,
                    fencing_token=current.fencing_token,
                )
                existing.status = updated.status.value
                existing.interrupted_at = updated.interrupted_at
                existing.completed_at = updated.completed_at
            existing.fencing_token = request.fencing_token
            existing.revision += 1
            existing.warnings = []
            await self._stage_event(
                existing,
                RunEventWrite(
                    event_type="run.resumed",
                    status=AgentRunStatus.RUNNING.value,
                    public_summary="已恢复执行",
                ),
            )
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public_run(existing)

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
        if AgentRunStatus(run.status) in RUN_EVENT_CLOSED_STATUSES:
            await self._repository.rollback()
            raise RunTerminalConflictError("closed agent run cannot accept events")
        event = await self._stage_event(run, request)
        try:
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public_event(event)

    async def begin_attempt(
        self,
        run_id: uuid.UUID,
        request: RunAttemptCreate,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        """Create a private staging area without changing the public projection."""

        run = await self._locked_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        if run.fencing_token != fencing_token:
            await self._repository.rollback()
            raise RunFenceConflictError("agent run fencing token is stale")
        if AgentRunStatus(run.status) in RUN_EVENT_CLOSED_STATUSES:
            await self._repository.rollback()
            raise RunTerminalConflictError("closed agent run cannot start an attempt")
        if run.current_valid_attempt_id != request.expected_current_attempt_id:
            await self._repository.rollback()
            raise RunAttemptConflictError("current valid attempt changed")
        attempt_number = await self._repository.next_attempt_number(
            run_id,
            request.public_operation_id,
        )
        now = datetime.now(UTC)
        attempt = AgentRunAttempt(
            id=request.id,
            run_id=run_id,
            public_operation_id=request.public_operation_id,
            attempt=attempt_number,
            step_id=request.step_id,
            checkpoint_id=request.checkpoint_id,
            fencing_token=fencing_token,
            status=RunAttemptStatus.STAGING.value,
            expected_current_attempt_id=request.expected_current_attempt_id,
            error_code=None,
            validation_feedback=None,
            created_at=now,
            completed_at=None,
        )
        await self._repository.add_attempt(attempt)
        try:
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_private_attempt(attempt)

    async def update_plan_execution(
        self,
        run_id: uuid.UUID,
        updated: PlanExecutionSnapshot,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        capability_result: CapabilityResult | None = None,
    ) -> PlanExecutionSnapshot:
        """Persist exactly one fenced PlanNode transition and its current snapshot."""

        run = await self._locked_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        if run.fencing_token != fencing_token:
            await self._repository.rollback()
            raise RunFenceConflictError("agent run fencing token is stale")
        if AgentRunStatus(run.status) is not AgentRunStatus.RUNNING:
            await self._repository.rollback()
            raise RunTerminalConflictError("non-running agent run cannot advance its plan")
        try:
            plan = PersistedRunPlan.model_validate(run.plan)
            current = plan.effective_plan_execution()
            transitions = validate_plan_execution_transition(
                plan.dynamic_plan,
                current,
                updated,
            )
            capability_results = plan.capability_results
            if capability_result is not None:
                if len(transitions) != 1:
                    raise PlanningError("PLAN_CAPABILITY_RESULT_TRANSITION_INVALID")
                transition = transitions[0]
                node = next(
                    item
                    for item in plan.dynamic_plan.nodes
                    if item.node_id == transition.node_id
                )
                if (
                    transition.status is not PlanNodeStatus.COMPLETED
                    or node.capability != capability_result.capability_id
                    or capability_result.capability_id
                    not in plan.capability_selection.ids
                    or any(
                        item.capability_id == capability_result.capability_id
                        for item in capability_results
                    )
                ):
                    raise PlanningError("PLAN_CAPABILITY_RESULT_TRANSITION_INVALID")
                capability_results = (*capability_results, capability_result)
            persisted_plan = plan.model_copy(
                update={
                    "plan_execution": updated,
                    "capability_results": capability_results,
                }
            )
        except (PlanningError, ValueError) as error:
            await self._repository.rollback()
            raise AgentRunConflictError("stored run plan is invalid") from error
        run.plan = persisted_plan.model_dump(mode="json")
        run.revision += 1
        transitioned_at = datetime.now(UTC)
        for transition in transitions:
            await self._repository.add_plan_node_event(
                AgentRunPlanNodeEvent(
                    run_id=run.id,
                    node_id=transition.node_id,
                    attempt=transition.attempt,
                    status=transition.status.value,
                    error_code=transition.error_code,
                    fallback_for_node_id=transition.fallback_for_node_id,
                    fencing_token=fencing_token,
                    created_at=transitioned_at,
                )
            )
        try:
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return updated

    async def stage_attempt_event(
        self,
        attempt_id: uuid.UUID,
        request: RunEventWrite,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        """Persist one encrypted private event; no public sequence is allocated."""

        attempt = await self._repository.get_attempt(attempt_id, for_update=True)
        if attempt is None:
            raise AgentRunNotFoundError(str(attempt_id))
        run = await self._locked_run(
            attempt.run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        self._assert_staging_attempt(run, attempt, fencing_token=fencing_token)
        staged = await self._repository.list_attempt_events(attempt.id)
        event = AgentRunAttemptEvent(
            attempt_id=attempt.id,
            ordinal=len(staged) + 1,
            event_type=request.event_type,
            status=request.status,
            public_summary=request.public_summary,
            payload=request.payload,
            duration_ms=request.duration_ms,
            created_at=datetime.now(UTC),
        )
        await self._repository.add_attempt_event(event)
        try:
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_private_attempt(attempt)

    async def reject_attempt(
        self,
        attempt_id: uuid.UUID,
        feedback: ValidationFeedback,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        """Retain content-free failure metadata while keeping staged output private."""

        attempt = await self._repository.get_attempt(attempt_id, for_update=True)
        if attempt is None:
            raise AgentRunNotFoundError(str(attempt_id))
        run = await self._locked_run(
            attempt.run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        self._assert_staging_attempt(run, attempt, fencing_token=fencing_token)
        if feedback.attempt != attempt.attempt or feedback.checkpoint_id != attempt.checkpoint_id:
            await self._repository.rollback()
            raise RunAttemptConflictError("validation feedback does not match attempt")
        attempt.status = RunAttemptStatus.REJECTED.value
        attempt.error_code = feedback.error_code
        attempt.validation_feedback = feedback.model_dump(mode="json")
        attempt.completed_at = datetime.now(UTC)
        try:
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_private_attempt(attempt)

    async def commit_attempt(
        self,
        attempt_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        target: AgentRunStatus,
        terminal_event: RunEventWrite,
        warnings: tuple[str, ...] = (),
        commit: bool = True,
    ) -> tuple[AgentRunRead, tuple[RunEventRead, ...]]:
        """CAS-promote a validated attempt and its public events in one transaction."""

        attempt = await self._repository.get_attempt(attempt_id, for_update=True)
        if attempt is None:
            raise AgentRunNotFoundError(str(attempt_id))
        run = await self._locked_run(
            attempt.run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        self._assert_staging_attempt(run, attempt, fencing_token=fencing_token)
        if run.current_valid_attempt_id != attempt.expected_current_attempt_id:
            await self._repository.rollback()
            raise RunAttemptConflictError("current valid attempt changed")
        current = self._lifecycle_state(run)
        updated = self._state_machine.transition(
            current,
            target,
            expected_revision=current.revision,
            fencing_token=fencing_token,
            warnings=warnings,
        )
        staged = await self._repository.list_attempt_events(attempt.id)
        private_terminal = AgentRunAttemptEvent(
            attempt_id=attempt.id,
            ordinal=len(staged) + 1,
            event_type=terminal_event.event_type,
            status=terminal_event.status,
            public_summary=terminal_event.public_summary,
            payload=terminal_event.payload,
            duration_ms=terminal_event.duration_ms,
            created_at=datetime.now(UTC),
        )
        await self._repository.add_attempt_event(private_terminal)
        staged.append(private_terminal)
        public_events: list[RunEvent] = []
        for private_event in staged:
            public_event = await self._stage_event(
                run,
                RunEventWrite(
                    event_type=private_event.event_type,
                    status=private_event.status,
                    public_summary=private_event.public_summary,
                    payload=private_event.payload,
                    duration_ms=private_event.duration_ms,
                ),
                occurred_at=private_event.created_at,
            )
            public_events.append(public_event)
        run.status = updated.status.value
        run.revision = updated.revision
        run.warnings = list(updated.warnings)
        run.interrupted_at = updated.interrupted_at
        run.completed_at = updated.completed_at
        run.current_valid_attempt_id = attempt.id
        attempt.status = RunAttemptStatus.VALIDATED.value
        attempt.completed_at = datetime.now(UTC)
        if target in TERMINAL_RUN_STATUSES:
            await self._repository.defer_unconsumed_directives(
                run.id,
                run.conversation_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
        try:
            await self._repository.flush()
            if commit:
                await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return (
            self.to_public_run(run),
            tuple(self.to_public_event(event) for event in public_events),
        )

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
        expected_revision: int | None,
        fencing_token: int,
        warnings: tuple[str, ...] = (),
        public_summary: str | None = None,
        occurred_at: datetime | None = None,
        terminal_event: RunEventWrite | None = None,
        commit: bool = True,
    ) -> AgentRunRead:
        run = await self._locked_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        current = self._lifecycle_state(run)
        try:
            updated = self._state_machine.transition(
                current,
                target,
                expected_revision=(
                    current.revision if expected_revision is None else expected_revision
                ),
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
            run.interrupted_at = updated.interrupted_at
            run.completed_at = updated.completed_at
            if target in {
                AgentRunStatus.FAILED,
                AgentRunStatus.CANCELLED,
                AgentRunStatus.INTERRUPTED,
            }:
                await self._repository.invalidate_staging_attempts(
                    run.id,
                    completed_at=occurred_at or datetime.now(UTC),
                )
            if target in TERMINAL_RUN_STATUSES:
                await self._repository.defer_unconsumed_directives(
                    run.id,
                    run.conversation_id,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                )
            event_request = terminal_event or RunEventWrite(
                event_type="run.status",
                status=updated.status.value,
                public_summary=public_summary,
            )
            await self._stage_event(run, event_request, occurred_at=occurred_at)
            await self._repository.flush()
            if commit:
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
            run.interrupted_at = updated.interrupted_at
            run.completed_at = updated.completed_at
            await self._repository.invalidate_staging_attempts(
                run.id,
                completed_at=occurred_at or datetime.now(UTC),
            )
            await self._repository.defer_unconsumed_directives(
                run.id,
                run.conversation_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
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
        commit: bool = True,
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
            run.interrupted_at = updated.interrupted_at
            run.completed_at = updated.completed_at
            await self._repository.invalidate_staging_attempts(
                run.id,
                completed_at=occurred_at or datetime.now(UTC),
            )
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
            if commit:
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
            interrupted_at=run.interrupted_at,
            completed_at=run.completed_at,
        )

    @staticmethod
    def _validate_replayed_create(
        run: AgentRun,
        request: AgentRunCreate,
        *,
        compare_context: bool = True,
        compare_fence: bool = True,
    ) -> None:
        if (
            run.conversation_id != request.conversation_id
            or run.input_message_id != request.input_message_id
            or run.route != request.route.value
            or (compare_context and run.context_snapshot != request.context_snapshot)
            or AgentRunService._normalized_plan(run.plan)
            != AgentRunService._normalized_plan(request.plan)
            or (compare_fence and run.fencing_token != request.fencing_token)
        ):
            raise AgentRunConflictError("run trace conflicts with stored identity")

    @staticmethod
    def _normalized_plan(plan: Mapping[str, object]) -> dict[str, object]:
        """Treat pre-ID zero-count plans as equivalent to explicit empty lists."""

        normalized = dict(plan)
        for count_key, ids_key in (
            ("loaded_skill_count", "loaded_skill_ids"),
            ("uploaded_document_count", "uploaded_document_ids"),
            ("uploaded_image_count", "uploaded_image_fingerprints"),
        ):
            if normalized.get(count_key) == 0 and ids_key not in normalized:
                normalized[ids_key] = []
        return normalized

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
            current_valid_attempt_id=run.current_valid_attempt_id,
            warnings=tuple(run.warnings),
            last_sequence=run.last_sequence,
            revision=run.revision,
            started_at=run.started_at,
            interrupted_at=run.interrupted_at,
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

    @staticmethod
    def _assert_staging_attempt(
        run: AgentRun,
        attempt: AgentRunAttempt,
        *,
        fencing_token: int,
    ) -> None:
        if run.fencing_token != fencing_token or attempt.fencing_token != fencing_token:
            raise RunFenceConflictError("agent run attempt fencing token is stale")
        if attempt.status != RunAttemptStatus.STAGING.value:
            raise RunAttemptConflictError("attempt is no longer staging")
        if AgentRunStatus(run.status) in RUN_EVENT_CLOSED_STATUSES:
            raise RunTerminalConflictError("closed agent run cannot accept attempt output")

    @staticmethod
    def to_private_attempt(attempt: AgentRunAttempt) -> RunAttemptRead:
        feedback = (
            ValidationFeedback.model_validate(attempt.validation_feedback)
            if attempt.validation_feedback is not None
            else None
        )
        return RunAttemptRead(
            id=attempt.id,
            run_id=attempt.run_id,
            public_operation_id=attempt.public_operation_id,
            attempt=attempt.attempt,
            step_id=attempt.step_id,
            checkpoint_id=attempt.checkpoint_id,
            fencing_token=attempt.fencing_token,
            status=RunAttemptStatus(attempt.status),
            expected_current_attempt_id=attempt.expected_current_attempt_id,
            error_code=attempt.error_code,
            feedback=feedback,
            created_at=attempt.created_at,
            completed_at=attempt.completed_at,
        )
