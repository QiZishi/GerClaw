"""Explicit Run resume reconstruction and trust-boundary validation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import AgentRun, ExecutionTrace, Message
from gerclaw_api.repositories.run_resume import RunResumeRecord
from gerclaw_api.services.run_resume_service import (
    RunResumeConflictError,
    RunResumeDataError,
    RunResumeNotFoundError,
    RunResumeService,
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_unit0001"


class _Repository:
    def __init__(self, record: RunResumeRecord | None) -> None:
        self.record = record
        self.rollbacks = 0

    async def get_owned_context(
        self,
        _run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunResumeRecord | None:
        assert (tenant_id, actor_id) == (TENANT, ACTOR)
        return self.record

    async def get_latest_interrupted(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        assert (tenant_id, actor_id) == (TENANT, ACTOR)
        if self.record is None or self.record.run.conversation_id != conversation_id:
            return None
        return self.record.run

    async def rollback(self) -> None:
        self.rollbacks += 1


def _record() -> RunResumeRecord:
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()
    message_id = uuid.uuid4()
    trace_id = "trace_resume_unit_0001"
    now = datetime.now(UTC)
    run = AgentRun(
        id=run_id,
        tenant_id=TENANT,
        actor_id=ACTOR,
        conversation_id=session_id,
        input_message_id=message_id,
        trace_id=trace_id,
        route="standard",
        status="interrupted",
        context_snapshot={},
        plan={
            "loaded_skill_count": 1,
            "loaded_skill_ids": ["medication-reminder"],
            "uploaded_document_count": 1,
            "uploaded_document_ids": [str(uuid.uuid4())],
            "uploaded_image_count": 0,
            "uploaded_image_fingerprints": [],
            "workflow": "standard",
        },
        warnings=[],
        fencing_token=7,
        last_sequence=2,
        revision=2,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    message = Message(
        id=message_id,
        tenant_id=TENANT,
        session_id=session_id,
        trace_id=trace_id,
        role="user",
        content=[{"type": "text", "text": " 请恢复这次回答 "}],
        message_metadata={"channel": "web"},
        created_at=now,
    )
    trace = ExecutionTrace(
        trace_id=trace_id,
        request_id="request_resume_unit_0001",
        tenant_id=TENANT,
        actor_id=ACTOR,
        session_id=session_id,
        execution_type="agent.chat",
        status="running",
        attributes={},
        private_input_artifacts={},
        started_at=now,
    )
    return RunResumeRecord(run=run, input_message=message, trace=trace)


@pytest.mark.asyncio
async def test_prepare_reconstructs_only_server_persisted_input() -> None:
    record = _record()
    repository = _Repository(record)
    command = await RunResumeService(repository).prepare(
        record.run.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert command.trace_id == record.run.trace_id
    assert command.request.message == "请恢复这次回答"
    assert command.request.loaded_skills == ["medication-reminder"]
    assert len(command.request.uploaded_files) == 1
    assert command.request.images == []
    assert repository.rollbacks == 1


@pytest.mark.asyncio
async def test_prepare_preserves_server_validated_regeneration_identity() -> None:
    record = _record()
    source_run_id = uuid.uuid4()
    current_version_id = uuid.uuid4()
    record.run.plan = {
        **record.run.plan,
        "regenerate_from_run_id": str(source_run_id),
        "expected_current_answer_version_id": str(current_version_id),
    }
    command = await RunResumeService(_Repository(record)).prepare(
        record.run.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert command.request.regenerate_from_run_id == source_run_id
    assert command.request.expected_current_answer_version_id == current_version_id


@pytest.mark.asyncio
async def test_prepare_rejects_non_interrupted_or_corrupt_material() -> None:
    record = _record()
    record.run.status = "completed"
    repository = _Repository(record)
    with pytest.raises(RunResumeConflictError):
        await RunResumeService(repository).prepare(
            record.run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )

    record.run.status = "interrupted"
    record.run.plan = {**record.run.plan, "loaded_skill_count": 2}
    with pytest.raises(RunResumeDataError):
        await RunResumeService(repository).prepare(
            record.run.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_prepare_hides_missing_or_foreign_run() -> None:
    repository = _Repository(None)
    with pytest.raises(RunResumeNotFoundError):
        await RunResumeService(repository).prepare(
            uuid.uuid4(),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    assert repository.rollbacks == 1


@pytest.mark.asyncio
async def test_latest_interrupted_returns_public_run_without_contents() -> None:
    record = _record()
    repository = _Repository(record)
    latest = await RunResumeService(repository).latest_interrupted(
        record.run.conversation_id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert latest is not None
    assert latest.id == record.run.id
    assert latest.status.value == "interrupted"
    assert repository.rollbacks == 1
