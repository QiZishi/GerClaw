"""Fenced, exactly-once lifecycle for execution-time user directives."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime

from gerclaw_api.database.models import AgentRun, Message, RunDirective
from gerclaw_api.domain.run_schemas import (
    TERMINAL_RUN_STATUSES,
    AgentRunStatus,
    RunDirectiveClaim,
    RunDirectiveCreate,
    RunDirectiveMode,
    RunDirectiveRead,
    RunDirectiveStatus,
    RunQueuedDirectiveCreate,
)
from gerclaw_api.repositories.run_directive import (
    DuplicateRunDirectiveError,
    RunDirectiveRepository,
)


class RunDirectiveNotFoundError(LookupError):
    """Raised without disclosing whether another actor owns the directive."""


class RunDirectiveConflictError(RuntimeError):
    """Raised when a replay, claim, or state transition is incompatible."""


class RunDirectiveService:
    """Keep user steer/queue instructions durable without publishing bad attempts."""

    def __init__(self, repository: RunDirectiveRepository) -> None:
        self._repository = repository

    async def create(
        self,
        run_id: uuid.UUID,
        request: RunDirectiveCreate,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirectiveRead:
        existing = await self._repository.get_owned_by_idempotency(
            request.idempotency_key,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if existing is not None:
            self._validate_replay(existing, run_id, request)
            return self.to_public(existing)

        run = await self._owned_run(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        conversation = await self._repository.lock_conversation(
            run.conversation_id,
            tenant_id=tenant_id,
        )
        if conversation is None:
            await self._repository.rollback()
            raise RunDirectiveNotFoundError(str(run.conversation_id))
        conversation.last_directive_sequence += 1
        now = datetime.now(UTC)
        run_status = AgentRunStatus(run.status)
        directive = RunDirective(
            id=request.id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=run.conversation_id,
            target_run_id=run.id,
            successor_run_id=None,
            sequence=conversation.last_directive_sequence,
            mode=request.mode.value,
            status=(
                RunDirectiveStatus.PENDING_NEXT_RUN.value
                if run_status in TERMINAL_RUN_STATUSES
                else RunDirectiveStatus.PENDING.value
            ),
            instruction=request.instruction,
            idempotency_key=request.idempotency_key,
            claimed_by_fencing_token=None,
            claim_boundary_id=None,
            revision=1,
            claimed_at=None,
            applied_at=None,
            cancelled_at=None,
            created_at=now,
            updated_at=now,
        )
        await self._repository.add(directive)
        try:
            await self._repository.flush()
            await self._repository.commit()
        except DuplicateRunDirectiveError:
            existing = await self._repository.get_owned_by_idempotency(
                request.idempotency_key,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
            if existing is None:
                raise RunDirectiveConflictError(
                    "directive identity belongs to another principal"
                ) from None
            self._validate_replay(existing, run_id, request)
            return self.to_public(existing)
        return self.to_public(directive)

    async def queue_for_trace(
        self,
        trace_id: str,
        request: RunQueuedDirectiveCreate,
        *,
        tenant_id: str,
        actor_id: str,
        wait_seconds: float,
        poll_interval_seconds: float,
    ) -> RunDirectiveRead:
        if wait_seconds < 0 or poll_interval_seconds <= 0:
            raise ValueError("directive trace wait values are invalid")
        deadline = time.monotonic() + wait_seconds
        while True:
            run = await self._repository.get_owned_run_by_trace(
                trace_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
            if run is not None:
                break
            await self._repository.rollback()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RunDirectiveNotFoundError(trace_id)
            await asyncio.sleep(min(poll_interval_seconds, remaining))
        return await self.create(
            run.id,
            RunDirectiveCreate(
                mode=RunDirectiveMode.QUEUE_FOR_NEXT_BOUNDARY,
                instruction=request.instruction,
                idempotency_key=request.idempotency_key,
            ),
            tenant_id=tenant_id,
            actor_id=actor_id,
        )

    async def list_for_trace(
        self,
        trace_id: str,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int = 100,
    ) -> tuple[RunDirectiveRead, ...]:
        run = await self._repository.get_owned_run_by_trace(
            trace_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if run is None:
            await self._repository.rollback()
            raise RunDirectiveNotFoundError(trace_id)
        return await self.list_for_run(
            run.id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            limit=limit,
        )

    async def list_for_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int = 100,
    ) -> tuple[RunDirectiveRead, ...]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        await self._owned_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        directives = await self._repository.list_for_run(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            limit=limit,
        )
        return tuple(self.to_public(item) for item in directives)

    async def list_applied_for_execution(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> tuple[RunDirectiveRead, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        await self._owned_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        directives = await self._repository.list_applied_for_execution(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        return tuple(self.to_public(item) for item in directives)

    async def list_recent_applied_for_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        directives = await self._repository.list_recent_applied_for_conversation(
            conversation_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            limit=limit,
        )
        return tuple(self.to_public(item) for item in directives)

    async def cancel_unclaimed(
        self,
        directive_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirectiveRead:
        probe = await self._owned_directive(
            directive_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        execution_run_id = probe.successor_run_id or probe.target_run_id
        await self._owned_run(
            execution_run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        directive = await self._owned_directive(
            directive_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if (directive.successor_run_id or directive.target_run_id) != execution_run_id:
            await self._repository.rollback()
            raise RunDirectiveConflictError("directive execution target changed")
        status = RunDirectiveStatus(directive.status)
        if status is RunDirectiveStatus.CANCELLED:
            result = self.to_public(directive)
            await self._repository.rollback()
            return result
        if status not in {
            RunDirectiveStatus.PENDING,
            RunDirectiveStatus.PENDING_NEXT_RUN,
        }:
            await self._repository.rollback()
            raise RunDirectiveConflictError("claimed or applied directive cannot be cancelled")
        directive.status = RunDirectiveStatus.CANCELLED.value
        directive.cancelled_at = datetime.now(UTC)
        directive.revision += 1
        await self._commit()
        return self.to_public(directive)

    async def bind_to_successor(
        self,
        directive_id: uuid.UUID,
        successor_run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirectiveRead:
        probe = await self._owned_directive(
            directive_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        locked_runs: dict[uuid.UUID, AgentRun] = {}
        for run_id in sorted(
            {probe.successor_run_id or probe.target_run_id, successor_run_id},
            key=str,
        ):
            locked_runs[run_id] = await self._owned_run(
                run_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                for_update=True,
            )
        directive = await self._owned_directive(
            directive_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if (
            directive.successor_run_id or directive.target_run_id
        ) not in locked_runs:
            await self._repository.rollback()
            raise RunDirectiveConflictError("directive execution target changed")
        successor = locked_runs[successor_run_id]
        if successor.conversation_id != directive.conversation_id:
            await self._repository.rollback()
            raise RunDirectiveConflictError("successor run belongs to another conversation")
        if directive.successor_run_id is not None:
            if directive.successor_run_id == successor_run_id:
                result = self.to_public(directive)
                await self._repository.rollback()
                return result
            await self._repository.rollback()
            raise RunDirectiveConflictError("directive already has a different successor")
        if RunDirectiveStatus(directive.status) not in {
            RunDirectiveStatus.PENDING,
            RunDirectiveStatus.PENDING_NEXT_RUN,
        }:
            await self._repository.rollback()
            raise RunDirectiveConflictError("only unclaimed directives can move to a successor")
        directive.successor_run_id = successor_run_id
        directive.status = RunDirectiveStatus.PENDING.value
        directive.revision += 1
        await self._commit()
        return self.to_public(directive)

    async def claim_next(
        self,
        run_id: uuid.UUID,
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirectiveRead | None:
        claimed = await self.claim_batch(
            run_id,
            claim,
            tenant_id=tenant_id,
            actor_id=actor_id,
            limit=1,
        )
        return claimed[0] if claimed else None

    async def claim_batch(
        self,
        run_id: uuid.UUID,
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        run = await self._owned_run(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if AgentRunStatus(run.status) is not AgentRunStatus.RUNNING:
            await self._repository.rollback()
            raise RunDirectiveConflictError("only a running run can claim directives")
        if run.fencing_token != claim.fencing_token:
            await self._repository.rollback()
            raise RunDirectiveConflictError("directive claim fencing token is stale")
        directives = await self._repository.list_consumable(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            limit=limit,
        )
        if not directives:
            await self._repository.rollback()
            return ()
        changed = False
        now = datetime.now(UTC)
        for directive in directives:
            if RunDirectiveStatus(directive.status) is RunDirectiveStatus.CLAIMED:
                if (
                    directive.claimed_by_fencing_token == claim.fencing_token
                    and directive.claim_boundary_id == claim.boundary_id
                ):
                    continue
                if (directive.claimed_by_fencing_token or 0) >= claim.fencing_token:
                    await self._repository.rollback()
                    raise RunDirectiveConflictError(
                        "directive is owned by another boundary"
                    )
            directive.status = RunDirectiveStatus.CLAIMED.value
            directive.claimed_by_fencing_token = claim.fencing_token
            directive.claim_boundary_id = claim.boundary_id
            directive.claimed_at = now
            directive.revision += 1
            changed = True
        if changed:
            await self._commit()
        else:
            await self._repository.rollback()
        return tuple(self.to_public(item) for item in directives)

    async def mark_applied(
        self,
        directive_id: uuid.UUID,
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirectiveRead:
        probe = await self._owned_directive(
            directive_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        execution_run_id = probe.successor_run_id or probe.target_run_id
        applied = await self.mark_many_applied(
            execution_run_id,
            (directive_id,),
            claim,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        return applied[0]

    async def mark_many_applied(
        self,
        run_id: uuid.UUID,
        directive_ids: tuple[uuid.UUID, ...],
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> tuple[RunDirectiveRead, ...]:
        if not directive_ids or len(directive_ids) > 100:
            raise ValueError("directive_ids must contain between 1 and 100 items")
        if len(set(directive_ids)) != len(directive_ids):
            raise ValueError("directive_ids must be unique")
        run = await self._owned_run(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if AgentRunStatus(run.status) is not AgentRunStatus.RUNNING:
            await self._repository.rollback()
            raise RunDirectiveConflictError("terminal run cannot apply a directive")
        if run.fencing_token != claim.fencing_token:
            await self._repository.rollback()
            raise RunDirectiveConflictError("directive apply fencing token is stale")
        directives = [
            await self._owned_directive(
                directive_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                for_update=True,
            )
            for directive_id in directive_ids
        ]
        now = datetime.now(UTC)
        changed = False
        for directive in directives:
            execution_run_id = directive.successor_run_id or directive.target_run_id
            if execution_run_id != run_id:
                await self._repository.rollback()
                raise RunDirectiveConflictError("directive execution target changed")
            if (
                directive.claimed_by_fencing_token != claim.fencing_token
                or directive.claim_boundary_id != claim.boundary_id
            ):
                await self._repository.rollback()
                raise RunDirectiveConflictError("directive claim identity does not match")
            status = RunDirectiveStatus(directive.status)
            if status is RunDirectiveStatus.APPLIED:
                changed = await self._ensure_message_projection(directive) or changed
                continue
            if status is not RunDirectiveStatus.CLAIMED:
                await self._repository.rollback()
                raise RunDirectiveConflictError("only a claimed directive can be applied")
            directive.status = RunDirectiveStatus.APPLIED.value
            directive.applied_at = now
            directive.revision += 1
            changed = True
            await self._ensure_message_projection(directive)
        if changed:
            await self._commit()
        else:
            await self._repository.rollback()
        return tuple(self.to_public(item) for item in directives)

    async def _ensure_message_projection(self, directive: RunDirective) -> bool:
        trace_id = f"directive_{directive.id.hex}"
        existing = await self._repository.get_projected_message(
            trace_id,
            tenant_id=directive.tenant_id,
        )
        expected_content = [{"type": "text", "text": directive.instruction}]
        if existing is not None:
            if (
                existing.session_id != directive.conversation_id
                or existing.content != expected_content
            ):
                await self._repository.rollback()
                raise RunDirectiveConflictError("directive message projection conflicts")
            return False
        await self._repository.add_projected_message(
            Message(
                id=uuid.uuid4(),
                tenant_id=directive.tenant_id,
                session_id=directive.conversation_id,
                trace_id=trace_id,
                role="user",
                content=expected_content,
                message_metadata={
                    "channel": "runtime_directive",
                    "directive_id": str(directive.id),
                    "mode": directive.mode,
                    "sequence": directive.sequence,
                },
            )
        )
        return True

    async def _owned_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> AgentRun:
        run = await self._repository.get_owned_run(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=for_update,
        )
        if run is None:
            await self._repository.rollback()
            raise RunDirectiveNotFoundError(str(run_id))
        return run

    async def _owned_directive(
        self,
        directive_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> RunDirective:
        directive = await self._repository.get_owned(
            directive_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=for_update,
        )
        if directive is None:
            await self._repository.rollback()
            raise RunDirectiveNotFoundError(str(directive_id))
        return directive

    async def _commit(self) -> None:
        try:
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise

    @staticmethod
    def _validate_replay(
        directive: RunDirective,
        run_id: uuid.UUID,
        request: RunDirectiveCreate,
    ) -> None:
        if (
            directive.target_run_id != run_id
            or directive.mode != request.mode.value
            or directive.instruction != request.instruction
        ):
            raise RunDirectiveConflictError(
                "idempotency key was already used for a different directive"
            )

    @staticmethod
    def to_public(directive: RunDirective) -> RunDirectiveRead:
        return RunDirectiveRead(
            id=directive.id,
            conversation_id=directive.conversation_id,
            target_run_id=directive.target_run_id,
            successor_run_id=directive.successor_run_id,
            sequence=directive.sequence,
            mode=RunDirectiveMode(directive.mode),
            status=RunDirectiveStatus(directive.status),
            instruction=directive.instruction,
            idempotency_key=directive.idempotency_key,
            claimed_by_fencing_token=directive.claimed_by_fencing_token,
            claim_boundary_id=directive.claim_boundary_id,
            revision=directive.revision,
            created_at=directive.created_at,
            claimed_at=directive.claimed_at,
            applied_at=directive.applied_at,
            cancelled_at=directive.cancelled_at,
        )
