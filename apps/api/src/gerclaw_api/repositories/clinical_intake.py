"""Tenant-, actor- and session-scoped persistence for fail-closed clinical intake."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import ClinicalIntake


class ClinicalIntakeNotFoundError(RuntimeError):
    """The authenticated caller cannot access the requested intake."""


class SqlAlchemyClinicalIntakeRepository:
    """All reads and locks enforce principal ownership in SQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
        kind: str,
        definition_version: str,
    ) -> ClinicalIntake:
        """Create once per principal/session/kind, including concurrent retries.

        A client may retry while a previous request is still committing. The
        database unique key is the authority for this idempotency boundary, so a
        conflict returns the already-owned record instead of leaking a 500.
        """

        statement = (
            postgresql_insert(ClinicalIntake)
            .values(
                tenant_id=tenant_id,
                actor_id=actor_id,
                session_id=session_id,
                kind=kind,
                definition_version=definition_version,
                status="collecting",
                revision=1,
                answers={},
            )
            .on_conflict_do_nothing(constraint="uq_clinical_intakes_principal_session_kind")
            .returning(ClinicalIntake.id)
        )
        created_id = await self._session.scalar(statement)
        if created_id is not None:
            return await self.get(created_id, tenant_id=tenant_id, actor_id=actor_id)

        existing = await self.find_by_session_kind(
            tenant_id=tenant_id,
            actor_id=actor_id,
            session_id=session_id,
            kind=kind,
        )
        if existing is None:  # pragma: no cover - PostgreSQL conflict must expose the row.
            raise RuntimeError("clinical intake conflict did not expose an existing record")
        return existing

    async def find_by_session_kind(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
        kind: str,
    ) -> ClinicalIntake | None:
        statement = select(ClinicalIntake).where(
            ClinicalIntake.tenant_id == tenant_id,
            ClinicalIntake.actor_id == actor_id,
            ClinicalIntake.session_id == session_id,
            ClinicalIntake.kind == kind,
        )
        return cast(ClinicalIntake | None, await self._session.scalar(statement))

    async def get(self, intake_id: uuid.UUID, *, tenant_id: str, actor_id: str) -> ClinicalIntake:
        statement = select(ClinicalIntake).where(
            ClinicalIntake.id == intake_id,
            ClinicalIntake.tenant_id == tenant_id,
            ClinicalIntake.actor_id == actor_id,
        )
        record = cast(ClinicalIntake | None, await self._session.scalar(statement))
        if record is None:
            raise ClinicalIntakeNotFoundError(str(intake_id))
        return record

    async def lock(self, intake_id: uuid.UUID, *, tenant_id: str, actor_id: str) -> ClinicalIntake:
        statement = (
            select(ClinicalIntake)
            .where(
                ClinicalIntake.id == intake_id,
                ClinicalIntake.tenant_id == tenant_id,
                ClinicalIntake.actor_id == actor_id,
            )
            .with_for_update()
        )
        record = cast(ClinicalIntake | None, await self._session.scalar(statement))
        if record is None:
            raise ClinicalIntakeNotFoundError(str(intake_id))
        return record
