"""Tenant- and actor-scoped persistence for deterministic CGA assessments."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import CgaAssessment


class CgaAssessmentNotFoundError(RuntimeError):
    """The authenticated principal cannot access the requested assessment."""


class SqlAlchemyCgaRepository:
    """Every lookup includes the verified tenant and actor identity."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, tenant_id: str, actor_id: str, scale_id: str, definition_version: str
    ) -> CgaAssessment:
        record = CgaAssessment(
            tenant_id=tenant_id,
            actor_id=actor_id,
            scale_id=scale_id,
            definition_version=definition_version,
            status="active",
            current_position=1,
            revision=1,
            answers={},
            notes={},
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(
        self, assessment_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> CgaAssessment:
        statement = select(CgaAssessment).where(
            CgaAssessment.id == assessment_id,
            CgaAssessment.tenant_id == tenant_id,
            CgaAssessment.actor_id == actor_id,
        )
        record = cast(CgaAssessment | None, await self._session.scalar(statement))
        if record is None:
            raise CgaAssessmentNotFoundError(str(assessment_id))
        return record

    async def lock(
        self, assessment_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> CgaAssessment:
        statement = (
            select(CgaAssessment)
            .where(
                CgaAssessment.id == assessment_id,
                CgaAssessment.tenant_id == tenant_id,
                CgaAssessment.actor_id == actor_id,
            )
            .with_for_update()
        )
        record = cast(CgaAssessment | None, await self._session.scalar(statement))
        if record is None:
            raise CgaAssessmentNotFoundError(str(assessment_id))
        return record

    async def list_completed(
        self, *, tenant_id: str, actor_id: str, limit: int
    ) -> list[CgaAssessment]:
        """Return only the caller's completed records, newest completion first."""

        statement = (
            select(CgaAssessment)
            .where(
                CgaAssessment.tenant_id == tenant_id,
                CgaAssessment.actor_id == actor_id,
                CgaAssessment.status == "completed",
            )
            .order_by(CgaAssessment.updated_at.desc(), CgaAssessment.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def list_active(
        self, *, tenant_id: str, actor_id: str, limit: int
    ) -> list[CgaAssessment]:
        """Return only resumable assessments owned by the authenticated caller."""

        statement = (
            select(CgaAssessment)
            .where(
                CgaAssessment.tenant_id == tenant_id,
                CgaAssessment.actor_id == actor_id,
                CgaAssessment.status == "active",
            )
            .order_by(CgaAssessment.updated_at.desc(), CgaAssessment.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def previous_completed_same_scale(
        self,
        record: CgaAssessment,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> CgaAssessment | None:
        """Find the immediately preceding owned completion for one scale only."""

        if record.updated_at is None:
            return None
        statement = (
            select(CgaAssessment)
            .where(
                CgaAssessment.tenant_id == tenant_id,
                CgaAssessment.actor_id == actor_id,
                CgaAssessment.scale_id == record.scale_id,
                CgaAssessment.status == "completed",
                CgaAssessment.updated_at < record.updated_at,
            )
            .order_by(CgaAssessment.updated_at.desc(), CgaAssessment.id.desc())
            .limit(1)
        )
        return cast(CgaAssessment | None, await self._session.scalar(statement))
