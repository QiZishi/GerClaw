"""Encrypted, principal-scoped persistence for generated prescription drafts."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import PrescriptionDraftRecord


class SqlAlchemyPrescriptionDraftRepository:
    """Persist and read drafts only through the owning tenant and actor."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
        clinical_intake_id: uuid.UUID,
        template_version: str,
        workflow_version: str,
        status: str,
        content: dict[str, Any],
    ) -> PrescriptionDraftRecord:
        record = PrescriptionDraftRecord(
            tenant_id=tenant_id,
            actor_id=actor_id,
            session_id=session_id,
            clinical_intake_id=clinical_intake_id,
            template_version=template_version,
            workflow_version=workflow_version,
            status=status,
            content=content,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_for_intake(
        self,
        *,
        intake_id: uuid.UUID,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> list[PrescriptionDraftRecord]:
        statement = (
            select(PrescriptionDraftRecord)
            .where(
                PrescriptionDraftRecord.clinical_intake_id == intake_id,
                PrescriptionDraftRecord.tenant_id == tenant_id,
                PrescriptionDraftRecord.actor_id == actor_id,
            )
            .order_by(PrescriptionDraftRecord.created_at.desc(), PrescriptionDraftRecord.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())
