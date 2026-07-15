"""Authenticated deterministic PHQ-9 assessment endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import AuthContext, require_cga_read, require_cga_write
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.cga.models import (
    CgaAnswerRequest,
    CgaAssessmentRead,
    CgaCompleteRequest,
    CgaQuestionRead,
    CgaReportRead,
    CgaScaleRead,
    CgaScalesRead,
    CgaStartRequest,
)
from gerclaw_api.modules.cga.phq9 import PHQ9_OPTIONS, PHQ9_QUESTIONS, PHQ9_VERSION
from gerclaw_api.repositories.cga import CgaAssessmentNotFoundError, SqlAlchemyCgaRepository
from gerclaw_api.services.cga_service import CgaAssessmentConflictError, CgaService

router = APIRouter(prefix="/cga", tags=["cga"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ReadIdentity = Annotated[AuthContext, Depends(require_cga_read)]
WriteIdentity = Annotated[AuthContext, Depends(require_cga_write)]


@router.get("/scales", response_model=CgaScalesRead)
async def list_scales(identity: ReadIdentity) -> CgaScalesRead:
    """Expose only server-supported, versioned definitions."""

    del identity
    questions = [
        CgaQuestionRead(
            id=item.id,
            position=item.position,
            text=item.text,
            sensitive_prefix=item.sensitive_prefix,
            options=list(PHQ9_OPTIONS),
        )
        for item in PHQ9_QUESTIONS
    ]
    return CgaScalesRead(
        scales=[
            CgaScaleRead(
                id="phq9",
                version=PHQ9_VERSION,
                name="PHQ-9",
                description="过去两周抑郁症状筛查量表",
                questions=questions,
            )
        ]
    )


@router.post("/assessments", response_model=CgaAssessmentRead, status_code=status.HTTP_201_CREATED)
async def start_assessment(
    payload: CgaStartRequest, session: SessionDependency, identity: WriteIdentity
) -> CgaAssessmentRead:
    """Start a server-owned PHQ-9 state machine for the current principal."""

    del payload
    result = await CgaService(SqlAlchemyCgaRepository(session)).start(
        tenant_id=identity.tenant_id, actor_id=identity.actor_id
    )
    await session.commit()
    return result


@router.get("/assessments/{assessment_id}", response_model=CgaAssessmentRead)
async def get_assessment(
    assessment_id: uuid.UUID, session: SessionDependency, identity: ReadIdentity
) -> CgaAssessmentRead:
    try:
        return await CgaService(SqlAlchemyCgaRepository(session)).get(
            assessment_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except CgaAssessmentNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "CGA_NOT_FOUND"}) from error


@router.post("/assessments/{assessment_id}/answers", response_model=CgaAssessmentRead)
async def answer_assessment(
    assessment_id: uuid.UUID,
    payload: CgaAnswerRequest,
    session: SessionDependency,
    identity: WriteIdentity,
) -> CgaAssessmentRead:
    service = CgaService(SqlAlchemyCgaRepository(session))
    try:
        result = await service.answer(
            assessment_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            expected_revision=payload.expected_revision,
            question_id=payload.question_id,
            score=payload.score,
        )
    except CgaAssessmentNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "CGA_NOT_FOUND"}) from error
    except CgaAssessmentConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "CGA_CONFLICT"}) from error
    await session.commit()
    return result


@router.post("/assessments/{assessment_id}/complete", response_model=CgaAssessmentRead)
async def complete_assessment(
    assessment_id: uuid.UUID,
    payload: CgaCompleteRequest,
    session: SessionDependency,
    identity: WriteIdentity,
) -> CgaAssessmentRead:
    service = CgaService(SqlAlchemyCgaRepository(session))
    try:
        result = await service.complete(
            assessment_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            expected_revision=payload.expected_revision,
        )
    except CgaAssessmentNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "CGA_NOT_FOUND"}) from error
    except CgaAssessmentConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "CGA_CONFLICT"}) from error
    await session.commit()
    return result


@router.get("/assessments/{assessment_id}/report", response_model=CgaReportRead)
async def get_assessment_report(
    assessment_id: uuid.UUID, session: SessionDependency, identity: ReadIdentity
) -> CgaReportRead:
    try:
        return await CgaService(SqlAlchemyCgaRepository(session)).report(
            assessment_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except CgaAssessmentNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "CGA_NOT_FOUND"}) from error
    except CgaAssessmentConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "CGA_REPORT_NOT_READY"}) from error
