"""Authenticated session APIs and production Agent Harness SSE endpoint."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.api.sse import encode_sse
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
    SessionListRead,
    SessionMessagesRead,
    SessionRead,
)
from gerclaw_api.domain.trace_schemas import TRACE_ID_PATTERN
from gerclaw_api.middleware import set_active_trace
from gerclaw_api.modules.agent_harness import StreamEvent
from gerclaw_api.modules.document import DocumentService
from gerclaw_api.modules.memory.memory_module import ProductionMemoryModule
from gerclaw_api.modules.memory.runtime import create_memory_module
from gerclaw_api.modules.rag.runtime import RAGRuntime, create_rag_runtime
from gerclaw_api.modules.risk_alert.service import RiskAlertService
from gerclaw_api.modules.search.runtime import SearchRuntime, create_search_runtime
from gerclaw_api.modules.skill import ProductionSkillModule
from gerclaw_api.modules.validation import validate_public_chat_stream_event
from gerclaw_api.repositories.account_model_override import SqlAlchemyAccountModelOverrideRepository
from gerclaw_api.repositories.approval import SqlAlchemyApprovalRepository
from gerclaw_api.repositories.conversation import (
    ConversationConflictError,
    SqlAlchemyConversationRepository,
)
from gerclaw_api.repositories.document import SqlAlchemyDocumentRepository
from gerclaw_api.repositories.memory import SqlAlchemyMemoryRepository
from gerclaw_api.repositories.prescription_draft import SqlAlchemyPrescriptionDraftRepository
from gerclaw_api.repositories.risk_alert import SqlAlchemyRiskAlertRepository
from gerclaw_api.repositories.run_resume import SqlAlchemyRunResumeRepository
from gerclaw_api.repositories.skill import SqlAlchemySkillRepository
from gerclaw_api.repositories.trace import SqlAlchemyTraceRepository
from gerclaw_api.services.account_model_configuration import (
    has_service_override,
    resolve_effective_configs,
    resolve_effective_settings,
)
from gerclaw_api.services.chat_cancellation import (
    ChatCancellationRegistry,
    ChatCancellationUnavailable,
)
from gerclaw_api.services.chat_run_journal import DatabaseChatRunJournal
from gerclaw_api.services.chat_service import ChatService
from gerclaw_api.services.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
)
from gerclaw_api.services.model_egress_audit import SqlAlchemyModelPromptEgressAudit
from gerclaw_api.services.model_router import FailoverChatModel, bind_model_prompt_egress_audit
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.run_resume_service import RunResumeService
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


@router.get("/sessions", response_model=SessionListRead)
async def list_sessions(
    request: Request,
    session: SessionDependency,
    identity: ChatReadIdentity,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SessionListRead:
    """Restore durable conversation metadata for an authenticated account only."""

    await _enforce_rate_limit(request, identity)
    if identity.account_role == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "GUEST_SESSION_HISTORY_DISABLED"},
        )
    conversations = await _conversation_service(session).list_sessions(
        tenant_id=identity.tenant_id, actor_id=identity.actor_id, limit=limit
    )
    draft_session_ids = await SqlAlchemyPrescriptionDraftRepository(
        session
    ).session_ids_with_drafts(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        session_ids=tuple(item.id for item in conversations),
    )
    return SessionListRead(
        sessions=[
            SessionRead.model_validate(item).model_copy(
                update={"has_prescription_draft": item.id in draft_session_ids}
            )
            for item in conversations
        ]
    )


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
    if identity.account_role == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "GUEST_SESSION_HISTORY_DISABLED"},
        )
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
    return await _stream_chat(
        payload,
        request=request,
        identity=identity,
        trace_id=trace_id,
        request_id=request_id,
    )


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ChatWriteIdentity,
) -> StreamingResponse:
    """Reconstruct and stream the exact persisted input of one interrupted Run."""

    command = await RunResumeService(
        SqlAlchemyRunResumeRepository(session)
    ).prepare(
        run_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    if command.request.loaded_skills:
        authorize_scope(identity, "skill:execute")
    await _enforce_rate_limit(request, identity)
    return await _stream_chat(
        command.request,
        request=request,
        identity=identity,
        trace_id=command.trace_id,
        request_id=str(request.state.request_id),
    )


async def _stream_chat(
    payload: ChatRequest,
    *,
    request: Request,
    identity: AuthContext,
    trace_id: str,
    request_id: str,
) -> StreamingResponse:
    """Run the shared SSE transport for a new or explicitly resumed turn."""

    set_active_trace(request.scope, trace_id)
    queue: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=128)
    registry: ChatCancellationRegistry = request.app.state.chat_cancellations
    consumer_detached = asyncio.Event()

    async def publish(event: StreamEvent) -> None:
        event = validate_public_chat_stream_event(event)
        if consumer_detached.is_set():
            return
        enqueue = asyncio.create_task(queue.put(event))
        detached = asyncio.create_task(consumer_detached.wait())
        done, pending = await asyncio.wait(
            {enqueue, detached},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for pending_task in pending:
            pending_task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for completed_task in done:
            await completed_task

    async def run_turn() -> None:
        database: Database = request.app.state.database
        try:
            async with database.session() as database_session:
                model = request.app.state.agent_model
                request_owned_model: FailoverChatModel | None = None
                request_owned_rag: RAGRuntime | None = None
                request_owned_search: SearchRuntime | None = None
                effective_settings = request.app.state.settings
                rag_runtime = request.app.state.rag_runtime
                search_runtime = request.app.state.search_runtime
                if identity.account_role != "guest":
                    override = await SqlAlchemyAccountModelOverrideRepository(database_session).get(
                        tenant_id=identity.tenant_id, actor_id=identity.actor_id
                    )
                    if override is not None:
                        effective_settings = resolve_effective_settings(
                            request.app.state.settings, override.configuration
                        )
                        request_owned_model = FailoverChatModel(
                            resolve_effective_configs(effective_settings, override.configuration)
                        )
                        model = request_owned_model
                        if has_service_override(override.configuration, "vector"):
                            request_owned_rag = create_rag_runtime(
                                effective_settings, request.app.state.qdrant
                            )
                            rag_runtime = request_owned_rag
                        if has_service_override(override.configuration, "search"):
                            request_owned_search = create_search_runtime(effective_settings)
                            search_runtime = request_owned_search
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
                        settings=effective_settings,
                        repository=memory_repository,
                        model=model,
                        embedding_model=rag_runtime.embedding_model,
                        vector_store=request.app.state.memory_store,
                        tenant_id=tenant_id,
                        actor_id=actor_id,
                        user_id=user_id,
                        session_id=session_id,
                        trace_id=trace_id,
                    )

                service = ChatService(
                    settings=effective_settings,
                    conversation=ConversationService(
                        SqlAlchemyConversationRepository(database_session)
                    ),
                    traces=TraceService(
                        SqlAlchemyTraceRepository(database_session),
                        max_events_per_trace=effective_settings.max_events_per_trace,
                    ),
                    lease=SessionLease(
                        request.app.state.redis,
                        ttl_seconds=(effective_settings.chat_session_lease_ttl_seconds),
                    ),
                    model=model,
                    rag_module=rag_runtime.module,
                    memory_factory=memory_factory,
                    search_module=search_runtime.module,
                    skill_module=ProductionSkillModule(
                        repository=SqlAlchemySkillRepository(database_session),
                        tenant_id=identity.tenant_id,
                        actor_id=identity.actor_id,
                        model=model,
                        allowed_tools=frozenset(effective_settings.skill_allowed_tools),
                    ),
                    approval_repository=SqlAlchemyApprovalRepository(database_session),
                    document_service=DocumentService(
                        SqlAlchemyDocumentRepository(database_session), effective_settings
                    ),
                    risk_alert_service=RiskAlertService(
                        SqlAlchemyRiskAlertRepository(database_session)
                    ),
                    run_journal=DatabaseChatRunJournal(
                        database,
                        completion_session=database_session,
                    ),
                )
                with bind_model_prompt_egress_audit(
                    SqlAlchemyModelPromptEgressAudit(
                        database, tenant_id=identity.tenant_id, actor_id=identity.actor_id
                    )
                ):
                    try:
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
                    finally:
                        if request_owned_search is not None:
                            await request_owned_search.aclose()
                        if request_owned_rag is not None:
                            await request_owned_rag.aclose()
                        if request_owned_model is not None:
                            await request_owned_model.aclose()
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
                # Do not preflight ``request.is_disconnected()`` here.  A
                # streaming reverse proxy can report its upstream request as
                # disconnected before it starts consuming the SSE body, which
                # would discard a completed turn and return an empty 200
                # stream.  Starlette cancels this generator when the actual
                # downstream stream closes; ``finally`` below then cancels the
                # owned task if it is still running.
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
                if item.run_id is not None and item.sequence is not None:
                    data["run_id"] = str(item.run_id)
                    data["sequence"] = item.sequence
                yield _encode_sse(event_name, data, sequence=item.sequence)
        finally:
            # A transport disconnect is not an explicit user cancellation.
            # The owner task keeps running and persists RunEvents; the client
            # can attach to the same Run with ``after_sequence``.
            consumer_detached.set()

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


def _encode_sse(
    event: str,
    data: Mapping[str, object],
    *,
    sequence: int | None = None,
) -> str:
    return encode_sse(event, data, sequence=sequence)


def _public_error(code: str) -> tuple[str, bool]:
    errors = {
        "CHAT_SESSION_BUSY": ("该会话正在生成，请等待当前回复完成后再试。", True),
        "CHAT_COORDINATION_UNAVAILABLE": ("会话协调服务暂时不可用，请稍后重试。", True),
        "CHAT_SESSION_NOT_FOUND": ("会话不存在或无权访问。", False),
        "CHAT_CONFLICT": ("本次请求与已保存的会话数据冲突。", False),
        "CHAT_REGENERATION_NOT_FOUND": ("原回答不存在或无权重新生成。", False),
        "CHAT_REGENERATION_CONFLICT": (
            "原回答或上下文已变化，请刷新对话后再重新生成。",
            False,
        ),
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
