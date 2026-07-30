"""State-machine tests for queued and steering user directives."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import AgentRun, ConversationSession, Message, RunDirective
from gerclaw_api.domain.run_schemas import (
    AgentRunStatus,
    RunDirectiveClaim,
    RunDirectiveCreate,
    RunDirectiveMode,
    RunDirectiveStatus,
    RunQueuedDirectiveCreate,
)
from gerclaw_api.services.run_directive_service import (
    RunDirectiveConflictError,
    RunDirectiveNotFoundError,
    RunDirectiveService,
)

TENANT = "tenant_directive_unit"
ACTOR = "guest_directive_unit"


class _Repository:
    def __init__(self) -> None:
        self.runs: dict[uuid.UUID, AgentRun] = {}
        self.conversations: dict[uuid.UUID, ConversationSession] = {}
        self.directives: dict[uuid.UUID, RunDirective] = {}
        self.messages: dict[str, Message] = {}
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

    async def get_owned(
        self,
        directive_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> RunDirective | None:
        del for_update
        directive = self.directives.get(directive_id)
        if (
            directive is None
            or directive.tenant_id != tenant_id
            or directive.actor_id != actor_id
        ):
            return None
        return directive

    async def get_owned_by_idempotency(
        self,
        idempotency_key: str,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunDirective | None:
        return next(
            (
                item
                for item in self.directives.values()
                if item.tenant_id == tenant_id
                and item.actor_id == actor_id
                and item.idempotency_key == idempotency_key
            ),
            None,
        )

    async def lock_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
    ) -> ConversationSession | None:
        conversation = self.conversations.get(conversation_id)
        if conversation is None or conversation.tenant_id != tenant_id:
            return None
        return conversation

    async def list_consumable(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunDirective]:
        candidates = [
            item
            for item in self.directives.values()
            if item.tenant_id == tenant_id
            and item.actor_id == actor_id
            and item.status in {
                RunDirectiveStatus.PENDING.value,
                RunDirectiveStatus.CLAIMED.value,
            }
            and (
                item.successor_run_id == run_id
                or (
                    item.successor_run_id is None
                    and
                    item.target_run_id == run_id
                    and item.mode == RunDirectiveMode.QUEUE_FOR_NEXT_BOUNDARY.value
                )
            )
        ]
        return sorted(candidates, key=lambda item: item.sequence)[:limit]

    async def list_applied_for_execution(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int,
        limit: int,
    ) -> list[RunDirective]:
        return sorted(
            (
                item
                for item in self.directives.values()
                if item.tenant_id == tenant_id
                and item.actor_id == actor_id
                and item.status == RunDirectiveStatus.APPLIED.value
                and item.sequence > after_sequence
                and (
                    item.successor_run_id == run_id
                    or (
                        item.successor_run_id is None
                        and item.target_run_id == run_id
                        and item.mode == RunDirectiveMode.QUEUE_FOR_NEXT_BOUNDARY.value
                    )
                )
            ),
            key=lambda item: item.sequence,
        )[:limit]

    async def list_recent_applied_for_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunDirective]:
        newest_first = sorted(
            (
                item
                for item in self.directives.values()
                if item.conversation_id == conversation_id
                and item.tenant_id == tenant_id
                and item.actor_id == actor_id
                and item.status == RunDirectiveStatus.APPLIED.value
            ),
            key=lambda item: item.sequence,
            reverse=True,
        )[:limit]
        return list(reversed(newest_first))

    async def list_for_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunDirective]:
        return sorted(
            (
                item
                for item in self.directives.values()
                if item.tenant_id == tenant_id
                and item.actor_id == actor_id
                and (item.target_run_id == run_id or item.successor_run_id == run_id)
            ),
            key=lambda item: item.sequence,
        )[:limit]

    async def get_projected_message(
        self,
        trace_id: str,
        *,
        tenant_id: str,
    ) -> Message | None:
        message = self.messages.get(trace_id)
        if message is None or message.tenant_id != tenant_id:
            return None
        return message

    async def add_projected_message(self, message: Message) -> None:
        if message.trace_id is None:
            raise AssertionError("directive projection requires a trace identity")
        self.messages[message.trace_id] = message

    async def add(self, directive: RunDirective) -> None:
        self.directives[directive.id] = directive

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _setup(
    *,
    status: AgentRunStatus = AgentRunStatus.RUNNING,
    fence: int = 7,
) -> tuple[_Repository, AgentRun]:
    repository = _Repository()
    conversation_id = uuid.uuid4()
    now = datetime.now(UTC)
    repository.conversations[conversation_id] = ConversationSession(
        id=conversation_id,
        user_id=None,
        tenant_id=TENANT,
        agent_id="geriatric-specialist",
        title=None,
        status="active",
        active_fencing_token=fence,
        active_fencing_trace_id="trace_directive",
        last_directive_sequence=0,
        context_summary={},
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        actor_id=ACTOR,
        conversation_id=conversation_id,
        input_message_id=uuid.uuid4(),
        trace_id=f"trace_{uuid.uuid4().hex}",
        route="standard",
        status=status.value,
        context_snapshot={},
        plan={},
        warnings=[],
        current_answer_version_id=None,
        current_valid_attempt_id=None,
        fencing_token=fence,
        last_sequence=0,
        revision=1,
        started_at=now,
        interrupted_at=now if status is AgentRunStatus.INTERRUPTED else None,
        completed_at=now
        if status
        in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.COMPLETED_WITH_WARNINGS,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
        else None,
        created_at=now,
        updated_at=now,
    )
    repository.runs[run.id] = run
    return repository, run


def _create(
    *,
    mode: RunDirectiveMode = RunDirectiveMode.QUEUE_FOR_NEXT_BOUNDARY,
    key: str = "directive-idempotency-1",
    instruction: str = "先核对药物清单后再继续回答。",
) -> RunDirectiveCreate:
    return RunDirectiveCreate(
        mode=mode,
        instruction=instruction,
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_create_allocates_monotonic_conversation_sequence() -> None:
    repository, run = _setup()
    service = RunDirectiveService(repository)

    first = await service.create(run.id, _create(), tenant_id=TENANT, actor_id=ACTOR)
    second = await service.create(
        run.id,
        _create(key="directive-idempotency-2", instruction="补充考虑最近一次化验。"),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert (first.sequence, second.sequence) == (1, 2)
    assert first.status is RunDirectiveStatus.PENDING
    assert repository.conversations[run.conversation_id].last_directive_sequence == 2


@pytest.mark.asyncio
async def test_trace_queue_waits_for_run_creation_without_losing_instruction() -> None:
    repository, run = _setup()
    repository.runs.clear()
    service = RunDirectiveService(repository)

    async def publish_run() -> None:
        await asyncio.sleep(0.01)
        repository.runs[run.id] = run

    publisher = asyncio.create_task(publish_run())
    created = await service.queue_for_trace(
        run.trace_id,
        request=RunQueuedDirectiveCreate(
            instruction="Run 建立后继续处理这条要求。",
            idempotency_key="directive-before-run-visible",
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
        wait_seconds=0.1,
        poll_interval_seconds=0.005,
    )
    await publisher

    assert created.target_run_id == run.id
    assert created.status is RunDirectiveStatus.PENDING


@pytest.mark.asyncio
async def test_terminal_run_preserves_instruction_for_next_run() -> None:
    repository, run = _setup(status=AgentRunStatus.COMPLETED)

    created = await RunDirectiveService(repository).create(
        run.id,
        _create(),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert created.status is RunDirectiveStatus.PENDING_NEXT_RUN


@pytest.mark.asyncio
async def test_idempotent_replay_returns_original_identity() -> None:
    repository, run = _setup()
    service = RunDirectiveService(repository)
    request = _create()
    first = await service.create(run.id, request, tenant_id=TENANT, actor_id=ACTOR)

    replay = await service.create(
        run.id,
        request.model_copy(update={"id": uuid.uuid4()}),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert replay.id == first.id
    assert replay.sequence == first.sequence
    assert len(repository.directives) == 1


@pytest.mark.asyncio
async def test_idempotency_key_rejects_changed_payload() -> None:
    repository, run = _setup()
    service = RunDirectiveService(repository)
    await service.create(run.id, _create(), tenant_id=TENANT, actor_id=ACTOR)

    with pytest.raises(RunDirectiveConflictError):
        await service.create(
            run.id,
            _create(instruction="把原要求改成另一个要求。"),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_owner_scope_hides_directive_and_run() -> None:
    repository, run = _setup()
    service = RunDirectiveService(repository)
    created = await service.create(run.id, _create(), tenant_id=TENANT, actor_id=ACTOR)

    with pytest.raises(RunDirectiveNotFoundError):
        await service.cancel_unclaimed(
            created.id,
            tenant_id=TENANT,
            actor_id="guest_other_actor",
        )


@pytest.mark.asyncio
async def test_queue_claim_and_apply_are_idempotent() -> None:
    repository, run = _setup()
    service = RunDirectiveService(repository)
    created = await service.create(run.id, _create(), tenant_id=TENANT, actor_id=ACTOR)
    claim = RunDirectiveClaim(fencing_token=run.fencing_token, boundary_id="before-model-2")

    claimed = await service.claim_next(
        run.id,
        claim,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    replayed_claim = await service.claim_next(
        run.id,
        claim,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    applied = await service.mark_applied(
        created.id,
        claim,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    replayed_apply = await service.mark_applied(
        created.id,
        claim,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert claimed is not None
    assert replayed_claim is not None and replayed_claim.id == claimed.id
    assert applied.status is RunDirectiveStatus.APPLIED
    assert replayed_apply.revision == applied.revision
    projected = repository.messages[f"directive_{created.id.hex}"]
    assert projected.content == [{"type": "text", "text": created.instruction}]
    assert projected.message_metadata["directive_id"] == str(created.id)


@pytest.mark.asyncio
async def test_applied_replay_repairs_missing_conversation_projection() -> None:
    repository, run = _setup()
    service = RunDirectiveService(repository)
    created = await service.create(run.id, _create(), tenant_id=TENANT, actor_id=ACTOR)
    claim = RunDirectiveClaim(fencing_token=run.fencing_token, boundary_id="before-model-2")
    await service.claim_next(run.id, claim, tenant_id=TENANT, actor_id=ACTOR)
    await service.mark_applied(
        created.id,
        claim,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    repository.messages.clear()
    commits_before_repair = repository.commits

    repaired = await service.mark_applied(
        created.id,
        claim,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert repaired.status is RunDirectiveStatus.APPLIED
    assert f"directive_{created.id.hex}" in repository.messages
    assert repository.commits == commits_before_repair + 1


@pytest.mark.asyncio
async def test_stale_worker_cannot_apply_after_fence_adoption() -> None:
    repository, run = _setup(fence=7)
    service = RunDirectiveService(repository)
    created = await service.create(run.id, _create(), tenant_id=TENANT, actor_id=ACTOR)
    old_claim = RunDirectiveClaim(fencing_token=7, boundary_id="before-tool-1")
    await service.claim_next(run.id, old_claim, tenant_id=TENANT, actor_id=ACTOR)
    run.fencing_token = 8
    new_claim = RunDirectiveClaim(fencing_token=8, boundary_id="resume-before-model-1")

    adopted = await service.claim_next(
        run.id,
        new_claim,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    with pytest.raises(RunDirectiveConflictError):
        await service.mark_applied(
            created.id,
            old_claim,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )

    assert adopted is not None
    assert adopted.claimed_by_fencing_token == 8


@pytest.mark.asyncio
async def test_unclaimed_directive_can_be_withdrawn_but_claimed_cannot() -> None:
    repository, run = _setup()
    service = RunDirectiveService(repository)
    first = await service.create(run.id, _create(), tenant_id=TENANT, actor_id=ACTOR)
    cancelled = await service.cancel_unclaimed(
        first.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    assert cancelled.status is RunDirectiveStatus.CANCELLED

    second = await service.create(
        run.id,
        _create(key="directive-idempotency-2"),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    await service.claim_next(
        run.id,
        RunDirectiveClaim(fencing_token=7, boundary_id="before-model-2"),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    with pytest.raises(RunDirectiveConflictError):
        await service.cancel_unclaimed(
            second.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_interrupt_directive_is_not_consumed_on_original_run() -> None:
    repository, run = _setup()
    service = RunDirectiveService(repository)
    created = await service.create(
        run.id,
        _create(mode=RunDirectiveMode.INTERRUPT_AND_STEER),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    claim = await service.claim_next(
        run.id,
        RunDirectiveClaim(fencing_token=7, boundary_id="before-model-2"),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert claim is None
    assert created.status is RunDirectiveStatus.PENDING


@pytest.mark.asyncio
async def test_bound_queue_directive_is_not_consumed_on_original_run() -> None:
    repository, run = _setup()
    service = RunDirectiveService(repository)
    created = await service.create(run.id, _create(), tenant_id=TENANT, actor_id=ACTOR)
    repository.directives[created.id].successor_run_id = uuid.uuid4()

    claim = await service.claim_next(
        run.id,
        RunDirectiveClaim(fencing_token=7, boundary_id="before-model-2"),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert claim is None


@pytest.mark.asyncio
async def test_successor_binding_makes_steer_instruction_consumable() -> None:
    repository, original = _setup()
    service = RunDirectiveService(repository)
    created = await service.create(
        original.id,
        _create(mode=RunDirectiveMode.INTERRUPT_AND_STEER),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    now = datetime.now(UTC)
    successor = AgentRun(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        actor_id=ACTOR,
        conversation_id=original.conversation_id,
        input_message_id=original.input_message_id,
        trace_id=f"trace_{uuid.uuid4().hex}",
        route="standard",
        status=AgentRunStatus.RUNNING.value,
        context_snapshot={},
        plan={},
        warnings=[],
        current_answer_version_id=None,
        current_valid_attempt_id=None,
        fencing_token=8,
        last_sequence=0,
        revision=1,
        started_at=now,
        interrupted_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    repository.runs[successor.id] = successor

    bound = await service.bind_to_successor(
        created.id,
        successor.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    claimed = await service.claim_next(
        successor.id,
        RunDirectiveClaim(fencing_token=8, boundary_id="successor-start"),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert bound.successor_run_id == successor.id
    assert claimed is not None and claimed.id == created.id
