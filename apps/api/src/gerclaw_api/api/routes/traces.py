"""Authenticated, tenant-scoped execution Trace and feedback endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    require_feedback_write,
    require_trace_read,
    require_trace_write,
)
from gerclaw_api.dependencies import get_database_session, get_trace_service
from gerclaw_api.domain.trace_schemas import (
    TRACE_ID_PATTERN,
    FeedbackCreate,
    FeedbackRead,
    TraceDetail,
    TraceEventCreate,
    TraceEventRead,
    TraceFinishRequest,
    TraceRead,
    TraceStartRequest,
)
from gerclaw_api.middleware import set_active_trace
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.trace_service import TraceService

router = APIRouter(tags=["observability"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
TraceReadIdentity = Annotated[AuthContext, Depends(require_trace_read)]
TraceWriteIdentity = Annotated[AuthContext, Depends(require_trace_write)]
FeedbackWriteIdentity = Annotated[AuthContext, Depends(require_feedback_write)]


def _trace_service(request: Request, session: SessionDependency) -> TraceService:
    return get_trace_service(
        session,
        max_events_per_trace=request.app.state.settings.max_events_per_trace,
    )


TraceServiceDependency = Annotated[TraceService, Depends(_trace_service)]
TraceIdPath = Annotated[str, Path(pattern=TRACE_ID_PATTERN)]


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


@router.post("/traces", response_model=TraceRead, status_code=status.HTTP_201_CREATED)
async def start_trace(
    payload: TraceStartRequest,
    request: Request,
    service: TraceServiceDependency,
    identity: TraceWriteIdentity,
) -> TraceRead:
    """Start/replay one execution using only verified tenant and actor claims."""

    await _enforce_rate_limit(request, identity)
    trace_id = str(request.state.trace_id)
    trace = await service.start_trace(
        payload,
        request.state.request_id,
        trace_id=trace_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    set_active_trace(request.scope, trace.trace_id)
    return TraceRead.model_validate(trace)


@router.get("/traces/{trace_id}", response_model=TraceDetail)
async def get_trace(
    trace_id: TraceIdPath,
    request: Request,
    service: TraceServiceDependency,
    identity: TraceReadIdentity,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TraceDetail:
    """Return a Trace and one bounded cursor page of ordered events."""

    set_active_trace(request.scope, trace_id)
    await _enforce_rate_limit(request, identity)
    trace = await service.get_trace(identity.tenant_id, trace_id)
    events, next_cursor = await service.list_events(
        identity.tenant_id,
        trace_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return TraceDetail(
        **TraceRead.model_validate(trace).model_dump(),
        events=[TraceEventRead.model_validate(event) for event in events],
        next_event_cursor=next_cursor,
    )


@router.post(
    "/traces/{trace_id}/events",
    response_model=TraceEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def append_trace_event(
    trace_id: TraceIdPath,
    payload: TraceEventCreate,
    request: Request,
    service: TraceServiceDependency,
    identity: TraceWriteIdentity,
) -> TraceEventRead:
    """Append/replay one typed, idempotent, allowlisted audit event."""

    set_active_trace(request.scope, trace_id)
    await _enforce_rate_limit(request, identity)
    event = await service.append_event(identity.tenant_id, trace_id, payload)
    return TraceEventRead.model_validate(event)


@router.post("/traces/{trace_id}/finish", response_model=TraceRead)
async def finish_trace(
    trace_id: TraceIdPath,
    payload: TraceFinishRequest,
    request: Request,
    service: TraceServiceDependency,
    identity: TraceWriteIdentity,
) -> TraceRead:
    """Idempotently transition a tenant-owned Trace to one terminal state."""

    set_active_trace(request.scope, trace_id)
    await _enforce_rate_limit(request, identity)
    trace = await service.finish_trace(identity.tenant_id, trace_id, payload)
    return TraceRead.model_validate(trace)


@router.post("/feedback", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackCreate,
    request: Request,
    service: TraceServiceDependency,
    identity: FeedbackWriteIdentity,
) -> FeedbackRead:
    """Store encrypted feedback from the authenticated owner of a Trace."""

    set_active_trace(request.scope, payload.trace_id)
    await _enforce_rate_limit(request, identity)
    feedback = await service.submit_feedback(
        payload,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    return FeedbackRead.model_validate(feedback)
