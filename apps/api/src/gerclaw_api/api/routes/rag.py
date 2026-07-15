"""Authenticated local medical evidence retrieval with durable Trace capture."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import AuthContext, require_rag_read
from gerclaw_api.dependencies import get_database_session, get_trace_service
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import (
    TraceEventCreate,
    TraceFinishRequest,
    TraceStartRequest,
)
from gerclaw_api.metrics import RAG_RETRIEVAL_LATENCY, RAG_RETRIEVALS
from gerclaw_api.middleware import set_active_trace
from gerclaw_api.modules.rag.module import HybridRAGModule, RAGUnavailableError
from gerclaw_api.modules.rag.protocols import RAGFilters, RAGStatus, RetrievalResult
from gerclaw_api.security import audit_hmac_digest
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.trace_service import (
    TraceConflictError,
    TraceNotFoundError,
    TraceService,
)

LOGGER = logging.getLogger(__name__)
MEDICAL_DISCLAIMER = (
    "本接口返回本地医学知识库证据, 不构成诊断或治疗建议; "
    "如出现急危重症症状, 请立即就医或联系急救服务。"
)

router = APIRouter(prefix="/rag", tags=["rag"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
RAGReadIdentity = Annotated[AuthContext, Depends(require_rag_read)]


class RAGRetrieveRequest(BaseModel):
    """Bounded user query and allowlisted retrieval filters."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4_000)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: RAGFilters | None = None

    @field_validator("query")
    @classmethod
    def reject_blank_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must contain non-whitespace text")
        return normalized


