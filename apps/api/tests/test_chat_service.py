"""Chat ownership and public error semantics."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from agentscope.credential import CredentialBase
from agentscope.message import Msg, TextBlock
from agentscope.model import ChatModelBase, ChatResponse, ChatUsage
from agentscope.tool import ToolChoice

from gerclaw_api.api.routes.chat import _encode_sse
from gerclaw_api.auth import AuthContext
from gerclaw_api.config import Settings
from gerclaw_api.database.models import ConversationSession, ExecutionTrace, Message
from gerclaw_api.domain.chat_error_codes import public_chat_error
from gerclaw_api.domain.chat_schemas import ChatRequest
from gerclaw_api.domain.enums import TraceStatus
from gerclaw_api.domain.run_schemas import (
    TERMINAL_RUN_STATUSES,
    AgentRunCreate,
    AgentRunRead,
    AgentRunStatus,
    AnswerVersionRead,
    RunAnswerContext,
    RunAttemptCreate,
    RunAttemptRead,
    RunAttemptStatus,
    RunDirectiveClaim,
    RunDirectiveMode,
    RunDirectiveRead,
    RunDirectiveStatus,
    RunEventRead,
    RunEventWrite,
    RunRegenerationContext,
    ValidationFeedback,
)
from gerclaw_api.domain.trace_schemas import (
    TraceEventCreate,
    TraceFinishRequest,
    TraceStartRequest,
)
from gerclaw_api.modules.agent_harness.clinical_state import (
    ClinicalFact,
    ClinicalState,
    FactProvenance,
)
from gerclaw_api.modules.agent_harness.context_snapshot import (
    ContextBoundaryDraft,
    ControlledSuccessorState,
    FrozenRunState,
    PersistedContextSnapshot,
    PersistedRunPlan,
)
from gerclaw_api.modules.agent_harness.planning import (
    PlanExecutionSnapshot,
    PlanNodeStatus,
)
from gerclaw_api.modules.agent_harness.plugin_runtime import CapabilityResult
from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.modules.agent_harness.run_lifecycle import RunFenceConflictError
from gerclaw_api.modules.memory.models import MemoryUpdateResult
from gerclaw_api.modules.memory.protocols import MemoryMessage, UserProfile
from gerclaw_api.modules.orchestration import ChatSteeredInterruption
from gerclaw_api.modules.rag.protocols import RetrievalResult
from gerclaw_api.modules.runtime.models import ActorRole
from gerclaw_api.security import JsonValue
from gerclaw_api.services.chat_service import (
    ChatCancellationFinalizationError,
    ChatService,
    _runtime_principal,
)
from gerclaw_api.services.session_lease import SessionBusyError, SessionLeaseLostError
from gerclaw_api.services.trace_service import TraceStartResult


class _TextModel(ChatModelBase):
    class Parameters(ChatModelBase.Parameters):
        pass

    def __init__(self) -> None:
        self.last_messages: list[Msg] = []
        super().__init__(
            credential=CredentialBase(name="test"),
            model="chat-service-test",
            parameters=self.Parameters(),
            stream=True,
            max_retries=0,
            context_size=8_192,
        )

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        del model_name, tools, tool_choice, kwargs
        self.last_messages = messages

        async def stream() -> AsyncGenerator[ChatResponse, None]:
            text = (
                "1. 保留最重要的晨间安排。\n"
                "2. 保留最重要的日间安排。\n"
                "3. 保留最重要的晚间安排。"
                if any(message.name == "answer_presentation_contract" for message in messages)
                else "您好, 很高兴为您服务。"
            )
            yield ChatResponse(content=[TextBlock(text=text)], is_last=False)
            yield ChatResponse(
                content=[TextBlock(text=text)],
                is_last=True,
                usage=ChatUsage(input_tokens=4, output_tokens=6, time=0.01),
            )

        return stream()


class _ProtocolRepairModel(_TextModel):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        del model_name, tools, tool_choice, kwargs
        self.calls += 1
        self.last_messages = messages
        text = (
            '<invoke name="search_knowledge"><parameter name="query">作息</parameter></invoke>'
            if self.calls == 1
            else "1. 固定起床时间。\n2. 白天适量活动。\n3. 睡前减少刺激。"
        )

        async def stream() -> AsyncGenerator[ChatResponse, None]:
            yield ChatResponse(content=[TextBlock(text=text)], is_last=False)
            yield ChatResponse(
                content=[TextBlock(text=text)],
                is_last=True,
                usage=ChatUsage(input_tokens=4, output_tokens=6, time=0.01),
            )

        return stream()


class _NoopRAG:
    async def retrieve(self, *_args: object, **_kwargs: object) -> list[object]:
        return []


class _EvidenceRAG:
    async def retrieve(self, *_args: object, **_kwargs: object) -> list[RetrievalResult]:
        return [
            RetrievalResult(
                content="老年高血压管理应定期测量并记录血压。",
                source="老年高血压指南.md",
                score=0.9,
                metadata={
                    "chunk_id": "chunk-chat-memory-warning",
                    "document_id": "document-chat-memory-warning",
                    "title": "老年高血压管理指南",
                    "chapter": "综合评估",
                    "category": "高血压",
                    "source_type": "guideline",
                    "publish_year": 2024,
                    "chunk_index": 1,
                    "total_chunks": 2,
                },
            )
        ]


class _MedicalTextModel(_TextModel):
    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        del model_name, tools, tool_choice, kwargs
        self.last_messages = messages

        async def stream() -> AsyncGenerator[ChatResponse, None]:
            text = "建议每天定时测量并记录血压 [E1]。"
            yield ChatResponse(content=[TextBlock(text=text)], is_last=False)
            yield ChatResponse(
                content=[TextBlock(text=text)],
                is_last=True,
                usage=ChatUsage(input_tokens=4, output_tokens=6, time=0.01),
            )

        return stream()


class _MemoryFacade:
    def __init__(self) -> None:
        self.short_term_sessions: list[str] = []
        self.sources: list[str] = []
        self.last_update = MemoryUpdateResult(profile_version=1)
        self.compensation_count = 0
        self.committed_count = 0

    async def get_short_term(self, session_id: str, max_turns: int) -> list[MemoryMessage]:
        del max_turns
        self.short_term_sessions.append(session_id)
        return []

    async def compress_context(
        self, messages: list[MemoryMessage], max_tokens: int
    ) -> list[MemoryMessage]:
        assert max_tokens > 0
        return messages

    async def get_context_summary(self) -> str:
        return ""

    async def core_profile_context(self) -> tuple[str, int, list[str]]:
        return "", 1, []

    async def get_long_term(self, _actor_id: str, query: str | None = None) -> UserProfile:
        del query
        return UserProfile(schema_version=1, version=1, profile={})

    async def extract_and_update_profile(
        self, _actor_id: str, conversation: list[MemoryMessage]
    ) -> None:
        self.sources.extend(message.text() for message in conversation)

    async def compensate_uncommitted_vectors(self) -> bool:
        self.compensation_count += 1
        return True

    def mark_vectors_committed(self) -> None:
        self.committed_count += 1


class _FailingCompressionMemory(_MemoryFacade):
    async def get_short_term(self, session_id: str, max_turns: int) -> list[MemoryMessage]:
        await super().get_short_term(session_id, max_turns)
        return [
            MemoryMessage(
                role="user" if index % 2 == 0 else "assistant",
                content=[
                    {
                        "type": "text",
                        "text": (
                            "必须继续保留用户要求和验收标准。"
                            if index == 0
                            else "较旧的重复上下文。" * 120
                        ),
                    }
                ],
            )
            for index in range(20)
        ]

    async def compress_context(
        self, messages: list[MemoryMessage], max_tokens: int
    ) -> list[MemoryMessage]:
        del messages, max_tokens
        raise RuntimeError("injected context compressor failure")


class _FailingWriteMemory(_MemoryFacade):
    async def extract_and_update_profile(
        self, _actor_id: str, conversation: list[MemoryMessage]
    ) -> None:
        self.sources.extend(message.text() for message in conversation)
        raise RuntimeError("injected memory extraction failure")


def _memory_factory(memory: _MemoryFacade | None = None) -> Any:
    instance = memory or _MemoryFacade()

    def factory(**_kwargs: object) -> _MemoryFacade:
        return instance

    return factory


class _ConversationFacade:
    def __init__(self, session_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        self.session = ConversationSession(
            id=session_id,
            user_id=uuid.uuid4(),
            tenant_id="tenant_public0001",
            agent_id="gerclaw-geriatric-specialist",
            status="active",
            context_summary={},
            created_at=now,
            updated_at=now,
        )
        self.user_text: str | None = None
        self.response: object | None = None
        self.assistant_commit: bool | None = None
        self.failure_text: str | None = None
        self.rollback_count = 0
        self.history_exclude_trace_id: str | None = None
        self.active_fencing_token = 0
        self.active_fencing_trace_id: str | None = None

    async def next_fencing_token(self) -> int:
        return 17

    async def claim_fencing_token(self, *_args: object, **kwargs: object) -> ConversationSession:
        self.active_fencing_token = cast(int, kwargs["fencing_token"])
        self.active_fencing_trace_id = cast(str, kwargs["trace_id"])
        return self.session

    async def assert_fencing_token(self, *_args: object, **_kwargs: object) -> ConversationSession:
        return self.session

    async def lock_trace_failure_fence(self, *_args: object, **kwargs: object) -> bool:
        fencing_token = cast(int, kwargs["fencing_token"])
        trace_id = cast(str, kwargs["trace_id"])
        return not (
            self.active_fencing_trace_id == trace_id and self.active_fencing_token > fencing_token
        )

    async def ensure_session(self, *_args: object, **_kwargs: object) -> ConversationSession:
        return self.session

    async def load_history(self, *_args: object, **kwargs: object) -> list[object]:
        self.history_exclude_trace_id = cast(str | None, kwargs.get("exclude_trace_id"))
        return []

    async def store_user_message(self, **kwargs: object) -> Message:
        self.user_text = cast(str, kwargs["text"])
        return Message(
            id=uuid.uuid4(),
            tenant_id=self.session.tenant_id,
            session_id=self.session.id,
            trace_id=cast(str, kwargs["trace_id"]),
            role="user",
            content=[{"type": "text", "text": self.user_text}],
            message_metadata={},
            created_at=datetime.now(UTC),
        )

    async def store_assistant_message(self, **kwargs: object) -> Message:
        self.response = kwargs["response"]
        self.assistant_commit = cast(bool, kwargs["commit"])
        return Message(
            id=uuid.uuid4(),
            tenant_id=self.session.tenant_id,
            session_id=self.session.id,
            trace_id=cast(str, kwargs["trace_id"]),
            role="assistant",
            content=[{"type": "text", "text": cast(Any, self.response).text}],
            message_metadata={},
            created_at=datetime.now(UTC),
        )

    async def store_failure_message(self, **kwargs: object) -> Message:
        self.failure_text = cast(str, kwargs["text"])
        return Message(
            id=uuid.uuid4(),
            tenant_id=self.session.tenant_id,
            session_id=self.session.id,
            trace_id=cast(str, kwargs["trace_id"]),
            role="assistant",
            content=[{"type": "text", "text": self.failure_text}],
            message_metadata={"failed_turn_notice": True},
            created_at=datetime.now(UTC),
        )

    async def rollback(self) -> None:
        self.response = None
        self.rollback_count += 1

    async def get_replayed_assistant(self, **_kwargs: object) -> object | None:
        return self.response

    def to_agent_response(self, stored: object) -> Any:
        return stored


class _UnverifiableConversation(_ConversationFacade):
    async def lock_trace_failure_fence(self, *_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("database ownership check unavailable")


class _OwnedLease:
    @asynccontextmanager
    async def acquire(self, **kwargs: object) -> AsyncIterator[object]:
        yield _LeaseGuard(cast(int, kwargs["fencing_token"]))


class _BusyLease:
    @asynccontextmanager
    async def acquire(self, **_kwargs: object) -> AsyncIterator[object]:
        raise SessionBusyError("busy")
        yield  # pragma: no cover - required async-contextmanager shape


class _LeaseGuard:
    def __init__(self, fencing_token: int) -> None:
        self.fencing_token = fencing_token

    async def assert_owned(self) -> None:
        return None


class _SupersedingLease:
    def __init__(self, conversation: _ConversationFacade) -> None:
        self.conversation = conversation

    @asynccontextmanager
    async def acquire(self, **kwargs: object) -> AsyncIterator[object]:
        yield _SupersedingLeaseGuard(cast(int, kwargs["fencing_token"]), self.conversation)


class _SupersedingLeaseGuard(_LeaseGuard):
    def __init__(self, fencing_token: int, conversation: _ConversationFacade) -> None:
        super().__init__(fencing_token)
        self.conversation = conversation

    async def assert_owned(self) -> None:
        self.conversation.active_fencing_token = self.fencing_token + 1
        raise SessionLeaseLostError("successor adopted the same Trace")


class _TraceFacade:
    def __init__(
        self,
        *,
        created: bool,
        session_id: uuid.UUID,
        fail_completed_finish: bool = False,
        fail_cancelled_finish: bool = False,
    ) -> None:
        self.created = created
        self.fail_completed_finish = fail_completed_finish
        self.fail_cancelled_finish = fail_cancelled_finish
        self.events: list[TraceEventCreate] = []
        self.finishes: list[TraceFinishRequest] = []
        self.start_request: TraceStartRequest | None = None
        self.trace = ExecutionTrace(
            trace_id="trace_chat_busy_0001",
            request_id="request_chat_busy_0001",
            tenant_id="tenant_public0001",
            actor_id="usr_patient_unit0001",
            session_id=session_id,
            execution_type="agent.chat",
            status="running",
            attributes={},
            started_at=datetime.now(UTC),
        )

    async def start_trace_with_status(
        self, request: TraceStartRequest, *_args: object, **_kwargs: object
    ) -> TraceStartResult:
        self.start_request = request
        return TraceStartResult(trace=self.trace, created=self.created)

    async def append_event(
        self,
        _tenant_id: str,
        _trace_id: str,
        request: TraceEventCreate,
        *,
        commit: bool = True,
    ) -> None:
        del commit
        self.events.append(request)

    async def finish_trace(
        self,
        _tenant_id: str,
        _trace_id: str,
        request: TraceFinishRequest,
        *,
        commit: bool = True,
    ) -> ExecutionTrace:
        del commit
        if self.fail_completed_finish and request.status is TraceStatus.COMPLETED:
            raise RuntimeError("injected terminal Trace commit failure")
        if self.fail_cancelled_finish and request.status is TraceStatus.CANCELLED:
            raise RuntimeError("injected cancelled Trace commit failure")
        self.finishes.append(request)
        self.trace.status = request.status.value
        return self.trace


class _RiskAlertRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def sync_chat_red_flag(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


class _RunJournal:
    def __init__(self) -> None:
        self.run_id = uuid.uuid4()
        self.start_requests: list[AgentRunCreate] = []
        self.events: list[RunEventWrite] = []
        self.answer_message_ids: list[uuid.UUID] = []
        self.transitions: list[AgentRunStatus] = []
        self.regeneration: RunRegenerationContext | None = None
        self.completion_error: Exception | None = None
        self.clinical_state = ClinicalState()
        self.attempt: RunAttemptRead | None = None
        self.rejected_attempts: list[ValidationFeedback] = []
        self.attempt_count = 0
        self.attempt_event_start = 0
        self.plan_executions: list[PlanExecutionSnapshot] = []
        self.completion_warnings: tuple[str, ...] = ()
        self.context_boundaries: list[tuple[str, int, ContextBoundaryDraft]] = []

    async def resolve_regeneration(
        self,
        request: ChatRequest,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunRegenerationContext | None:
        del request, tenant_id, actor_id
        return self.regeneration

    async def read_answer_context(
        self,
        trace_id: str,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunAnswerContext | None:
        del trace_id, tenant_id, actor_id
        if not self.answer_message_ids:
            return None
        return RunAnswerContext(
            run_id=self.run_id,
            answer_group_run_id=self.run_id,
            answer_version_id=uuid.uuid4(),
            answer_version=1,
        )

    async def read_clinical_state(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> ClinicalState:
        del conversation_id, tenant_id, actor_id
        return self.clinical_state

    async def start(
        self,
        request: AgentRunCreate,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRunRead:
        del tenant_id, actor_id
        self.start_requests.append(request)
        return self._run(request, AgentRunStatus.RUNNING, revision=1)

    async def append(
        self,
        run_id: uuid.UUID,
        event: RunEventWrite,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunEventRead:
        del tenant_id, actor_id
        assert run_id == self.run_id
        assert fencing_token == 17
        self.events.append(event)
        return RunEventRead(
            run_id=run_id,
            sequence=len(self.events),
            **event.model_dump(),
            created_at=datetime.now(UTC),
        )

    async def append_context_boundary(
        self,
        run_id: uuid.UUID,
        draft: ContextBoundaryDraft,
        *,
        boundary_kind: str,
        model_call_count: int,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> object:
        del tenant_id, actor_id
        assert run_id == self.run_id
        assert fencing_token == 17
        self.context_boundaries.append((boundary_kind, model_call_count, draft))
        return object()

    async def update_plan_execution(
        self,
        run_id: uuid.UUID,
        updated: PlanExecutionSnapshot,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        capability_result: object | None = None,
    ) -> PlanExecutionSnapshot:
        del tenant_id, actor_id, capability_result
        assert run_id == self.run_id
        assert fencing_token == 17
        self.plan_executions.append(updated)
        return updated

    async def begin_attempt(
        self,
        run_id: uuid.UUID,
        request: RunAttemptCreate,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        del tenant_id, actor_id
        assert run_id == self.run_id
        self.attempt_count += 1
        self.attempt_event_start = len(self.events)
        self.attempt = RunAttemptRead(
            id=request.id,
            run_id=run_id,
            public_operation_id=request.public_operation_id,
            attempt=self.attempt_count,
            step_id=request.step_id,
            checkpoint_id=request.checkpoint_id,
            fencing_token=fencing_token,
            status=RunAttemptStatus.STAGING,
            expected_current_attempt_id=request.expected_current_attempt_id,
            created_at=datetime.now(UTC),
        )
        return self.attempt

    async def stage_attempt_event(
        self,
        attempt_id: uuid.UUID,
        event: RunEventWrite,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        del tenant_id, actor_id
        assert self.attempt is not None
        assert attempt_id == self.attempt.id
        assert fencing_token == 17
        self.events.append(event)
        return self.attempt

    async def reject_attempt(
        self,
        attempt_id: uuid.UUID,
        feedback: ValidationFeedback,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunAttemptRead:
        del tenant_id, actor_id
        assert self.attempt is not None
        assert attempt_id == self.attempt.id
        assert fencing_token == 17
        self.rejected_attempts.append(feedback)
        del self.events[self.attempt_event_start :]
        self.attempt = self.attempt.model_copy(
            update={
                "status": RunAttemptStatus.REJECTED,
                "error_code": feedback.error_code,
                "feedback": feedback,
                "completed_at": datetime.now(UTC),
            }
        )
        return self.attempt

    async def complete_answer(
        self,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        done_payload: dict[str, JsonValue],
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        answer_group_run_id: uuid.UUID | None = None,
        expected_current_version_id: uuid.UUID | None = None,
        warnings: tuple[str, ...] = (),
    ) -> tuple[AnswerVersionRead, AgentRunRead, tuple[RunEventRead, ...]]:
        del tenant_id, actor_id, expected_current_version_id
        assert run_id == self.run_id
        assert self.attempt is not None
        assert attempt_id == self.attempt.id
        assert fencing_token == 17
        if self.completion_error is not None:
            raise self.completion_error
        self.answer_message_ids.append(assistant_message_id)
        answer = AnswerVersionRead(
            id=uuid.uuid4(),
            run_id=answer_group_run_id or run_id,
            producer_run_id=run_id,
            answer_group_id=uuid.uuid4(),
            assistant_message_id=assistant_message_id,
            version=1,
            is_current=True,
            created_at=datetime.now(UTC),
        )
        terminal_status = (
            AgentRunStatus.COMPLETED_WITH_WARNINGS if warnings else AgentRunStatus.COMPLETED
        )
        self.completion_warnings = warnings
        self.events.append(
            RunEventWrite(
                event_type="done",
                status=terminal_status.value,
                payload=cast(dict[str, Any], done_payload),
            )
        )
        self.transitions.append(terminal_status)
        public_events = tuple(
            RunEventRead(
                run_id=run_id,
                sequence=index,
                **event.model_dump(),
                created_at=datetime.now(UTC),
            )
            for index, event in enumerate(self.events, start=1)
        )
        return (
            answer,
            self._run(
                self.start_requests[0],
                terminal_status,
                revision=len(self.transitions) + 1,
            ),
            public_events,
        )

    async def complete_with_warnings(
        self,
        run_id: uuid.UUID,
        done_payload: dict[str, object],
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        warnings: tuple[str, ...],
    ) -> AgentRunRead:
        del tenant_id, actor_id, fencing_token, warnings
        assert run_id == self.run_id
        self.events.append(
            RunEventWrite(
                event_type="done",
                status="completed_with_warnings",
                payload=cast(dict[str, Any], done_payload),
            )
        )
        self.transitions.append(AgentRunStatus.COMPLETED_WITH_WARNINGS)
        return self._run(
            self.start_requests[0],
            AgentRunStatus.COMPLETED_WITH_WARNINGS,
            revision=len(self.transitions) + 1,
        )

    async def transition(
        self,
        run_id: uuid.UUID,
        target: AgentRunStatus,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        warnings: tuple[str, ...] = (),
        public_summary: str | None = None,
    ) -> AgentRunRead:
        del tenant_id, actor_id, fencing_token, warnings, public_summary
        assert run_id == self.run_id
        self.transitions.append(target)
        return self._run(
            self.start_requests[0],
            target,
            revision=len(self.transitions) + 1,
        )

    def _run(
        self,
        request: AgentRunCreate,
        status: AgentRunStatus,
        *,
        revision: int,
    ) -> AgentRunRead:
        return AgentRunRead(
            id=self.run_id,
            conversation_id=request.conversation_id,
            input_message_id=request.input_message_id,
            trace_id=request.trace_id,
            route=request.route,
            status=status,
            last_sequence=len(self.events),
            revision=revision,
            started_at=datetime.now(UTC),
            interrupted_at=(datetime.now(UTC) if status is AgentRunStatus.INTERRUPTED else None),
            completed_at=(datetime.now(UTC) if status in TERMINAL_RUN_STATUSES else None),
        )


class _CapabilityRuntime:
    def __init__(self, run_journal: _RunJournal, *, fail: bool = False) -> None:
        self._run_journal = run_journal
        self._fail = fail
        self.calls: list[str] = []

    async def invoke(
        self,
        capability_id: str,
        payload: dict[str, JsonValue],
    ) -> CapabilityResult:
        assert self._run_journal.start_requests
        assert self._run_journal.plan_executions
        assert any(
            status is PlanNodeStatus.RUNNING
            for status in self._run_journal.plan_executions[-1].statuses.values()
        )
        assert payload["trace_id"]
        self.calls.append(capability_id)
        if self._fail:
            raise RuntimeError("capability owner unavailable")
        return CapabilityResult(
            capability_id=capability_id,
            result_ref=f"owner:{capability_id}:unit",
            public_summary="专业能力已完成。",
        )


class _DirectiveJournal:
    def __init__(self) -> None:
        self.claimed = False
        self.applied: list[tuple[uuid.UUID, RunDirectiveClaim]] = []
        self.directive_id = uuid.uuid4()
        self.recent: tuple[RunDirectiveRead, ...] = ()
        self.successor_bindings: list[tuple[uuid.UUID, uuid.UUID, int]] = []

    async def bind_successor_input(
        self,
        directive_id: uuid.UUID,
        successor_run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> RunDirectiveRead:
        del tenant_id, actor_id
        self.successor_bindings.append((directive_id, successor_run_id, fencing_token))
        now = datetime.now(UTC)
        return RunDirectiveRead(
            id=directive_id,
            conversation_id=uuid.uuid4(),
            target_run_id=uuid.uuid4(),
            successor_run_id=successor_run_id,
            sequence=1,
            mode=RunDirectiveMode.INTERRUPT_AND_STEER,
            status=RunDirectiveStatus.APPLIED,
            instruction="请按新要求继续。",
            idempotency_key="directive-successor-input-1",
            claimed_by_fencing_token=fencing_token,
            claim_boundary_id="successor.input.v1",
            revision=2,
            created_at=now,
            claimed_at=now,
            applied_at=now,
        )

    async def list_recent_applied_directives(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        del conversation_id, tenant_id, actor_id
        return self.recent[-limit:]

    async def list_applied_directives(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        after_sequence: int,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        del run_id, tenant_id, actor_id, after_sequence, limit
        return ()

    async def claim_directives(
        self,
        run_id: uuid.UUID,
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        del run_id, tenant_id, actor_id, limit
        if self.claimed:
            return ()
        self.claimed = True
        now = datetime.now(UTC)
        return (
            RunDirectiveRead(
                id=self.directive_id,
                conversation_id=uuid.uuid4(),
                target_run_id=uuid.uuid4(),
                sequence=1,
                mode=RunDirectiveMode.QUEUE_FOR_NEXT_BOUNDARY,
                status=RunDirectiveStatus.CLAIMED,
                instruction="请把回答控制在两句话以内。",
                idempotency_key="directive-chat-service-1",
                claimed_by_fencing_token=claim.fencing_token,
                claim_boundary_id=claim.boundary_id,
                revision=2,
                created_at=now,
                claimed_at=now,
            ),
        )

    async def mark_directives_applied(
        self,
        run_id: uuid.UUID,
        directive_ids: tuple[uuid.UUID, ...],
        claim: RunDirectiveClaim,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> tuple[RunDirectiveRead, ...]:
        del run_id, tenant_id, actor_id
        self.applied.extend((directive_id, claim) for directive_id in directive_ids)
        now = datetime.now(UTC)
        return tuple(
            RunDirectiveRead(
                id=directive_id,
                conversation_id=uuid.uuid4(),
                target_run_id=uuid.uuid4(),
                sequence=1,
                mode=RunDirectiveMode.QUEUE_FOR_NEXT_BOUNDARY,
                status=RunDirectiveStatus.APPLIED,
                instruction="请把回答控制在两句话以内。",
                idempotency_key="directive-chat-service-1",
                claimed_by_fencing_token=claim.fencing_token,
                claim_boundary_id=claim.boundary_id,
                revision=3,
                created_at=now,
                claimed_at=now,
                applied_at=now,
            )
            for directive_id in directive_ids
        )


@pytest.mark.parametrize(
    ("role", "expected_role", "has_patient_proof"),
    [
        ("guest", ActorRole.GUEST, True),
        ("patient", ActorRole.PATIENT, True),
        ("doctor", ActorRole.DOCTOR, False),
        ("admin", ActorRole.ADMIN, False),
    ],
)
def test_runtime_principal_keeps_account_role_and_never_invents_doctor_patient_access(
    role: str, expected_role: ActorRole, has_patient_proof: bool
) -> None:
    user_id = uuid.uuid4()
    principal = _runtime_principal(
        AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            role=cast(Any, role),
            scopes=frozenset({"chat:write"}),
        ),
        user_id=user_id,
    )

    assert principal.role is expected_role
    assert principal.patient_access_verified is has_patient_proof
    if has_patient_proof:
        assert principal.patient_id == user_id
    else:
        assert principal.patient_id is None


@pytest.mark.asyncio
async def test_busy_new_trace_is_durably_failed_by_its_creator(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, traces),
        lease=cast(Any, _BusyLease()),
        model=cast(Any, None),
        rag_module=cast(Any, None),
        memory_factory=_memory_factory(),
    )

    async def callback(_event: object) -> None:
        return None

    with pytest.raises(SessionBusyError):
        await service.process(
            ChatRequest(session_id=session_id, message="您好"),
            identity=AuthContext(
                actor_id="usr_patient_unit0001",
                tenant_id="tenant_public0001",
                scopes=frozenset({"chat:write"}),
            ),
            request_id="request_chat_busy_0001",
            trace_id="trace_chat_busy_0001",
            callback=cast(Any, callback),
        )

    assert len(traces.events) == 1
    assert len(traces.finishes) == 1
    assert traces.trace.status == "failed"


@pytest.mark.asyncio
async def test_unverifiable_fence_never_mutates_possibly_adopted_trace(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _UnverifiableConversation(session_id)),
        traces=cast(Any, traces),
        lease=cast(Any, _BusyLease()),
        model=cast(Any, None),
        rag_module=cast(Any, None),
        memory_factory=_memory_factory(),
    )

    async def callback(_event: object) -> None:
        return None

    with pytest.raises(SessionBusyError):
        await service.process(
            ChatRequest(session_id=session_id, message="您好"),
            identity=AuthContext(
                actor_id="usr_patient_unit0001",
                tenant_id="tenant_public0001",
                scopes=frozenset({"chat:write"}),
            ),
            request_id="request_chat_unverified_0001",
            trace_id="trace_chat_busy_0001",
            callback=cast(Any, callback),
        )
    assert traces.finishes == []
    assert traces.trace.status == TraceStatus.RUNNING.value


@pytest.mark.asyncio
async def test_owned_turn_streams_only_after_durable_success(unit_settings: Settings) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    conversation = _ConversationFacade(session_id)
    memory = _MemoryFacade()
    run_journal = _RunJournal()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, conversation),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(memory),
        run_journal=run_journal,
    )
    events: list[object] = []

    async def callback(event: object) -> None:
        events.append(event)

    response = await service.process(
        ChatRequest(session_id=session_id, message="您好!"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_chat_success_0001",
        trace_id="trace_chat_busy_0001",
        callback=cast(Any, callback),
    )

    event_types = [cast(Any, event).event_type for event in events]
    assert event_types[0] == "agent_start"
    assert "reasoning_summary" in event_types
    assert "text_delta" in event_types
    assert event_types[-1] == "done"
    assert [cast(Any, event).sequence for event in events] == list(range(1, len(events) + 1))
    assert all(cast(Any, event).run_id == run_journal.run_id for event in events)
    assert conversation.user_text == "您好!"
    assert conversation.response is response
    assert conversation.assistant_commit is False
    assert conversation.rollback_count == 0
    assert memory.short_term_sessions == []
    assert memory.sources == []
    assert memory.committed_count == 0
    assert memory.compensation_count == 0
    assert response.text == "您好, 很高兴为您服务。"
    assert response.safety.disclaimer_applied is False
    assert traces.trace.status == TraceStatus.COMPLETED.value
    assert traces.start_request is not None
    assert traces.start_request.attributes["workflow"] == "standard"
    assert traces.start_request.attributes["workflow_version"] == "1.0.0"
    assert traces.start_request.attributes["workflow_owner_module"] == "agent_harness"
    trace_event_types = [event.event_type.value for event in traces.events]
    assert trace_event_types == [
        "agent.start",
        "model.call",
        "safety.check",
        "agent.finish",
    ]
    assert traces.finishes[-1].status is TraceStatus.COMPLETED
    assert len(run_journal.start_requests) == 1
    assert run_journal.start_requests[0].route is RouteKind.QUICK
    dynamic_plan = cast(dict[str, Any], run_journal.start_requests[0].plan["dynamic_plan"])
    assert dynamic_plan["route"] == "quick"
    assert cast(list[dict[str, Any]], dynamic_plan["nodes"])[0]["capability"] == "answer.quick"
    agent_context = cast(
        dict[str, Any],
        run_journal.start_requests[0].context_snapshot["agent_context"],
    )
    projection = cast(dict[str, Any], agent_context["projection"])
    assert projection["schema_version"] == "context-projection-v2"
    assert (
        projection["estimated_tokens_after"]
        <= projection["effective_limit_tokens"]
        <= projection["hard_stop_tokens"]
    )
    assert projection["source_hash"]
    assert run_journal.start_requests[0].fencing_token == 17
    assert run_journal.answer_message_ids
    assert run_journal.events[-1].event_type == "done"
    assert run_journal.transitions == [AgentRunStatus.COMPLETED]
    assert [snapshot.statuses["quick_answer"] for snapshot in run_journal.plan_executions] == [
        PlanNodeStatus.RUNNING,
        PlanNodeStatus.COMPLETED,
    ]

    replay_events: list[object] = []

    async def replay_callback(event: object) -> None:
        replay_events.append(event)

    replayed = await service.process(
        ChatRequest(session_id=session_id, message="您好!"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_chat_replay_0001",
        trace_id="trace_chat_busy_0001",
        callback=cast(Any, replay_callback),
    )
    assert replayed is response
    assert cast(Any, replay_events[0]).event_type == "agent_start"
    replay_done = cast(Any, replay_events[-1])
    assert replay_done.event_type == "done"
    assert replay_done.data["replayed"] is True


@pytest.mark.asyncio
async def test_owner_capability_runs_only_after_durable_run_checkpoint(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    run_journal = _RunJournal()
    runtime = _CapabilityRuntime(run_journal)
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=run_journal,
        capability_runtime=runtime,
    )

    async def callback(_event: object) -> None:
        return None

    await service.process(
        ChatRequest(session_id=session_id, message="请做老年综合评估"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_capability_checkpoint_0001",
        trace_id="trace_capability_checkpoint_0001",
        callback=cast(Any, callback),
    )

    assert runtime.calls == ["gerclaw.cga"]
    frozen_plan = PersistedRunPlan.model_validate(run_journal.start_requests[0].plan)
    assert frozen_plan.capability_results == ()
    assert any(
        snapshot.statuses.get("capability_1") is PlanNodeStatus.COMPLETED
        for snapshot in run_journal.plan_executions
    )
    assert run_journal.transitions == [AgentRunStatus.COMPLETED]


@pytest.mark.asyncio
async def test_optional_owner_failure_finishes_with_private_warning_and_answer(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    run_journal = _RunJournal()
    runtime = _CapabilityRuntime(run_journal, fail=True)
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=run_journal,
        capability_runtime=runtime,
    )

    async def callback(_event: object) -> None:
        return None

    response = await service.process(
        ChatRequest(session_id=session_id, message="请做老年综合评估"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_capability_warning_0001",
        trace_id="trace_capability_warning_0001",
        callback=cast(Any, callback),
    )

    assert response.text
    assert "CAPABILITY_OWNER_FAILED" not in response.text
    assert run_journal.completion_warnings == ("OPTIONAL_CAPABILITY_FAILED",)
    assert run_journal.transitions == [AgentRunStatus.COMPLETED_WITH_WARNINGS]


@pytest.mark.asyncio
async def test_memory_write_failure_finishes_with_private_warning_and_answer(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    run_journal = _RunJournal()
    memory = _FailingWriteMemory()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _MedicalTextModel()),
        rag_module=cast(Any, _EvidenceRAG()),
        memory_factory=_memory_factory(memory),
        run_journal=run_journal,
    )

    async def callback(_event: object) -> None:
        return None

    response = await service.process(
        ChatRequest(session_id=session_id, message="老年人高血压日常如何管理？"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write", "memory:read"}),
        ),
        request_id="request_memory_warning_0001",
        trace_id="trace_memory_warning_0001",
        callback=cast(Any, callback),
    )

    assert response.text
    assert "MEMORY_WRITE_FAILED" not in response.text
    assert memory.sources == ["老年人高血压日常如何管理?"]
    assert run_journal.completion_warnings == ("MEMORY_WRITE_FAILED",)
    assert run_journal.transitions == [AgentRunStatus.COMPLETED_WITH_WARNINGS]


@pytest.mark.asyncio
async def test_missing_optional_owner_runtime_preserves_answer_after_run_checkpoint(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    run_journal = _RunJournal()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=run_journal,
        capability_runtime=None,
    )

    async def callback(_event: object) -> None:
        return None

    response = await service.process(
        ChatRequest(session_id=session_id, message="请做老年综合评估"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_capability_unavailable_0001",
        trace_id="trace_capability_unavailable_0001",
        callback=cast(Any, callback),
    )

    assert response.text
    assert run_journal.start_requests
    assert any(
        snapshot.statuses.get("capability_1") is PlanNodeStatus.FAILED
        for snapshot in run_journal.plan_executions
    )
    assert run_journal.completion_warnings == ("OPTIONAL_CAPABILITY_FAILED",)
    assert run_journal.transitions == [AgentRunStatus.COMPLETED_WITH_WARNINGS]


@pytest.mark.asyncio
async def test_owner_runtime_is_never_invoked_without_durable_run_journal(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    unused_journal = _RunJournal()
    runtime = _CapabilityRuntime(unused_journal)
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=None,
        capability_runtime=runtime,
    )

    async def callback(_event: object) -> None:
        return None

    response = await service.process(
        ChatRequest(session_id=session_id, message="请做老年综合评估"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_capability_no_run_0001",
        trace_id="trace_capability_no_run_0001",
        callback=cast(Any, callback),
    )

    assert response.text
    assert runtime.calls == []
    assert response.structured["warning_codes"] == ["OPTIONAL_CAPABILITY_FAILED"]


@pytest.mark.asyncio
async def test_invalid_protocol_attempt_is_rejected_and_replaced_in_place(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    run_journal = _RunJournal()
    model = _ProtocolRepairModel()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, model),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=run_journal,
    )
    events: list[object] = []

    async def callback(event: object) -> None:
        events.append(event)

    response = await service.process(
        ChatRequest(session_id=session_id, message="请给三个建立规律作息的建议"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_chat_output_repair_0001",
        trace_id="trace_chat_output_repair_0001",
        callback=cast(Any, callback),
    )

    assert model.calls == 2
    assert run_journal.attempt_count == 2
    assert [item.error_code for item in run_journal.rejected_attempts] == ["answer_protocol_markup"]
    assert "<invoke" not in response.text
    assert "固定起床时间" in response.text
    assert all("<invoke" not in str(cast(Any, event).data.get("content", "")) for event in events)
    assert run_journal.transitions == [AgentRunStatus.COMPLETED]


@pytest.mark.asyncio
async def test_chat_service_connects_directive_journal_after_run_start(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    run_journal = _RunJournal()
    directives = _DirectiveJournal()
    model = _TextModel()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, model),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=run_journal,
        directive_journal=directives,
    )

    async def callback(_event: object) -> None:
        return None

    await service.process(
        ChatRequest(session_id=session_id, message="请帮我整理安排"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_chat_directive_0001",
        trace_id="trace_chat_directive_0001",
        callback=cast(Any, callback),
    )

    assert directives.applied
    assert directives.applied[0][1].fencing_token == 17
    assert directives.applied[0][1].boundary_id == "before-model-1"
    assert "请把回答控制在两句话以内" in model.last_messages[-1].get_text_content()


@pytest.mark.asyncio
async def test_applied_medical_directive_is_projected_into_next_clinical_state(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    run_journal = _RunJournal()
    directives = _DirectiveJournal()
    directive_id = uuid.uuid4()
    observed_at = datetime(2026, 7, 29, tzinfo=UTC)
    directives.recent = (
        RunDirectiveRead(
            id=directive_id,
            conversation_id=session_id,
            target_run_id=uuid.uuid4(),
            sequence=1,
            mode=RunDirectiveMode.QUEUE_FOR_NEXT_BOUNDARY,
            status=RunDirectiveStatus.APPLIED,
            instruction="补充：老人最近三天持续头晕。",
            idempotency_key="directive-clinical-projection-1",
            claimed_by_fencing_token=16,
            claim_boundary_id="after-tool-result-1",
            revision=3,
            created_at=observed_at,
            claimed_at=observed_at,
            applied_at=observed_at,
        ),
    )
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=run_journal,
        directive_journal=directives,
    )

    async def callback(_event: object) -> None:
        return None

    await service.process(
        ChatRequest(session_id=session_id, message="请继续"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_chat_directive_clinical_0001",
        trace_id="trace_chat_directive_clinical_0001",
        callback=cast(Any, callback),
    )

    persisted = ClinicalState.model_validate(
        cast(
            dict[str, Any],
            run_journal.start_requests[0].context_snapshot["agent_context"],
        )["clinical_state"]
    )
    directive_facts = [
        fact
        for fact in persisted.facts
        if any(item.source_id == f"message:{directive_id}" for item in fact.provenance)
    ]
    assert directive_facts
    assert any(fact.category == "symptom" for fact in directive_facts)
    assert all(fact.status == "reported" for fact in directive_facts)


@pytest.mark.asyncio
async def test_context_compressor_failure_uses_deterministic_high_value_fallback(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    memory = _FailingCompressionMemory()
    run_journal = _RunJournal()
    model = _TextModel()
    model.context_size = 16_384
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, model),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(memory),
        run_journal=run_journal,
    )

    async def callback(_event: object) -> None:
        return None

    await service.process(
        ChatRequest(
            session_id=session_id,
            message="请结合既往信息评估我的高血压用药和近期头晕情况。" * 12,
        ),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_context_fallback_0001",
        trace_id="trace_context_fallback_0001",
        callback=cast(Any, callback),
    )

    projection = cast(
        dict[str, Any],
        cast(
            dict[str, Any],
            run_journal.start_requests[0].context_snapshot["agent_context"],
        )["projection"],
    )
    assert projection["schema_version"] == "context-projection-v2"
    assert projection["compression_strategy"] == "deterministic-extractive-v1"
    assert projection["estimated_tokens_after"] <= projection["effective_limit_tokens"]
    assert len(projection["source_message_ids"]) == 20
    assert len(projection["retained_message_ids"]) + len(projection["omitted_message_ids"]) == 20


@pytest.mark.asyncio
async def test_completion_fence_failure_never_publishes_done(unit_settings: Settings) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    conversation = _ConversationFacade(session_id)
    run_journal = _RunJournal()
    run_journal.completion_error = RunFenceConflictError("stale worker")
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, conversation),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=run_journal,
    )
    events: list[object] = []

    async def callback(event: object) -> None:
        events.append(event)

    with pytest.raises(RunFenceConflictError, match="stale worker"):
        await service.process(
            ChatRequest(session_id=session_id, message="您好!"),
            identity=AuthContext(
                actor_id="usr_patient_unit0001",
                tenant_id="tenant_public0001",
                scopes=frozenset({"chat:write"}),
            ),
            request_id="request_chat_completion_fence_0001",
            trace_id="trace_chat_completion_fence_0001",
            callback=cast(Any, callback),
        )

    assert events == []
    assert run_journal.answer_message_ids == []
    assert run_journal.transitions == [AgentRunStatus.FAILED]
    assert len(run_journal.rejected_attempts) == 1


@pytest.mark.asyncio
async def test_companion_turn_keeps_long_term_memory_and_memory_trace_disabled(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    conversation = _ConversationFacade(session_id)
    memory = _MemoryFacade()
    run_journal = _RunJournal()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, conversation),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(memory),
        run_journal=run_journal,
    )

    async def callback(_event: object) -> None:
        return None

    response = await service.process(
        ChatRequest(session_id=session_id, message="我今天有点孤单。", workflow="companion"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_companion_memory0001",
        trace_id="trace_companion_memory0001",
        callback=cast(Any, callback),
    )

    assert response.medical_content is False
    assert memory.short_term_sessions == []
    assert memory.sources == []
    assert memory.committed_count == 0
    assert conversation.history_exclude_trace_id is None
    assert [event.event_type.value for event in traces.events] == [
        "agent.start",
        "model.call",
        "safety.check",
        "agent.finish",
    ]


@pytest.mark.asyncio
async def test_durable_cancel_intent_fences_success_when_runtime_swallows_task_cancel(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    conversation = _ConversationFacade(session_id)
    memory = _MemoryFacade()
    run_journal = _RunJournal()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, conversation),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(memory),
        run_journal=run_journal,
    )
    events: list[object] = []

    async def callback(event: object) -> None:
        events.append(event)

    async def cancellation_requested() -> bool:
        return True

    with pytest.raises(asyncio.CancelledError):
        await service.process(
            ChatRequest(session_id=session_id, message="您好!"),
            identity=AuthContext(
                actor_id="usr_patient_unit0001",
                tenant_id="tenant_public0001",
                scopes=frozenset({"chat:write"}),
            ),
            request_id="request_chat_cancel_fence_0001",
            trace_id="trace_chat_busy_0001",
            callback=cast(Any, callback),
            cancellation_requested=cancellation_requested,
        )

    assert conversation.response is None
    assert conversation.rollback_count == 2
    assert memory.compensation_count == 1
    assert memory.committed_count == 0
    assert traces.trace.status == TraceStatus.CANCELLED.value
    assert traces.finishes[-1].status is TraceStatus.CANCELLED
    assert events == []
    assert run_journal.answer_message_ids == []
    assert run_journal.transitions == [AgentRunStatus.CANCELLED]
    assert len(run_journal.rejected_attempts) == 1


@pytest.mark.asyncio
async def test_durable_steer_invalidates_attempt_without_publishing_cancel_or_failure(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    conversation = _ConversationFacade(session_id)
    memory = _MemoryFacade()
    run_journal = _RunJournal()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, conversation),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(memory),
        run_journal=run_journal,
    )
    events: list[object] = []

    async def callback(event: object) -> None:
        events.append(event)

    async def steering_requested() -> bool:
        return True

    with pytest.raises(ChatSteeredInterruption):
        await service.process(
            ChatRequest(session_id=session_id, message="您好!"),
            identity=AuthContext(
                actor_id="usr_patient_unit0001",
                tenant_id="tenant_public0001",
                scopes=frozenset({"chat:write"}),
            ),
            request_id="request_chat_steer_fence_0001",
            trace_id="trace_chat_steer_0001",
            callback=cast(Any, callback),
            steering_requested=steering_requested,
        )

    assert conversation.response is None
    assert memory.compensation_count == 1
    assert memory.committed_count == 0
    assert traces.trace.status == TraceStatus.RUNNING.value
    assert traces.finishes == []
    assert events == []
    assert run_journal.answer_message_ids == []
    assert run_journal.transitions == [AgentRunStatus.INTERRUPTED]
    assert [item.error_code for item in run_journal.rejected_attempts] == ["chat_steered"]
    assert run_journal.rejected_attempts[0].repair_action == "start_controlled_successor"


@pytest.mark.asyncio
async def test_cancel_does_not_publish_success_when_terminal_trace_commit_fails(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(
        created=True,
        session_id=session_id,
        fail_cancelled_finish=True,
    )
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
    )

    async def callback(_event: object) -> None:
        return None

    async def cancellation_requested() -> bool:
        return True

    with pytest.raises(RuntimeError, match="cancelled Trace could not be durably finalized"):
        await service.process(
            ChatRequest(session_id=session_id, message="您好!"),
            identity=AuthContext(
                actor_id="usr_patient_unit0001",
                tenant_id="tenant_public0001",
                scopes=frozenset({"chat:write"}),
            ),
            request_id="request_chat_cancel_commit_failure_0001",
            trace_id="trace_chat_busy_0001",
            callback=cast(Any, callback),
            cancellation_requested=cancellation_requested,
        )

    assert traces.trace.status == TraceStatus.RUNNING.value
    assert traces.finishes == []


@pytest.mark.asyncio
async def test_emergency_short_circuit_trace_does_not_claim_a_model_call(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    alerts = _RiskAlertRecorder()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        risk_alert_service=cast(Any, alerts),
    )

    async def callback(_event: object) -> None:
        return None

    response = await service.process(
        ChatRequest(session_id=session_id, message="老人突然胸痛并且呼吸困难"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_chat_emergency_0001",
        trace_id="trace_chat_busy_0001",
        callback=cast(Any, callback),
    )

    assert response.emergency_short_circuit is True
    assert "model.call" not in [event.event_type.value for event in traces.events]
    finish = next(event for event in traces.events if event.event_type.value == "agent.finish")
    assert "model" not in finish.payload
    assert "total_tokens" not in finish.payload
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["tenant_id"] == "tenant_public0001"
    assert alerts.calls[0]["actor_id"] == "usr_patient_unit0001"
    assert len(alerts.calls[0]["source_fingerprint"]) == 52


@pytest.mark.asyncio
async def test_emergency_bypasses_skill_memory_and_document_dependencies(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)

    def unavailable_memory(**_kwargs: object) -> _MemoryFacade:
        raise AssertionError("Emergency must not construct Memory")

    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=unavailable_memory,
        skill_module=None,
        document_service=None,
    )

    async def callback(_event: object) -> None:
        return None

    response = await service.process(
        ChatRequest(
            session_id=session_id,
            message="老人突然胸痛并且呼吸困难",
            loaded_skills=["risk-assessment"],
            uploaded_files=[uuid.uuid4()],
        ),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_chat_emergency_dependencies_0001",
        trace_id="trace_chat_emergency_dependencies_0001",
        callback=cast(Any, callback),
    )

    assert response.emergency_short_circuit is True
    assert response.structured["model_invoked"] is False
    assert response.structured["tool_names"] == []
    assert "立即拨打 120" in response.text


@pytest.mark.asyncio
async def test_medical_turn_reduces_prior_clinical_state_into_run_snapshot(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    run_journal = _RunJournal()
    run_journal.clinical_state = ClinicalState(
        facts=(
            ClinicalFact(
                fact_id="allergy:penicillin",
                category="allergy",
                value="青霉素",
                status="reported",
                provenance=(
                    FactProvenance(
                        source_type="user",
                        source_id="message:prior",
                        observed_at=datetime(2026, 7, 1, tzinfo=UTC),
                    ),
                ),
            ),
        ),
        unknowns=("当前用药",),
    )
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=run_journal,
    )

    async def callback(_event: object) -> None:
        return None

    await service.process(
        ChatRequest(session_id=session_id, message="老人最近头晕"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_chat_clinical_state_0001",
        trace_id="trace_chat_clinical_state_0001",
        callback=cast(Any, callback),
    )

    persisted = ClinicalState.model_validate(
        cast(
            dict[str, Any],
            run_journal.start_requests[0].context_snapshot["agent_context"],
        )["clinical_state"]
    )
    assert persisted.unknowns == ("当前用药",)
    assert persisted.facts[0].fact_id == "allergy:penicillin"
    current = persisted.facts[1]
    assert current.category == "chief_complaint"
    assert current.value == "老人最近头晕"
    assert current.status == "reported"
    assert current.provenance[0].source_type == "user"


@pytest.mark.asyncio
async def test_resume_uses_frozen_context_without_reloading_mutable_memory_or_input(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    request_id = "request_chat_frozen_resume_0001"
    trace_id = "trace_chat_frozen_resume_0001"
    payload = ChatRequest(
        session_id=session_id,
        message="请帮我整理一份日常安排建议，" * 12,
    )
    initial_journal = _RunJournal()
    initial_service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=initial_journal,
    )

    async def callback(_event: object) -> None:
        return None

    identity = AuthContext(
        actor_id="usr_patient_unit0001",
        tenant_id="tenant_public0001",
        scopes=frozenset({"chat:write"}),
    )
    await initial_service.process(
        payload,
        identity=identity,
        request_id=request_id,
        trace_id=trace_id,
        callback=cast(Any, callback),
    )
    original = initial_journal.start_requests[0]
    frozen = FrozenRunState(
        snapshot=PersistedContextSnapshot.model_validate(original.context_snapshot),
        plan=PersistedRunPlan.model_validate(original.plan),
    )

    mutable_memory = _MemoryFacade()
    resumed_conversation = _ConversationFacade(session_id)
    resumed_journal = _RunJournal()
    resumed_service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, resumed_conversation),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(mutable_memory),
        run_journal=resumed_journal,
    )
    await resumed_service.process(
        payload,
        identity=identity,
        request_id=request_id,
        trace_id=trace_id,
        callback=cast(Any, callback),
        resume_state=frozen,
    )

    resumed = resumed_journal.start_requests[0]
    assert resumed.context_snapshot == original.context_snapshot
    assert resumed.plan == original.plan
    assert mutable_memory.short_term_sessions == []
    assert resumed_conversation.user_text is None


@pytest.mark.asyncio
async def test_controlled_successor_reuses_frozen_assets_but_replans_new_instruction(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    source_payload = ChatRequest(
        session_id=session_id,
        message="请帮我整理一份详细的日常安排建议，" * 12,
    )
    identity = AuthContext(
        actor_id="usr_patient_unit0001",
        tenant_id="tenant_public0001",
        scopes=frozenset({"chat:write"}),
    )
    source_journal = _RunJournal()
    source_service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=source_journal,
    )

    async def ignore_event(_event: object) -> None:
        return None

    await source_service.process(
        source_payload,
        identity=identity,
        request_id="request_successor_source_0001",
        trace_id="trace_successor_source_0001",
        callback=cast(Any, ignore_event),
    )
    source_request = source_journal.start_requests[0]
    frozen = FrozenRunState(
        snapshot=PersistedContextSnapshot.model_validate(source_request.context_snapshot),
        plan=PersistedRunPlan.model_validate(source_request.plan),
    )
    new_instruction = "请改为只给我三条最重要的安排。"
    successor_payload = source_payload.model_copy(update={"message": new_instruction})
    mutable_memory = _MemoryFacade()
    successor_conversation = _ConversationFacade(session_id)
    successor_journal = _RunJournal()
    directive_journal = _DirectiveJournal()
    successor_model = _TextModel()
    successor_service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, successor_conversation),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, successor_model),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(mutable_memory),
        run_journal=successor_journal,
        directive_journal=directive_journal,
    )
    public_events: list[object] = []

    async def collect_event(event: object) -> None:
        public_events.append(event)

    with pytest.raises(ValueError, match="source Trace does not match snapshot"):
        ControlledSuccessorState(
            source_run_id=source_journal.run_id,
            source_trace_id="trace_wrong_successor_source_0001",
            directive_id=directive_journal.directive_id,
            source=frozen,
        )

    await successor_service.process(
        successor_payload,
        identity=identity,
        request_id="request_successor_new_0001",
        trace_id="trace_successor_new_0001",
        callback=cast(Any, collect_event),
        successor_state=ControlledSuccessorState(
            source_run_id=source_journal.run_id,
            source_trace_id=frozen.snapshot.agent_context.execution.trace_id,
            directive_id=directive_journal.directive_id,
            source=frozen,
        ),
    )

    successor_request = successor_journal.start_requests[0]
    successor_snapshot = PersistedContextSnapshot.model_validate(successor_request.context_snapshot)
    successor_plan = PersistedRunPlan.model_validate(successor_request.plan)
    assert successor_conversation.user_text == new_instruction
    assert mutable_memory.short_term_sessions == []
    assert successor_snapshot.skill_definitions == frozen.snapshot.skill_definitions
    assert successor_snapshot.uploaded_documents == frozen.snapshot.uploaded_documents
    assert successor_snapshot.agent_context.execution.trace_id == "trace_successor_new_0001"
    assert successor_plan.route_decision != frozen.plan.route_decision
    assert directive_journal.successor_bindings == [
        (directive_journal.directive_id, successor_journal.run_id, 17)
    ]
    first = cast(Any, public_events[0])
    assert first.event_type == "reasoning_summary"
    assert first.data["content"] == "已按新要求调整执行"
    assert str(successor_model.last_messages).count(new_instruction) == 1


@pytest.mark.asyncio
async def test_treatment_unknown_still_gets_model_answer_with_follow_up_context(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    run_journal = _RunJournal()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
        run_journal=run_journal,
    )

    async def callback(_event: object) -> None:
        return None

    response = await service.process(
        ChatRequest(session_id=session_id, message="这些药需要怎么调整剂量?"),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        request_id="request_chat_treatment_ask_0001",
        trace_id="trace_chat_treatment_ask_0001",
        callback=cast(Any, callback),
    )

    dynamic_plan = cast(dict[str, Any], run_journal.start_requests[0].plan["dynamic_plan"])
    assert [node["capability"] for node in dynamic_plan["nodes"]] == [
        "evidence.retrieve",
        "answer.compose",
    ]
    action = cast(dict[str, Any], response.structured["action_selection"])
    assert cast(dict[str, Any], action["selected"])["candidate"]["kind"] == "ask"
    assert response.structured["model_invoked"] is True
    assert "您好" in response.text
    execution = cast(dict[str, Any], response.structured["plan_execution"])
    assert execution["statuses"] == {
        "retrieve_evidence": "completed",
        "answer": "completed",
    }
    persisted = ClinicalState.model_validate(
        cast(
            dict[str, Any],
            run_journal.start_requests[0].context_snapshot["agent_context"],
        )["clinical_state"]
    )
    assert "年龄" in persisted.unknowns
    assert "完整当前用药名称、剂量和频次" in persisted.unknowns


@pytest.mark.asyncio
async def test_cancelled_running_skill_viewer_gets_a_terminal_audit_event(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    conversation = _ConversationFacade(session_id)
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, conversation),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
    )

    await service._finish_failure(
        ChatRequest(
            session_id=session_id,
            message="请读取风险评估技能",
            loaded_skills=["risk-assessment"],
        ),
        identity=AuthContext(
            actor_id="usr_patient_unit0001",
            tenant_id="tenant_public0001",
            scopes=frozenset({"chat:write"}),
        ),
        trace_id="trace_chat_busy_0001",
        status=TraceStatus.CANCELLED,
        code="CHAT_CANCELLED",
        request_fingerprint="f" * 64,
        fencing_token=17,
        lease_guard=cast(Any, _LeaseGuard(17)),
        active_skill_calls={
            "tool_call_skill_001": (time.monotonic() - 0.01, "risk-assessment", "1.0.0")
        },
        skill_audit_events=[],
    )

    skill_event = next(
        event for event in traces.events if event.event_type.value == "skill.execute"
    )
    assert skill_event.status.value == "cancelled"
    assert skill_event.payload["outcome"] == "cancelled"
    assert skill_event.payload["skill"] == "risk-assessment"
    assert skill_event.payload["version"] == "1.0.0"
    assert traces.finishes[-1].status is TraceStatus.CANCELLED


@pytest.mark.asyncio
async def test_terminal_trace_failure_rolls_back_assistant_before_recording_failure(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(
        created=True,
        session_id=session_id,
        fail_completed_finish=True,
    )
    conversation = _ConversationFacade(session_id)
    memory = _MemoryFacade()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, conversation),
        traces=cast(Any, traces),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(memory),
    )
    events: list[object] = []

    async def callback(event: object) -> None:
        events.append(event)

    with pytest.raises(RuntimeError, match="terminal Trace commit failure"):
        await service.process(
            ChatRequest(session_id=session_id, message="您好!"),
            identity=AuthContext(
                actor_id="usr_patient_unit0001",
                tenant_id="tenant_public0001",
                scopes=frozenset({"chat:write"}),
            ),
            request_id="request_chat_atomic_0001",
            trace_id="trace_chat_busy_0001",
            callback=cast(Any, callback),
        )

    assert conversation.response is None
    assert conversation.rollback_count == 2
    assert memory.compensation_count == 1
    assert memory.committed_count == 0
    assert conversation.failure_text == "这次回答没有完整生成，请重试。"
    assert traces.trace.status == TraceStatus.FAILED.value
    assert traces.finishes[-1].status is TraceStatus.FAILED
    assert all(cast(Any, event).event_type != "done" for event in events)


@pytest.mark.asyncio
async def test_stale_owner_cannot_fail_same_trace_after_successor_adoption(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
    conversation = _ConversationFacade(session_id)
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, conversation),
        traces=cast(Any, traces),
        lease=cast(Any, _SupersedingLease(conversation)),
        model=cast(Any, _TextModel()),
        rag_module=cast(Any, _NoopRAG()),
        memory_factory=_memory_factory(),
    )

    async def callback(_event: object) -> None:
        return None

    with pytest.raises(SessionLeaseLostError):
        await service.process(
            ChatRequest(session_id=session_id, message="您好!"),
            identity=AuthContext(
                actor_id="usr_patient_unit0001",
                tenant_id="tenant_public0001",
                scopes=frozenset({"chat:write"}),
            ),
            request_id="request_chat_fenced_0001",
            trace_id="trace_chat_busy_0001",
            callback=cast(Any, callback),
        )

    assert conversation.response is None
    assert conversation.rollback_count == 2
    assert traces.trace.status == TraceStatus.RUNNING.value
    assert traces.finishes == []


def test_chat_error_codes_never_expose_provider_details() -> None:
    assert ChatService.error_code(SessionBusyError("internal redis key")) == "CHAT_SESSION_BUSY"
    assert ChatService.error_code(RuntimeError("provider secret response")) == (
        "CHAT_EXECUTION_FAILED"
    )
    assert ChatService.error_code(ChatCancellationFinalizationError("database details")) == (
        "CHAT_CANCELLATION_FINALIZATION_FAILED"
    )


def test_sse_encoding_and_public_errors_are_stable() -> None:
    encoded = _encode_sse("text_delta", {"content": "您好"})
    assert encoded == 'event: text_delta\ndata: {"content":"您好"}\n\n'
    assert public_chat_error("CHAT_SESSION_BUSY") == (
        "该会话正在生成，请等待当前回复完成后再试。",
        True,
    )
    assert public_chat_error("UNRECOGNIZED_INTERNAL_ERROR") == (
        "这次回答没有完整生成，请重试。",
        True,
    )
