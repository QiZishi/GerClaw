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
from gerclaw_api.database.models import ConversationSession, ExecutionTrace, Message
from gerclaw_api.domain.chat_schemas import ChatRequest
from gerclaw_api.domain.enums import TraceStatus
from gerclaw_api.domain.run_schemas import (
    TERMINAL_RUN_STATUSES,
    AgentRunCreate,
    AgentRunRead,
    AgentRunStatus,
    AnswerVersionRead,
    RunAnswerContext,
    RunEventRead,
    RunEventWrite,
    RunRegenerationContext,
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
from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.modules.agent_harness.run_lifecycle import RunFenceConflictError
from gerclaw_api.modules.memory.models import MemoryUpdateResult
from gerclaw_api.modules.memory.protocols import MemoryMessage, UserProfile
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

    async def complete_answer(
        self,
        run_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        done_payload: dict[str, JsonValue],
        *,
        tenant_id: str,
        actor_id: str,
        fencing_token: int,
        answer_group_run_id: uuid.UUID | None = None,
        expected_current_version_id: uuid.UUID | None = None,
    ) -> tuple[AnswerVersionRead, AgentRunRead]:
        del tenant_id, actor_id, expected_current_version_id
        assert run_id == self.run_id
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
        self.events.append(
            RunEventWrite(
                event_type="done",
                status="completed",
                payload=cast(dict[str, Any], done_payload),
            )
        )
        self.transitions.append(AgentRunStatus.COMPLETED)
        return (
            answer,
            self._run(
                self.start_requests[0],
                AgentRunStatus.COMPLETED,
                revision=len(self.transitions) + 1,
            ),
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
            interrupted_at=(
                datetime.now(UTC)
                if status is AgentRunStatus.INTERRUPTED
                else None
            ),
            completed_at=(
                datetime.now(UTC) if status in TERMINAL_RUN_STATUSES else None
            ),
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
    assert [cast(Any, event).sequence for event in events] == list(
        range(1, len(events) + 1)
    )
    assert all(cast(Any, event).run_id == run_journal.run_id for event in events)
    assert conversation.user_text == "您好!"
    assert conversation.response is response
    assert conversation.assistant_commit is False
    assert conversation.rollback_count == 0
    assert memory.short_term_sessions == []
    assert memory.sources == []
    assert memory.committed_count == 0
    assert memory.compensation_count == 0
    assert response.text.endswith("内容由 AI 生成，仅供参考。身体不适请及时就医。")
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
    assert run_journal.start_requests[0].fencing_token == 17
    assert run_journal.answer_message_ids
    assert run_journal.events[-1].event_type == "done"
    assert run_journal.transitions == [AgentRunStatus.COMPLETED]

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

    assert all(cast(Any, event).event_type != "done" for event in events)
    assert run_journal.answer_message_ids == []
    assert run_journal.transitions == [AgentRunStatus.FAILED]


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
    assert all(cast(Any, event).event_type != "done" for event in events)
    assert run_journal.answer_message_ids == []
    assert run_journal.transitions == [AgentRunStatus.CANCELLED]


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
        run_journal.start_requests[0].context_snapshot["clinical_state"]
    )
    assert persisted.unknowns == ("当前用药",)
    assert persisted.facts[0].fact_id == "allergy:penicillin"
    current = persisted.facts[1]
    assert current.category == "chief_complaint"
    assert current.value == "老人最近头晕"
    assert current.status == "reported"
    assert current.provenance[0].source_type == "user"


@pytest.mark.asyncio
async def test_treatment_unknown_returns_persisted_ask_without_model_or_rag(
    unit_settings: Settings,
) -> None:
    class _FailingRAG:
        async def retrieve(self, *_args: object, **_kwargs: object) -> list[object]:
            raise AssertionError("RAG must not run before a mandatory treatment prerequisite")

    class _FailingModel(_TextModel):
        async def _call_api(
            self,
            model_name: str,
            messages: list[Msg],
            tools: list[dict[str, Any]] | None = None,
            tool_choice: ToolChoice | None = None,
            **kwargs: Any,
        ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
            del model_name, messages, tools, tool_choice, kwargs
            raise AssertionError("model must not run before a mandatory treatment prerequisite")

    session_id = uuid.uuid4()
    run_journal = _RunJournal()
    service = ChatService(
        settings=unit_settings,
        conversation=cast(Any, _ConversationFacade(session_id)),
        traces=cast(Any, _TraceFacade(created=True, session_id=session_id)),
        lease=cast(Any, _OwnedLease()),
        model=cast(Any, _FailingModel()),
        rag_module=cast(Any, _FailingRAG()),
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
    assert [node["capability"] for node in dynamic_plan["nodes"]] == ["clinical.ask"]
    action = cast(dict[str, Any], response.structured["action_selection"])
    assert cast(dict[str, Any], action["selected"])["candidate"]["kind"] == "ask"
    assert response.structured["model_invoked"] is False
    assert "完整当前用药名称、剂量和频次" in response.text
    execution = cast(dict[str, Any], response.structured["plan_execution"])
    assert execution["statuses"] == {"clarify_unknowns": "completed"}
    persisted = ClinicalState.model_validate(
        run_journal.start_requests[0].context_snapshot["clinical_state"]
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
