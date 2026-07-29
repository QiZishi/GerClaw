"""Protocol-driven projection of AgentScope events into safe public stream events."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from agentscope.agent import Agent
from agentscope.event import (
    ExceedMaxItersEvent,
    ModelCallEndEvent,
    ModelCallStartEvent,
    ReplyEndEvent,
    RequireExternalExecutionEvent,
    RequireUserConfirmEvent,
    TextBlockDeltaEvent,
    ToolCallDeltaEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
)
from agentscope.message import Msg, ToolCallBlock

from gerclaw_api.domain.trace_schemas import bounded_trace_duration_ms
from gerclaw_api.modules.agent_harness.run_lifecycle.errors import (
    AgentApprovalRequiredError,
    AgentHarnessError,
    AgentIterationLimitError,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.protocols import RunLifecycle
from gerclaw_api.modules.agent_harness.run_lifecycle.streaming import (
    bounded_events,
)
from gerclaw_api.modules.agent_harness.safety import sanitize_medical_text
from gerclaw_api.security import JsonValue

_LOGGER = logging.getLogger("gerclaw.agent_harness")
EventEmitter = Callable[[str, dict[str, JsonValue]], Awaitable[None]]
ApprovalParker = Callable[[list[ToolCallBlock]], Awaitable[tuple[str, ...]]]
EvidenceAvailable = Callable[[], bool]


class StreamBudget(Protocol):
    """Runtime budget operations needed by the lifecycle projector."""

    def check_wall_clock(self) -> None: ...

    def add_step(self) -> None: ...

    def add_model_call(self) -> None: ...

    def add_tokens(self, *, input_tokens: int, output_tokens: int) -> None: ...

    def add_tool_call(self) -> None: ...

    def add_output(self, value: str) -> None: ...


class MemoryWriteGuard(Protocol):
    """Expose only the post-stream Memory failure check."""

    def raise_if_failed(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AgentStreamResult:
    """Public, content-minimal result of one completed AgentScope stream."""

    text: str
    deterministic_diagnosis_blocked: bool
    input_tokens: int
    output_tokens: int


def final_agent_text(agent: Agent) -> str:
    """Read the completed public text retained by AgentScope's isolated state."""

    for message in reversed(agent.state.context):
        if (
            message.role == "assistant"
            and message.name == agent.name
            and message.id == agent.state.reply_id
        ):
            return "".join(block.text for block in message.get_content_blocks("text"))
    return ""


def _event_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _skill_result_identity(
    argument_text: str,
    skill_metadata: dict[str, tuple[str, str]],
) -> dict[str, JsonValue]:
    try:
        arguments = json.loads(argument_text)
    except (json.JSONDecodeError, TypeError):
        arguments = None
    selected_name = arguments.get("skill") if isinstance(arguments, dict) else None
    selected_metadata = (
        skill_metadata.get(selected_name) if isinstance(selected_name, str) else None
    )
    if selected_metadata is None:
        return {}
    return {"skill": selected_metadata[0], "version": selected_metadata[1]}


