"""Chapter 4.6 Agent Harness interfaces and bounded streaming contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from gerclaw_api.modules.agent_harness.context_snapshot import (
    AgentContext,
    ConversationHistoryMessage,
)
from gerclaw_api.modules.contracts import AgentResponse
from gerclaw_api.security import JsonValue

__all__ = [
    "AgentContext",
    "AgentHarness",
    "ConversationHistoryMessage",
    "StreamEvent",
]


class StreamEvent(BaseModel):
    """SSE event carrying audit summaries, never raw chain-of-thought."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal[
        "agent_start",
        "reasoning_summary",
        "tool_call",
        "tool_result",
        "approval_required",
        "text_delta",
        "safety_notice",
        "done",
    ]
    data: dict[str, JsonValue]
    timestamp: datetime


class AgentHarness(Protocol):
    """Agent lifecycle, context assembly, safety checkpoints, and streaming boundary."""

    async def process_message(
        self,
        user_message: str,
        session_id: str,
        context: AgentContext,
        stream_callback: Callable[[StreamEvent], Awaitable[None] | None],
    ) -> AgentResponse:
        """Process one safe, traced message through AgentScope."""

    async def assemble_context(
        self,
        session_id: str,
        user_id: str,
        loaded_skills: list[str],
        uploaded_files: list[str],
    ) -> AgentContext:
        """Assemble the required context sources for a turn."""
