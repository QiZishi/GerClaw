"""Authenticated registration and revocation of parsed session documents."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    require_document_read,
    require_document_write,
)
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.document.models import (
    DocumentParseEgressFinish,
    DocumentParseEgressPrepared,
    UploadedDocumentCreate,
    UploadedDocumentDeleted,
    UploadedDocumentRead,
)
from gerclaw_api.modules.document.service import DocumentContextError, DocumentService
from gerclaw_api.repositories.conversation import SqlAlchemyConversationRepository
from gerclaw_api.repositories.document import (
    SqlAlchemyDocumentRepository,
    UploadedDocumentNotFoundError,
)
from gerclaw_api.repositories.provider_egress import SqlAlchemyProviderEgressRepository
from gerclaw_api.services.conversation_service import ConversationNotFoundError, ConversationService
from gerclaw_api.services.rate_limit import RateLimiter

router = APIRouter(prefix="/documents", tags=["documents"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ReadIdentity = Annotated[AuthContext, Depends(require_document_read)]
WriteIdentity = Annotated[AuthContext, Depends(require_document_write)]


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


def _documents(session: AsyncSession, request: Request) -> DocumentService:
    return DocumentService(SqlAlchemyDocumentRepository(session), request.app.state.settings)


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


@router.post("", response_model=UploadedDocumentRead, status_code=status.HTTP_201_CREATED)
async def register_document(
    payload: UploadedDocumentCreate,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> UploadedDocumentRead:
    """Persist one BFF-parsed document only after ownership of its session is proved."""

    await _enforce_rate_limit(request, identity)
    await _require_session(session, payload.session_id, identity)
    try:
        result = await _documents(session, request).register(
            payload, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except DocumentContextError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "DOCUMENT_CONTENT_INVALID", "message": "文档解析内容无法安全使用"},
        ) from error
    await session.commit()
    return result


@router.post("/provider-egress/mineru", response_model=DocumentParseEgressPrepared)
async def prepare_mineru_egress(
    request: Request, session: SessionDependency, identity: WriteIdentity
) -> DocumentParseEgressPrepared:
    """Prepare an owner-bound MinerU audit record before the BFF calls the provider."""

    await _enforce_rate_limit(request, identity)
    event = await SqlAlchemyProviderEgressRepository(session).record_prepared_document_parse(
        tenant_id=identity.tenant_id, actor_id=identity.actor_id
    )
    await session.commit()
    return DocumentParseEgressPrepared(egress_id=event.id)


@router.post("/provider-egress/mineru/{egress_id}", status_code=status.HTTP_204_NO_CONTENT)
async def finish_mineru_egress(
    egress_id: uuid.UUID,
    payload: DocumentParseEgressFinish,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> None:
    """Finish only the caller's prepared MinerU egress record."""

    await _enforce_rate_limit(request, identity)
    repository = SqlAlchemyProviderEgressRepository(session)
    event = await repository.get_document_parse_for_owner(
        egress_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
    )
    if event is None or event.outcome != "prepared":
        raise HTTPException(status_code=404, detail={"code": "DOCUMENT_EGRESS_NOT_FOUND"})
    await repository.set_outcome(event, outcome=payload.outcome)
    await session.commit()


@router.get("/sessions/{session_id}/{document_id}", response_model=UploadedDocumentRead)
async def get_document(
    session_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> UploadedDocumentRead:
    """Return owner-visible metadata only; never return parsed body to this API."""

    await _enforce_rate_limit(request, identity)
    await _require_session(session, session_id, identity)
    try:
        return await _documents(session, request).get(
            document_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            session_id=session_id,
        )
    except UploadedDocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "DOCUMENT_NOT_FOUND"}) from error


@router.delete("/sessions/{session_id}/{document_id}", response_model=UploadedDocumentDeleted)
async def revoke_document(
    session_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> UploadedDocumentDeleted:
    """Revoke and wipe the parsed body; an owner retry remains idempotent."""

    await _enforce_rate_limit(request, identity)
    await _require_session(session, session_id, identity)
    try:
        await _documents(session, request).revoke(
            document_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            session_id=session_id,
        )
    except UploadedDocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "DOCUMENT_NOT_FOUND"}) from error
    await session.commit()
    return UploadedDocumentDeleted(document_id=document_id)
