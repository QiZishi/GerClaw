"""Patient-controlled doctor read grants and their narrow clinical projections."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    authenticate,
    require_cga_read,
    require_clinical_intake_read,
    require_memory_read,
)
from gerclaw_api.database.models import PrescriptionDraftReview
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.cga.models import CgaHistoryRead
from gerclaw_api.modules.consent.models import (
    DoctorPatientAccessListRead,
    DoctorPatientAccessRead,
    DoctorPatientGrantScopeRead,
    PatientAccessGrantCreate,
    PatientAccessGrantListRead,
    PatientAccessGrantRead,
    PatientAccessGrantRevoke,
)
from gerclaw_api.modules.memory.models import HealthProfileRead
from gerclaw_api.modules.memory.runtime import create_memory_module
from gerclaw_api.modules.prescription.models import (
    DoctorPrescriptionDraftListRead,
    DoctorPrescriptionDraftRead,
    FivePrescriptionDraft,
    PrescriptionDraftReviewRead,
    PrescriptionDraftReviewRequest,
)
from gerclaw_api.repositories.cga import SqlAlchemyCgaRepository
from gerclaw_api.repositories.consent import (
    PatientAccessGrantConflictError,
    PatientAccessGrantNotFoundError,
    SqlAlchemyPatientAccessGrantRepository,
)
from gerclaw_api.repositories.memory import SqlAlchemyMemoryRepository
from gerclaw_api.repositories.prescription_draft import (
    PrescriptionDraftNotFoundError,
    SqlAlchemyPrescriptionDraftRepository,
)
from gerclaw_api.services.cga_service import CgaService
from gerclaw_api.services.model_router import FailoverChatModel

router = APIRouter(prefix="/access-grants", tags=["consent"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
Identity = Annotated[AuthContext, Depends(authenticate)]
DoctorMemoryIdentity = Annotated[AuthContext, Depends(require_memory_read)]
DoctorCgaIdentity = Annotated[AuthContext, Depends(require_cga_read)]
DoctorPrescriptionIdentity = Annotated[AuthContext, Depends(require_clinical_intake_read)]
PatientActorId = Annotated[str, Path(pattern=r"^usr_account_[a-f0-9]{32}$")]
_NO_SESSION = uuid.UUID(int=0)


def _require_patient(identity: AuthContext) -> None:
    if identity.account_role != "patient":
        raise HTTPException(status_code=403, detail={"code": "PATIENT_ACCOUNT_REQUIRED"})


def _require_doctor(identity: AuthContext) -> None:
    if identity.account_role != "doctor":
        raise HTTPException(status_code=403, detail={"code": "DOCTOR_ACCOUNT_REQUIRED"})


def _project(record: object) -> PatientAccessGrantRead:
    grant = PatientAccessGrantRead.model_validate(record)
    if grant.status == "active" and grant.expires_at <= datetime.now(UTC):
        return grant.model_copy(update={"status": "expired"})
    return grant


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "PATIENT_ACCESS_NOT_FOUND"})


def _review_read(record: PrescriptionDraftReview) -> PrescriptionDraftReviewRead:
    return PrescriptionDraftReviewRead(
        review_id=record.id,
        draft_id=record.prescription_draft_id,
        doctor_actor_id=record.doctor_actor_id,
        decision=record.decision,
        review_note=record.review_note,
        revision=record.revision,
        reviewed_at=record.reviewed_at,
    )


def _doctor_health_profile_projection(profile: HealthProfileRead) -> HealthProfileRead:
    """Doctors receive only facts already confirmed by the patient."""

    return profile.model_copy(
        update={"facts": [fact for fact in profile.facts if fact.status == "confirmed"]}
    )


@router.post("", response_model=PatientAccessGrantListRead, status_code=status.HTTP_201_CREATED)
async def grant_access(
    payload: PatientAccessGrantCreate,
    session: SessionDependency,
    identity: Identity,
) -> PatientAccessGrantListRead:
    """Let a patient grant only bounded read access to one active doctor."""

    _require_patient(identity)
    now = datetime.now(UTC)
    if payload.expires_at.tzinfo is None or not (
        now < payload.expires_at <= now + timedelta(days=365)
    ):
        raise HTTPException(status_code=422, detail={"code": "PATIENT_ACCESS_EXPIRY_INVALID"})
    repository = SqlAlchemyPatientAccessGrantRepository(session)
    try:
        await repository.require_active_doctor(
            tenant_id=identity.tenant_id, actor_id=payload.doctor_actor_id
        )
    except PatientAccessGrantNotFoundError as error:
        raise _not_found() from error
    records = [
        await repository.grant(
            tenant_id=identity.tenant_id,
            patient_actor_id=identity.actor_id,
            doctor_actor_id=payload.doctor_actor_id,
            resource_scope=resource_scope,
            expires_at=payload.expires_at,
        )
        for resource_scope in payload.resource_scopes
    ]
    await session.commit()
    return PatientAccessGrantListRead(items=[_project(record) for record in records])


@router.get("", response_model=PatientAccessGrantListRead)
async def list_my_grants(
    session: SessionDependency, identity: Identity
) -> PatientAccessGrantListRead:
    """List only grants owned by the authenticated patient."""

    _require_patient(identity)
    records = await SqlAlchemyPatientAccessGrantRepository(session).list_for_patient(
        tenant_id=identity.tenant_id, patient_actor_id=identity.actor_id
    )
    return PatientAccessGrantListRead(items=[_project(record) for record in records])


@router.get("/patients", response_model=DoctorPatientAccessListRead)
async def list_authorized_patients(
    session: SessionDependency, identity: Identity
) -> DoctorPatientAccessListRead:
    """List only patients that currently authorize this authenticated doctor."""

    _require_doctor(identity)
    repository = SqlAlchemyPatientAccessGrantRepository(session)
    try:
        await repository.require_active_doctor(
            tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except PatientAccessGrantNotFoundError as error:
        raise _not_found() from error
    records = await repository.list_active_for_doctor(
        tenant_id=identity.tenant_id, doctor_actor_id=identity.actor_id
    )
    by_patient: dict[str, list[DoctorPatientGrantScopeRead]] = {}
    for record in records:
        by_patient.setdefault(record.patient_actor_id, []).append(
            DoctorPatientGrantScopeRead(
                resource_scope=record.resource_scope,
                expires_at=record.expires_at,
            )
        )
    return DoctorPatientAccessListRead(
        items=[
            DoctorPatientAccessRead(patient_actor_id=patient_actor_id, grants=tuple(grants))
            for patient_actor_id, grants in by_patient.items()
        ]
    )


@router.post("/{grant_id}/revoke", response_model=PatientAccessGrantRead)
async def revoke_access(
    grant_id: uuid.UUID,
    payload: PatientAccessGrantRevoke,
    session: SessionDependency,
    identity: Identity,
) -> PatientAccessGrantRead:
    """Revoke one patient-owned grant with optimistic revision fencing."""

    _require_patient(identity)
    try:
        record = await SqlAlchemyPatientAccessGrantRepository(session).revoke(
            grant_id=grant_id,
            tenant_id=identity.tenant_id,
            patient_actor_id=identity.actor_id,
            expected_revision=payload.expected_revision,
        )
    except PatientAccessGrantNotFoundError as error:
        raise _not_found() from error
    except PatientAccessGrantConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "PATIENT_ACCESS_CONFLICT"}) from error
    await session.commit()
    return _project(record)


@router.get("/patients/{patient_actor_id}/health-profile", response_model=HealthProfileRead)
async def get_authorized_health_profile(
    patient_actor_id: PatientActorId,
    request: Request,
    session: SessionDependency,
    identity: DoctorMemoryIdentity,
) -> HealthProfileRead:
    """Read a patient's profile only after a current explicit grant."""

    _require_doctor(identity)
    grants = SqlAlchemyPatientAccessGrantRepository(session)
    try:
        await grants.require_active_grant(
            tenant_id=identity.tenant_id,
            patient_actor_id=patient_actor_id,
            doctor_actor_id=identity.actor_id,
            resource_scope="health_profile_read",
        )
    except PatientAccessGrantNotFoundError as error:
        raise _not_found() from error
    repository = SqlAlchemyMemoryRepository(session)
    user = await repository.get_user(tenant_id=identity.tenant_id, actor_id=patient_actor_id)
    if user is None:
        raise _not_found()
    model = request.app.state.agent_model
    if not isinstance(model, FailoverChatModel):
        raise HTTPException(status_code=503, detail={"code": "MEMORY_UNAVAILABLE"})
    module = create_memory_module(
        settings=request.app.state.settings,
        repository=repository,
        model=model,
        embedding_model=request.app.state.rag_runtime.embedding_model,
        vector_store=request.app.state.memory_store,
        tenant_id=identity.tenant_id,
        actor_id=patient_actor_id,
        user_id=user.id,
        session_id=_NO_SESSION,
        trace_id=str(request.state.trace_id),
    )
    return _doctor_health_profile_projection(await module.read_profile())


