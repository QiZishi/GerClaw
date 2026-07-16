"""Authenticated, non-clinical collection endpoints for future governed workflows."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    require_clinical_intake_read,
    require_clinical_intake_write,
)
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.document.service import DocumentService
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
from gerclaw_api.services.clinical_intake_service import (
    ClinicalIntakeConflictError,
    ClinicalIntakeService,
)
from gerclaw_api.services.conversation_service import ConversationNotFoundError, ConversationService
from gerclaw_api.services.rate_limit import RateLimiter

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


@router.post("", response_model=ClinicalIntakeRead, status_code=status.HTTP_201_CREATED)
async def start_intake(
    payload: ClinicalIntakeStartRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> ClinicalIntakeRead:
    """Create an encrypted collection record; never generate clinical output."""

    await _enforce_rate_limit(request, identity)
    await _require_session(session, payload.session_id, identity)
    result = await _service(session, request).start(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        session_id=payload.session_id,
        kind=payload.kind,
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
) -> ClinicalIntakeRead:
    """Apply a fenced, server-validated answer update with no clinical interpretation."""

    await _enforce_rate_limit(request, identity)
    try:
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
    await session.commit()
    return result
