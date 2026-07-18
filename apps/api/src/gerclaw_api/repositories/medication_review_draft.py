"""Encrypted, principal-scoped persistence for medication-review artifacts."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import MedicationReviewDraftRecord, MedicationReviewDraftReview


class MedicationReviewDraftNotFoundError(LookupError):
    """A review artifact is absent or outside the caller's ownership boundary."""


def _content_fingerprint(content: dict[str, Any]) -> str:
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


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

    async def list_for_patient(
        self,
        *,
        tenant_id: str,
        patient_actor_id: str,
        limit: int,
    ) -> list[MedicationReviewDraftRecord]:
        """Return bounded newest-first drafts for one consented patient only."""

        statement = (
            select(MedicationReviewDraftRecord)
            .where(
                MedicationReviewDraftRecord.tenant_id == tenant_id,
                MedicationReviewDraftRecord.actor_id == patient_actor_id,
            )
            .order_by(
                MedicationReviewDraftRecord.created_at.desc(),
                MedicationReviewDraftRecord.id.desc(),
            )
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def list_reviews_for_drafts(
        self,
        *,
        tenant_id: str,
        draft_ids: tuple[uuid.UUID, ...],
        doctor_actor_id: str | None,
    ) -> list[MedicationReviewDraftReview]:
        """Read bounded review records without widening the consent projection."""

        if not draft_ids:
            return []
        statement = (
            select(MedicationReviewDraftReview)
            .where(
                MedicationReviewDraftReview.tenant_id == tenant_id,
                MedicationReviewDraftReview.medication_review_draft_id.in_(draft_ids),
            )
            .order_by(
                MedicationReviewDraftReview.reviewed_at.desc(),
                MedicationReviewDraftReview.id.desc(),
            )
            .limit(100)
        )
        if doctor_actor_id is not None:
            statement = statement.where(
                MedicationReviewDraftReview.doctor_actor_id == doctor_actor_id
            )
        return list((await self._session.scalars(statement)).all())

    async def append_review(
        self,
        *,
        draft_id: uuid.UUID,
        tenant_id: str,
        patient_actor_id: str,
        doctor_actor_id: str,
        decision: str,
        review_note: str,
    ) -> MedicationReviewDraftReview:
        """Append a doctor decision while locking the exact encrypted artifact."""

        draft = await self._session.scalar(
            select(MedicationReviewDraftRecord)
            .where(
                MedicationReviewDraftRecord.id == draft_id,
                MedicationReviewDraftRecord.tenant_id == tenant_id,
                MedicationReviewDraftRecord.actor_id == patient_actor_id,
            )
            .with_for_update()
        )
        if draft is None:
            raise MedicationReviewDraftNotFoundError("medication review draft not found")
        latest_revision = await self._session.scalar(
            select(func.max(MedicationReviewDraftReview.revision)).where(
                MedicationReviewDraftReview.tenant_id == tenant_id,
                MedicationReviewDraftReview.medication_review_draft_id == draft_id,
                MedicationReviewDraftReview.doctor_actor_id == doctor_actor_id,
            )
        )
        record = MedicationReviewDraftReview(
            tenant_id=tenant_id,
            medication_review_draft_id=draft.id,
            patient_actor_id=patient_actor_id,
            doctor_actor_id=doctor_actor_id,
            draft_content_sha256=_content_fingerprint(draft.content),
            decision=decision,
            review_note=review_note,
            revision=(int(latest_revision or 0) + 1),
        )
        self._session.add(record)
        await self._session.flush()
        return record