@router.get("/patients/{patient_actor_id}/cga-reports", response_model=CgaHistoryRead)
async def list_authorized_cga_reports(
    patient_actor_id: PatientActorId,
    session: SessionDependency,
    identity: DoctorCgaIdentity,
) -> CgaHistoryRead:
    """Read completed CGA report summaries, never active states or answers."""

    _require_doctor(identity)
    try:
        await SqlAlchemyPatientAccessGrantRepository(session).require_active_grant(
            tenant_id=identity.tenant_id,
            patient_actor_id=patient_actor_id,
            doctor_actor_id=identity.actor_id,
            resource_scope="cga_report_read",
        )
    except PatientAccessGrantNotFoundError as error:
        raise _not_found() from error
    return await CgaService(SqlAlchemyCgaRepository(session)).history(
        tenant_id=identity.tenant_id, actor_id=patient_actor_id, limit=20
    )


@router.get(
    "/patients/{patient_actor_id}/prescription-drafts",
    response_model=DoctorPrescriptionDraftListRead,
)
async def list_authorized_prescription_drafts(
    patient_actor_id: PatientActorId,
    session: SessionDependency,
    identity: DoctorPrescriptionIdentity,
) -> DoctorPrescriptionDraftListRead:
    """Read only review-only drafts after the patient's current grant."""

    _require_doctor(identity)
    grants = SqlAlchemyPatientAccessGrantRepository(session)
    try:
        await grants.require_active_grant(
            tenant_id=identity.tenant_id,
            patient_actor_id=patient_actor_id,
            doctor_actor_id=identity.actor_id,
            resource_scope="prescription_draft_review",
        )
    except PatientAccessGrantNotFoundError as error:
        raise _not_found() from error
    drafts_repository = SqlAlchemyPrescriptionDraftRepository(session)
    records = await drafts_repository.list_for_patient(
        tenant_id=identity.tenant_id, patient_actor_id=patient_actor_id, limit=20
    )
    reviews = await drafts_repository.list_reviews_for_drafts(
        tenant_id=identity.tenant_id,
        draft_ids=tuple(record.id for record in records),
        doctor_actor_id=identity.actor_id,
    )
    reviews_by_draft: dict[uuid.UUID, list[PrescriptionDraftReviewRead]] = {}
    for review in reviews:
        reviews_by_draft.setdefault(review.prescription_draft_id, []).append(_review_read(review))
    return DoctorPrescriptionDraftListRead(
        items=tuple(
            DoctorPrescriptionDraftRead(
                draft_id=record.id,
                intake_id=record.clinical_intake_id,
                created_at=record.created_at,
                draft=FivePrescriptionDraft.model_validate(record.content),
                reviews=tuple(reviews_by_draft.get(record.id, ())),
            )
            for record in records
        )
    )


