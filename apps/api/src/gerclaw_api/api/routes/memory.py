"""Authenticated current-user health profile and memory decisions."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import AuthContext, require_memory_read, require_memory_write
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.memory.models import (
    HealthProfileRead,
    MemoryFactDecisionRead,
    MemoryFactDecisionRequest,
    MemoryFactHistoryRead,
)
from gerclaw_api.modules.memory.profile import empty_profile
from gerclaw_api.modules.memory.runtime import create_memory_module
from gerclaw_api.repositories.memory import (
    MemoryConflictError,
    MemoryNotFoundError,
    SqlAlchemyMemoryRepository,
)
from gerclaw_api.services.model_router import FailoverChatModel
from gerclaw_api.services.rate_limit import RateLimiter

router = APIRouter(prefix="/memory", tags=["memory"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
MemoryReadIdentity = Annotated[AuthContext, Depends(require_memory_read)]
MemoryWriteIdentity = Annotated[AuthContext, Depends(require_memory_write)]
_NO_SESSION = uuid.UUID(int=0)


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


def _required_model(request: Request) -> FailoverChatModel:
    model = request.app.state.agent_model
    if not isinstance(model, FailoverChatModel):
        raise HTTPException(
            status_code=503,
            detail={"code": "MEMORY_UNAVAILABLE", "message": "记忆服务暂时不可用。"},
        )
    return model


@router.get("/profile", response_model=HealthProfileRead)
async def get_profile(
    request: Request,
    session: SessionDependency,
    identity: MemoryReadIdentity,
) -> HealthProfileRead:
    """Return only the authenticated principal's decrypted profile."""

    await _enforce_rate_limit(request, identity)
    repository = SqlAlchemyMemoryRepository(session)
    user = await repository.get_user(tenant_id=identity.tenant_id, actor_id=identity.actor_id)
    if user is None:
        return HealthProfileRead(schema_version=1, version=0, profile=empty_profile(), facts=[])
    module = create_memory_module(
        settings=request.app.state.settings,
        repository=repository,
        model=_required_model(request),
        embedding_model=request.app.state.rag_runtime.embedding_model,
        vector_store=request.app.state.memory_store,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        user_id=user.id,
        session_id=_NO_SESSION,
        trace_id=str(request.state.trace_id),
    )
    return await module.read_profile()


@router.post("/facts/{fact_id}/decision", response_model=MemoryFactDecisionRead)
async def decide_fact(
    fact_id: uuid.UUID,
    payload: MemoryFactDecisionRequest,
    request: Request,
    session: SessionDependency,
    identity: MemoryWriteIdentity,
) -> MemoryFactDecisionRead:
    """Confirm or reject one fact using an optimistic revision."""

    await _enforce_rate_limit(request, identity)
    repository = SqlAlchemyMemoryRepository(session)
    user = await repository.get_user(tenant_id=identity.tenant_id, actor_id=identity.actor_id)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "MEMORY_FACT_NOT_FOUND", "message": "记忆事实不存在。"},
        )
    module = create_memory_module(
        settings=request.app.state.settings,
        repository=repository,
        model=_required_model(request),
        embedding_model=request.app.state.rag_runtime.embedding_model,
        vector_store=request.app.state.memory_store,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        user_id=user.id,
        session_id=_NO_SESSION,
        trace_id=str(request.state.trace_id),
    )
    try:
        result = await module.decide_fact(fact_id, payload)
        await module.commit()
        return result
    except MemoryNotFoundError as error:
        await module.rollback()
        raise HTTPException(
            status_code=404,
            detail={"code": "MEMORY_FACT_NOT_FOUND", "message": "记忆事实不存在。"},
        ) from error
    except MemoryConflictError as error:
        await module.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "MEMORY_REVISION_CONFLICT", "message": "记忆已更新, 请刷新后重试。"},
        ) from error
    except BaseException:
        # The request session dependency only rolls back PostgreSQL. Memory
        # additionally owns pre-commit Qdrant points and must compensate them
        # for provider, flush, response projection, and cancellation failures.
        await module.rollback()
        raise


@router.get("/facts/{fact_id}/history", response_model=MemoryFactHistoryRead)
async def get_fact_history(
    fact_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: MemoryReadIdentity,
    limit: int = Query(default=10, ge=1, le=50),
) -> MemoryFactHistoryRead:
    """Return caller-owned immutable fact versions without exposing another principal's data."""

    await _enforce_rate_limit(request, identity)
    repository = SqlAlchemyMemoryRepository(session)
    user = await repository.get_user(tenant_id=identity.tenant_id, actor_id=identity.actor_id)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "MEMORY_FACT_NOT_FOUND", "message": "记忆事实不存在。"},
        )
    module = create_memory_module(
        settings=request.app.state.settings,
        repository=repository,
        model=_required_model(request),
        embedding_model=request.app.state.rag_runtime.embedding_model,
        vector_store=request.app.state.memory_store,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        user_id=user.id,
        session_id=_NO_SESSION,
        trace_id=str(request.state.trace_id),
    )
    try:
        return await module.read_fact_history(fact_id, limit=limit)
    except MemoryNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "MEMORY_FACT_NOT_FOUND", "message": "记忆事实不存在。"},
        ) from error
