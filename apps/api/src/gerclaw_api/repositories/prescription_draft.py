"""Encrypted, principal-scoped persistence for generated prescription drafts."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import PrescriptionDraftRecord, PrescriptionDraftReview


class PrescriptionDraftNotFoundError(LookupError):
    """A draft is absent or outside the current principal's narrow boundary."""


def _content_fingerprint(content: dict[str, Any]) -> str:
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


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

    async def list_for_patient(
        self, *, tenant_id: str, patient_actor_id: str, limit: int
    ) -> list[PrescriptionDraftRecord]:
        """Read only generated drafts belonging to one consented patient."""

        statement = (
            select(PrescriptionDraftRecord)
            .where(
                PrescriptionDraftRecord.tenant_id == tenant_id,
                PrescriptionDraftRecord.actor_id == patient_actor_id,
            )
            .order_by(PrescriptionDraftRecord.created_at.desc(), PrescriptionDraftRecord.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_for_patient(
        self, *, draft_id: uuid.UUID, tenant_id: str, patient_actor_id: str
    ) -> PrescriptionDraftRecord:
        statement = select(PrescriptionDraftRecord).where(
            PrescriptionDraftRecord.id == draft_id,
            PrescriptionDraftRecord.tenant_id == tenant_id,
            PrescriptionDraftRecord.actor_id == patient_actor_id,
        )
        record = await self._session.scalar(statement)
        if record is None:
            raise PrescriptionDraftNotFoundError("prescription draft not found")
        return record

    async def list_reviews_for_drafts(
        self,
        *,
        tenant_id: str,
        draft_ids: tuple[uuid.UUID, ...],
        doctor_actor_id: str | None,
    ) -> list[PrescriptionDraftReview]:
        if not draft_ids:
            return []
        statement = (
            select(PrescriptionDraftReview)
            .where(
                PrescriptionDraftReview.tenant_id == tenant_id,
                PrescriptionDraftReview.prescription_draft_id.in_(draft_ids),
            )
            .order_by(PrescriptionDraftReview.reviewed_at.desc(), PrescriptionDraftReview.id.desc())
            .limit(100)
        )
        if doctor_actor_id is not None:
            statement = statement.where(PrescriptionDraftReview.doctor_actor_id == doctor_actor_id)
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
    ) -> PrescriptionDraftReview:
        """Append a review while locking the exact encrypted draft revision."""

        draft = await self._session.scalar(
            select(PrescriptionDraftRecord)
            .where(
                PrescriptionDraftRecord.id == draft_id,
                PrescriptionDraftRecord.tenant_id == tenant_id,
                PrescriptionDraftRecord.actor_id == patient_actor_id,
            )
            .with_for_update()
        )
        if draft is None:
            raise PrescriptionDraftNotFoundError("prescription draft not found")
        latest_revision = await self._session.scalar(
            select(func.max(PrescriptionDraftReview.revision)).where(
                PrescriptionDraftReview.tenant_id == tenant_id,
                PrescriptionDraftReview.prescription_draft_id == draft_id,
                PrescriptionDraftReview.doctor_actor_id == doctor_actor_id,
            )
        )
        record = PrescriptionDraftReview(
            tenant_id=tenant_id,
            prescription_draft_id=draft.id,
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
