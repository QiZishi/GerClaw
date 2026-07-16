"""Tenant-, actor- and session-scoped persistence for fail-closed clinical intake."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select
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
        record = ClinicalIntake(
            tenant_id=tenant_id,
            actor_id=actor_id,
            session_id=session_id,
            kind=kind,
            definition_version=definition_version,
            status="collecting",
            revision=1,
            answers={},
        )
        self._session.add(record)
        await self._session.flush()
        return record

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

    async def get(
        self, intake_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ClinicalIntake:
        statement = select(ClinicalIntake).where(
            ClinicalIntake.id == intake_id,
            ClinicalIntake.tenant_id == tenant_id,
            ClinicalIntake.actor_id == actor_id,
        )
        record = cast(ClinicalIntake | None, await self._session.scalar(statement))
        if record is None:
            raise ClinicalIntakeNotFoundError(str(intake_id))
        return record

    async def lock(
        self, intake_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ClinicalIntake:
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
