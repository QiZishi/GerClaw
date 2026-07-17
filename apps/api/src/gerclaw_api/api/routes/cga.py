"""Authenticated deterministic CGA assessment endpoints."""

from __future__ import annotations

import json
import uuid
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import AuthContext, require_cga_read, require_cga_write
from gerclaw_api.dependencies import get_database_session, get_trace_service
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import TraceEventCreate, TraceFinishRequest, TraceStartRequest
from gerclaw_api.middleware import set_active_trace
from gerclaw_api.modules.cga.models import (
    CgaActiveAssessmentsRead,
    CgaAnswerRequest,
    CgaAssessmentRead,
    CgaComparisonRead,
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
from gerclaw_api.modules.risk_alert.service import RiskAlertService
from gerclaw_api.repositories.cga import CgaAssessmentNotFoundError, SqlAlchemyCgaRepository
from gerclaw_api.repositories.risk_alert import SqlAlchemyRiskAlertRepository
from gerclaw_api.security import audit_hmac_digest
from gerclaw_api.services.cga_service import CgaAssessmentConflictError, CgaService
from gerclaw_api.services.trace_service import TraceConflictError, TraceService

router = APIRouter(prefix="/cga", tags=["cga"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ReadIdentity = Annotated[AuthContext, Depends(require_cga_read)]
WriteIdentity = Annotated[AuthContext, Depends(require_cga_write)]


def _trace_service(request: Request, session: SessionDependency) -> TraceService:
    return get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )


TraceServiceDependency = Annotated[TraceService, Depends(_trace_service)]


def _request_fingerprint(
    request: Request,
    payload: CgaStartRequest | CgaAnswerRequest | CgaCompleteRequest,
) -> str:
    """Bind a write request without retaining screening answers in audit storage."""

    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return audit_hmac_digest(
        request.app.state.settings.auth_jwt_secret.get_secret_value().encode(),
        canonical.encode(),
    )


async def _start_write_trace(
    *,
    request: Request,
    traces: TraceService,
    identity: AuthContext,
    scale_id: str,
    operation: str,
    payload: CgaStartRequest | CgaAnswerRequest | CgaCompleteRequest,
) -> tuple[str, float]:
    trace_id = str(request.state.trace_id)
    set_active_trace(request.scope, trace_id)
    started = monotonic()
    result = await traces.start_trace_with_status(
        TraceStartRequest(
            execution_type="cga.assessment",
            attributes={
                "feature": "cga",
                "module": "cga",
                "operation": operation,
                "request_fingerprint": _request_fingerprint(request, payload),
                "scale": scale_id,
            },
        ),
        str(request.state.request_id),
        trace_id=trace_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        commit=False,
    )
    if not result.created:
        raise TraceConflictError("CGA assessment trace is already in use")
    return trace_id, started


async def _finish_write_trace(
    *,
    traces: TraceService,
    tenant_id: str,
    trace_id: str,
    operation: str,
    elapsed_started_at: float,
    result: CgaAssessmentRead,
) -> None:
    trace_suffix = trace_id.removeprefix("trace_")
    await traces.append_event(
        tenant_id,
        trace_id,
        TraceEventCreate(
            event_id=f"event_{trace_suffix}_{operation}",
            event_type=TraceEventType.CGA_ASSESSMENT,
            status=TraceEventStatus.SUCCEEDED,
            payload={
                "feature": "cga",
                "operation": operation,
                "scale": result.scale_id,
                "version": result.definition_version,
                "answered_count": result.answered_count,
                "outcome": result.status,
                "success": True,
            },
            duration_ms=max(0, int((monotonic() - elapsed_started_at) * 1_000)),
        ),
        commit=False,
    )
    await traces.finish_trace(
        tenant_id,
        trace_id,
        TraceFinishRequest(
            idempotency_key=f"finish_{trace_suffix}_{operation}",
            status=TraceStatus.COMPLETED,
            attributes={
                "feature": "cga",
                "module": "cga",
                "operation": operation,
                "result_code": result.status,
                "scale": result.scale_id,
                "version": result.definition_version,
            },
        ),
        commit=False,
    )


def _risk_source_fingerprint(request: Request, *, assessment_id: uuid.UUID, kind: str) -> str:
    """Deduplicate a sensitive source without storing its assessment identifier."""

    material = f"risk-alert:v1:cga:{kind}:{assessment_id}".encode()
    return audit_hmac_digest(
        request.app.state.settings.auth_jwt_secret.get_secret_value().encode(), material
    )


async def _sync_risk_alerts(
    *,
    request: Request,
    session: AsyncSession,
    identity: AuthContext,
    result: CgaAssessmentRead,
) -> None:
    """Persist only server-derived CGA safety signals in the current transaction."""

    if not (
        result.risk.requires_immediate_safety_assessment or result.risk.high_severity_follow_up
    ):
        return
    await RiskAlertService(SqlAlchemyRiskAlertRepository(session)).sync_cga_risk(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        immediate_source_fingerprint=_risk_source_fingerprint(
            request, assessment_id=result.assessment_id, kind="immediate"
        ),
        follow_up_source_fingerprint=_risk_source_fingerprint(
            request, assessment_id=result.assessment_id, kind="follow_up"
        ),
        risk=result.risk,
    )


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
    payload: CgaStartRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> CgaAssessmentRead:
    """Start a server-owned deterministic assessment for the current principal."""

    try:
        trace_id, started_at = await _start_write_trace(
            request=request,
            traces=traces,
            identity=identity,
            scale_id=payload.scale_id,
            operation="start",
            payload=payload,
        )
    except TraceConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "CGA_TRACE_CONFLICT"}) from error
    result = await CgaService(SqlAlchemyCgaRepository(session)).start(
        tenant_id=identity.tenant_id, actor_id=identity.actor_id, scale_id=payload.scale_id
    )
    await _sync_risk_alerts(request=request, session=session, identity=identity, result=result)
    await _finish_write_trace(
        traces=traces,
        tenant_id=identity.tenant_id,
        trace_id=trace_id,
        operation="start",
        elapsed_started_at=started_at,
        result=result,
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
        tenant_id=identity.tenant_id, actor_id=identity.actor_id, limit=20
    )