async def project_agent_stream(
    *,
    agent: Agent,
    user_message: Msg,
    budget: StreamBudget,
    wall_clock_seconds: float,
    max_output_characters: int,
    emit: EventEmitter,
    park_approvals: ApprovalParker,
    evidence_available: EvidenceAvailable,
    memory_guard: MemoryWriteGuard,
    skill_metadata: dict[str, tuple[str, str]],
    search_results: list[Any],
    lifecycle: RunLifecycle,
    timeout_error_factory: Callable[[], Exception],
) -> AgentStreamResult:
    """Execute one agent stream while enforcing safety, budgets, and terminal integrity."""

    canonical_stream = lifecycle.canonical_stream()
    buffer = lifecycle.sentence_buffer(evidence_available)
    emitted_parts: list[str] = []
    streamed_agent_parts: list[str] = []
    model_input_tokens = 0
    model_output_tokens = 0
    raw_character_count = 0
    tool_names: dict[str, str] = {}
    tool_arguments: dict[str, str] = {}
    tool_started: dict[str, float] = {}
    finished_reason = "completed"
    search_emitted = 0

    async def observed_events() -> AsyncIterator[Any]:
        try:
            async for next_event in agent.reply_stream(user_message):
                yield next_event
        except BaseException as error:
            terminal_status = "cancelled" if isinstance(error, asyncio.CancelledError) else "failed"
            for tool_call_id, started_at in list(tool_started.items()):
                tool_name = tool_names.get(tool_call_id, "unknown_tool")
                result_data: dict[str, JsonValue] = {
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "status": terminal_status,
                    "duration_ms": bounded_trace_duration_ms(time.monotonic() - started_at),
                }
                if tool_name == "Skill":
                    result_data.update(
                        _skill_result_identity(
                            tool_arguments.get(tool_call_id, ""),
                            skill_metadata,
                        )
                    )
                await emit("tool_result", result_data)
                tool_started.pop(tool_call_id, None)
                tool_names.pop(tool_call_id, None)
                tool_arguments.pop(tool_call_id, None)
            raise

    async for event in bounded_events(
        observed_events(),
        wall_clock_seconds=wall_clock_seconds,
        timeout_error_factory=timeout_error_factory,
    ):
        if isinstance(event, ModelCallStartEvent):
            budget.check_wall_clock()
            budget.add_step()
            budget.add_model_call()
            await emit(
                "reasoning_summary",
                {"content": "正在分析并整理可执行建议…", "status": "running"},
            )
        elif isinstance(event, ModelCallEndEvent):
            budget.check_wall_clock()
            model_input_tokens += event.input_tokens
            model_output_tokens += event.output_tokens
            budget.add_tokens(
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
            )
        elif isinstance(event, ToolCallStartEvent):
            budget.check_wall_clock()
            budget.add_tool_call()
            tool_names[event.tool_call_id] = event.tool_call_name
            tool_arguments[event.tool_call_id] = ""
            tool_started[event.tool_call_id] = time.monotonic()
            await emit(
                "tool_call",
                {
                    "tool_call_id": event.tool_call_id,
                    "tool_name": event.tool_call_name,
                    "status": "running",
                },
            )
        elif isinstance(event, ToolCallDeltaEvent):
            current = tool_arguments.get(event.tool_call_id, "")
            if len(current) < 2_048:
                tool_arguments[event.tool_call_id] = (current + event.delta)[:2_048]
        elif isinstance(event, ToolResultEndEvent):
            started = tool_started.pop(event.tool_call_id, time.monotonic())
            tool_name = tool_names.pop(event.tool_call_id, "unknown_tool")
            argument_text = tool_arguments.pop(event.tool_call_id, "")
            result_data: dict[str, JsonValue] = {
                "tool_call_id": event.tool_call_id,
                "tool_name": tool_name,
                "status": _event_value(event.state),
                "duration_ms": max(0, int((time.monotonic() - started) * 1_000)),
            }
            if tool_name == "Skill":
                result_data.update(_skill_result_identity(argument_text, skill_metadata))
            if tool_name == "web_search" and len(search_results) > search_emitted:
                current_results = search_results[search_emitted:]
                result_data["results"] = [
                    item.model_dump(mode="json") for item in current_results
                ]
                search_emitted = len(search_results)
            await emit("tool_result", result_data)
        elif isinstance(event, TextBlockDeltaEvent):
            budget.check_wall_clock()
            raw_character_count += len(event.delta)
            if raw_character_count > max_output_characters:
                raise AgentHarnessError("agent output exceeded the configured limit")
            for safe_part in buffer.feed(event.delta):
                public_part = canonical_stream.feed(safe_part)
                if public_part:
                    budget.add_output(public_part)
                    emitted_parts.append(public_part)
                    streamed_agent_parts.append(public_part)
                    await emit("text_delta", {"content": public_part})
        elif isinstance(event, ExceedMaxItersEvent):
            raise AgentIterationLimitError("AgentScope ReAct loop exceeded its limit")
        elif isinstance(event, (RequireUserConfirmEvent, RequireExternalExecutionEvent)):
            approval_ids = await park_approvals(event.tool_calls)
            raise AgentApprovalRequiredError(
                "side-effecting actions are parked pending explicit approval",
                approval_ids=approval_ids,
            )
        elif isinstance(event, ReplyEndEvent):
            finished_reason = _event_value(event.finished_reason)

    memory_guard.raise_if_failed()
    tail = buffer.finish()
    budget.check_wall_clock()
    if tail:
        public_tail = canonical_stream.feed(tail)
        if public_tail:
            budget.add_output(public_tail)
            emitted_parts.append(public_tail)
            streamed_agent_parts.append(public_tail)
            await emit("text_delta", {"content": public_tail})

    retained_text = final_agent_text(agent)
    if len(retained_text) > max_output_characters:
        raise AgentHarnessError("agent output exceeded the configured limit")
    sanitized_retained_text = sanitize_medical_text(
        retained_text,
        allow_evidence_backed_clinical_conclusion=evidence_available(),
    )
    safe_retained_text = sanitized_retained_text.strip()
    buffer.deterministic_diagnosis_blocked |= sanitized_retained_text != retained_text
    streamed_agent_text = "".join(streamed_agent_parts)
    observed_agent_text = streamed_agent_text + canonical_stream.pending_whitespace
    if safe_retained_text.startswith(observed_agent_text):
        missing_final_text = safe_retained_text[len(observed_agent_text) :]
    elif safe_retained_text == streamed_agent_text:
        missing_final_text = ""
    else:
        stream_without_whitespace = "".join(observed_agent_text.split())
        retained_without_whitespace = "".join(safe_retained_text.split())
        differences_only_whitespace = stream_without_whitespace == retained_without_whitespace
        diagnostic_attributes = {
            "stream_characters": len(streamed_agent_text),
            "pending_whitespace_characters": len(canonical_stream.pending_whitespace),
            "final_state_characters": len(safe_retained_text),
            "differences_only_whitespace": differences_only_whitespace,
        }
        if differences_only_whitespace:
            _LOGGER.info(
                "agent_state_stream_whitespace_normalized",
                extra=diagnostic_attributes,
            )
            missing_final_text = ""
        else:
            _LOGGER.warning("agent_state_stream_mismatch", extra=diagnostic_attributes)
            raise AgentHarnessError(
                "AgentScope final state did not match the public model stream"
            )
    if missing_final_text:
        public_final = canonical_stream.feed(missing_final_text)
        if public_final:
            emitted_parts.append(public_final)
            streamed_agent_parts.append(public_final)
            await emit("text_delta", {"content": public_final})
    canonical_stream.finish()
    if finished_reason != "completed":
        raise AgentHarnessError(f"AgentScope reply ended with {finished_reason}")
    return AgentStreamResult(
        text="".join(emitted_parts),
        deterministic_diagnosis_blocked=buffer.deterministic_diagnosis_blocked,
        input_tokens=model_input_tokens,
        output_tokens=model_output_tokens,
    )
