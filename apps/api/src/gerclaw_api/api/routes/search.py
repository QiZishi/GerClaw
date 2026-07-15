"""Authenticated online medical evidence search with PHI-free Trace capture."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import AuthContext, require_search_read
from gerclaw_api.dependencies import get_database_session, get_trace_service
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import TraceEventCreate, TraceFinishRequest, TraceStartRequest
from gerclaw_api.middleware import set_active_trace
from gerclaw_api.modules.search import (
    ProductionSearchModule,
    SearchAttempt,
    SearchResult,
    SearchStatus,
    SearchUnavailableError,
    capture_search_attempts,
)
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.trace_service import TraceConflictError, TraceService

router = APIRouter(prefix="/search", tags=["search"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
SearchReadIdentity = Annotated[AuthContext, Depends(require_search_read)]


class SearchQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4_000)
    max_results: int = Field(default=5, ge=1, le=10)
    domain: Literal["general", "health", "academic"] = "health"

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query cannot contain only whitespace")
        return normalized


class SearchExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: AnyHttpUrl


class SearchQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    results: list[SearchResult] = Field(max_length=10)


class SearchExtractResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    content: str = Field(min_length=1, max_length=100_000)


def _trace_service(request: Request, session: SessionDependency) -> TraceService:
    return get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )


TraceServiceDependency = Annotated[TraceService, Depends(_trace_service)]


def _search_module(request: Request) -> ProductionSearchModule:
    return cast(ProductionSearchModule, request.app.state.search_runtime.module)


SearchModuleDependency = Annotated[ProductionSearchModule, Depends(_search_module)]


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


def _fingerprint(request: Request, payload: BaseModel) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    key = request.app.state.settings.auth_jwt_secret.get_secret_value().encode()
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


async def _start_trace(
    *,
    request: Request,
    service: TraceService,
    identity: AuthContext,
    execution_type: str,
    operation: str,
    request_fingerprint: str,
) -> tuple[str, bool]:
    trace_id = str(request.state.trace_id)
    set_active_trace(request.scope, trace_id)
    result = await service.start_trace_with_status(
        TraceStartRequest(
            execution_type=execution_type,
            attributes={
                "module": "search",
                "operation": operation,
                "request_fingerprint": request_fingerprint,
            },
        ),
        str(request.state.request_id),
        trace_id=trace_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    if result.created:
        return trace_id, False
    if result.trace.status == TraceStatus.COMPLETED.value:
        return trace_id, True
    if result.trace.status == TraceStatus.RUNNING.value:
        raise TraceConflictError("the search for this trace identifier is still running")
    raise SearchUnavailableError(
        "the previous search attempt did not complete; retry with a new trace identifier"
    )


async def _append_attempts(
    service: TraceService,
    *,
    tenant_id: str,
    trace_id: str,
    attempts: list[SearchAttempt],
) -> None:
    for attempt in attempts:
        succeeded = attempt.outcome in {"success", "empty"}
        await service.append_event(
            tenant_id,
            trace_id,
            TraceEventCreate(
                event_id=f"event_{uuid.uuid4().hex}",
                event_type=TraceEventType.SEARCH_QUERY,
                status=(TraceEventStatus.SUCCEEDED if succeeded else TraceEventStatus.FAILED),
                duration_ms=attempt.duration_ms,
                payload={
                    "module": "search",
                    "operation": attempt.operation,
                    "provider": attempt.provider,
                    "outcome": attempt.outcome,
                    "retry_index": attempt.retry_index,
                    "result_count": attempt.result_count,
                    "success": succeeded,
                },
            ),
            commit=False,
        )


async def _finish_success(
    service: TraceService,
    *,
    tenant_id: str,
    trace_id: str,
    operation: str,
    attempts: list[SearchAttempt],
    result_count: int,
    authority_levels: list[str],
) -> None:
    await _append_attempts(service, tenant_id=tenant_id, trace_id=trace_id, attempts=attempts)
    await service.finish_trace(
        tenant_id,
        trace_id,
        TraceFinishRequest(
            idempotency_key=f"finish_{uuid.uuid4().hex}",
            status=TraceStatus.COMPLETED,
            attributes={
                "module": "search",
                "operation": operation,
                "result_count": result_count,
                "authority_levels": authority_levels,
                "fallback": any(item.provider == "tavily" for item in attempts),
                "success": True,
            },
        ),
    )


async def _finish_failure(
    service: TraceService,
    *,
    tenant_id: str,
    trace_id: str,
    operation: str,
    attempts: list[SearchAttempt],
) -> None:
    try:
        await _append_attempts(service, tenant_id=tenant_id, trace_id=trace_id, attempts=attempts)
        await service.finish_trace(
            tenant_id,
            trace_id,
            TraceFinishRequest(
                idempotency_key=f"finish_{uuid.uuid4().hex}",
                status=TraceStatus.FAILED,
                error_code="search_unavailable",
                error_summary="online evidence operation failed",
                attributes={
                    "module": "search",
                    "operation": operation,
                    "result_count": 0,
                    "fallback": any(item.provider == "tavily" for item in attempts),
                    "success": False,
                },
            ),
        )
    except Exception:
        return


@router.post("/query", response_model=SearchQueryResponse)
async def search_query(
    payload: SearchQueryRequest,
    request: Request,
    module: SearchModuleDependency,
    service: TraceServiceDependency,
    identity: SearchReadIdentity,
) -> SearchQueryResponse:
    await _enforce_rate_limit(request, identity)
    request_fingerprint = _fingerprint(request, payload)
    trace_id, replay_completed = await _start_trace(
        request=request,
        service=service,
        identity=identity,
        execution_type="search.query",
        operation="query",
        request_fingerprint=request_fingerprint,
    )
    with capture_search_attempts() as attempts:
        try:
            results = await module.search(
                payload.query,
                max_results=payload.max_results,
                domain=payload.domain,
            )
            if not replay_completed:
                await _finish_success(
                    service,
                    tenant_id=identity.tenant_id,
                    trace_id=trace_id,
                    operation="query",
                    attempts=attempts,
                    result_count=len(results),
                    authority_levels=sorted({item.authority_level for item in results}),
                )
            return SearchQueryResponse(trace_id=trace_id, results=results)
        except BaseException:
            if not replay_completed:
                await _finish_failure(
                    service,
                    tenant_id=identity.tenant_id,
                    trace_id=trace_id,
                    operation="query",
                    attempts=attempts,
                )
            raise


@router.post("/extract", response_model=SearchExtractResponse)
async def extract_content(
    payload: SearchExtractRequest,
    request: Request,
    module: SearchModuleDependency,
    service: TraceServiceDependency,
    identity: SearchReadIdentity,
) -> SearchExtractResponse:
    await _enforce_rate_limit(request, identity)
    trace_id, replay_completed = await _start_trace(
        request=request,
        service=service,
        identity=identity,
        execution_type="search.extract",
        operation="extract",
        request_fingerprint=_fingerprint(request, payload),
    )
    with capture_search_attempts() as attempts:
        try:
            content = await module.extract_content(str(payload.url))
            if not replay_completed:
                await _finish_success(
                    service,
                    tenant_id=identity.tenant_id,
                    trace_id=trace_id,
                    operation="extract",
                    attempts=attempts,
                    result_count=1,
                    authority_levels=[],
                )
            return SearchExtractResponse(trace_id=trace_id, content=content)
        except BaseException:
            if not replay_completed:
                await _finish_failure(
                    service,
                    tenant_id=identity.tenant_id,
                    trace_id=trace_id,
                    operation="extract",
                    attempts=attempts,
                )
            raise


@router.get("/status", response_model=SearchStatus)
async def search_status(
    request: Request,
    identity: SearchReadIdentity,
) -> SearchStatus:
    await _enforce_rate_limit(request, identity)
    return cast(SearchStatus, request.app.state.search_runtime.status())
