"""Answer version history, selection, ownership, and conflict tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import AgentRun, AnswerVersion, Message
from gerclaw_api.domain.run_schemas import AnswerVersionRegister, AnswerVersionSelect
from gerclaw_api.services.answer_version_service import (
    AnswerVersionConflictError,
    AnswerVersionDataError,
    AnswerVersionNotFoundError,
    AnswerVersionService,
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_unit0001"


class _Repository:
    def __init__(
        self,
        run: AgentRun,
        messages: list[Message],
        producer_runs: list[AgentRun],
    ) -> None:
        self.run = run
        self.runs = {item.id: item for item in [run, *producer_runs]}
        self.messages = {message.id: message for message in messages}
        self.versions: list[AnswerVersion] = []
        self.flushes = 0
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
            self.run.id != run_id
            or self.run.tenant_id != tenant_id
            or self.run.actor_id != actor_id
        ):
            return None
        return self.run

    async def get_assistant_message(
        self,
        message_id: uuid.UUID,
        *,
        tenant_id: str,
        conversation_id: uuid.UUID,
    ) -> Message | None:
        message = self.messages.get(message_id)
        if (
            message is None
            or message.tenant_id != tenant_id
            or message.session_id != conversation_id
            or message.role != "assistant"
        ):
            return None
        return message

    async def get_owned_producer_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        conversation_id: uuid.UUID,
    ) -> AgentRun | None:
        run = self.runs.get(run_id)
        if (
            run is None
            or run.tenant_id != tenant_id
            or run.actor_id != actor_id
            or run.conversation_id != conversation_id
        ):
            return None
        return run

    def producer_for(self, message: Message) -> AgentRun:
        return next(run for run in self.runs.values() if run.trace_id == message.trace_id)

    async def get_by_message(
        self,
        run_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
    ) -> AnswerVersion | None:
        return next(
            (
                version
                for version in self.versions
                if version.run_id == run_id
                and version.assistant_message_id == assistant_message_id
            ),
            None,
        )

    async def get_by_producer_run(
        self,
        producer_run_id: uuid.UUID,
    ) -> AnswerVersion | None:
        return next(
            (
                version
                for version in self.versions
                if version.producer_run_id == producer_run_id
            ),
            None,
        )

    async def get_version(
        self,
        run_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> AnswerVersion | None:
        return next(
            (
                version
                for version in self.versions
                if version.run_id == run_id and version.id == version_id
            ),
            None,
        )

    async def get_current(self, run_id: uuid.UUID) -> AnswerVersion | None:
        return next(
            (
                version
                for version in self.versions
                if version.run_id == run_id and version.is_current
            ),
            None,
        )

    async def list_versions(self, run_id: uuid.UUID, *, limit: int) -> list[AnswerVersion]:
        return [version for version in self.versions if version.run_id == run_id][:limit]

    async def add_version(self, version: AnswerVersion) -> None:
        self.versions.append(version)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _fixtures() -> tuple[_Repository, list[Message]]:
    conversation_id = uuid.uuid4()
    run = AgentRun(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        actor_id=ACTOR,
        conversation_id=conversation_id,
        input_message_id=uuid.uuid4(),
        trace_id="trace_answer_0",
        route="standard",
        status="completed",
        context_snapshot={},
        plan={},
        warnings=[],
        current_answer_version_id=None,
        fencing_token=3,
        last_sequence=1,
        revision=2,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    messages = [
        Message(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            session_id=conversation_id,
            trace_id=f"trace_answer_{index}",
            role="assistant",
            content=[{"type": "text", "text": f"answer {index}"}],
            message_metadata={},
            created_at=datetime.now(UTC),
        )
        for index in range(2)
    ]
    producer = AgentRun(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        actor_id=ACTOR,
        conversation_id=conversation_id,
        input_message_id=run.input_message_id,
        trace_id="trace_answer_1",
        route="standard",
        status="completed",
        context_snapshot={},
        plan={},
        warnings=[],
        current_answer_version_id=None,
        fencing_token=4,
        last_sequence=1,
        revision=2,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return _Repository(run, messages, [producer]), messages


@pytest.mark.asyncio
async def test_register_preserves_history_and_moves_current_pointer() -> None:
    repository, messages = _fixtures()
    service = AnswerVersionService(repository)

    first = await service.register(
        repository.run.id,
        AnswerVersionRegister(assistant_message_id=messages[0].id),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    second = await service.register(
        repository.run.id,
        AnswerVersionRegister(
            assistant_message_id=messages[1].id,
            producer_run_id=repository.producer_for(messages[1]).id,
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert (first.version, second.version) == (1, 2)
    assert second.answer_group_id == first.answer_group_id
    assert second.supersedes_id == first.id
    assert repository.versions[0].is_current is False
    assert repository.versions[1].is_current is True
    assert repository.run.current_answer_version_id == second.id
    assert len(await service.list_versions(
        repository.run.id, tenant_id=TENANT, actor_id=ACTOR
    )) == 2


@pytest.mark.asyncio
async def test_registration_is_idempotent_without_reselecting_old_version() -> None:
    repository, messages = _fixtures()
    service = AnswerVersionService(repository)
    first = await service.register(
        repository.run.id,
        AnswerVersionRegister(assistant_message_id=messages[0].id),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    await service.register(
        repository.run.id,
        AnswerVersionRegister(
            assistant_message_id=messages[1].id,
            producer_run_id=repository.producer_for(messages[1]).id,
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    replay = await service.register(
        repository.run.id,
        AnswerVersionRegister(assistant_message_id=messages[0].id),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert replay.id == first.id
    assert replay.is_current is False
    assert len(repository.versions) == 2


@pytest.mark.asyncio
async def test_registration_rechecks_expected_current_version_under_run_lock() -> None:
    repository, messages = _fixtures()
    service = AnswerVersionService(repository)
    first = await service.register(
        repository.run.id,
        AnswerVersionRegister(assistant_message_id=messages[0].id),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    with pytest.raises(AnswerVersionConflictError, match="current answer version changed"):
        await service.register(
            repository.run.id,
            AnswerVersionRegister(
                assistant_message_id=messages[1].id,
                producer_run_id=repository.producer_for(messages[1]).id,
                expected_current_version_id=uuid.uuid4(),
            ),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )

    assert len(repository.versions) == 1
    assert repository.versions[0].is_current is True
    assert repository.run.current_answer_version_id == first.id


@pytest.mark.asyncio
async def test_select_uses_optimistic_current_pointer_and_keeps_all_versions() -> None:
    repository, messages = _fixtures()
    service = AnswerVersionService(repository)
    first = await service.register(
        repository.run.id,
        AnswerVersionRegister(assistant_message_id=messages[0].id),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    second = await service.register(
        repository.run.id,
        AnswerVersionRegister(
            assistant_message_id=messages[1].id,
            producer_run_id=repository.producer_for(messages[1]).id,
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    with pytest.raises(AnswerVersionConflictError):
        await service.select(
            repository.run.id,
            first.id,
            AnswerVersionSelect(expected_current_version_id=first.id),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    selected = await service.select(
        repository.run.id,
        first.id,
        AnswerVersionSelect(expected_current_version_id=second.id),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert selected.id == first.id
    assert selected.is_current is True
    assert len(repository.versions) == 2
    assert repository.run.current_answer_version_id == first.id


@pytest.mark.asyncio
async def test_owner_and_message_boundaries_fail_closed() -> None:
    repository, messages = _fixtures()
    service = AnswerVersionService(repository)
    with pytest.raises(AnswerVersionNotFoundError):
        await service.register(
            repository.run.id,
            AnswerVersionRegister(assistant_message_id=messages[0].id),
            tenant_id=TENANT,
            actor_id="usr_other",
        )
    with pytest.raises(AnswerVersionNotFoundError):
        await service.register(
            repository.run.id,
            AnswerVersionRegister(assistant_message_id=uuid.uuid4()),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_inconsistent_current_pointer_is_rejected() -> None:
    repository, messages = _fixtures()
    repository.run.current_answer_version_id = uuid.uuid4()
    service = AnswerVersionService(repository)

    with pytest.raises(AnswerVersionDataError):
        await service.register(
            repository.run.id,
            AnswerVersionRegister(assistant_message_id=messages[0].id),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    assert repository.rollbacks == 1


@pytest.mark.asyncio
async def test_registration_rejects_message_not_produced_by_declared_run() -> None:
    repository, messages = _fixtures()
    service = AnswerVersionService(repository)

    with pytest.raises(AnswerVersionNotFoundError):
        await service.register(
            repository.run.id,
            AnswerVersionRegister(
                assistant_message_id=messages[0].id,
                producer_run_id=uuid.uuid4(),
            ),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
