"""Feedback reconciliation idempotency, audit, and owner-scope tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import (
    AgentRun,
    RunFeedbackRevision,
    RunFeedbackState,
)
from gerclaw_api.domain.run_schemas import FeedbackReconcileRequest
from gerclaw_api.services.run_feedback_service import (
    RunFeedbackConflictError,
    RunFeedbackNotFoundError,
    RunFeedbackService,
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_unit0001"


class _Repository:
    def __init__(self, run: AgentRun) -> None:
        self.run = run
        self.state: RunFeedbackState | None = None
        self.revisions: list[RunFeedbackRevision] = []
        self.commits = 0
        self.rollbacks = 0

    async def get_owned_run_for_update(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        if (
            self.run.id == run_id
            and self.run.tenant_id == tenant_id
            and self.run.actor_id == actor_id
        ):
            return self.run
        return None

    async def get_state(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunFeedbackState | None:
        state = self.state
        if (
            state is None
            or state.run_id != run_id
            or state.tenant_id != tenant_id
            or state.actor_id != actor_id
        ):
            return None
        return state

    async def add_state(self, state: RunFeedbackState) -> None:
        self.state = state

    async def add_revision(self, revision: RunFeedbackRevision) -> None:
        revision.id = len(self.revisions) + 1
        self.revisions.append(revision)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _run() -> AgentRun:
    now = datetime.now(UTC)
    return AgentRun(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        actor_id=ACTOR,
        conversation_id=uuid.uuid4(),
        input_message_id=uuid.uuid4(),
        trace_id="trace_feedback_unit",
        route="standard",
        status="completed",
        context_snapshot={},
        plan={},
        warnings=[],
        current_answer_version_id=None,
        fencing_token=9,
        last_sequence=1,
        revision=2,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_reconcile_tracks_current_value_and_append_only_revisions() -> None:
    repository = _Repository(_run())
    service = RunFeedbackService(repository)
    liked = await service.reconcile(
        repository.run.id,
        FeedbackReconcileRequest(value=1, expected_revision=0),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    disliked = await service.reconcile(
        repository.run.id,
        FeedbackReconcileRequest(value=-1, expected_revision=1),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    cleared = await service.reconcile(
        repository.run.id,
        FeedbackReconcileRequest(value=0, expected_revision=2),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert (liked.revision, disliked.revision, cleared.revision) == (1, 2, 3)
    assert [item.value for item in repository.revisions] == [1, -1, 0]
    assert await service.get(
        repository.run.id, tenant_id=TENANT, actor_id=ACTOR
    ) == cleared


@pytest.mark.asyncio
async def test_duplicate_value_does_not_duplicate_evolution_signal() -> None:
    repository = _Repository(_run())
    service = RunFeedbackService(repository)
    first = await service.reconcile(
        repository.run.id,
        FeedbackReconcileRequest(value=1, expected_revision=0),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    replay = await service.reconcile(
        repository.run.id,
        FeedbackReconcileRequest(value=1, expected_revision=1),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert replay == first
    assert len(repository.revisions) == 1
    assert repository.commits == 1


@pytest.mark.asyncio
async def test_stale_revision_is_rejected_without_audit_write() -> None:
    repository = _Repository(_run())
    service = RunFeedbackService(repository)
    await service.reconcile(
        repository.run.id,
        FeedbackReconcileRequest(value=1, expected_revision=0),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    with pytest.raises(RunFeedbackConflictError):
        await service.reconcile(
            repository.run.id,
            FeedbackReconcileRequest(value=-1, expected_revision=0),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )

    assert len(repository.revisions) == 1
    assert repository.rollbacks == 1


@pytest.mark.asyncio
async def test_other_actor_cannot_observe_or_reconcile_feedback() -> None:
    repository = _Repository(_run())
    service = RunFeedbackService(repository)
    with pytest.raises(RunFeedbackNotFoundError):
        await service.get(
            repository.run.id,
            tenant_id=TENANT,
            actor_id="usr_other",
        )
    with pytest.raises(RunFeedbackNotFoundError):
        await service.reconcile(
            repository.run.id,
            FeedbackReconcileRequest(value=1, expected_revision=0),
            tenant_id=TENANT,
            actor_id="usr_other",
        )
