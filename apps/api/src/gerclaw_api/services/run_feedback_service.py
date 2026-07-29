"""Run feedback current-state reconciliation with append-only revisions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from gerclaw_api.database.models import RunFeedbackRevision, RunFeedbackState
from gerclaw_api.domain.run_schemas import (
    FeedbackReconcileRequest,
    FeedbackStateRead,
)
from gerclaw_api.repositories.run_feedback import RunFeedbackRepository


class RunFeedbackNotFoundError(LookupError):
    """Raised without revealing whether another principal owns the run."""


class RunFeedbackConflictError(RuntimeError):
    """Raised when the caller's observed feedback revision is stale."""


class RunFeedbackService:
    """Reconcile one current value and emit only accepted value changes."""

    def __init__(self, repository: RunFeedbackRepository) -> None:
        self._repository = repository

    async def get(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> FeedbackStateRead | None:
        run = await self._repository.get_owned_run_for_update(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if run is None:
            raise RunFeedbackNotFoundError(str(run_id))
        state = await self._repository.get_state(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        result = self.to_public(state) if state is not None else None
        await self._repository.rollback()
        return result

    async def reconcile(
        self,
        run_id: uuid.UUID,
        request: FeedbackReconcileRequest,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> FeedbackStateRead:
        run = await self._repository.get_owned_run_for_update(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if run is None:
            raise RunFeedbackNotFoundError(str(run_id))
        state = await self._repository.get_state(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        current_revision = state.revision if state is not None else 0
        if request.expected_revision != current_revision:
            await self._repository.rollback()
            raise RunFeedbackConflictError("feedback revision changed")
        if state is not None and state.value == request.value:
            result = self.to_public(state)
            await self._repository.rollback()
            return result

        now = datetime.now(UTC)
        if state is None:
            state = RunFeedbackState(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                actor_id=actor_id,
                run_id=run.id,
                value=request.value,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            await self._repository.add_state(state)
            # The audit row references state, so materialize it first.
            await self._repository.flush()
        else:
            state.value = request.value
            state.revision += 1
            state.updated_at = now
        revision = RunFeedbackRevision(
            feedback_state_id=state.id,
            value=state.value,
            revision=state.revision,
            created_at=now,
        )
        try:
            await self._repository.add_revision(revision)
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public(state)

    @staticmethod
    def to_public(state: RunFeedbackState) -> FeedbackStateRead:
        return FeedbackStateRead.model_validate(
            {
                "run_id": state.run_id,
                "value": state.value,
                "revision": state.revision,
                "updated_at": state.updated_at,
            }
        )