@router.get("/assessments/{assessment_id}/comparison", response_model=CgaComparisonRead)
async def get_assessment_comparison(
    assessment_id: uuid.UUID, session: SessionDependency, identity: ReadIdentity
) -> CgaComparisonRead:
    """Return a caller-owned, same-version numerical screening comparison only."""

    try:
        return await CgaService(SqlAlchemyCgaRepository(session)).comparison(
            assessment_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except CgaAssessmentNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "CGA_NOT_FOUND"}) from error
    except CgaAssessmentConflictError as error:
        raise HTTPException(
            status_code=409, detail={"code": "CGA_COMPARISON_UNAVAILABLE"}
        ) from error


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
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> CgaAssessmentRead:
    service = CgaService(SqlAlchemyCgaRepository(session))
    try:
        current = await service.get(
            assessment_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
        trace_id, started_at = await _start_write_trace(
            request=request,
            traces=traces,
            identity=identity,
            scale_id=current.scale_id,
            operation="answer",
            payload=payload,
        )
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
    except TraceConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "CGA_TRACE_CONFLICT"}) from error
    await _sync_risk_alerts(request=request, session=session, identity=identity, result=result)
    await _finish_write_trace(
        traces=traces,
        tenant_id=identity.tenant_id,
        trace_id=trace_id,
        operation="answer",
        elapsed_started_at=started_at,
        result=result,
    )
    await session.commit()
    return result


@router.post("/assessments/{assessment_id}/complete", response_model=CgaAssessmentRead)
async def complete_assessment(
    assessment_id: uuid.UUID,
    payload: CgaCompleteRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> CgaAssessmentRead:
    service = CgaService(SqlAlchemyCgaRepository(session))
    try:
        current = await service.get(
            assessment_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
        trace_id, started_at = await _start_write_trace(
            request=request,
            traces=traces,
            identity=identity,
            scale_id=current.scale_id,
            operation="complete",
            payload=payload,
        )
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
    except TraceConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "CGA_TRACE_CONFLICT"}) from error
    await _sync_risk_alerts(request=request, session=session, identity=identity, result=result)
    await _finish_write_trace(
        traces=traces,
        tenant_id=identity.tenant_id,
        trace_id=trace_id,
        operation="complete",
        elapsed_started_at=started_at,
        result=result,
    )
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
