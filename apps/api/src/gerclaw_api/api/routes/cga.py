"""Authenticated deterministic CGA assessment endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import AuthContext, require_cga_read, require_cga_write
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.cga.models import (
    CgaActiveAssessmentsRead,
    CgaAnswerRequest,
    CgaAssessmentRead,
    CgaCompleteRequest,
    CgaHistoryRead,
    CgaQuestionRead,
    CgaReportRead,
    CgaScaleRead,
    CgaScalesRead,
    CgaStartRequest,
)
from gerclaw_api.modules.cga.phq9 import PHQ9_OPTIONS, PHQ9_QUESTIONS, PHQ9_VERSION
from gerclaw_api.modules.cga.psqi import PSQI_QUESTIONS, PSQI_VERSION, psqi_options_for
from gerclaw_api.modules.cga.sas import SAS_OPTIONS, SAS_QUESTIONS, SAS_VERSION
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
    phq9_questions = [
        CgaQuestionRead(
            id=item.id,
            position=item.position,
            text=item.text,
            sensitive_prefix=item.sensitive_prefix,
            options=list(PHQ9_OPTIONS),
        )
        for item in PHQ9_QUESTIONS
    ]
    sas_questions = [
        CgaQuestionRead(
            id=item.id,
            position=item.position,
            text=item.text,
            options=list(SAS_OPTIONS),
        )
        for item in SAS_QUESTIONS
    ]
    psqi_questions = [
        CgaQuestionRead(
            id=item.id,
            position=item.position,
            text=item.text,
            input_kind=item.input_kind,
            options=list(psqi_options_for(item.id)),
        )
        for item in PSQI_QUESTIONS
    ]
    return CgaScalesRead(
        scales=[
            CgaScaleRead(
                id="phq9",
                version=PHQ9_VERSION,
                name="PHQ-9",
                description="过去两周抑郁症状筛查量表",
                question_count=len(phq9_questions),
                questions=phq9_questions,
            ),
            CgaScaleRead(
                id="sas",
                version=SAS_VERSION,
                name="SAS",
                description="最近一周焦虑症状筛查量表",
                question_count=len(sas_questions),
                questions=sas_questions,
            ),
            CgaScaleRead(
                id="psqi",
                version=PSQI_VERSION,
                name="PSQI",
                description="过去一个月睡眠质量筛查量表",
                question_count=len(psqi_questions),
                questions=psqi_questions,
            ),
        ]
    )


@router.post("/assessments", response_model=CgaAssessmentRead, status_code=status.HTTP_201_CREATED)
async def start_assessment(
    payload: CgaStartRequest, session: SessionDependency, identity: WriteIdentity
) -> CgaAssessmentRead:
    """Start a server-owned deterministic assessment for the current principal."""

    result = await CgaService(SqlAlchemyCgaRepository(session)).start(
        tenant_id=identity.tenant_id, actor_id=identity.actor_id, scale_id=payload.scale_id
    )
    await session.commit()
    return result


@router.get("/assessments", response_model=CgaHistoryRead)
async def list_assessment_history(
    session: SessionDependency,
    identity: ReadIdentity,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> CgaHistoryRead:
    """List only the caller's completed reports for personal comparison."""

    try:
        return await CgaService(SqlAlchemyCgaRepository(session)).history(
            tenant_id=identity.tenant_id, actor_id=identity.actor_id, limit=limit
        )
    except CgaAssessmentConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "CGA_HISTORY_UNAVAILABLE"}) from error


@router.get("/assessments/active", response_model=CgaActiveAssessmentsRead)
async def list_active_assessments(
    session: SessionDependency,
    identity: ReadIdentity,
) -> CgaActiveAssessmentsRead:
    """List only the caller's unfinished assessments for explicit resume UI."""

    return await CgaService(SqlAlchemyCgaRepository(session)).active(
        tenant_id=identity.tenant_id, actor_id=identity.actor_id, limit=3
    )


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
            supplemental_detail=payload.supplemental_detail,
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
