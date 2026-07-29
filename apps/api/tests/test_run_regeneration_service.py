"""Server-authoritative answer regeneration validation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import AgentRun, AnswerVersion, Message
from gerclaw_api.domain.chat_schemas import ChatRequest
from gerclaw_api.repositories.run_regeneration import RegenerationSource
from gerclaw_api.services.run_regeneration_service import (
    RunRegenerationConflictError,
    RunRegenerationNotFoundError,
    RunRegenerationService,
    image_fingerprint,
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_unit0001"


class _Repository:
    def __init__(self, source: RegenerationSource | None) -> None:
        self.source = source
        self.rollbacks = 0

    async def get_owned_source(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RegenerationSource | None:
        if (
            self.source is None
            or self.source.run.id != run_id
            or self.source.run.tenant_id != tenant_id
            or self.source.run.actor_id != actor_id
        ):
            return None
        return self.source

    async def rollback(self) -> None:
        self.rollbacks += 1


def _source() -> tuple[RegenerationSource, ChatRequest]:
    session_id = uuid.uuid4()
    input_message_id = uuid.uuid4()
    run_id = uuid.uuid4()
    version_id = uuid.uuid4()
    document_id = uuid.uuid4()
    image = {
        "media_type": "image/png",
        "base64": "aGVsbG8=",
    }
    request = ChatRequest(
        session_id=session_id,
        message="请重新评估",
        loaded_skills=["risk-assessment"],
        uploaded_files=[document_id],
        images=[image],
        regenerate_from_run_id=run_id,
        expected_current_answer_version_id=version_id,
    )
    now = datetime.now(UTC)
    run = AgentRun(
        id=run_id,
        tenant_id=TENANT,
        actor_id=ACTOR,
        conversation_id=session_id,
        input_message_id=input_message_id,
        trace_id="trace_regeneration_source_0001",
        route="standard",
        status="completed",
        context_snapshot={},
        plan={
            "workflow": "standard",
            "loaded_skill_count": 1,
            "loaded_skill_ids": ["risk-assessment"],
            "uploaded_document_count": 1,
            "uploaded_document_ids": [str(document_id)],
            "uploaded_image_count": 1,
            "uploaded_image_fingerprints": [
                image_fingerprint(image["media_type"], image["base64"])
            ],
        },
        warnings=[],
        current_answer_version_id=version_id,
        fencing_token=3,
        last_sequence=2,
        revision=2,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    message = Message(
        id=input_message_id,
        tenant_id=TENANT,
        session_id=session_id,
        trace_id=run.trace_id,
        role="user",
        content=[{"type": "text", "text": request.message}],
        message_metadata={"channel": "web"},
        created_at=now,
    )
    version = AnswerVersion(
        id=version_id,
        run_id=run_id,
        producer_run_id=run_id,
        answer_group_id=uuid.uuid4(),
        assistant_message_id=uuid.uuid4(),
        version=1,
        is_current=True,
        created_at=now,
    )
    return RegenerationSource(run, message, version), request


@pytest.mark.asyncio
async def test_exact_current_source_is_accepted() -> None:
    source, request = _source()
    repository = _Repository(source)

    resolved = await RunRegenerationService(repository).resolve(
        request,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert resolved is not None
    assert resolved.source_run_id == source.run.id
    assert resolved.input_message_id == source.input_message.id
    assert repository.rollbacks == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        {"message": "篡改输入"},
        {"loaded_skills": []},
        {"uploaded_files": []},
        {"images": []},
        {"expected_current_answer_version_id": uuid.uuid4()},
    ],
)
async def test_changed_source_facts_fail_closed(mutation: dict[str, object]) -> None:
    source, request = _source()
    changed = request.model_copy(update=mutation)
    repository = _Repository(source)

    with pytest.raises(RunRegenerationConflictError):
        await RunRegenerationService(repository).resolve(
            changed,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    assert repository.rollbacks == 1


@pytest.mark.asyncio
async def test_other_owner_is_indistinguishable_from_missing() -> None:
    source, request = _source()
    repository = _Repository(source)

    with pytest.raises(RunRegenerationNotFoundError):
        await RunRegenerationService(repository).resolve(
            request,
            tenant_id=TENANT,
            actor_id="usr_other",
        )
    assert repository.rollbacks == 1
