"""Authenticated session APIs and production Agent Harness SSE endpoint."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    authorize_scope,
    require_chat_read,
    require_chat_write,
)
from gerclaw_api.database.session import Database
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.domain.chat_schemas import (
    ChatCancelledData,
    ChatCancelRead,
    ChatErrorData,
    ChatRequest,
    SessionCreateRequest,
    SessionDeleted,
    SessionMessagesRead,
    SessionRead,
)
from gerclaw_api.domain.trace_schemas import TRACE_ID_PATTERN
from gerclaw_api.middleware import set_active_trace
from gerclaw_api.modules.agent_harness import StreamEvent
from gerclaw_api.modules.document import DocumentService
from gerclaw_api.modules.memory.memory_module import ProductionMemoryModule
from gerclaw_api.modules.memory.runtime import create_memory_module
from gerclaw_api.modules.risk_alert.service import RiskAlertService
from gerclaw_api.modules.skill import ProductionSkillModule
from gerclaw_api.repositories.approval import SqlAlchemyApprovalRepository
from gerclaw_api.repositories.conversation import (
    ConversationConflictError,
    SqlAlchemyConversationRepository,
)
from gerclaw_api.repositories.document import SqlAlchemyDocumentRepository
from gerclaw_api.repositories.memory import SqlAlchemyMemoryRepository
from gerclaw_api.repositories.risk_alert import SqlAlchemyRiskAlertRepository
from gerclaw_api.repositories.skill import SqlAlchemySkillRepository
from gerclaw_api.repositories.trace import SqlAlchemyTraceRepository
from gerclaw_api.services.chat_cancellation import (
    ChatCancellationRegistry,
    ChatCancellationUnavailable,
)
from gerclaw_api.services.chat_service import ChatService
from gerclaw_api.services.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
)
from gerclaw_api.services.model_egress_audit import SqlAlchemyModelPromptEgressAudit
from gerclaw_api.services.model_router import bind_model_prompt_egress_audit
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.session_lease import SessionLease
from gerclaw_api.services.trace_service import TraceService

router = APIRouter(tags=["chat"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ChatReadIdentity = Annotated[AuthContext, Depends(require_chat_read)]
ChatWriteIdentity = Annotated[AuthContext, Depends(require_chat_write)]
TraceIdPath = Annotated[str, Path(pattern=TRACE_ID_PATTERN)]


class _Terminal:
    """Typed internal queue sentinel."""


_TERMINAL = _Terminal()
QueueItem = StreamEvent | ChatCancelledData | ChatErrorData | _Terminal


def _force_enqueue(queue: asyncio.Queue[QueueItem], item: QueueItem) -> None:
    """Enqueue a control/terminal item without waiting on an abandoned consumer."""

    while True:
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            # Drop the oldest streamed delta. Terminal tool results and control
            # frames are inserted last, so successive control inserts preserve
            # them while freeing bounded capacity.
            with suppress(asyncio.QueueEmpty):
                queue.get_nowait()


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


def _conversation_service(session: AsyncSession) -> ConversationService:
    return ConversationService(SqlAlchemyConversationRepository(session))


@router.post(
    "/chat/{trace_id}/cancel",
    response_model=ChatCancelRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_chat(
    trace_id: TraceIdPath,
    request: Request,
    identity: ChatWriteIdentity,
) -> ChatCancelRead:
    """Request identity-scoped cancellation without tearing down the SSE stream."""

    await _enforce_rate_limit(request, identity)
    registry: ChatCancellationRegistry = request.app.state.chat_cancellations
    try:
        await registry.request_cancel(
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            trace_id=trace_id,
        )
    except ChatCancellationUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CHAT_CANCELLATION_UNAVAILABLE",
                "message": "暂时无法安全停止，请稍后重试。",
            },
        ) from error
    return ChatCancelRead(trace_id=trace_id)


@router.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreateRequest,
    request: Request,
    session: SessionDependency,
    identity: ChatWriteIdentity,
) -> SessionRead:
    """Create or idempotently return one caller-owned conversation."""

    await _enforce_rate_limit(request, identity)
    service = _conversation_service(session)
    try:
        conversation = await service.create_session(
            payload.session_id or uuid.uuid4(),
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
        )
    except ConversationConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "CHAT_SESSION_CONFLICT", "message": str(error)},
        ) from error
    return SessionRead.model_validate(conversation)


@router.delete("/sessions/{session_id}", response_model=SessionDeleted)
async def delete_session(
    session_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ChatWriteIdentity,
) -> SessionDeleted:
    """Irreversibly delete one idle, caller-owned conversation and session data."""

    await _enforce_rate_limit(request, identity)
    try:
        await _conversation_service(session).delete_session(
            session_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "CHAT_SESSION_NOT_FOUND", "message": "session not found"},
        ) from error
    except ConversationConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "CHAT_SESSION_ACTIVE", "message": "session has a running execution"},
        ) from error
    return SessionDeleted(session_id=session_id)


@router.get("/sessions/{session_id}/messages", response_model=SessionMessagesRead)
async def get_session_messages(
    session_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ChatReadIdentity,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SessionMessagesRead:
    """Return bounded decrypted history only to its actor and tenant."""

    await _enforce_rate_limit(request, identity)
    service = _conversation_service(session)
    try:
        messages = await service.list_messages(
            session_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            limit=limit,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "CHAT_SESSION_NOT_FOUND", "message": "session not found"},
        ) from error
    return SessionMessagesRead(session_id=session_id, messages=messages)


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    request: Request,
    identity: ChatWriteIdentity,
) -> StreamingResponse:
    """Execute one real AgentScope turn and stream safe, backpressured SSE."""

    if payload.loaded_skills:
        authorize_scope(identity, "skill:execute")
    await _enforce_rate_limit(request, identity)
    trace_id = str(request.state.trace_id)
    request_id = str(request.state.request_id)
    set_active_trace(request.scope, trace_id)
    queue: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=128)
    registry: ChatCancellationRegistry = request.app.state.chat_cancellations

    async def publish(event: StreamEvent) -> None:
        if event.event_type == "tool_result":
            _force_enqueue(queue, event)
        else:
            await queue.put(event)

    async def run_turn() -> None:
        database: Database = request.app.state.database
        try:
            async with database.session() as database_session:
                memory_repository = SqlAlchemyMemoryRepository(database_session)

                def memory_factory(
                    *,
                    tenant_id: str,
                    actor_id: str,
                    user_id: uuid.UUID,
                    session_id: uuid.UUID,
                    trace_id: str,
                ) -> ProductionMemoryModule:
                    return create_memory_module(
                        settings=request.app.state.settings,
                        repository=memory_repository,
                        model=request.app.state.agent_model,
                        embedding_model=request.app.state.rag_runtime.embedding_model,
                        vector_store=request.app.state.memory_store,
                        tenant_id=tenant_id,
                        actor_id=actor_id,
                        user_id=user_id,
                        session_id=session_id,
                        trace_id=trace_id,
                    )

                service = ChatService(
                    settings=request.app.state.settings,
                    conversation=ConversationService(
                        SqlAlchemyConversationRepository(database_session)
                    ),
                    traces=TraceService(
                        SqlAlchemyTraceRepository(database_session),
                        max_events_per_trace=request.app.state.settings.max_events_per_trace,
                    ),
                    lease=SessionLease(
                        request.app.state.redis,
                        ttl_seconds=(request.app.state.settings.chat_session_lease_ttl_seconds),
                    ),
                    model=request.app.state.agent_model,
                    rag_module=request.app.state.rag_runtime.module,
                    memory_factory=memory_factory,
                    search_module=request.app.state.search_runtime.module,
                    skill_module=ProductionSkillModule(
                        repository=SqlAlchemySkillRepository(database_session),
                        tenant_id=identity.tenant_id,
                        actor_id=identity.actor_id,
                        model=request.app.state.agent_model,
                        allowed_tools=frozenset(request.app.state.settings.skill_allowed_tools),
                    ),
                    approval_repository=SqlAlchemyApprovalRepository(database_session),
                    document_service=DocumentService(
                        SqlAlchemyDocumentRepository(database_session), request.app.state.settings
                    ),
                    risk_alert_service=RiskAlertService(
                        SqlAlchemyRiskAlertRepository(database_session)
                    ),
                )
                with bind_model_prompt_egress_audit(
                    SqlAlchemyModelPromptEgressAudit(
                        database, tenant_id=identity.tenant_id, actor_id=identity.actor_id
                    )
                ):
                    await service.process(
                        payload,
                        identity=identity,
                        request_id=request_id,
                        trace_id=trace_id,
                        callback=publish,
                        cancellation_requested=lambda: registry.is_cancel_requested(
                            tenant_id=identity.tenant_id,
                            actor_id=identity.actor_id,
                            trace_id=trace_id,
                        ),
                    )
        except asyncio.CancelledError:
            _force_enqueue(
                queue,
                ChatCancelledData(trace_id=trace_id),
            )
        except Exception as error:
            code = ChatService.error_code(error)
            message, retriable = _public_error(code)
            _force_enqueue(
                queue,
                ChatErrorData(
                    code=code,
                    message=message,
                    trace_id=trace_id,
                    retriable=retriable,
                ),
            )
        finally:
            current = asyncio.current_task()
            if current is not None:
                await registry.unregister(
                    tenant_id=identity.tenant_id,
                    actor_id=identity.actor_id,
                    trace_id=trace_id,
                    task=current,
                )
            _force_enqueue(queue, _TERMINAL)

    task = asyncio.create_task(run_turn(), name=f"chat-turn-{trace_id}")
    try:
        await registry.register(
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            trace_id=trace_id,
            task=task,
        )
    except ChatCancellationUnavailable as error:
        task.cancel("chat cancellation registry unavailable")
        with suppress(asyncio.CancelledError):
            await task
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CHAT_CANCELLATION_UNAVAILABLE",
                "message": "对话安全停止服务暂时不可用，请稍后重试。",
            },
        ) from error

    async def event_stream() -> AsyncIterator[str]:
        try:
            while True:
                if await request.is_disconnected():
                    task.cancel()
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=10.0)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if isinstance(item, _Terminal):
                    break
                if isinstance(item, ChatCancelledData):
                    yield _encode_sse("cancelled", item.model_dump(mode="json"))
                    continue
                if isinstance(item, ChatErrorData):
                    yield _encode_sse("error", item.model_dump(mode="json"))
                    continue
                event_name = (
                    "thinking" if item.event_type == "reasoning_summary" else item.event_type
                )
                data = dict(item.data)
                data["timestamp"] = item.timestamp.timestamp()
                yield _encode_sse(event_name, data)
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Trace-ID": trace_id,
        },
    )


def _encode_sse(event: str, data: Mapping[str, object]) -> str:
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _public_error(code: str) -> tuple[str, bool]:
    errors = {
        "CHAT_SESSION_BUSY": ("该会话正在生成，请等待当前回复完成后再试。", True),
        "CHAT_COORDINATION_UNAVAILABLE": ("会话协调服务暂时不可用，请稍后重试。", True),
        "CHAT_SESSION_NOT_FOUND": ("会话不存在或无权访问。", False),
        "CHAT_CONFLICT": ("本次请求与已保存的会话数据冲突。", False),
        "CHAT_EVIDENCE_UNAVAILABLE": (
            "未检索到足够的本地医学依据，本次不生成医学建议，请稍后重试或咨询医生。",
            True,
        ),
        "CHAT_MODEL_UNAVAILABLE": ("模型服务暂时不可用，请稍后重试。", True),
        "CHAT_MODEL_STREAM_INTERRUPTED": (
            "模型流式响应中断，为避免重复医疗内容，本次已停止。",
            True,
        ),
        "CHAT_ITERATION_LIMIT": ("分析步骤达到安全上限，本次已停止。", True),
        "CHAT_APPROVAL_REQUIRED": ("该操作需要医生确认，当前未执行。", False),
        "CHAT_CONTEXT_UNSUPPORTED": ("当前请求包含尚未启用的上下文类型。", False),
        "CHAT_DOCUMENT_UNAVAILABLE": (
            "所选文档已移除、不可用或不属于当前会话，请重新上传后再试。",
            False,
        ),
        "CHAT_EMPTY_RESPONSE": ("模型未返回可用内容，请稍后重试。", True),
        "CHAT_MEMORY_UNAVAILABLE": ("健康记忆服务暂时不可用，本次未完成，请稍后重试。", True),
        "CHAT_SKILL_UNAVAILABLE": ("所选技能不存在、已禁用或暂不可用，请刷新技能列表。", False),
        "CHAT_CANCELLATION_FINALIZATION_FAILED": (
            "停止请求未能安全落库，请稍后重试并核对本次执行记录。",
            True,
        ),
    }
    return errors.get(code, ("本次对话执行失败，请稍后重试。", True))
