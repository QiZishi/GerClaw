"""Actor-owned Agent run artifact persistence boundary."""

from __future__ import annotations

import uuid
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import AgentRun, RunArtifact


class RunArtifactRepository(Protocol):
    """Storage operations that preserve run and artifact ownership."""

    async def get_owned_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        """Return one caller-owned run."""

    async def get_owned_artifact(
        self,
        artifact_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> RunArtifact | None:
        """Return one caller-owned artifact, optionally locking it."""

    async def list_owned_artifacts(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunArtifact]:
        """Return recently updated artifacts from one owned conversation."""

    async def add_artifact(self, artifact: RunArtifact) -> None:
        """Stage one artifact."""

    async def delete_artifact(self, artifact: RunArtifact) -> None:
        """Stage deletion of one locked artifact."""

    async def flush(self) -> None:
        """Flush staged writes."""

    async def commit(self) -> None:
        """Commit the current transaction."""

    async def rollback(self) -> None:
        """Release locks and discard staged changes."""


class SqlAlchemyRunArtifactRepository:
    """PostgreSQL implementation with tenant and actor filters on every read."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owned_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun | None:
        statement = select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == tenant_id,
            AgentRun.actor_id == actor_id,
        )
        return cast(AgentRun | None, await self._session.scalar(statement))

    async def get_owned_artifact(
        self,
        artifact_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> RunArtifact | None:
        statement = select(RunArtifact).where(
            RunArtifact.id == artifact_id,
            RunArtifact.tenant_id == tenant_id,
            RunArtifact.actor_id == actor_id,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(RunArtifact | None, await self._session.scalar(statement))

    async def list_owned_artifacts(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[RunArtifact]:
        statement = (
            select(RunArtifact)
            .where(
                RunArtifact.conversation_id == conversation_id,
                RunArtifact.tenant_id == tenant_id,
                RunArtifact.actor_id == actor_id,
            )
            .order_by(RunArtifact.updated_at.desc(), RunArtifact.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def add_artifact(self, artifact: RunArtifact) -> None:
        self._session.add(artifact)

    async def delete_artifact(self, artifact: RunArtifact) -> None:
        await self._session.delete(artifact)

    async def flush(self) -> None:
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