@router.post(
    "/patients/{patient_actor_id}/prescription-drafts/{draft_id}/reviews",
    response_model=PrescriptionDraftReviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def append_authorized_prescription_review(
    patient_actor_id: PatientActorId,
    draft_id: uuid.UUID,
    payload: PrescriptionDraftReviewRequest,
    session: SessionDependency,
    identity: DoctorPrescriptionIdentity,
) -> PrescriptionDraftReviewRead:
    """Record a doctor's review; the underlying report remains non-executable."""

    _require_doctor(identity)
    try:
        await SqlAlchemyPatientAccessGrantRepository(session).require_active_grant(
            tenant_id=identity.tenant_id,
            patient_actor_id=patient_actor_id,
            doctor_actor_id=identity.actor_id,
            resource_scope="prescription_draft_review",
        )
        review = await SqlAlchemyPrescriptionDraftRepository(session).append_review(
            draft_id=draft_id,
            tenant_id=identity.tenant_id,
            patient_actor_id=patient_actor_id,
            doctor_actor_id=identity.actor_id,
            decision=payload.decision,
            review_note=payload.review_note,
        )
    except (PatientAccessGrantNotFoundError, PrescriptionDraftNotFoundError) as error:
        raise _not_found() from error
    await session.commit()
    return _review_read(review)
