"""The durable chat shell must preserve replay, lease and cancellation semantics."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from gerclaw_api.domain.enums import TraceStatus
from gerclaw_api.domain.trace_schemas import TraceStartRequest
from gerclaw_api.modules.orchestration import (
    ChatSteeredInterruption,
    ChatTurnCoordinator,
)
from gerclaw_api.services.session_lease import SessionBusyError


class _Conversation:
    def __init__(self) -> None:
        self.next_calls = 0

    async def next_fencing_token(self) -> int:
        self.next_calls += 1
        return 7


class _Traces:
    def __init__(self, *, status: str, created: bool) -> None:
        self.result = SimpleNamespace(trace=SimpleNamespace(status=status), created=created)
        self.private_artifacts: list[tuple[str, str, dict[str, object]]] = []

    async def start_trace_with_status(self, *args: object, **kwargs: object) -> SimpleNamespace:
        return self.result

    async def record_private_input_artifacts(
        self, tenant_id: str, trace_id: str, artifacts: dict[str, object]
    ) -> None:
        self.private_artifacts.append((tenant_id, trace_id, artifacts))

    async def get_trace(self, tenant_id: str, trace_id: str) -> SimpleNamespace:
        del tenant_id, trace_id
        return self.result.trace


class _Lease:
    def __init__(self) -> None:
        self.calls: list[tuple[str, uuid.UUID, int]] = []

    @asynccontextmanager
    async def acquire(self, *, tenant_id: str, session_id: uuid.UUID, fencing_token: int):
        self.calls.append((tenant_id, session_id, fencing_token))
        yield SimpleNamespace(fencing_token=fencing_token)

class _BusyLease(_Lease):
    @asynccontextmanager
    async def acquire(self, *, tenant_id: str, session_id: uuid.UUID, fencing_token: int):
        self.calls.append((tenant_id, session_id, fencing_token))
        raise SessionBusyError("same trace is already running")
        yield  # pragma: no cover


def _start_request(session_id: uuid.UUID) -> TraceStartRequest:
    return TraceStartRequest(session_id=session_id, execution_type="agent.chat")


@pytest.mark.asyncio
async def test_completed_trace_replays_without_a_new_lease_or_private_artifact() -> None:
    conversation = _Conversation()
    traces = _Traces(status="completed", created=False)
    lease = _Lease()
    coordinator = ChatTurnCoordinator(conversation=conversation, traces=traces, lease=lease)  # type: ignore[arg-type]
    response = SimpleNamespace(marker="replayed")
    emitted: list[object] = []

    result = await coordinator.execute(
        start_request=_start_request(uuid.uuid4()),
        request_id="req_replay",
        trace_id="trace_replay_12345678",
        tenant_id="tenant_test",
        actor_id="actor_test",
        session_id=uuid.uuid4(),
        private_input_artifacts={"images": [{"evidence_id": "ev_img"}]},
        read_replay=lambda: _return(response),  # type: ignore[arg-type]
        emit_replay=lambda item: _append(emitted, item),
        wait_for_replay=None,
        run_owned_turn=lambda guard: _unexpected("owned turn must not run"),
        finalize_failure=lambda *args: _return(True),
        error_code=lambda error: "CHAT_EXECUTION_FAILED",
    )

    assert result is response
    assert emitted == [response]
    assert conversation.next_calls == 0
    assert lease.calls == []
    assert traces.private_artifacts == []


@pytest.mark.asyncio
async def test_running_trace_uses_lease_and_preserves_private_artifacts_outside_events() -> None:
    conversation = _Conversation()
    traces = _Traces(status="running", created=True)
    lease = _Lease()
    coordinator = ChatTurnCoordinator(conversation=conversation, traces=traces, lease=lease)  # type: ignore[arg-type]
    session_id = uuid.uuid4()
    response = SimpleNamespace(marker="completed")
    guard_tokens: list[int] = []

    async def run_owned_turn(guard: SimpleNamespace) -> object:
        guard_tokens.append(guard.fencing_token)
        return response

    result = await coordinator.execute(
        start_request=_start_request(session_id),
        request_id="req_owned",
        trace_id="trace_owned_123456789",
        tenant_id="tenant_test",
        actor_id="actor_test",
        session_id=session_id,
        private_input_artifacts={"images": [{"evidence_id": "ev_img"}]},
        read_replay=lambda: _unexpected("replay must not run"),
        emit_replay=lambda item: _unexpected("replay must not emit"),
        wait_for_replay=None,
        run_owned_turn=run_owned_turn,  # type: ignore[arg-type]
        finalize_failure=lambda *args: _return(True),
        error_code=lambda error: "CHAT_EXECUTION_FAILED",
    )

    assert result is response
    assert conversation.next_calls == 1
    assert lease.calls == [("tenant_test", session_id, 7)]
    assert guard_tokens == [7]
    assert traces.private_artifacts == [
        ("tenant_test", "trace_owned_123456789", {"images": [{"evidence_id": "ev_img"}]})
    ]


@pytest.mark.asyncio
async def test_cancelled_owned_turn_requires_a_durable_cancelled_finalization() -> None:
    coordinator = ChatTurnCoordinator(
        conversation=_Conversation(), traces=_Traces(status="running", created=True), lease=_Lease()
    )  # type: ignore[arg-type]
    statuses: list[tuple[TraceStatus, str, int | None]] = []

    async def cancelled_turn(guard: SimpleNamespace) -> object:
        raise asyncio.CancelledError("stop")

    async def finalize(
        status: TraceStatus, code: str, fencing_token: int | None, guard: object
    ) -> bool:
        statuses.append((status, code, fencing_token))
        return True

    with pytest.raises(asyncio.CancelledError):
        await coordinator.execute(
            start_request=_start_request(uuid.uuid4()),
            request_id="req_cancel",
            trace_id="trace_cancel_12345678",
            tenant_id="tenant_test",
            actor_id="actor_test",
            session_id=uuid.uuid4(),
            private_input_artifacts=None,
            read_replay=lambda: _unexpected("replay must not run"),
            emit_replay=lambda item: _unexpected("replay must not emit"),
            wait_for_replay=None,
            run_owned_turn=cancelled_turn,  # type: ignore[arg-type]
            finalize_failure=finalize,
            error_code=lambda error: "CHAT_EXECUTION_FAILED",
        )

    assert statuses == [(TraceStatus.CANCELLED, "CHAT_CANCELLED", 7)]


@pytest.mark.asyncio
async def test_steered_turn_uses_distinct_interruption_code() -> None:
    coordinator = ChatTurnCoordinator(
        conversation=_Conversation(),
        traces=_Traces(status="running", created=True),
        lease=_Lease(),
    )  # type: ignore[arg-type]
    statuses: list[tuple[TraceStatus, str, int | None]] = []
    acknowledgements: list[str] = []

    async def interrupted_turn(_guard: SimpleNamespace) -> object:
        raise asyncio.CancelledError("steer")

    async def finalize(
        status: TraceStatus,
        code: str,
        fencing_token: int | None,
        _guard: object,
    ) -> bool:
        statuses.append((status, code, fencing_token))
        return True

    with pytest.raises(ChatSteeredInterruption):
        await coordinator.execute(
            start_request=_start_request(uuid.uuid4()),
            request_id="req_steer",
            trace_id="trace_steer_12345678",
            tenant_id="tenant_test",
            actor_id="actor_test",
            session_id=uuid.uuid4(),
            private_input_artifacts=None,
            read_replay=lambda: _unexpected("replay must not run"),
            emit_replay=lambda item: _unexpected("replay must not emit"),
            wait_for_replay=None,
            run_owned_turn=interrupted_turn,  # type: ignore[arg-type]
            finalize_failure=finalize,
            error_code=lambda error: "CHAT_EXECUTION_FAILED",
            steering_requested=lambda: _return(True),  # type: ignore[arg-type]
            interruption_acknowledged=lambda: acknowledgements.append("ack"),
        )

    assert statuses == [(TraceStatus.CANCELLED, "CHAT_STEERED", 7)]
    assert acknowledgements == ["ack"]


@pytest.mark.asyncio
async def test_provider_converted_cancel_error_still_uses_steer_interruption() -> None:
    coordinator = ChatTurnCoordinator(
        conversation=_Conversation(),
        traces=_Traces(status="running", created=True),
        lease=_Lease(),
    )  # type: ignore[arg-type]
    statuses: list[tuple[TraceStatus, str, int | None]] = []
    acknowledgements: list[str] = []

    async def converted_cancellation(_guard: SimpleNamespace) -> object:
        raise RuntimeError("provider converted task cancellation into stream failure")

    async def finalize(
        status: TraceStatus,
        code: str,
        fencing_token: int | None,
        _guard: object,
    ) -> bool:
        statuses.append((status, code, fencing_token))
        return True

    with pytest.raises(ChatSteeredInterruption):
        await coordinator.execute(
            start_request=_start_request(uuid.uuid4()),
            request_id="req_converted_steer",
            trace_id="trace_converted_steer_1234",
            tenant_id="tenant_test",
            actor_id="actor_test",
            session_id=uuid.uuid4(),
            private_input_artifacts=None,
            read_replay=lambda: _unexpected("replay must not run"),
            emit_replay=lambda item: _unexpected("replay must not emit"),
            wait_for_replay=None,
            run_owned_turn=converted_cancellation,  # type: ignore[arg-type]
            finalize_failure=finalize,
            error_code=lambda error: "CHAT_EXECUTION_FAILED",
            cancellation_requested=lambda: _return(False),  # type: ignore[arg-type]
            steering_requested=lambda: _return(True),  # type: ignore[arg-type]
            interruption_acknowledged=lambda: acknowledgements.append("ack"),
        )

    assert statuses == [(TraceStatus.CANCELLED, "CHAT_STEERED", 7)]
    assert acknowledgements == ["ack"]


@pytest.mark.asyncio
async def test_concurrent_same_trace_waits_for_owner_and_replays() -> None:
    conversation = _Conversation()
    traces = _Traces(status="running", created=False)
    lease = _BusyLease()
    coordinator = ChatTurnCoordinator(
        conversation=conversation,
        traces=traces,
        lease=lease,
    )  # type: ignore[arg-type]
    response = SimpleNamespace(marker="waited-replay")
    emitted: list[object] = []
    owned_turn_calls = 0

    async def run_owned_turn(_guard: object) -> object:
        nonlocal owned_turn_calls
        owned_turn_calls += 1
        return response

    result = await coordinator.execute(
        start_request=_start_request(uuid.uuid4()),
        request_id="req_waited_replay",
        trace_id="trace_waited_replay_1234",
        tenant_id="tenant_test",
        actor_id="actor_test",
        session_id=uuid.uuid4(),
        private_input_artifacts=None,
        read_replay=lambda: _unexpected("initial trace is still running"),
        emit_replay=lambda item: _append(emitted, item),
        wait_for_replay=lambda: _return(response),  # type: ignore[arg-type]
        run_owned_turn=run_owned_turn,  # type: ignore[arg-type]
        finalize_failure=lambda *args: _return(True),
        error_code=lambda error: "CHAT_EXECUTION_FAILED",
    )

    assert result is response
    assert emitted == [response]
    assert owned_turn_calls == 0
    assert conversation.next_calls == 1
    assert lease.calls


async def _return(value: object) -> object:
    return value


async def _append(values: list[object], value: object) -> None:
    values.append(value)


async def _unexpected(message: str) -> object:
    raise AssertionError(message)
