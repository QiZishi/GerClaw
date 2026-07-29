"""Artifact CRUD ownership and optimistic revision tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import AgentRun, RunArtifact
from gerclaw_api.domain.run_schemas import ArtifactKind, ArtifactWrite
from gerclaw_api.services.run_artifact_service import (
    RunArtifactConflictError,
    RunArtifactNotFoundError,
    RunArtifactService,
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_unit0001"


class _Repository:
    def __init__(self, run: AgentRun) -> None:
        self.run = run
        self.artifacts: dict[uuid.UUID, RunArtifact] = {}
        self.commits = 0
        self.rollbacks = 0

    async def get_owned_run(
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

    async def get_owned_artifact(
        self,
        artifact_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> RunArtifact | None:
        del for_update
        artifact = self.artifacts.get(artifact_id)
        if (
            artifact is None
            or artifact.tenant_id != tenant_id
            or artifact.actor_id != actor_id
        ):
            return None
        return artifact

    async def list_owned_artifacts(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunArtifact]:
        return [
            artifact
            for artifact in reversed(list(self.artifacts.values()))
            if artifact.conversation_id == conversation_id
            and artifact.tenant_id == tenant_id
            and artifact.actor_id == actor_id
        ][:limit]

    async def add_artifact(self, artifact: RunArtifact) -> None:
        self.artifacts[artifact.id] = artifact

    async def delete_artifact(self, artifact: RunArtifact) -> None:
        del self.artifacts[artifact.id]

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
        trace_id="trace_artifact_unit",
        route="standard",
        status="completed",
        context_snapshot={},
        plan={},
        warnings=[],
        current_answer_version_id=None,
        fencing_token=5,
        last_sequence=1,
        revision=2,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_artifact_crud_increments_revision_and_keeps_run_identity() -> None:
    repository = _Repository(_run())
    service = RunArtifactService(repository)
    created = await service.create(
        repository.run.id,
        ArtifactWrite(title="出院计划", markdown="初稿", kind=ArtifactKind.REPORT),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    updated = await service.update(
        created.id,
        ArtifactWrite(
            title="出院计划 (更新)",
            markdown="更新内容",
            kind=ArtifactKind.REPORT,
            expected_revision=1,
        ),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert updated.revision == 2
    assert updated.run_id == repository.run.id
    assert updated.conversation_id == repository.run.conversation_id
    assert (await service.get(updated.id, tenant_id=TENANT, actor_id=ACTOR)) == updated
    assert await service.list_for_conversation(
        repository.run.conversation_id,
        tenant_id=TENANT,
        actor_id=ACTOR,
    ) == [updated]
    await service.delete(
        updated.id,
        tenant_id=TENANT,
        actor_id=ACTOR,
        expected_revision=2,
    )
    with pytest.raises(RunArtifactNotFoundError):
        await service.get(updated.id, tenant_id=TENANT, actor_id=ACTOR)


@pytest.mark.asyncio
async def test_create_and_update_have_distinct_revision_contracts() -> None:
    repository = _Repository(_run())
    service = RunArtifactService(repository)
    with pytest.raises(RunArtifactConflictError, match="create"):
        await service.create(
            repository.run.id,
            ArtifactWrite(title="文档", markdown="", expected_revision=1),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    created = await service.create(
        repository.run.id,
        ArtifactWrite(title="文档", markdown=""),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    with pytest.raises(RunArtifactConflictError, match="update"):
        await service.update(
            created.id,
            ArtifactWrite(title="文档", markdown=""),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_stale_update_and_delete_are_rejected() -> None:
    repository = _Repository(_run())
    service = RunArtifactService(repository)
    created = await service.create(
        repository.run.id,
        ArtifactWrite(title="文档", markdown="版本 1"),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    with pytest.raises(RunArtifactConflictError, match="revision"):
        await service.update(
            created.id,
            ArtifactWrite(title="文档", markdown="过期", expected_revision=2),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    with pytest.raises(RunArtifactConflictError, match="revision"):
        await service.delete(
            created.id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            expected_revision=2,
        )
    assert repository.rollbacks == 2


@pytest.mark.asyncio
async def test_other_actor_cannot_read_or_mutate_artifact() -> None:
    repository = _Repository(_run())
    service = RunArtifactService(repository)
    created = await service.create(
        repository.run.id,
        ArtifactWrite(title="私有文档", markdown="敏感内容"),
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    with pytest.raises(RunArtifactNotFoundError):
        await service.get(created.id, tenant_id=TENANT, actor_id="usr_other")
    with pytest.raises(RunArtifactNotFoundError):
        await service.update(
            created.id,
            ArtifactWrite(title="越权", markdown="", expected_revision=1),
            tenant_id=TENANT,
            actor_id="usr_other",
        )
