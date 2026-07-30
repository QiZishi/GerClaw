"""Durable coordination around one already-defined chat turn."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from gerclaw_api.domain.enums import TraceStatus
from gerclaw_api.domain.trace_schemas import TraceStartRequest
from gerclaw_api.metrics import CHAT_TURN_LATENCY, CHAT_TURNS
from gerclaw_api.modules.contracts import AgentResponse
from gerclaw_api.modules.orchestration.errors import (
    ChatCancellationFinalizationError,
    ChatReplayUnavailableError,
    ChatSteeredInterruption,
)
from gerclaw_api.services.conversation_service import ConversationService
from gerclaw_api.services.session_lease import (
    SessionBusyError,
    SessionLease,
    SessionLeaseGuard,
)
from gerclaw_api.services.trace_service import TraceService

ReplayReader = Callable[[], Awaitable[AgentResponse | None]]
ReplayEmitter = Callable[[AgentResponse], Awaitable[None]]
ReplayWaiter = Callable[[], Awaitable[AgentResponse]]
OwnedTurnRunner = Callable[[SessionLeaseGuard], Awaitable[AgentResponse]]
FailureFinalizer = Callable[
    [TraceStatus, str, int | None, SessionLeaseGuard | None], Awaitable[bool]
]
ErrorCodeMapper = Callable[[Exception], str]
CancellationProbe = Callable[[], Awaitable[bool]]
InterruptionAcknowledgement = Callable[[], None]


class ChatTurnCoordinator:
    """Own the idempotency, lease and terminal-Trace lifecycle of one turn.

    This coordinator deliberately does not assemble prompts or execute a model.
    The owning feature supplies those operations as callbacks, while this module
    ensures every execution has one owner and one durable terminal outcome.
    """

    def __init__(
        self,
        *,
        conversation: ConversationService,
        traces: TraceService,
        lease: SessionLease,
    ) -> None:
        self._conversation = conversation
        self._traces = traces
        self._lease = lease

    async def execute(
        self,
        *,
        start_request: TraceStartRequest,
        request_id: str,
        trace_id: str,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
        private_input_artifacts: dict[str, Any] | None,
        read_replay: ReplayReader,
        emit_replay: ReplayEmitter,
        wait_for_replay: ReplayWaiter | None,
        run_owned_turn: OwnedTurnRunner,
        finalize_failure: FailureFinalizer,
        error_code: ErrorCodeMapper,
        cancellation_requested: CancellationProbe | None = None,
        steering_requested: CancellationProbe | None = None,
        interruption_acknowledged: InterruptionAcknowledgement | None = None,
    ) -> AgentResponse:
        """Run or replay one turn without exposing partial success.

        A running trace can be adopted only after this coordinator owns the
        session lease. A cancellation is reported only after the supplied
        finalizer durably reaches the corresponding terminal Trace state.
        """

        started = time.monotonic()
        trace_start = await self._traces.start_trace_with_status(
            start_request,
            request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        trace = trace_start.trace
        if trace.status == TraceStatus.COMPLETED.value:
            response = await read_replay()
            if response is None:
                raise ChatReplayUnavailableError("completed chat trace has no stored response")
            await emit_replay(response)
            CHAT_TURNS.labels(outcome="replayed").inc()
            CHAT_TURN_LATENCY.observe(time.monotonic() - started)
            return response
        if trace.status != TraceStatus.RUNNING.value:
            raise ChatReplayUnavailableError("failed or cancelled chat traces cannot be replayed")

        if private_input_artifacts:
            await self._traces.record_private_input_artifacts(
                tenant_id, trace_id, private_input_artifacts
            )

        owns_trace_execution = trace_start.created
        fencing_token: int | None = None
        lease_guard: SessionLeaseGuard | None = None
        failure_handled = False
        steered = False
        try:
            fencing_token = await self._conversation.next_fencing_token()
            async with self._lease.acquire(
                tenant_id=tenant_id,
                session_id=session_id,
                fencing_token=fencing_token,
            ) as acquired_guard:
                lease_guard = acquired_guard
                # A retry may adopt a previously running Trace only after it
                # proves no other replica holds the same session lease.
                owns_trace_execution = True
                try:
                    response = await run_owned_turn(lease_guard)
                except asyncio.CancelledError as cancellation_error:
                    if interruption_acknowledged is not None:
                        interruption_acknowledged()
                    steered = steering_requested is not None and await steering_requested()
                    cancellation_persisted = await finalize_failure(
                        TraceStatus.CANCELLED,
                        "CHAT_STEERED" if steered else "CHAT_CANCELLED",
                        fencing_token,
                        lease_guard,
                    )
                    failure_handled = True
                    if not cancellation_persisted:
                        raise ChatCancellationFinalizationError(
                            "cancelled Trace could not be durably finalized"
                        ) from cancellation_error
                    if steered:
                        raise ChatSteeredInterruption(
                            "old chat execution was replaced"
                        ) from cancellation_error
                    raise
                except Exception as error:
                    # Some provider/AgentScope stream wrappers convert an
                    # injected task cancellation into a normal stream error.
                    # The durable user intent remains authoritative: never
                    # turn a requested stop/steer into a failed Run.
                    cancelled = (
                        cancellation_requested is not None and await cancellation_requested()
                    )
                    steered = (
                        not cancelled
                        and steering_requested is not None
                        and await steering_requested()
                    )
                    if cancelled or steered:
                        if interruption_acknowledged is not None:
                            interruption_acknowledged()
                        cancellation_persisted = await finalize_failure(
                            TraceStatus.CANCELLED,
                            "CHAT_STEERED" if steered else "CHAT_CANCELLED",
                            fencing_token,
                            lease_guard,
                        )
                        failure_handled = True
                        if not cancellation_persisted:
                            raise ChatCancellationFinalizationError(
                                "converted cancellation could not be durably finalized"
                            ) from error
                        if steered:
                            raise ChatSteeredInterruption(
                                "old chat execution was replaced"
                            ) from error
                        raise asyncio.CancelledError(
                            "explicit chat cancellation requested"
                        ) from error
                    await finalize_failure(
                        TraceStatus.FAILED,
                        error_code(error),
                        fencing_token,
                        lease_guard,
                    )
                    failure_handled = True
                    raise
                CHAT_TURNS.labels(outcome="completed").inc()
                CHAT_TURN_LATENCY.observe(time.monotonic() - started)
                return response
        except SessionBusyError as error:
            if trace_start.created:
                await finalize_failure(
                    TraceStatus.FAILED,
                    error_code(error),
                    fencing_token,
                    lease_guard,
                )
                failure_handled = True
                CHAT_TURNS.labels(outcome="failed").inc()
                CHAT_TURN_LATENCY.observe(time.monotonic() - started)
                raise
            if wait_for_replay is None:
                raise
            response = await wait_for_replay()
            await emit_replay(response)
            CHAT_TURNS.labels(outcome="replayed").inc()
            CHAT_TURN_LATENCY.observe(time.monotonic() - started)
            return response
        except asyncio.CancelledError as cancellation_error:
            if owns_trace_execution and not failure_handled:
                if interruption_acknowledged is not None:
                    interruption_acknowledged()
                steered = steering_requested is not None and await steering_requested()
                cancellation_persisted = await finalize_failure(
                    TraceStatus.CANCELLED,
                    "CHAT_STEERED" if steered else "CHAT_CANCELLED",
                    fencing_token,
                    lease_guard,
                )
                if not cancellation_persisted:
                    raise ChatCancellationFinalizationError(
                        "cancelled Trace could not be durably finalized"
                    ) from cancellation_error
                if steered:
                    raise ChatSteeredInterruption(
                        "old chat execution was replaced"
                    ) from cancellation_error
            CHAT_TURNS.labels(outcome="interrupted" if steered else "cancelled").inc()
            CHAT_TURN_LATENCY.observe(time.monotonic() - started)
            raise
        except Exception as error:
            if owns_trace_execution and not failure_handled:
                await finalize_failure(
                    TraceStatus.FAILED,
                    error_code(error),
                    fencing_token,
                    lease_guard,
                )
            CHAT_TURNS.labels(outcome="failed").inc()
            CHAT_TURN_LATENCY.observe(time.monotonic() - started)
            raise
