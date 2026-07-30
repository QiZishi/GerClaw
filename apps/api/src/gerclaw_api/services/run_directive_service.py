"""Fenced, exactly-once lifecycle for execution-time user directives."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from gerclaw_api.database.models import AgentRun, RunDirective
from gerclaw_api.domain.run_schemas import (
    TERMINAL_RUN_STATUSES,
    AgentRunStatus,
    RunDirectiveClaim,
    RunDirectiveCreate,
    RunDirectiveMode,
    RunDirectiveRead,
    RunDirectiveStatus,
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

    async def cancel_unclaimed(
        self,
        directive_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirectiveRead:
        directive = await self._owned_directive(
            directive_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
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
        directive = await self._owned_directive(
            directive_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        successor = await self._owned_run(
            successor_run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
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
        directive = await self._repository.first_consumable(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if directive is None:
            await self._repository.rollback()
            return None
        if RunDirectiveStatus(directive.status) is RunDirectiveStatus.CLAIMED:
            if (
                directive.claimed_by_fencing_token == claim.fencing_token
                and directive.claim_boundary_id == claim.boundary_id
            ):
                result = self.to_public(directive)
                await self._repository.rollback()
                return result
            if (directive.claimed_by_fencing_token or 0) >= claim.fencing_token:
                await self._repository.rollback()
                raise RunDirectiveConflictError("directive is owned by another boundary")
        directive.status = RunDirectiveStatus.CLAIMED.value
        directive.claimed_by_fencing_token = claim.fencing_token
        directive.claim_boundary_id = claim.boundary_id
        directive.claimed_at = datetime.now(UTC)
        directive.revision += 1
        await self._commit()
        return self.to_public(directive)

    async def mark_applied(
        self,
        directive_id: uuid.UUID,
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirectiveRead:
        directive = await self._owned_directive(
            directive_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        execution_run_id = directive.successor_run_id or directive.target_run_id
        run = await self._owned_run(
            execution_run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if run.fencing_token != claim.fencing_token:
            await self._repository.rollback()
            raise RunDirectiveConflictError("directive apply fencing token is stale")
        if (
            directive.claimed_by_fencing_token != claim.fencing_token
            or directive.claim_boundary_id != claim.boundary_id
        ):
            await self._repository.rollback()
            raise RunDirectiveConflictError("directive claim identity does not match")
        status = RunDirectiveStatus(directive.status)
        if status is RunDirectiveStatus.APPLIED:
            result = self.to_public(directive)
            await self._repository.rollback()
            return result
        if status is not RunDirectiveStatus.CLAIMED:
            await self._repository.rollback()
            raise RunDirectiveConflictError("only a claimed directive can be applied")
        directive.status = RunDirectiveStatus.APPLIED.value
        directive.applied_at = datetime.now(UTC)
        directive.revision += 1
        await self._commit()
        return self.to_public(directive)

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
