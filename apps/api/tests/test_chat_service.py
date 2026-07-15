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

from gerclaw_api.api.routes.chat import _encode_sse, _public_error
from gerclaw_api.auth import AuthContext
from gerclaw_api.config import Settings
from gerclaw_api.database.models import ConversationSession, ExecutionTrace
from gerclaw_api.domain.chat_schemas import ChatRequest
from gerclaw_api.domain.enums import TraceStatus
from gerclaw_api.domain.trace_schemas import TraceEventCreate, TraceFinishRequest
from gerclaw_api.modules.memory.models import MemoryUpdateResult
from gerclaw_api.modules.memory.protocols import MemoryMessage, UserProfile
from gerclaw_api.services.chat_service import ChatCancellationFinalizationError, ChatService
from gerclaw_api.services.session_lease import SessionBusyError, SessionLeaseLostError
from gerclaw_api.services.trace_service import TraceStartResult


class _TextModel(ChatModelBase):
    class Parameters(ChatModelBase.Parameters):
        pass

    def __init__(self) -> None:
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
        del model_name, messages, tools, tool_choice, kwargs

        async def stream() -> AsyncGenerator[ChatResponse, None]:
            text = "您好, 很高兴为您服务。"
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
        self.history_exclude_trace_id = cast(str, kwargs["exclude_trace_id"])
        return []

    async def store_user_message(self, **kwargs: object) -> None:
        self.user_text = cast(str, kwargs["text"])

    async def store_assistant_message(self, **kwargs: object) -> None:
        self.response = kwargs["response"]
        self.assistant_commit = cast(bool, kwargs["commit"])

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

    async def start_trace_with_status(self, *_args: object, **_kwargs: object) -> TraceStartResult:
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


@pytest.mark.parametrize("created", [False, True])
@pytest.mark.asyncio
async def test_busy_retry_only_finishes_trace_created_by_this_request(
    unit_settings: Settings, created: bool
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=created, session_id=session_id)
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

    if created:
        assert len(traces.events) == 1
        assert len(traces.finishes) == 1
        assert traces.trace.status == "failed"
    else:
        assert traces.events == []
        assert traces.finishes == []
        assert traces.trace.status == "running"


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
    assert conversation.user_text == "您好!"
    assert conversation.response is response
    assert conversation.assistant_commit is False
    assert conversation.rollback_count == 0
    assert memory.short_term_sessions == [str(session_id)]
    assert memory.sources == ["您好!"]
    assert memory.committed_count == 1
    assert memory.compensation_count == 0
    assert response.text.endswith("内容由 AI 生成，仅供参考。身体不适请及时就医。")
    assert traces.trace.status == TraceStatus.COMPLETED.value
    trace_event_types = [event.event_type.value for event in traces.events]
    assert trace_event_types == [
        "agent.start",
        "model.call",
        "memory.update",
        "safety.check",
        "agent.finish",
    ]
    assert traces.finishes[-1].status is TraceStatus.COMPLETED

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
async def test_durable_cancel_intent_fences_success_when_runtime_swallows_task_cancel(
    unit_settings: Settings,
) -> None:
    session_id = uuid.uuid4()
    traces = _TraceFacade(created=True, session_id=session_id)
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
    assert all(cast(Any, event).event_type != "done" for event in events)


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
    assert _public_error("CHAT_SESSION_BUSY") == (
        "该会话正在生成，请等待当前回复完成后再试。",
        True,
    )
    assert _public_error("UNRECOGNIZED_INTERNAL_ERROR") == (
        "本次对话执行失败，请稍后重试。",
        True,
    )