class RAGRetrieveResponse(BaseModel):
    """Evidence-only response with a durable correlation identifier."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    results: list[RetrievalResult]
    medical_disclaimer: str = MEDICAL_DISCLAIMER


def _trace_service(request: Request, session: SessionDependency) -> TraceService:
    return get_trace_service(
        session,
        max_events_per_trace=request.app.state.settings.max_events_per_trace,
    )


TraceServiceDependency = Annotated[TraceService, Depends(_trace_service)]


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


def _rag_module(request: Request) -> HybridRAGModule:
    return cast(HybridRAGModule, request.app.state.rag_runtime.module)


RAGModuleDependency = Annotated[HybridRAGModule, Depends(_rag_module)]


def _request_fingerprint(payload: RAGRetrieveRequest, request: Request) -> str:
    """Keyed, non-reversible request identity for safe completed-request replay."""

    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    key = request.app.state.settings.auth_jwt_secret.get_secret_value().encode()
    return audit_hmac_digest(key, canonical.encode())


@router.post("/retrieve", response_model=RAGRetrieveResponse)
async def retrieve_evidence(
    payload: RAGRetrieveRequest,
    request: Request,
    module: RAGModuleDependency,
    service: TraceServiceDependency,
    identity: RAGReadIdentity,
) -> RAGRetrieveResponse:
    """Run dense+sparse retrieval and rerank while storing PHI-free audit metadata."""

    await _enforce_rate_limit(request, identity)
    trace_id = str(request.state.trace_id)
    set_active_trace(request.scope, trace_id)
    request_fingerprint = _request_fingerprint(payload, request)
    start_request = TraceStartRequest(
        execution_type="rag.retrieve",
        attributes={
            "module": "rag",
            "operation": "retrieve",
            "model": request.app.state.settings.embedding_model,
            "request_fingerprint": request_fingerprint,
        },
    )
    try:
        trace = await service.get_trace(identity.tenant_id, trace_id)
    except TraceNotFoundError:
        trace = await service.start_trace(
            start_request,
            str(request.state.request_id),
            trace_id=trace_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
        )
    else:
        if (
            trace.actor_id != identity.actor_id
            or trace.execution_type != start_request.execution_type
            or trace.attributes.get("request_fingerprint") != request_fingerprint
        ):
            raise TraceConflictError(
                "trace identifier was already used for another retrieval request"
            )
    replay_completed = trace.status == TraceStatus.COMPLETED.value
    if trace.status == TraceStatus.FAILED.value:
        raise RAGUnavailableError(
            "the previous retrieval attempt failed; retry with a new trace identifier"
        )
    if trace.status == TraceStatus.RUNNING.value and trace.request_id != str(
        request.state.request_id
    ):
        raise TraceConflictError("the retrieval for this trace identifier is still running")
    started = time.perf_counter()
    try:
        results = await module.retrieve(payload.query, top_k=payload.top_k, filters=payload.filters)
        duration_seconds = time.perf_counter() - started
        if replay_completed:
            RAG_RETRIEVALS.labels(outcome="replayed").inc()
            RAG_RETRIEVAL_LATENCY.observe(duration_seconds)
            return RAGRetrieveResponse(trace_id=trace_id, results=results)
        duration_ms = round(duration_seconds * 1_000)
        await service.append_event(
            identity.tenant_id,
            trace_id,
            TraceEventCreate(
                event_id=f"event_{uuid.uuid4().hex}",
                event_type=TraceEventType.RAG_RETRIEVE,
                status=TraceEventStatus.SUCCEEDED,
                duration_ms=duration_ms,
                payload={
                    "operation": "retrieve",
                    "provider": "siliconflow",
                    "model": request.app.state.settings.rerank_model,
                    "document_count": len({result.metadata["document_id"] for result in results}),
                    "document_ids": [result.metadata["document_id"] for result in results],
                    "chunk_ids": [result.metadata["chunk_id"] for result in results],
                    "scores": [round(result.score, 8) for result in results],
                    "duration_ms": duration_ms,
                    "success": True,
                },
            ),
        )
        await service.finish_trace(
            identity.tenant_id,
            trace_id,
            TraceFinishRequest(
                idempotency_key=f"finish_{uuid.uuid4().hex}",
                status=TraceStatus.COMPLETED,
                attributes={
                    "document_count": len({result.source for result in results}),
                    "citation_count": len(results),
                    "success": True,
                },
            ),
        )
        RAG_RETRIEVALS.labels(outcome="succeeded" if results else "empty").inc()
        RAG_RETRIEVAL_LATENCY.observe(duration_seconds)
        return RAGRetrieveResponse(trace_id=trace_id, results=results)
    except Exception as error:
        duration_seconds = time.perf_counter() - started
        RAG_RETRIEVALS.labels(outcome="failed").inc()
        RAG_RETRIEVAL_LATENCY.observe(duration_seconds)
        if replay_completed:
            LOGGER.exception("rag_replay_failed")
            raise RAGUnavailableError(
                "local medical evidence retrieval replay is unavailable"
            ) from error
        duration_ms = round(duration_seconds * 1_000)
        try:
            await service.append_event(
                identity.tenant_id,
                trace_id,
                TraceEventCreate(
                    event_id=f"event_{uuid.uuid4().hex}",
                    event_type=TraceEventType.RAG_RETRIEVE,
                    status=TraceEventStatus.FAILED,
                    duration_ms=duration_ms,
                    payload={
                        "operation": "retrieve",
                        "provider": "siliconflow",
                        "model": request.app.state.settings.rerank_model,
                        "duration_ms": duration_ms,
                        "success": False,
                    },
                ),
            )
            await service.finish_trace(
                identity.tenant_id,
                trace_id,
                TraceFinishRequest(
                    idempotency_key=f"finish_{uuid.uuid4().hex}",
                    status=TraceStatus.FAILED,
                    error_code="rag_unavailable",
                    error_summary="RAG retrieval failed",
                    attributes={"module": "rag", "operation": "retrieve", "success": False},
                ),
            )
        except Exception:
            LOGGER.exception("rag_failure_trace_persistence_failed")
        LOGGER.exception("rag_retrieval_failed")
        raise RAGUnavailableError("local medical evidence retrieval is unavailable") from error


@router.get("/status", response_model=RAGStatus)
async def rag_status(
    request: Request,
    module: RAGModuleDependency,
    identity: RAGReadIdentity,
) -> RAGStatus:
    """Return source/index parity without exposing credentials or host paths."""

    await _enforce_rate_limit(request, identity)
    try:
        return await module.status()
    except Exception as error:
        raise RAGUnavailableError("local medical evidence status is unavailable") from error
