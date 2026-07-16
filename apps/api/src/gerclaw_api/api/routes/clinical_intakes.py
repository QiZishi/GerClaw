"""Authenticated, non-clinical collection endpoints for future governed workflows."""

from __future__ import annotations

import json
import uuid
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    require_clinical_intake_read,
    require_clinical_intake_write,
)
from gerclaw_api.dependencies import get_database_session, get_trace_service
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import TraceEventCreate, TraceFinishRequest, TraceStartRequest
from gerclaw_api.middleware import set_active_trace
from gerclaw_api.modules.document.service import DocumentService
from gerclaw_api.modules.input_output.clinical_intake import ClinicalIntakeKind
from gerclaw_api.modules.prescription.models import (
    ClinicalIntakeRead,
    ClinicalIntakeStartRequest,
    ClinicalIntakeUpdateRequest,
)
from gerclaw_api.repositories.clinical_intake import (
    ClinicalIntakeNotFoundError,
    SqlAlchemyClinicalIntakeRepository,
)
from gerclaw_api.repositories.conversation import SqlAlchemyConversationRepository
from gerclaw_api.repositories.document import SqlAlchemyDocumentRepository
from gerclaw_api.security import audit_hmac_digest
from gerclaw_api.services.clinical_intake_service import (
    ClinicalIntakeConflictError,
    ClinicalIntakeService,
)
from gerclaw_api.services.conversation_service import ConversationNotFoundError, ConversationService
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.trace_service import TraceConflictError, TraceService

router = APIRouter(prefix="/clinical-intakes", tags=["clinical-intakes"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ReadIdentity = Annotated[AuthContext, Depends(require_clinical_intake_read)]
WriteIdentity = Annotated[AuthContext, Depends(require_clinical_intake_write)]


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


async def _require_session(
    session: AsyncSession, session_id: uuid.UUID, identity: AuthContext
) -> None:
    try:
        await ConversationService(SqlAlchemyConversationRepository(session)).require_session(
            session_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CHAT_SESSION_NOT_FOUND", "message": "session not found"},
        ) from error


def _service(session: AsyncSession, request: Request) -> ClinicalIntakeService:
    return ClinicalIntakeService(
        SqlAlchemyClinicalIntakeRepository(session),
        DocumentService(SqlAlchemyDocumentRepository(session), request.app.state.settings),
    )


def _trace_service(request: Request, session: SessionDependency) -> TraceService:
    return get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )


TraceServiceDependency = Annotated[TraceService, Depends(_trace_service)]


def _module_name(kind: ClinicalIntakeKind) -> str:
    """Return the audited domain owner for one server-defined intake type."""

    return "prescription" if kind == "prescription" else "medication_review"


def _request_fingerprint(
    request: Request,
    payload: ClinicalIntakeStartRequest | ClinicalIntakeUpdateRequest,
) -> str:
    """Bind retries without exposing encrypted clinical input in audit storage."""

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
    session_id: uuid.UUID,
    kind: ClinicalIntakeKind,
    operation: str,
    payload: ClinicalIntakeStartRequest | ClinicalIntakeUpdateRequest,
) -> tuple[str, float]:
    trace_id = str(request.state.trace_id)
    set_active_trace(request.scope, trace_id)
    started = monotonic()
    result = await traces.start_trace_with_status(
        TraceStartRequest(
            session_id=session_id,
            execution_type="clinical.intake",
            attributes={
                "feature": kind,
                "module": _module_name(kind),
                "operation": operation,
                "request_fingerprint": _request_fingerprint(request, payload),
                "version": "clinical-intake-v1",
            },
        ),
        str(request.state.request_id),
        trace_id=trace_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        commit=False,
    )
    if not result.created:
        raise TraceConflictError("clinical intake trace is already in use")
    return trace_id, started


async def _finish_write_trace(
    *,
    traces: TraceService,
    tenant_id: str,
    trace_id: str,
    operation: str,
    elapsed_started_at: float,
    result: ClinicalIntakeRead,
) -> None:
    trace_suffix = trace_id.removeprefix("trace_")
    await traces.append_event(
        tenant_id,
        trace_id,
        TraceEventCreate(
            event_id=f"event_{trace_suffix}_{operation}",
            event_type=TraceEventType.CLINICAL_INTAKE,
            status=TraceEventStatus.SUCCEEDED,
            payload={
                "feature": result.kind,
                "operation": operation,
                "version": result.definition_version,
                "event_count": len(result.answers),
                "document_count": len(result.document_ids),
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
                "feature": result.kind,
                "module": _module_name(result.kind),
                "operation": operation,
                "result_code": result.status,
                "version": result.definition_version,
            },
        ),
        commit=False,
    )


@router.post("", response_model=ClinicalIntakeRead, status_code=status.HTTP_201_CREATED)
async def start_intake(
    payload: ClinicalIntakeStartRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> ClinicalIntakeRead:
    """Create an encrypted collection record; never generate clinical output."""

    await _enforce_rate_limit(request, identity)
    await _require_session(session, payload.session_id, identity)
    try:
        trace_id, started_at = await _start_write_trace(
            request=request,
            traces=traces,
            identity=identity,
            session_id=payload.session_id,
            kind=payload.kind,
            operation="start",
            payload=payload,
        )
    except TraceConflictError as error:
        raise HTTPException(
            status_code=409, detail={"code": "CLINICAL_INTAKE_TRACE_CONFLICT"}
        ) from error
    result = await _service(session, request).start(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        session_id=payload.session_id,
        kind=payload.kind,
    )
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


@router.get("/{intake_id}", response_model=ClinicalIntakeRead)
async def get_intake(
    intake_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> ClinicalIntakeRead:
    """Read only the authenticated caller's encrypted intake values."""

    await _enforce_rate_limit(request, identity)
    try:
        return await _service(session, request).get(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ClinicalIntakeNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "CLINICAL_INTAKE_NOT_FOUND"}
        ) from error


@router.patch("/{intake_id}", response_model=ClinicalIntakeRead)
async def update_intake(
    intake_id: uuid.UUID,
    payload: ClinicalIntakeUpdateRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> ClinicalIntakeRead:
    """Apply a fenced, server-validated answer update with no clinical interpretation."""

    await _enforce_rate_limit(request, identity)
    try:
        current = await _service(session, request).get(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
        trace_id, started_at = await _start_write_trace(
            request=request,
            traces=traces,
            identity=identity,
            session_id=current.session_id,
            kind=current.kind,
            operation="update",
            payload=payload,
        )
        result = await _service(session, request).update(
            intake_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            expected_revision=payload.expected_revision,
            answers=payload.answers,
            document_ids=payload.document_ids,
        )
    except ClinicalIntakeNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "CLINICAL_INTAKE_NOT_FOUND"}
        ) from error
    except ClinicalIntakeConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "CLINICAL_INTAKE_CONFLICT"}) from error
    except TraceConflictError as error:
        raise HTTPException(
            status_code=409, detail={"code": "CLINICAL_INTAKE_TRACE_CONFLICT"}
        ) from error
    await _finish_write_trace(
        traces=traces,
        tenant_id=identity.tenant_id,
        trace_id=trace_id,
        operation="update",
        elapsed_started_at=started_at,
        result=result,
    )
    await session.commit()
    return result
