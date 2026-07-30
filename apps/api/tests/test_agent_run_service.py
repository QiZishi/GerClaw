"""Unit tests for the durable Agent run transaction boundary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import (
    AgentRun,
    AgentRunAttempt,
    AgentRunAttemptEvent,
    RunEvent,
)
from gerclaw_api.domain.run_schemas import (
    AgentRunCreate,
    AgentRunStatus,
    RunAttemptCreate,
    RunAttemptStatus,
    RunEventWrite,
    ValidationFeedback,
)
from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.modules.agent_harness.run_lifecycle import (
    RunFenceConflictError,
    RunRevisionConflictError,
    RunTerminalConflictError,
)
from gerclaw_api.services.agent_run_service import (
    AgentRunConflictError,
    AgentRunNotFoundError,
    AgentRunService,
    RunAttemptConflictError,
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_unit0001"


class _Repository:
    def __init__(self) -> None:
        self.runs: dict[uuid.UUID, AgentRun] = {}
        self.events: list[RunEvent] = []
        self.attempts: dict[uuid.UUID, AgentRunAttempt] = {}
        self.attempt_events: list[AgentRunAttemptEvent] = []
        self.commits = 0
        self.rollbacks = 0
        self.deferred_binding_calls = 0

    async def get_owned_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> AgentRun | None:
        del for_update
        run = self.runs.get(run_id)
        if run is None or run.tenant_id != tenant_id or run.actor_id != actor_id:
            return None
        return run

    async def get_owned_run_by_trace(
        self,
        trace_id: str,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> AgentRun | None:
        del for_update
        return next(
            (
                run
                for run in self.runs.values()
                if run.trace_id == trace_id
                and run.tenant_id == tenant_id
                and run.actor_id == actor_id
            ),
            None,
        )

    async def add_run(self, run: AgentRun) -> None:
        self.runs[run.id] = run

    async def add_event(self, event: RunEvent) -> None:
        event.id = len(self.events) + 1
        self.events.append(event)

    async def get_attempt(
        self,
        attempt_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> AgentRunAttempt | None:
        del for_update
        return self.attempts.get(attempt_id)

    async def next_attempt_number(
        self,
        run_id: uuid.UUID,
        public_operation_id: uuid.UUID,
    ) -> int:
        return (
            max(
                (
                    attempt.attempt
                    for attempt in self.attempts.values()
                    if attempt.run_id == run_id
                    and attempt.public_operation_id == public_operation_id
                ),
                default=0,
            )
            + 1
        )

    async def add_attempt(self, attempt: AgentRunAttempt) -> None:
        self.attempts[attempt.id] = attempt

    async def add_attempt_event(self, event: AgentRunAttemptEvent) -> None:
        event.id = len(self.attempt_events) + 1
        self.attempt_events.append(event)

    async def list_attempt_events(
        self,
        attempt_id: uuid.UUID,
    ) -> list[AgentRunAttemptEvent]:
        return sorted(
            (event for event in self.attempt_events if event.attempt_id == attempt_id),
            key=lambda event: event.ordinal,
        )

    async def invalidate_staging_attempts(
        self,
        run_id: uuid.UUID,
        *,
        completed_at: datetime,
    ) -> None:
        for attempt in self.attempts.values():
            if attempt.run_id == run_id and attempt.status == RunAttemptStatus.STAGING.value:
                attempt.status = RunAttemptStatus.INVALIDATED.value
                attempt.completed_at = completed_at

    async def bind_deferred_directives(
        self,
        run_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> None:
        del run_id, conversation_id, tenant_id, actor_id
        self.deferred_binding_calls += 1

    async def defer_unconsumed_directives(
        self,
        run_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> None:
        del run_id, conversation_id, tenant_id, actor_id

    async def list_events(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int,
        limit: int,
    ) -> list[RunEvent]:
        if await self.get_owned_run(run_id, tenant_id=tenant_id, actor_id=actor_id) is None:
            return []
        return [
            event
            for event in self.events
            if event.run_id == run_id and event.sequence > after_sequence
        ][:limit]

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _request(**updates: object) -> AgentRunCreate:
    values: dict[str, object] = {
        "conversation_id": uuid.uuid4(),
        "input_message_id": uuid.uuid4(),
        "trace_id": "trace_agent_run_unit_0001",
        "route": RouteKind.STANDARD,
        "context_snapshot": {"turn_count": 2},
        "plan": {"nodes": []},
        "fencing_token": 7,
    }
    values.update(updates)
    return AgentRunCreate.model_validate(values)


@pytest.mark.asyncio
async def test_create_is_trace_idempotent_and_rejects_conflicting_replay() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    request = _request()

    created = await service.create_run(request, tenant_id=TENANT, actor_id=ACTOR)
    replay = await service.create_run(
        request.model_copy(update={"id": uuid.uuid4()}),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert replay.id == created.id
    assert len(repository.runs) == 1
    assert repository.commits == 1
    with pytest.raises(AgentRunConflictError):
        await service.create_run(
            request.model_copy(update={"fencing_token": 8}),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_owner_scope_hides_run_and_events_from_other_actor() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)

    with pytest.raises(AgentRunNotFoundError):
        await service.get_run(created.id, tenant_id=TENANT, actor_id="usr_other")
    with pytest.raises(AgentRunNotFoundError):
        await service.list_events(
            created.id,
            tenant_id=TENANT,
            actor_id="usr_other",
        )


@pytest.mark.asyncio
async def test_event_sequence_and_after_sequence_replay_are_monotonic() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)

    first = await service.append_event(
        created.id,
        RunEventWrite(
            event_type="plan.started",
            status="running",
            public_summary="正在整理信息",
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )
    second = await service.append_event(
        created.id,
        RunEventWrite(
            event_type="plan.completed",
            status="succeeded",
            duration_ms=17,
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )
    replay = await service.list_events(
        created.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
        after_sequence=1,
    )

    assert (first.sequence, second.sequence) == (1, 2)
    assert [event.sequence for event in replay] == [2]
    assert (await service.get_run(created.id, tenant_id=TENANT, actor_id=ACTOR)).last_sequence == 2


@pytest.mark.asyncio
async def test_private_attempt_events_are_invisible_until_atomic_promotion() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)
    operation_id = uuid.uuid4()
    attempt = await service.begin_attempt(
        created.id,
        RunAttemptCreate(
            public_operation_id=operation_id,
            step_id="chat.answer",
            checkpoint_id="chat.answer.pre_model.v1",
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )
    await service.stage_attempt_event(
        attempt.id,
        RunEventWrite(
            event_type="text_delta",
            status="running",
            payload={"content": "validated answer"},
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )

    assert (
        await service.list_events(
            created.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        == []
    )
    completed, events = await service.commit_attempt(
        attempt.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
        target=AgentRunStatus.COMPLETED,
        terminal_event=RunEventWrite(event_type="done", status="completed"),
    )

    assert completed.current_valid_attempt_id == attempt.id
    assert [event.event_type for event in events] == ["text_delta", "done"]
    assert [event.sequence for event in events] == [1, 2]
    assert [
        event.event_type
        for event in await service.list_events(
            created.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    ] == ["text_delta", "done"]


@pytest.mark.asyncio
async def test_rejected_attempt_never_enters_public_replay_and_retry_keeps_operation_id() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)
    operation_id = uuid.uuid4()
    first = await service.begin_attempt(
        created.id,
        RunAttemptCreate(
            public_operation_id=operation_id,
            step_id="chat.answer",
            checkpoint_id="chat.answer.pre_model.v1",
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )
    await service.stage_attempt_event(
        first.id,
        RunEventWrite(
            event_type="text_delta",
            status="running",
            payload={"content": "bad hidden output"},
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )
    rejected = await service.reject_attempt(
        first.id,
        ValidationFeedback(
            step_id="chat.answer",
            attempt=1,
            error_code="citation_contract_invalid",
            field_paths=("citations.0.locator",),
            contract_version="citation-v1",
            repair_action="rebind_citation",
            checkpoint_id="chat.answer.pre_model.v1",
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )
    second = await service.begin_attempt(
        created.id,
        RunAttemptCreate(
            public_operation_id=operation_id,
            step_id="chat.answer",
            checkpoint_id="chat.answer.pre_model.v1",
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )

    assert rejected.status is RunAttemptStatus.REJECTED
    assert second.attempt == 2
    assert second.public_operation_id == first.public_operation_id
    assert (
        await service.list_events(
            created.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        == []
    )


@pytest.mark.asyncio
async def test_attempt_cas_and_fence_block_stale_promotion() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)
    attempt = await service.begin_attempt(
        created.id,
        RunAttemptCreate(
            public_operation_id=uuid.uuid4(),
            step_id="chat.answer",
            checkpoint_id="chat.answer.pre_model.v1",
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )

    with pytest.raises(RunFenceConflictError):
        await service.commit_attempt(
            attempt.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=8,
            target=AgentRunStatus.COMPLETED,
            terminal_event=RunEventWrite(event_type="done", status="completed"),
        )
    repository.runs[created.id].current_valid_attempt_id = uuid.uuid4()
    with pytest.raises(RunAttemptConflictError):
        await service.commit_attempt(
            attempt.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=7,
            target=AgentRunStatus.COMPLETED,
            terminal_event=RunEventWrite(event_type="done", status="completed"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "closed_status",
    [AgentRunStatus.COMPLETED, AgentRunStatus.INTERRUPTED],
)
async def test_event_append_rejects_stale_worker_and_closed_run(
    closed_status: AgentRunStatus,
) -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)
    event = RunEventWrite(event_type="plan.started", status="running")

    with pytest.raises(RunFenceConflictError):
        await service.append_event(
            created.id,
            event,
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=6,
        )
    closed = await service.transition(
        created.id,
        closed_status,
        tenant_id=TENANT,
        actor_id=ACTOR,
        expected_revision=1,
        fencing_token=7,
    )
    with pytest.raises(RunTerminalConflictError, match="closed agent run"):
        await service.append_event(
            closed.id,
            event,
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=7,
        )


@pytest.mark.asyncio
async def test_transition_commits_status_and_event_atomically_with_fence_checks() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)
    occurred_at = datetime.now(UTC)

    completed = await service.transition(
        created.id,
        AgentRunStatus.COMPLETED,
        tenant_id=TENANT,
        actor_id=ACTOR,
        expected_revision=1,
        fencing_token=7,
        public_summary="回答已完成",
        occurred_at=occurred_at,
    )

    assert completed.status is AgentRunStatus.COMPLETED
    assert completed.revision == 2
    assert completed.last_sequence == 1
    assert completed.completed_at == occurred_at
    assert repository.events[0].status == AgentRunStatus.COMPLETED.value
    with pytest.raises(RunRevisionConflictError):
        await service.transition(
            created.id,
            AgentRunStatus.CANCELLED,
            tenant_id=TENANT,
            actor_id=ACTOR,
            expected_revision=1,
            fencing_token=7,
        )
    assert repository.rollbacks == 1


@pytest.mark.asyncio
async def test_completed_transition_can_use_one_canonical_terminal_event() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)

    completed = await service.transition(
        created.id,
        AgentRunStatus.COMPLETED,
        tenant_id=TENANT,
        actor_id=ACTOR,
        expected_revision=1,
        fencing_token=7,
        terminal_event=RunEventWrite(
            event_type="done",
            status="completed",
            public_summary="回答已完成",
            payload={"answer_version": 1},
        ),
    )

    assert completed.status is AgentRunStatus.COMPLETED
    assert [(event.event_type, event.status) for event in repository.events] == [
        ("done", "completed")
    ]


@pytest.mark.asyncio
async def test_stale_worker_cannot_write_terminal_and_cancel_replay_is_idempotent() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)

    with pytest.raises(RunFenceConflictError):
        await service.transition(
            created.id,
            AgentRunStatus.COMPLETED,
            tenant_id=TENANT,
            actor_id=ACTOR,
            expected_revision=1,
            fencing_token=6,
        )
    cancelled = await service.transition(
        created.id,
        AgentRunStatus.CANCELLED,
        tenant_id=TENANT,
        actor_id=ACTOR,
        expected_revision=1,
        fencing_token=7,
    )
    replay = await service.transition(
        created.id,
        AgentRunStatus.CANCELLED,
        tenant_id=TENANT,
        actor_id=ACTOR,
        expected_revision=2,
        fencing_token=7,
    )

    assert replay == cancelled
    assert len(repository.events) == 1


@pytest.mark.asyncio
async def test_owner_cancel_uses_stored_fence_and_remains_idempotent() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)
    attempt = await service.begin_attempt(
        created.id,
        RunAttemptCreate(
            public_operation_id=uuid.uuid4(),
            step_id="chat.answer",
            checkpoint_id="chat.answer.pre_model.v1",
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )

    cancelled = await service.cancel_owned(
        created.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    replay = await service.cancel_owned(
        created.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert cancelled.status is AgentRunStatus.CANCELLED
    assert replay == cancelled
    assert [event.status for event in repository.events] == ["cancelled"]
    assert repository.attempts[attempt.id].status == RunAttemptStatus.INVALIDATED.value
    with pytest.raises(AgentRunNotFoundError):
        await service.cancel_owned(
            created.id,
            tenant_id=TENANT,
            actor_id="usr_other",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial_status",
    [AgentRunStatus.RUNNING, AgentRunStatus.WAITING_FOR_USER],
)
async def test_lease_orphan_can_be_marked_interrupted(
    initial_status: AgentRunStatus,
) -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    created = await service.create_run(_request(), tenant_id=TENANT, actor_id=ACTOR)
    repository.runs[created.id].status = initial_status.value
    attempt = await service.begin_attempt(
        created.id,
        RunAttemptCreate(
            public_operation_id=uuid.uuid4(),
            step_id="chat.answer",
            checkpoint_id="chat.answer.pre_model.v1",
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        fencing_token=7,
    )

    interrupted = await service.interrupt_owned(
        created.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert interrupted.status is AgentRunStatus.INTERRUPTED
    assert interrupted.completed_at is None
    assert interrupted.interrupted_at is not None
    assert repository.events[-1].status == "interrupted"
    assert repository.attempts[attempt.id].status == RunAttemptStatus.INVALIDATED.value


@pytest.mark.asyncio
async def test_new_worker_adopts_interrupted_run_and_fences_old_worker() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    request = _request()
    created = await service.create_run(request, tenant_id=TENANT, actor_id=ACTOR)
    interrupted = await service.interrupt_owned(
        created.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    resumed = await service.adopt_for_worker(
        request.model_copy(update={"fencing_token": 8}),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert resumed.id == interrupted.id
    assert resumed.status is AgentRunStatus.RUNNING
    assert resumed.completed_at is None
    assert resumed.interrupted_at == interrupted.interrupted_at
    assert repository.runs[resumed.id].fencing_token == 8
    assert repository.events[-1].event_type == "run.resumed"
    assert repository.deferred_binding_calls == 1
    with pytest.raises(RunFenceConflictError):
        await service.append_event(
            resumed.id,
            RunEventWrite(event_type="text_delta", status="running"),
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=7,
        )


@pytest.mark.asyncio
async def test_adoption_rejects_stale_fence_and_nonrecoverable_terminal() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    request = _request()
    created = await service.create_run(request, tenant_id=TENANT, actor_id=ACTOR)
    with pytest.raises(AgentRunConflictError, match="stale"):
        await service.adopt_for_worker(
            request.model_copy(update={"fencing_token": 6}),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    await service.cancel_owned(created.id, tenant_id=TENANT, actor_id=ACTOR)
    with pytest.raises(AgentRunConflictError, match="terminal"):
        await service.adopt_for_worker(
            request.model_copy(update={"fencing_token": 8}),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_adoption_accepts_legacy_zero_count_plan_without_empty_id_lists() -> None:
    repository = _Repository()
    service = AgentRunService(repository)
    legacy = _request().model_copy(
        update={
            "plan": {
                "loaded_skill_count": 0,
                "uploaded_document_count": 0,
                "uploaded_image_count": 0,
            }
        }
    )
    created = await service.create_run(legacy, tenant_id=TENANT, actor_id=ACTOR)
    await service.interrupt_owned(created.id, tenant_id=TENANT, actor_id=ACTOR)

    resumed = await service.adopt_for_worker(
        legacy.model_copy(
            update={
                "fencing_token": legacy.fencing_token + 1,
                "plan": {
                    **legacy.plan,
                    "loaded_skill_ids": [],
                    "uploaded_document_ids": [],
                    "uploaded_image_fingerprints": [],
                },
            }
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert resumed.status is AgentRunStatus.RUNNING
