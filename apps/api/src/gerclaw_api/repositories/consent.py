"""Tenant-scoped persistence and enforcement for patient access grants."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import PatientAccessGrant, User

ResourceScope = Literal[
    "health_profile_read",
    "cga_report_read",
    "prescription_draft_review",
]


class PatientAccessGrantNotFoundError(RuntimeError):
    """The caller cannot learn whether the patient or grant exists."""


class PatientAccessGrantConflictError(RuntimeError):
    """A stale patient revoke/renew request cannot overwrite a newer record."""


class SqlAlchemyPatientAccessGrantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def require_active_doctor(self, *, tenant_id: str, actor_id: str) -> None:
        statement = select(User.id).where(
            User.tenant_id == tenant_id,
            User.external_id == actor_id,
            User.role == "doctor",
            User.is_active.is_(True),
        )
        if await self._session.scalar(statement) is None:
            raise PatientAccessGrantNotFoundError(actor_id)

    async def grant(
        self,
        *,
        tenant_id: str,
        patient_actor_id: str,
        doctor_actor_id: str,
        resource_scope: ResourceScope,
        expires_at: datetime,
    ) -> PatientAccessGrant:
        statement = (
            select(PatientAccessGrant)
            .where(
                PatientAccessGrant.tenant_id == tenant_id,
                PatientAccessGrant.patient_actor_id == patient_actor_id,
                PatientAccessGrant.doctor_actor_id == doctor_actor_id,
                PatientAccessGrant.resource_scope == resource_scope,
            )
            .with_for_update()
        )
        record = cast(PatientAccessGrant | None, await self._session.scalar(statement))
        if record is None:
            record = PatientAccessGrant(
                tenant_id=tenant_id,
                patient_actor_id=patient_actor_id,
                doctor_actor_id=doctor_actor_id,
                resource_scope=resource_scope,
                expires_at=expires_at,
                status="active",
                revision=1,
            )
            self._session.add(record)
        else:
            record.expires_at = expires_at
            record.status = "active"
            record.revoked_at = None
            record.revision += 1
        await self._session.flush()
        return record

    async def list_for_patient(
        self, *, tenant_id: str, patient_actor_id: str
    ) -> list[PatientAccessGrant]:
        statement = (
            select(PatientAccessGrant)
            .where(
                PatientAccessGrant.tenant_id == tenant_id,
                PatientAccessGrant.patient_actor_id == patient_actor_id,
            )
            .order_by(PatientAccessGrant.granted_at.desc(), PatientAccessGrant.id.desc())
            .limit(100)
        )
        return list((await self._session.scalars(statement)).all())

    async def list_active_for_doctor(
        self, *, tenant_id: str, doctor_actor_id: str
    ) -> list[PatientAccessGrant]:
        """Return only the doctor's live grants, with no patient profile join."""

        statement = (
            select(PatientAccessGrant)
            .where(
                PatientAccessGrant.tenant_id == tenant_id,
                PatientAccessGrant.doctor_actor_id == doctor_actor_id,
                PatientAccessGrant.status == "active",
                PatientAccessGrant.expires_at > datetime.now(UTC),
            )
            .order_by(
                PatientAccessGrant.patient_actor_id.asc(),
                PatientAccessGrant.resource_scope.asc(),
                PatientAccessGrant.id.asc(),
            )
            .limit(300)
        )
        return list((await self._session.scalars(statement)).all())

    async def revoke(
        self,
        *,
        grant_id: uuid.UUID,
        tenant_id: str,
        patient_actor_id: str,
        expected_revision: int,
    ) -> PatientAccessGrant:
        statement = (
            select(PatientAccessGrant)
            .where(
                PatientAccessGrant.id == grant_id,
                PatientAccessGrant.tenant_id == tenant_id,
                PatientAccessGrant.patient_actor_id == patient_actor_id,
            )
            .with_for_update()
        )
        record = cast(PatientAccessGrant | None, await self._session.scalar(statement))
        if record is None:
            raise PatientAccessGrantNotFoundError(str(grant_id))
        if record.revision != expected_revision:
            raise PatientAccessGrantConflictError(str(grant_id))
        if record.status == "active":
            record.status = "revoked"
            record.revoked_at = datetime.now(UTC)
            record.revision += 1
        return record

    async def require_active_grant(
        self,
        *,
        tenant_id: str,
        patient_actor_id: str,
        doctor_actor_id: str,
        resource_scope: ResourceScope,
    ) -> None:
        statement = select(PatientAccessGrant.id).where(
            PatientAccessGrant.tenant_id == tenant_id,
            PatientAccessGrant.patient_actor_id == patient_actor_id,
            PatientAccessGrant.doctor_actor_id == doctor_actor_id,
            PatientAccessGrant.resource_scope == resource_scope,
            PatientAccessGrant.status == "active",
            PatientAccessGrant.expires_at > datetime.now(UTC),
        )
        if await self._session.scalar(statement) is None:
            raise PatientAccessGrantNotFoundError(patient_actor_id)
