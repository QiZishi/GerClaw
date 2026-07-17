"""Authenticated Skill registry, generation, activation, and session APIs."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    require_skill_execute,
    require_skill_read,
    require_skill_write,
)
from gerclaw_api.dependencies import get_database_session, get_trace_service
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import TraceEventCreate, TraceFinishRequest, TraceStartRequest
from gerclaw_api.middleware import set_active_trace
from gerclaw_api.modules.skill import (
    CorruptSkillError,
    ProductionSkillModule,
    SessionSkillsRead,
    SessionSkillsRequest,
    SkillDefinition,
    SkillDisabledError,
    SkillDraftQualityReport,
    SkillDraftRequest,
    SkillEvolutionRequest,
    SkillExecuteRequest,
    SkillId,
    SkillInfo,
    SkillNotFoundError,
    SkillRegisterRequest,
    SkillResult,
    SkillUpdateRequest,
    evaluate_skill_draft,
    extract_skill_markdown,
)
from gerclaw_api.modules.skill.generator import StructuredSkillModel
from gerclaw_api.repositories.skill import SqlAlchemySkillRepository
from gerclaw_api.security import audit_hmac_digest
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.trace_service import TraceService

router = APIRouter(prefix="/skills", tags=["skills"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
SkillReadIdentity = Annotated[AuthContext, Depends(require_skill_read)]
SkillWriteIdentity = Annotated[AuthContext, Depends(require_skill_write)]
SkillExecuteIdentity = Annotated[AuthContext, Depends(require_skill_execute)]


class SkillDraftRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    definition: SkillDefinition
    quality_report: SkillDraftQualityReport


class SkillExecuteRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    result: SkillResult


class SkillDeleteRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted: bool


def _module(
    request: Request, session: AsyncSession, identity: AuthContext
) -> ProductionSkillModule:
    model = request.app.state.agent_model
    return ProductionSkillModule(
        repository=SqlAlchemySkillRepository(session),
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        model=cast(StructuredSkillModel, model) if model is not None else None,
        allowed_tools=frozenset(request.app.state.settings.skill_allowed_tools),
    )


async def _rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


def _fingerprint(request: Request, payload: BaseModel, *, resource_id: str | None = None) -> str:
    canonical = json.dumps(
        {"resource_id": resource_id, "payload": payload.model_dump(mode="json")},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    key = request.app.state.settings.auth_jwt_secret.get_secret_value().encode()
    return audit_hmac_digest(key, canonical.encode())


def _upload_fingerprint(request: Request, filename: str, content: bytes) -> str:
    """Key uploaded content identity without retaining its name or plaintext."""

    key = request.app.state.settings.auth_jwt_secret.get_secret_value().encode()
    return audit_hmac_digest(key, filename.encode() + b"\0" + content)


async def _start_trace(
    request: Request,
    service: TraceService,
    identity: AuthContext,
    *,
    operation: str,
    request_fingerprint: str,
) -> str:
    trace_id = str(request.state.trace_id)
    set_active_trace(request.scope, trace_id)
    await service.start_trace(
        TraceStartRequest(
            execution_type=f"skill.{operation}",
            attributes={
                "module": "skill",
                "operation": operation,
                "request_fingerprint": request_fingerprint,
            },
        ),
        str(request.state.request_id),
        trace_id=trace_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    return trace_id


async def _finish_trace(
    service: TraceService,
    identity: AuthContext,
    *,
    trace_id: str,
    operation: str,
    skill_id: str,
    success: bool,
    error_code: str | None = None,
    version: str | None = None,
    cancelled: bool = False,
) -> None:
    normalized_error_code = error_code.casefold() if error_code else None
    outcome = "cancelled" if cancelled else "success" if success else "failed"
    event_status = (
        TraceEventStatus.CANCELLED
        if cancelled
        else TraceEventStatus.SUCCEEDED
        if success
        else TraceEventStatus.FAILED
    )
    trace_status = (
        TraceStatus.CANCELLED
        if cancelled
        else TraceStatus.COMPLETED
        if success
        else TraceStatus.FAILED
    )
    await service.append_event(
        identity.tenant_id,
        trace_id,
        TraceEventCreate(
            event_id=f"event_{uuid.uuid4().hex}",
            event_type=TraceEventType.SKILL_EXECUTE,
            status=event_status,
            payload={
                "operation": operation,
                "outcome": outcome,
                "skill": skill_id,
                "success": success,
                **({"error_code": normalized_error_code} if normalized_error_code else {}),
                **({"version": version} if version else {}),
            },
        ),
        commit=False,
    )
    await service.finish_trace(
        identity.tenant_id,
        trace_id,
        TraceFinishRequest(
            idempotency_key=f"finish_{uuid.uuid4().hex}",
            status=trace_status,
            error_code=normalized_error_code,
            error_summary="Skill operation failed" if normalized_error_code else None,
            attributes={
                "module": "skill",
                "operation": operation,
                "skill": skill_id,
                "success": success,
                **({"version": version} if version else {}),
            },
        ),
    )


def _execution_error_code(error: Exception) -> str:
    if isinstance(error, SkillNotFoundError):
        return "SKILL_NOT_FOUND"
    if isinstance(error, SkillDisabledError):
        return "SKILL_DISABLED"
    if isinstance(error, CorruptSkillError):
        return "SKILL_STORAGE_INVALID"
    return "SKILL_EXECUTION_FAILED"


def _mutation_error_code(error: BaseException) -> str:
    """Map registry failures to stable PHI-free Trace codes."""

    mapping = {
        "SkillConflictError": "SKILL_CONFLICT",
        "SkillRepositoryConflictError": "SKILL_CONFLICT",
        "SkillNotFoundError": "SKILL_NOT_FOUND",
        "SkillFormatError": "SKILL_FORMAT_INVALID",
        "UnsafeSkillError": "SKILL_UNSAFE",
        "UnsafeSkillArchiveError": "SKILL_ARCHIVE_INVALID",
    }
    return mapping.get(type(error).__name__, "SKILL_MUTATION_FAILED")


@router.get("", response_model=list[SkillInfo])
async def list_skills(
    request: Request,
    session: SessionDependency,
    identity: SkillReadIdentity,
) -> list[SkillInfo]:
    await _rate_limit(request, identity)
    return await _module(request, session, identity).list_skills()


@router.get("/{skill_id}", response_model=SkillDefinition)
async def get_skill(
    skill_id: SkillId,
    request: Request,
    session: SessionDependency,
    identity: SkillReadIdentity,
) -> SkillDefinition:
    await _rate_limit(request, identity)
    return (await _module(request, session, identity).load_skill(skill_id)).definition


@router.post("", response_model=SkillDefinition, status_code=status.HTTP_201_CREATED)
async def register_skill(
    payload: SkillRegisterRequest,
    request: Request,
    session: SessionDependency,
    identity: SkillWriteIdentity,
) -> SkillDefinition:
    await _rate_limit(request, identity)
    service = get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )
    trace_id = await _start_trace(
        request,
        service,
        identity,
        operation="register",
        request_fingerprint=_fingerprint(request, payload),
    )
    try:
        definition = await _module(request, session, identity).register_markdown(
            payload.source_markdown, origin=payload.origin, commit=False
        )
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="register",
            skill_id=definition.skill_id,
            success=True,
            version=definition.version,
        )
        return definition
    except asyncio.CancelledError:
        await session.rollback()
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="register",
            skill_id="skill_registration",
            success=False,
            error_code="SKILL_REGISTRATION_CANCELLED",
            cancelled=True,
        )
        raise
    except Exception as error:
        await session.rollback()
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="register",
            skill_id="skill_registration",
            success=False,
            error_code=_mutation_error_code(error),
        )
        raise


@router.post("/upload", response_model=SkillDefinition, status_code=status.HTTP_201_CREATED)
async def upload_skill(
    request: Request,
    session: SessionDependency,
    identity: SkillWriteIdentity,
    file: Annotated[UploadFile, File(...)],
) -> SkillDefinition:
    await _rate_limit(request, identity)
    filename = file.filename or ""
    content = await file.read(request.app.state.settings.skill_max_archive_bytes + 1)
    service = get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )
    trace_id = await _start_trace(
        request,
        service,
        identity,
        operation="register",
        request_fingerprint=_upload_fingerprint(request, filename, content),
    )
    try:
        markdown = extract_skill_markdown(
            filename,
            content,
            max_archive_bytes=request.app.state.settings.skill_max_archive_bytes,
            max_markdown_characters=request.app.state.settings.skill_max_markdown_characters,
        )
        definition = await _module(request, session, identity).register_markdown(
            markdown, origin="upload", commit=False
        )
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="register",
            skill_id=definition.skill_id,
            success=True,
            version=definition.version,
        )
        return definition
    except asyncio.CancelledError:
        await session.rollback()
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="register",
            skill_id="skill_registration",
            success=False,
            error_code="SKILL_REGISTRATION_CANCELLED",
            cancelled=True,
        )
        raise
    except Exception as error:
        await session.rollback()
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="register",
            skill_id="skill_registration",
            success=False,
            error_code=_mutation_error_code(error),
        )
        raise


@router.post("/preview-upload", response_model=SkillDefinition)
async def preview_skill_upload(
    request: Request,
    session: SessionDependency,
    identity: SkillWriteIdentity,
    file: Annotated[UploadFile, File(...)],
) -> SkillDefinition:
    """Validate an upload and return a reviewable draft without registering it."""

    await _rate_limit(request, identity)
    filename = file.filename or ""
    content = await file.read(request.app.state.settings.skill_max_archive_bytes + 1)
    markdown = extract_skill_markdown(
        filename,
        content,
        max_archive_bytes=request.app.state.settings.skill_max_archive_bytes,
        max_markdown_characters=request.app.state.settings.skill_max_markdown_characters,
    )
    return _module(request, session, identity).preview_markdown(markdown, origin="upload")


@router.post("/generate", response_model=SkillDraftRead)
async def generate_skill(
    payload: SkillDraftRequest,
    request: Request,
    session: SessionDependency,
    identity: SkillWriteIdentity,
) -> SkillDraftRead:
    await _rate_limit(request, identity)
    service = get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )
    trace_id = await _start_trace(
        request,
        service,
        identity,
        operation="generate",
        request_fingerprint=_fingerprint(request, payload),
    )
    try:
        definition = await _module(request, session, identity).generate_skill_from_nl(
            payload.description
        )
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="generate",
            skill_id=definition.skill_id,
            success=True,
        )
        return SkillDraftRead(
            trace_id=trace_id,
            definition=definition,
            quality_report=evaluate_skill_draft(definition),
        )
    except asyncio.CancelledError:
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="generate",
            skill_id="skill_generation",
            success=False,
            error_code="SKILL_GENERATION_CANCELLED",
            cancelled=True,
        )
        raise
    except Exception:
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="generate",
            skill_id="skill_generation",
            success=False,
            error_code="SKILL_GENERATION_FAILED",
        )
        raise


@router.post("/{skill_id}/evolve", response_model=SkillDraftRead)
async def evolve_skill(
    skill_id: SkillId,
    payload: SkillEvolutionRequest,
    request: Request,
    session: SessionDependency,
    identity: SkillWriteIdentity,
) -> SkillDraftRead:
    """Generate a review-only new draft for a caller-owned custom Skill."""

    await _rate_limit(request, identity)
    service = get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )
    trace_id = await _start_trace(
        request,
        service,
        identity,
        operation="evolve",
        request_fingerprint=_fingerprint(request, payload, resource_id=skill_id),
    )
    try:
        definition = await _module(request, session, identity).evolve_skill_from_nl(
            skill_id,
            change_request=payload.change_request,
            expected_revision=payload.expected_revision,
        )
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="evolve",
            skill_id=skill_id,
            success=True,
            version=definition.version,
        )
        return SkillDraftRead(
            trace_id=trace_id,
            definition=definition,
            quality_report=evaluate_skill_draft(definition),
        )
    except asyncio.CancelledError:
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="evolve",
            skill_id=skill_id,
            success=False,
            error_code="SKILL_EVOLUTION_CANCELLED",
            cancelled=True,
        )
        raise
    except Exception:
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="evolve",
            skill_id=skill_id,
            success=False,
            error_code="SKILL_EVOLUTION_FAILED",
        )
        raise


@router.patch("/{skill_id}", response_model=SkillDefinition)
async def update_skill(
    skill_id: SkillId,
    payload: SkillUpdateRequest,
    request: Request,
    session: SessionDependency,
    identity: SkillWriteIdentity,
) -> SkillDefinition:
    await _rate_limit(request, identity)
    service = get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )
    trace_id = await _start_trace(
        request,
        service,
        identity,
        operation="update",
        request_fingerprint=_fingerprint(request, payload, resource_id=skill_id),
    )
    try:
        definition = await _module(request, session, identity).update_skill(
            skill_id,
            source_markdown=payload.source_markdown,
            enabled=payload.enabled,
            expected_revision=payload.expected_revision,
            commit=False,
        )
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="update",
            skill_id=skill_id,
            success=True,
            version=definition.version,
        )
        return definition
    except asyncio.CancelledError:
        await session.rollback()
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="update",
            skill_id=skill_id,
            success=False,
            error_code="SKILL_UPDATE_CANCELLED",
            cancelled=True,
        )
        raise
    except Exception as error:
        await session.rollback()
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="update",
            skill_id=skill_id,
            success=False,
            error_code=_mutation_error_code(error),
        )
        raise


@router.delete("/{skill_id}", response_model=SkillDeleteRead)
async def delete_skill(
    skill_id: SkillId,
    request: Request,
    session: SessionDependency,
    identity: SkillWriteIdentity,
    expected_revision: Annotated[int, Query(ge=1)],
) -> SkillDeleteRead:
    await _rate_limit(request, identity)
    service = get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )
    payload = SkillUpdateRequest(enabled=False, expected_revision=expected_revision)
    trace_id = await _start_trace(
        request,
        service,
        identity,
        operation="delete",
        request_fingerprint=_fingerprint(request, payload, resource_id=skill_id),
    )
    try:
        await _module(request, session, identity).delete_skill(
            skill_id, expected_revision=expected_revision, commit=False
        )
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="delete",
            skill_id=skill_id,
            success=True,
        )
        return SkillDeleteRead(deleted=True)
    except asyncio.CancelledError:
        await session.rollback()
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="delete",
            skill_id=skill_id,
            success=False,
            error_code="SKILL_DELETE_CANCELLED",
            cancelled=True,
        )
        raise
    except Exception as error:
        await session.rollback()
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="delete",
            skill_id=skill_id,
            success=False,
            error_code=_mutation_error_code(error),
        )
        raise


@router.post("/{skill_id}/execute", response_model=SkillExecuteRead)
async def execute_skill(
    skill_id: SkillId,
    payload: SkillExecuteRequest,
    request: Request,
    session: SessionDependency,
    identity: SkillExecuteIdentity,
) -> SkillExecuteRead:
    await _rate_limit(request, identity)
    service = get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )
    trace_id = await _start_trace(
        request,
        service,
        identity,
        operation="execute",
        request_fingerprint=_fingerprint(request, payload, resource_id=skill_id),
    )
    try:
        result = await _module(request, session, identity).execute_skill(skill_id, payload.params)
        version = result.output.get("version")
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="execute",
            skill_id=skill_id,
            success=result.ok,
            error_code=result.error_code,
            version=version if isinstance(version, str) else None,
        )
    except asyncio.CancelledError:
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="execute",
            skill_id=skill_id,
            success=False,
            error_code="SKILL_EXECUTION_CANCELLED",
            cancelled=True,
        )
        raise
    except Exception as error:
        await _finish_trace(
            service,
            identity,
            trace_id=trace_id,
            operation="execute",
            skill_id=skill_id,
            success=False,
            error_code=_execution_error_code(error),
        )
        raise
    if not result.ok:
        raise HTTPException(
            status_code=422,
            detail={"code": result.error_code, "message": "Skill parameters are invalid"},
        )
    return SkillExecuteRead(trace_id=trace_id, result=result)


@router.get("/sessions/{session_id}/selection", response_model=SessionSkillsRead)
async def get_session_skills(
    session_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: SkillReadIdentity,
) -> SessionSkillsRead:
    await _rate_limit(request, identity)
    skill_ids = await _module(request, session, identity).list_session_skills(session_id)
    return SessionSkillsRead(session_id=str(session_id), skill_ids=skill_ids)


@router.put("/sessions/{session_id}/selection", response_model=SessionSkillsRead)
async def replace_session_skills(
    session_id: uuid.UUID,
    payload: SessionSkillsRequest,
    request: Request,
    session: SessionDependency,
    identity: SkillWriteIdentity,
) -> SessionSkillsRead:
    await _rate_limit(request, identity)
    if len(payload.skill_ids) > request.app.state.settings.skill_max_loaded:
        raise HTTPException(
            status_code=422,
            detail={"code": "SKILL_LIMIT", "message": "too many Skills are loaded"},
        )
    await _module(request, session, identity).replace_session_skills(session_id, payload.skill_ids)
    return SessionSkillsRead(session_id=str(session_id), skill_ids=payload.skill_ids)
