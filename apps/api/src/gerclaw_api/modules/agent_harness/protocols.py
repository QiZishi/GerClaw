"""Chapter 4.6 Agent Harness interface; implementation follows in the next milestone."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.contracts import AgentResponse, ExecutionContext
from gerclaw_api.security import JsonValue


class AgentContext(BaseModel):
    """Nine-source context assembled before entering the AgentScope ReAct loop."""

    model_config = ConfigDict(extra="forbid")

    execution: ExecutionContext
    system_instructions: list[str] = Field(max_length=20)
    tool_names: list[str] = Field(max_length=100)
    profile_ref: str | None = None
    memory_refs: list[str] = Field(default_factory=list, max_length=100)
    loaded_skills: list[str] = Field(default_factory=list, max_length=50)
    uploaded_files: list[str] = Field(default_factory=list, max_length=20)


class StreamEvent(BaseModel):
    """SSE event carrying audit summaries, never raw chain-of-thought."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal[
        "agent_start",
        "reasoning_summary",
        "tool_call",
        "tool_result",
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
        stream_callback: Callable[[StreamEvent], None],
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
