"""Execution-round boundary tests for the AgentScope stream projector."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agentscope.event import (
    ReplyEndEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
)
from agentscope.message import ToolResultState, UserMsg

from gerclaw_api.modules.agent_harness.run_lifecycle import (
    ProductionRunLifecycle,
    project_agent_stream,
)


class _Budget:
    def check_wall_clock(self) -> None:
        pass

    def add_step(self) -> None:
        pass

    def add_model_call(self) -> None:
        pass

    def add_tokens(self, *, input_tokens: int, output_tokens: int) -> None:
        del input_tokens, output_tokens

    def add_tool_call(self) -> None:
        pass

    def add_output(self, value: str) -> None:
        del value


class _MemoryGuard:
    def raise_if_failed(self) -> None:
        pass


@pytest.mark.asyncio
async def test_runtime_directives_wait_until_whole_tool_round_finishes() -> None:
    ordering: list[str] = []

    class _Agent:
        name = "GerClaw"

        def __init__(self) -> None:
            self.state = SimpleNamespace(
                session_id="session",
                reply_id="reply",
                context=[],
            )

        async def reply_stream(self, _message: object):
            yield ToolCallStartEvent(
                reply_id="reply",
                tool_call_id="call-1",
                tool_call_name="one",
            )
            yield ToolCallStartEvent(
                reply_id="reply",
                tool_call_id="call-2",
                tool_call_name="two",
            )
            yield ToolResultEndEvent(
                reply_id="reply",
                tool_call_id="call-1",
                state=ToolResultState.SUCCESS,
            )
            ordering.append("after-first-result")
            yield ToolResultEndEvent(
                reply_id="reply",
                tool_call_id="call-2",
                state=ToolResultState.SUCCESS,
            )
            ordering.append("after-second-result")
            yield ReplyEndEvent(
                session_id="session",
                reply_id="reply",
            )

    async def emit(_kind: str, _data: object) -> None:
        pass

    async def park(_calls: object) -> tuple[str, ...]:
        return ()

    async def safe_boundary() -> int:
        ordering.append("safe-boundary")
        return 0

    await project_agent_stream(
        agent=_Agent(),  # type: ignore[arg-type]
        user_message=UserMsg(name="user", content="继续"),
        budget=_Budget(),
        wall_clock_seconds=10,
        max_output_characters=10_000,
        emit=emit,  # type: ignore[arg-type]
        park_approvals=park,  # type: ignore[arg-type]
        evidence_available=lambda _value: True,
        public_text_transform=lambda value: value,
        memory_guard=_MemoryGuard(),
        skill_metadata={},
        search_results=[],
        lifecycle=ProductionRunLifecycle(),
        timeout_error_factory=lambda: RuntimeError("timeout"),
        safe_boundary_observer=safe_boundary,
    )

    assert ordering == [
        "after-first-result",
        "safe-boundary",
        "after-second-result",
    ]
