"""Transactional chat turn orchestration across lease, Trace, Harness, and storage."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from gerclaw_api.auth import AuthContext
from gerclaw_api.config import Settings
from gerclaw_api.domain.chat_schemas import ChatDoneData, ChatRequest
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import (
    TraceEventCreate,
    TraceFinishRequest,
    TraceStartRequest,
)
from gerclaw_api.metrics import CHAT_TURN_LATENCY, CHAT_TURNS
from gerclaw_api.modules.agent_harness import (
    ConversationHistoryMessage,
    ProductionAgentHarness,
    StreamEvent,
)
from gerclaw_api.modules.contracts import AgentResponse, ExecutionContext
from gerclaw_api.modules.memory.memory_module import ProductionMemoryModule
from gerclaw_api.modules.memory.models import MemoryUpdateResult
from gerclaw_api.modules.rag import HybridRAGModule
from gerclaw_api.security import JsonValue
from gerclaw_api.services.conversation_service import ConversationService
from gerclaw_api.services.model_router import FailoverChatModel
from gerclaw_api.services.session_lease import SessionLease, SessionLeaseGuard
from gerclaw_api.services.trace_service import TraceService

StreamCallback = Callable[[StreamEvent], Awaitable[None]]


class MemoryModuleFactory(Protocol):
    """Build a principal- and turn-isolated Memory graph."""

    def __call__(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        trace_id: str,
    ) -> ProductionMemoryModule: ...


class ChatReplayUnavailableError(RuntimeError):
    """Raised when a terminal Trace has no successful replayable response."""


def _fingerprint(payload: ChatRequest, settings: Settings) -> str:
    """Return a keyed payload identity without exposing enumerable user text."""

    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    key = settings.auth_jwt_secret.get_secret_value().encode()
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


def _event_id() -> str:
    return f"event_{uuid.uuid4().hex}"


def _finish_id() -> str:
    return f"finish_{uuid.uuid4().hex}"


class ChatService:
    """Execute one idempotent Agent turn and emit success only after commit."""

    def __init__(
        self,
        *,
        settings: Settings,
        conversation: ConversationService,
        traces: TraceService,
        lease: SessionLease,
        model: FailoverChatModel,
        rag_module: HybridRAGModule,
        memory_factory: MemoryModuleFactory,
    ) -> None:
        self._settings = settings
        self._conversation = conversation
        self._traces = traces
        self._lease = lease
        self._model = model
        self._rag_module = rag_module
        self._memory_factory = memory_factory

    async def process(
        self,
        payload: ChatRequest,
        *,
        identity: AuthContext,
        request_id: str,
        trace_id: str,
        callback: StreamCallback,
    ) -> AgentResponse:
        started = time.monotonic()
        request_fingerprint = _fingerprint(payload, self._settings)
        trace_start = await self._traces.start_trace_with_status(
            TraceStartRequest(
                session_id=payload.session_id,
                execution_type="agent.chat",
                attributes={
                    "channel": payload.channel,
                    "feature": "medical_chat",
                    "module": "agent_harness",
                    "operation": "process_message",
                    "request_fingerprint": request_fingerprint,
                },
            ),
            request_id,
            trace_id=trace_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
        )
        trace = trace_start.trace
        if trace.status == TraceStatus.COMPLETED.value:
            stored = await self._conversation.get_replayed_assistant(
                tenant_id=identity.tenant_id,
                trace_id=trace_id,
                session_id=payload.session_id,
            )
            if stored is None:
                raise ChatReplayUnavailableError("completed chat trace has no stored response")
            response = self._conversation.to_agent_response(stored)
            await self._emit_replay(
                response,
                trace_id=trace_id,
                session_id=payload.session_id,
                callback=callback,
            )
            CHAT_TURNS.labels(outcome="replayed").inc()
            CHAT_TURN_LATENCY.observe(time.monotonic() - started)
            return response
        if trace.status != TraceStatus.RUNNING.value:
            raise ChatReplayUnavailableError("failed or cancelled chat traces cannot be replayed")

        owns_trace_execution = trace_start.created
        fencing_token: int | None = None
        lease_guard: SessionLeaseGuard | None = None
        failure_handled = False
        try:
            fencing_token = await self._conversation.next_fencing_token()
            async with self._lease.acquire(
                tenant_id=identity.tenant_id,
                session_id=payload.session_id,
                fencing_token=fencing_token,
            ) as acquired_guard:
                lease_guard = acquired_guard
                # A retry may safely adopt a previously running Trace only after it
                # proves that no other replica owns the session lease.
                owns_trace_execution = True
                try:
                    response = await self._process_owned_turn(
                        payload,
                        identity=identity,
                        request_id=request_id,
                        trace_id=trace_id,
                        request_fingerprint=request_fingerprint,
                        lease_guard=lease_guard,
                        callback=callback,
                    )
                except asyncio.CancelledError:
                    await self._finish_failure(
                        payload,
                        identity=identity,
                        trace_id=trace_id,
                        status=TraceStatus.CANCELLED,
                        code="CHAT_CANCELLED",
                        request_fingerprint=request_fingerprint,
                        fencing_token=fencing_token,
                        lease_guard=lease_guard,
                    )
                    failure_handled = True
                    raise
                except Exception as error:
                    await self._finish_failure(
                        payload,
                        identity=identity,
                        trace_id=trace_id,
                        status=TraceStatus.FAILED,
                        code=self.error_code(error),
                        request_fingerprint=request_fingerprint,
                        fencing_token=fencing_token,
                        lease_guard=lease_guard,
                    )
                    failure_handled = True
                    raise
                CHAT_TURNS.labels(outcome="completed").inc()
                CHAT_TURN_LATENCY.observe(time.monotonic() - started)
                return response
        except asyncio.CancelledError:
            if owns_trace_execution and not failure_handled:
                await self._finish_failure(
                    payload,
                    identity=identity,
                    trace_id=trace_id,
                    status=TraceStatus.CANCELLED,
                    code="CHAT_CANCELLED",
                    request_fingerprint=request_fingerprint,
                    fencing_token=fencing_token,
                    lease_guard=lease_guard,
                )
            CHAT_TURNS.labels(outcome="cancelled").inc()
            CHAT_TURN_LATENCY.observe(time.monotonic() - started)
            raise
        except Exception as error:
            if owns_trace_execution and not failure_handled:
                await self._finish_failure(
                    payload,
                    identity=identity,
                    trace_id=trace_id,
                    status=TraceStatus.FAILED,
                    code=self.error_code(error),
                    request_fingerprint=request_fingerprint,
                    fencing_token=fencing_token,
                    lease_guard=lease_guard,
                )
            CHAT_TURNS.labels(outcome="failed").inc()
            CHAT_TURN_LATENCY.observe(time.monotonic() - started)
            raise

    async def _process_owned_turn(
        self,
        payload: ChatRequest,
        *,
        identity: AuthContext,
        request_id: str,
        trace_id: str,
        request_fingerprint: str,
        lease_guard: SessionLeaseGuard,
        callback: StreamCallback,
    ) -> AgentResponse:
        conversation = await self._conversation.ensure_session(
            payload.session_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
        )
        conversation = await self._conversation.claim_fencing_token(
            payload.session_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            fencing_token=lease_guard.fencing_token,
            trace_id=trace_id,
        )
        if conversation.user_id is None:
            raise RuntimeError("conversation has no active user principal")
        memory = self._memory_factory(
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            user_id=conversation.user_id,
            session_id=payload.session_id,
            trace_id=trace_id,
        )
        short_term = await memory.get_short_term(
            str(payload.session_id),
            max_turns=max(1, self._settings.agent_history_messages // 2),
        )
        await self._conversation.store_user_message(
            tenant_id=identity.tenant_id,
            session_id=payload.session_id,
            trace_id=trace_id,
            text=payload.message,
            channel=payload.channel,
        )
        compressed = await memory.compress_context(
            short_term,
            max_tokens=max(
                1,
                int(self._model.context_size * self._settings.memory_context_budget_ratio),
            ),
        )
        history = [
            ConversationHistoryMessage(role=message.role, text=message.text())
            for message in compressed
            if message.role in {"user", "assistant"} and message.text()
        ]
        session_summary = "\n\n".join(
            message.text() for message in compressed if message.role == "system" and message.text()
        )
        profile_context, profile_version, memory_refs = await memory.core_profile_context()
        execution = ExecutionContext(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            session_id=payload.session_id,
        )
        harness = ProductionAgentHarness(
            settings=self._settings,
            model=self._model,
            rag_module=self._rag_module,
            memory_module=memory,
            execution=execution,
            history=history,
            profile_context=profile_context,
            profile_version=profile_version,
            memory_refs=memory_refs,
            session_summary=session_summary,
        )
        context = await harness.assemble_context(
            str(payload.session_id),
            identity.actor_id,
            payload.loaded_skills,
            [str(item) for item in payload.uploaded_files],
        )
        await self._append_event(
            identity.tenant_id,
            trace_id,
            TraceEventType.AGENT_START,
            TraceEventStatus.STARTED,
            {
                "channel": payload.channel,
                "feature": "medical_chat",
                "module": "agent_harness",
                "operation": "process_message",
            },
            commit=False,
        )

        async def projected(event: StreamEvent) -> None:
            if event.event_type == "done":
                return
            await callback(event)
            if event.event_type == "tool_result":
                data = event.data
                success = data.get("status") == "success"
                raw_duration = data.get("duration_ms")
                duration_ms = (
                    raw_duration
                    if isinstance(raw_duration, int) and not isinstance(raw_duration, bool)
                    else 0
                )
                await self._append_event(
                    identity.tenant_id,
                    trace_id,
                    TraceEventType.TOOL_CALL,
                    TraceEventStatus.SUCCEEDED if success else TraceEventStatus.FAILED,
                    {
                        "duration_ms": duration_ms,
                        "operation": "execute",
                        "outcome": "success" if success else "failed",
                        "success": success,
                        "tool_name": data.get("tool_name", "unknown_tool"),
                    },
                    duration_ms=duration_ms,
                    commit=False,
                )

        try:
            response = await harness.process_message(
                payload.message,
                str(payload.session_id),
                context,
                projected,
            )
            # Conversation and Trace repositories share this request's
            # AsyncSession. Stage the assistant plus success events, then let the
            # terminal Trace transition commit the whole success unit atomically.
            await lease_guard.assert_owned()
            conversation = await self._conversation.assert_fencing_token(
                payload.session_id,
                tenant_id=identity.tenant_id,
                actor_id=identity.actor_id,
                fencing_token=lease_guard.fencing_token,
                trace_id=trace_id,
            )
            await self._conversation.store_assistant_message(
                tenant_id=identity.tenant_id,
                session=conversation,
                trace_id=trace_id,
                response=response,
                commit=False,
            )
            await self._record_success(
                identity.tenant_id,
                trace_id,
                response,
                memory_update=memory.last_update,
                commit=False,
            )
            await self._traces.finish_trace(
                identity.tenant_id,
                trace_id,
                TraceFinishRequest(
                    idempotency_key=_finish_id(),
                    status=TraceStatus.COMPLETED,
                    attributes={
                        "outcome": "completed",
                        "request_fingerprint": request_fingerprint,
                        "success": True,
                    },
                ),
            )
        except BaseException:
            # Never leave a replayable assistant paired with a non-completed
            # Trace. The outer failure path records the durable failure after the
            # shared transaction has been cleared.
            try:
                await self._conversation.rollback()
            finally:
                await memory.compensate_uncommitted_vectors()
            raise
        memory.mark_vectors_committed()
        done = ChatDoneData(
            full_text=response.text,
            references=response.citations,
            safety=response.safety,
            trace_id=trace_id,
            session_id=payload.session_id,
        )
        await callback(
            StreamEvent(
                event_type="done",
                data=done.model_dump(mode="json"),
                timestamp=datetime.now(UTC),
            )
        )
        return response

    async def _record_success(
        self,
        tenant_id: str,
        trace_id: str,
        response: AgentResponse,
        *,
        memory_update: MemoryUpdateResult,
        commit: bool = True,
    ) -> None:
        structured = response.structured
        selected = structured.get("model_preference")
        model_slot = selected if isinstance(selected, str) else "unknown"
        input_tokens = structured.get("input_tokens")
        output_tokens = structured.get("output_tokens")
        input_tokens = input_tokens if isinstance(input_tokens, int) else 0
        output_tokens = output_tokens if isinstance(output_tokens, int) else 0
        retry_count = structured.get("model_failures")
        retry_count = retry_count if isinstance(retry_count, int) else 0
        await self._append_event(
            tenant_id,
            trace_id,
            TraceEventType.MODEL_CALL,
            TraceEventStatus.SUCCEEDED,
            {
                "input_tokens": input_tokens,
                "model": model_slot,
                "outcome": "success",
                "output_tokens": output_tokens,
                "retry_count": retry_count,
                "success": True,
                "total_tokens": input_tokens + output_tokens,
            },
            commit=commit,
        )
        if response.citations:
            citation_ids: list[JsonValue] = [item.source_id for item in response.citations]
            await self._append_event(
                tenant_id,
                trace_id,
                TraceEventType.RAG_RETRIEVE,
                TraceEventStatus.SUCCEEDED,
                {
                    "chunk_ids": citation_ids,
                    "citation_ids": citation_ids,
                    "document_count": len({item.title for item in response.citations}),
                    "operation": "agentic_evidence",
                    "success": True,
                },
                commit=commit,
            )
        memory_ids: list[JsonValue] = [str(item) for item in memory_update.changed_fact_ids]
        memory_categories: list[JsonValue] = list(memory_update.categories)
        memory_changed = bool(memory_ids)
        await self._append_event(
            tenant_id,
            trace_id,
            TraceEventType.MEMORY_UPDATE,
            TraceEventStatus.SUCCEEDED if memory_changed else TraceEventStatus.SKIPPED,
            {
                "categories": memory_categories,
                "confirmed_count": memory_update.confirmed_count,
                "event_count": len(memory_ids),
                "inactive_count": memory_update.inactive_count,
                "memory_ids": memory_ids,
                "outcome": "updated" if memory_changed else "unchanged",
                "pending_count": memory_update.pending_count,
                "success": True,
                "version": memory_update.profile_version,
            },
            commit=commit,
        )
        safety_flags: list[JsonValue] = list(response.safety.notices)
        await self._append_event(
            tenant_id,
            trace_id,
            TraceEventType.SAFETY_CHECK,
            TraceEventStatus.SUCCEEDED,
            {"outcome": "safe", "safety_flags": safety_flags, "success": True},
            commit=commit,
        )
        await self._append_event(
            tenant_id,
            trace_id,
            TraceEventType.AGENT_FINISH,
            TraceEventStatus.SUCCEEDED,
            {
                "citation_count": len(response.citations),
                "input_tokens": input_tokens,
                "model": model_slot,
                "outcome": "completed",
                "output_tokens": output_tokens,
                "safety_flags": safety_flags,
                "success": True,
                "total_tokens": input_tokens + output_tokens,
            },
            commit=commit,
        )

    async def _append_event(
        self,
        tenant_id: str,
        trace_id: str,
        event_type: TraceEventType,
        status: TraceEventStatus,
        payload: dict[str, JsonValue],
        *,
        duration_ms: int | None = None,
        commit: bool = True,
    ) -> None:
        await self._traces.append_event(
            tenant_id,
            trace_id,
            TraceEventCreate(
                event_id=_event_id(),
                event_type=event_type,
                status=status,
                payload=payload,
                duration_ms=duration_ms,
            ),
            commit=commit,
        )

    async def _finish_failure(
        self,
        payload: ChatRequest,
        *,
        identity: AuthContext,
        trace_id: str,
        status: TraceStatus,
        code: str,
        request_fingerprint: str,
        fencing_token: int | None,
        lease_guard: SessionLeaseGuard | None,
    ) -> None:
        try:
            # A memory tool may have staged encrypted facts before the agent
            # fails. Clear the shared unit of work before recording the durable
            # failure Trace, otherwise a failure transition could commit it.
            await self._conversation.rollback()
            if fencing_token is not None:
                allowed = await self._conversation.lock_trace_failure_fence(
                    payload.session_id,
                    tenant_id=identity.tenant_id,
                    actor_id=identity.actor_id,
                    fencing_token=fencing_token,
                    trace_id=trace_id,
                )
                if not allowed:
                    return
            if lease_guard is not None:
                await lease_guard.assert_owned()
            await self._traces.append_event(
                identity.tenant_id,
                trace_id,
                TraceEventCreate(
                    event_id=_event_id(),
                    event_type=TraceEventType.SYSTEM_ERROR,
                    status=(
                        TraceEventStatus.CANCELLED
                        if status is TraceStatus.CANCELLED
                        else TraceEventStatus.FAILED
                    ),
                    payload={
                        "error_code": code,
                        "module": "agent_harness",
                        "operation": "process_message",
                        "result_code": code,
                    },
                ),
                commit=False,
            )
            await self._traces.finish_trace(
                identity.tenant_id,
                trace_id,
                TraceFinishRequest(
                    idempotency_key=_finish_id(),
                    status=status,
                    error_code=code.casefold(),
                    error_summary="chat execution did not complete",
                    attributes={
                        "outcome": status.value,
                        "request_fingerprint": request_fingerprint,
                        "success": False,
                    },
                ),
            )
        except Exception:
            await self._conversation.rollback()
            # The original safe failure remains authoritative. Trace persistence
            # errors are logged by the route's request logger without user text.
            return

    async def _emit_replay(
        self,
        response: AgentResponse,
        *,
        trace_id: str,
        session_id: uuid.UUID,
        callback: StreamCallback,
    ) -> None:
        await callback(
            StreamEvent(
                event_type="agent_start",
                data={"agent": "gerclaw_geriatric_specialist", "status": "replay"},
                timestamp=datetime.now(UTC),
            )
        )
        for start in range(0, len(response.text), 80):
            await callback(
                StreamEvent(
                    event_type="text_delta",
                    data={"content": response.text[start : start + 80]},
                    timestamp=datetime.now(UTC),
                )
            )
        done = ChatDoneData(
            full_text=response.text,
            references=response.citations,
            safety=response.safety,
            trace_id=trace_id,
            session_id=session_id,
            replayed=True,
        )
        await callback(
            StreamEvent(
                event_type="done",
                data=done.model_dump(mode="json"),
                timestamp=datetime.now(UTC),
            )
        )

    @staticmethod
    def error_code(error: Exception) -> str:
        """Map internal exceptions to stable, non-provider public codes."""

        name = type(error).__name__
        mapping = {
            "SessionBusyError": "CHAT_SESSION_BUSY",
            "SessionLeaseUnavailableError": "CHAT_COORDINATION_UNAVAILABLE",
            "SessionLeaseLostError": "CHAT_COORDINATION_UNAVAILABLE",
            "ConversationConflictError": "CHAT_CONFLICT",
            "ConversationNotFoundError": "CHAT_SESSION_NOT_FOUND",
            "EvidenceUnavailableError": "CHAT_EVIDENCE_UNAVAILABLE",
            "RAGUnavailableError": "CHAT_EVIDENCE_UNAVAILABLE",
            "ModelChainExhaustedError": "CHAT_MODEL_UNAVAILABLE",
            "PartialModelStreamError": "CHAT_MODEL_STREAM_INTERRUPTED",
            "AgentIterationLimitError": "CHAT_ITERATION_LIMIT",
            "AgentApprovalRequiredError": "CHAT_APPROVAL_REQUIRED",
            "UnsupportedAgentContextError": "CHAT_CONTEXT_UNSUPPORTED",
            "EmptyAgentResponseError": "CHAT_EMPTY_RESPONSE",
            "AgentScopeMemoryAdapterError": "CHAT_MEMORY_UNAVAILABLE",
            "MemoryDataError": "CHAT_MEMORY_UNAVAILABLE",
            "MemoryExtractionError": "CHAT_MEMORY_UNAVAILABLE",
            "MemoryRepositoryError": "CHAT_MEMORY_UNAVAILABLE",
            "MemoryStoreError": "CHAT_MEMORY_UNAVAILABLE",
        }
        return mapping.get(name, "CHAT_EXECUTION_FAILED")
