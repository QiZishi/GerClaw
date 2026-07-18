"""Encrypted, principal-scoped persistence for medication-review artifacts."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import MedicationReviewDraftRecord


class MedicationReviewDraftNotFoundError(LookupError):
    """A review artifact is absent or outside the caller's ownership boundary."""


class SqlAlchemyMedicationReviewDraftRepository:
    """Store and reopen deterministic review revisions only for their owner."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
        clinical_intake_id: uuid.UUID,
        clinical_intake_revision: int,
        ruleset_version: str,
        content: dict[str, object],
    ) -> MedicationReviewDraftRecord:
        record = MedicationReviewDraftRecord(
            tenant_id=tenant_id,
            actor_id=actor_id,
            session_id=session_id,
            clinical_intake_id=clinical_intake_id,
            clinical_intake_revision=clinical_intake_revision,
            ruleset_version=ruleset_version,
            status="needs_clinician_review",
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
    ) -> list[MedicationReviewDraftRecord]:
        statement = (
            select(MedicationReviewDraftRecord)
            .where(
                MedicationReviewDraftRecord.clinical_intake_id == intake_id,
                MedicationReviewDraftRecord.tenant_id == tenant_id,
                MedicationReviewDraftRecord.actor_id == actor_id,
            )
            .order_by(
                MedicationReviewDraftRecord.created_at.desc(),
                MedicationReviewDraftRecord.id.desc(),
            )
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())
