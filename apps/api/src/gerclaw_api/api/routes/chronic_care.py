"""Authenticated chronic-care ledger endpoints without clinical interpretation."""

from __future__ import annotations

import json
import uuid
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    require_chronic_care_read,
    require_chronic_care_write,
)
from gerclaw_api.dependencies import get_database_session, get_trace_service
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import (
    TraceEventCreate,
    TraceFinishRequest,
    TraceStartRequest,
    bounded_trace_duration_ms,
)
from gerclaw_api.middleware import set_active_trace
from gerclaw_api.modules.chronic_care.models import (
    ChronicConditionCreateRequest,
    ChronicConditionListRead,
    ChronicConditionRead,
    ChronicMeasurementCreateRequest,
    ChronicMeasurementListRead,
    ChronicMeasurementRead,
    ChronicTrendListRead,
)
from gerclaw_api.repositories.chronic_care import (
    ChronicCareNotFoundError,
    SqlAlchemyChronicCareRepository,
)
from gerclaw_api.services.chronic_care_service import ChronicCareConflictError, ChronicCareService
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.trace_service import TraceConflictError, TraceService

router = APIRouter(prefix="/chronic-care", tags=["chronic-care"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ReadIdentity = Annotated[AuthContext, Depends(require_chronic_care_read)]
WriteIdentity = Annotated[AuthContext, Depends(require_chronic_care_write)]


def _service(session: AsyncSession) -> ChronicCareService:
    return ChronicCareService(SqlAlchemyChronicCareRepository(session))


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


def _trace_service(request: Request, session: SessionDependency) -> TraceService:
    return get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )


TraceServiceDependency = Annotated[TraceService, Depends(_trace_service)]


def _request_fingerprint(
    request: Request, payload: ChronicConditionCreateRequest | ChronicMeasurementCreateRequest
) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    from gerclaw_api.security import audit_hmac_digest

    return audit_hmac_digest(
        request.app.state.settings.auth_jwt_secret.get_secret_value().encode(), canonical.encode()
    )


async def _start_write_trace(
    *,
    request: Request,
    traces: TraceService,
    identity: AuthContext,
    operation: str,
    payload: ChronicConditionCreateRequest | ChronicMeasurementCreateRequest,
) -> tuple[str, float]:
    trace_id = str(request.state.trace_id)
    set_active_trace(request.scope, trace_id)
    result = await traces.start_trace_with_status(
        TraceStartRequest(
            execution_type="chronic_care.ledger",
            attributes={
                "feature": "chronic_care",
                "module": "chronic_care",
                "operation": operation,
                "request_fingerprint": _request_fingerprint(request, payload),
                "version": "chronic-care-v1",
            },
        ),
        str(request.state.request_id),
        trace_id=trace_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        commit=False,
    )
    if not result.created:
        raise TraceConflictError("chronic-care trace is already in use")
    return trace_id, monotonic()


async def _finish_write_trace(
    *,
    traces: TraceService,
    tenant_id: str,
    trace_id: str,
    operation: str,
    started_at: float,
) -> None:
    suffix = trace_id.removeprefix("trace_")
    await traces.append_event(
        tenant_id,
        trace_id,
        TraceEventCreate(
            event_id=f"event_{suffix}_{operation}",
            event_type=TraceEventType.CHRONIC_CARE,
            status=TraceEventStatus.SUCCEEDED,
            payload={
                "feature": "chronic_care",
                "operation": operation,
                "version": "chronic-care-v1",
                "event_count": 1,
                "outcome": "recorded",
                "success": True,
            },
            duration_ms=bounded_trace_duration_ms(monotonic() - started_at),
        ),
        commit=False,
    )
    await traces.finish_trace(
        tenant_id,
        trace_id,
        TraceFinishRequest(
            idempotency_key=f"finish_{suffix}_{operation}",
            status=TraceStatus.COMPLETED,
            attributes={
                "feature": "chronic_care",
                "module": "chronic_care",
                "operation": operation,
                "result_code": "recorded",
                "version": "chronic-care-v1",
            },
        ),
        commit=False,
    )


@router.post(
    "/conditions", response_model=ChronicConditionRead, status_code=status.HTTP_201_CREATED
)
async def create_condition(
    payload: ChronicConditionCreateRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> ChronicConditionRead:
    """Append one self-reported condition; it is not a clinical confirmation."""

    await _enforce_rate_limit(request, identity)
    try:
        trace_id, started_at = await _start_write_trace(
            request=request,
            traces=traces,
            identity=identity,
            operation="create_condition",
            payload=payload,
        )
    except TraceConflictError as error:
        raise HTTPException(
            status_code=409, detail={"code": "CHRONIC_CARE_TRACE_CONFLICT"}
        ) from error
    result = await _service(session).create_condition(
        payload, tenant_id=identity.tenant_id, actor_id=identity.actor_id
    )
    await _finish_write_trace(
        traces=traces,
        tenant_id=identity.tenant_id,
        trace_id=trace_id,
        operation="create_condition",
        started_at=started_at,
    )
    await session.commit()
    return result


@router.get("/conditions", response_model=ChronicConditionListRead)
async def list_conditions(
    session: SessionDependency,
    identity: ReadIdentity,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ChronicConditionListRead:
    return await _service(session).list_conditions(
        tenant_id=identity.tenant_id, actor_id=identity.actor_id, limit=limit
    )


@router.post(
    "/conditions/{condition_id}/measurements",
    response_model=ChronicMeasurementRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_measurement(
    condition_id: uuid.UUID,
    payload: ChronicMeasurementCreateRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> ChronicMeasurementRead:
    """Append a user-recorded measurement without evaluating it clinically."""

    await _enforce_rate_limit(request, identity)
    try:
        trace_id, started_at = await _start_write_trace(
            request=request,
            traces=traces,
            identity=identity,
            operation="create_measurement",
            payload=payload,
        )
        result = await _service(session).create_measurement(
            condition_id,
            payload,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
        )
    except ChronicCareNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "CHRONIC_CARE_NOT_FOUND"}) from error
    except ChronicCareConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "CHRONIC_CARE_CONFLICT"}) from error
    except TraceConflictError as error:
        raise HTTPException(
            status_code=409, detail={"code": "CHRONIC_CARE_TRACE_CONFLICT"}
        ) from error
    await _finish_write_trace(
        traces=traces,
        tenant_id=identity.tenant_id,
        trace_id=trace_id,
        operation="create_measurement",
        started_at=started_at,
    )
    await session.commit()
    return result


@router.get("/conditions/{condition_id}/measurements", response_model=ChronicMeasurementListRead)
async def list_measurements(
    condition_id: uuid.UUID,
    session: SessionDependency,
    identity: ReadIdentity,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ChronicMeasurementListRead:
    try:
        return await _service(session).list_measurements(
            condition_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            limit=limit,
        )
    except ChronicCareNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "CHRONIC_CARE_NOT_FOUND"}) from error


@router.get("/conditions/{condition_id}/trends", response_model=ChronicTrendListRead)
async def list_trends(
    condition_id: uuid.UUID,
    session: SessionDependency,
    identity: ReadIdentity,
) -> ChronicTrendListRead:
    try:
        return await _service(session).trends(
            condition_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ChronicCareNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "CHRONIC_CARE_NOT_FOUND"}) from error
