"""Unit tests for the durable Agent run transaction boundary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import AgentRun, RunEvent
from gerclaw_api.domain.run_schemas import (
    AgentRunCreate,
    AgentRunStatus,
    RunEventWrite,
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
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_unit0001"


class _Repository:
    def __init__(self) -> None:
        self.runs: dict[uuid.UUID, AgentRun] = {}
        self.events: list[RunEvent] = []
        self.commits = 0
        self.rollbacks = 0

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
    ) -> AgentRun | None:
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

    async def list_events(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int,
        limit: int,
    ) -> list[RunEvent]:
        if await self.get_owned_run(
            run_id, tenant_id=tenant_id, actor_id=actor_id
        ) is None:
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
async def test_event_append_rejects_stale_worker_and_terminal_run() -> None:
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
    completed = await service.transition(
        created.id,
        AgentRunStatus.COMPLETED,
        tenant_id=TENANT,
        actor_id=ACTOR,
        expected_revision=1,
        fencing_token=7,
    )
    with pytest.raises(RunTerminalConflictError, match="terminal agent run"):
        await service.append_event(
            completed.id,
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
    with pytest.raises(AgentRunNotFoundError):
        await service.cancel_owned(
            created.id,
            tenant_id=TENANT,
            actor_id="usr_other",
        )
