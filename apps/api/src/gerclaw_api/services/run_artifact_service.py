"""Optimistically versioned CRUD for editable Agent run artifacts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from gerclaw_api.database.models import RunArtifact
from gerclaw_api.domain.run_schemas import ArtifactKind, ArtifactRead, ArtifactWrite
from gerclaw_api.repositories.run_artifact import RunArtifactRepository


class RunArtifactNotFoundError(LookupError):
    """Raised without revealing another principal's artifact or run."""


class RunArtifactConflictError(RuntimeError):
    """Raised when an artifact revision changed or a request has wrong semantics."""


class RunArtifactService:
    """Create and edit encrypted Markdown artifacts with revision checks."""

    def __init__(self, repository: RunArtifactRepository) -> None:
        self._repository = repository

    async def create(
        self,
        run_id: uuid.UUID,
        request: ArtifactWrite,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> ArtifactRead:
        if request.expected_revision is not None:
            raise RunArtifactConflictError("create must not include expected_revision")
        run = await self._repository.get_owned_run(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if run is None:
            raise RunArtifactNotFoundError(str(run_id))
        now = datetime.now(UTC)
        artifact = RunArtifact(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_id=actor_id,
            run_id=run.id,
            conversation_id=run.conversation_id,
            title=request.title,
            markdown=request.markdown,
            kind=request.kind.value,
            revision=1,
            saved=True,
            created_at=now,
            updated_at=now,
        )
        try:
            await self._repository.add_artifact(artifact)
            await self._repository.flush()
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public(artifact)

    async def get(
        self,
        artifact_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> ArtifactRead:
        artifact = await self._repository.get_owned_artifact(
            artifact_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if artifact is None:
            raise RunArtifactNotFoundError(str(artifact_id))
        return self.to_public(artifact)

    async def list_for_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int = 50,
    ) -> list[ArtifactRead]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        artifacts = await self._repository.list_owned_artifacts(
            conversation_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            limit=limit,
        )
        return [self.to_public(artifact) for artifact in artifacts]

    async def update(
        self,
        artifact_id: uuid.UUID,
        request: ArtifactWrite,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> ArtifactRead:
        if request.expected_revision is None:
            raise RunArtifactConflictError("update requires expected_revision")
        artifact = await self._locked_artifact(
            artifact_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if artifact.revision != request.expected_revision:
            await self._repository.rollback()
            raise RunArtifactConflictError("artifact revision changed")
        artifact.title = request.title
        artifact.markdown = request.markdown
        artifact.kind = request.kind.value
        artifact.revision += 1
        artifact.saved = True
        artifact.updated_at = datetime.now(UTC)
        try:
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public(artifact)

    async def delete(
        self,
        artifact_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        expected_revision: int,
    ) -> None:
        if expected_revision < 1:
            raise ValueError("expected_revision must be positive")
        artifact = await self._locked_artifact(
            artifact_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if artifact.revision != expected_revision:
            await self._repository.rollback()
            raise RunArtifactConflictError("artifact revision changed")
        try:
            await self._repository.delete_artifact(artifact)
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise

    async def _locked_artifact(
        self,
        artifact_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunArtifact:
        artifact = await self._repository.get_owned_artifact(
            artifact_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if artifact is None:
            raise RunArtifactNotFoundError(str(artifact_id))
        return artifact

    @staticmethod
    def to_public(artifact: RunArtifact) -> ArtifactRead:
        return ArtifactRead(
            id=artifact.id,
            run_id=artifact.run_id,
            conversation_id=artifact.conversation_id,
            title=artifact.title,
            markdown=artifact.markdown,
            kind=ArtifactKind(artifact.kind),
            revision=artifact.revision,
            saved=artifact.saved,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
        )
