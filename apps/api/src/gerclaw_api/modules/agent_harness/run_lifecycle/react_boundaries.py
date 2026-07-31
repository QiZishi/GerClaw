"""Per-step ReAct capacity gates composed from protocol-safe callbacks."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Literal, Protocol, TypeVar

from agentscope.message import Msg, ToolCallBlock, UserMsg

from gerclaw_api.modules.agent_harness.context_snapshot import (
    ContextBoundaryDraft,
    estimate_context_tokens,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.directive_runtime import (
    DirectiveBudget,
    RuntimeDirectiveCoordinator,
    agent_text_values,
)


class BoundaryDecision(Protocol):
    @property
    def allowed(self) -> bool: ...

    @property
    def reason_code(self) -> str: ...


BoundaryPreflight = Callable[..., BoundaryDecision]
BoundaryErrorFactory = Callable[[str], Exception]
AgentProvider = Callable[[], Any]
ContextPreparer = Callable[
    [Any, tuple[str, ...], int],
    Awaitable[ContextBoundaryDraft],
]
ContextBoundaryObserver = Callable[
    [ContextBoundaryDraft, Literal["before-model", "before-tool"], int],
    Awaitable[None],
]
_AgentEvent = TypeVar("_AgentEvent")

_PROTECTED_CONTEXT_NAMES = frozenset(
    {
        "memory",
        "clinical_state",
        "clinical_decision",
        "uploaded_document_context",
        "local_medical_evidence",
        "runtime_user_directive",
        "output_contract_repair",
    }
)
_ORIGINAL_COMPRESSOR_ATTRIBUTE = "_gerclaw_original_context_compressor"
_BOUNDARY_INSTALLED_ATTRIBUTE = "_gerclaw_react_boundaries_installed"


def _message_text(message: Msg) -> str:
    return "\n".join(block.text for block in message.get_content_blocks("text") if block.text)


def _context_projection(agent: Any) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """Return stable ids, visible text and a content hash without persisting text."""

    ids: list[str] = []
    text_values: list[str] = []
    content_hashes: list[str] = []
    id_occurrences: dict[str, int] = {}
    summary = str(getattr(agent.state, "summary", "") or "")
    if summary:
        summary_hash = hashlib.sha256(summary.encode()).hexdigest()
        ids.append(f"summary_{summary_hash[:32]}")
        text_values.append(summary)
        content_hashes.append(summary_hash)
    for message in agent.state.context:
        text = _message_text(message)
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        message_id = str(getattr(message, "id", "") or content_hash[:32])
        identity_hash = hashlib.sha256(
            f"{message_id}\0{message.role}\0{message.name}\0{content_hash}".encode()
        ).hexdigest()
        base_id = f"ctx_{identity_hash[:48]}"
        occurrence = id_occurrences.get(base_id, 0) + 1
        id_occurrences[base_id] = occurrence
        ids.append(f"{base_id}_{occurrence}")
        text_values.append(text)
        content_hashes.append(content_hash)
    projection_hash = hashlib.sha256(
        json.dumps(
            {"ids": ids, "content_hashes": content_hashes},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return tuple(ids), tuple(text_values), projection_hash


def _deterministic_extractive_fallback(
    agent: Any,
    *,
    required_tokens: int,
) -> None:
    """Retain protected clinical/directive inputs and the newest useful messages."""

    context = list(agent.state.context)
    if not context:
        return
    protected_indices = {
        index for index, message in enumerate(context) if message.name in _PROTECTED_CONTEXT_NAMES
    }
    newest_user_index = next(
        (index for index in range(len(context) - 1, -1, -1) if context[index].role == "user"),
        None,
    )
    if newest_user_index is not None:
        protected_indices.add(newest_user_index)

    trigger_ratio = float(getattr(agent.context_config, "trigger_ratio", 0.8))
    context_size = int(getattr(agent.model, "context_size", 0) or 0)
    target_tokens = max(1, int(context_size * trigger_ratio) - required_tokens)
    selected = set(protected_indices)
    selected_tokens = sum(
        estimate_context_tokens(_message_text(context[index])) for index in selected
    )
    for index in range(len(context) - 1, -1, -1):
        if index in selected:
            continue
        item_tokens = estimate_context_tokens(_message_text(context[index]))
        if selected and selected_tokens + item_tokens > target_tokens:
            continue
        selected.add(index)
        selected_tokens += item_tokens
    agent.state.context = [message for index, message in enumerate(context) if index in selected]


def _protected_context(
    context: list[Msg],
) -> tuple[list[Msg], list[Msg]]:
    """Split context while retaining critical messages outside model compression."""

    protected_ids = {id(message) for message in context if message.name in _PROTECTED_CONTEXT_NAMES}
    newest_user = next(
        (message for message in reversed(context) if message.role == "user"),
        None,
    )
    if newest_user is not None:
        protected_ids.add(id(newest_user))
    protected = [message for message in context if id(message) in protected_ids]
    compressible = [message for message in context if id(message) not in protected_ids]
    return compressible, protected


async def prepare_react_context(
    agent: Any,
    extra_text_values: tuple[str, ...],
    reserved_tokens: int = 0,
) -> ContextBoundaryDraft:
    """Give AgentScope soft compression a bounded view of pending required input.

    A deterministic extractive fallback protects clinical state, runtime user
    directives and the newest user turn if provider-backed summarization
    fails. The subsequent hard preflight remains authoritative.
    """

    source_ids, before_text, context_hash_before = _context_projection(agent)
    required_input_hashes = tuple(
        hashlib.sha256(value.encode()).hexdigest() for value in extra_text_values
    )
    required_tokens = estimate_context_tokens(*extra_text_values) + reserved_tokens
    marker = None
    original_context = list(agent.state.context)
    compressible_context, protected_context = _protected_context(original_context)
    agent.state.context = compressible_context
    if extra_text_values or reserved_tokens:
        marker = UserMsg(
            name="context_capacity_reserve",
            content="pending required input capacity\n" + ("x " * required_tokens),
        )
        agent.state.context.append(marker)
    compression_failed = False
    try:
        compressor = getattr(
            agent,
            _ORIGINAL_COMPRESSOR_ATTRIBUTE,
            agent.compress_context,
        )
        await compressor()
    except asyncio.CancelledError:
        agent.state.context = original_context
        raise
    except Exception:
        compression_failed = True
        agent.state.context = original_context
        marker = None
        _deterministic_extractive_fallback(
            agent,
            required_tokens=required_tokens,
        )
    else:
        if marker is not None:
            agent.state.context = [item for item in agent.state.context if item is not marker]
        compressed_context = list(agent.state.context)
        if len(compressed_context) == len(compressible_context) and all(
            current is original
            for current, original in zip(compressed_context, compressible_context, strict=True)
        ):
            agent.state.context = original_context
        else:
            agent.state.context = [*compressed_context, *protected_context]

        retained_objects = {id(item) for item in agent.state.context}
        missing_protected = [item for item in protected_context if id(item) not in retained_objects]
        if missing_protected:
            agent.state.context.extend(missing_protected)

    after_ids, after_text, context_hash_after = _context_projection(agent)
    source_set = set(source_ids)
    after_set = set(after_ids)
    return ContextBoundaryDraft(
        estimated_tokens_before=estimate_context_tokens(*before_text) + required_tokens,
        estimated_tokens_after=estimate_context_tokens(*after_text) + required_tokens,
        compression_attempted=True,
        compression_failed=compression_failed,
        source_context_ids=source_ids,
        retained_context_ids=tuple(item for item in source_ids if item in after_set),
        omitted_context_ids=tuple(item for item in source_ids if item not in after_set),
        summary_lineage_ids=tuple(item for item in after_ids if item not in source_set),
        required_input_hashes=required_input_hashes,
        context_hash_before=context_hash_before,
        context_hash_after=context_hash_after,
    )


class ReActBoundaryCoordinator:
    """Bind directive admission and capacity checks to every ReAct side effect."""

    def __init__(
        self,
        *,
        directives: RuntimeDirectiveCoordinator,
        model_preflight: BoundaryPreflight,
        tool_preflight: BoundaryPreflight,
        context_preparer: ContextPreparer,
        error_factory: BoundaryErrorFactory,
        image_count: int,
        boundary_observer: ContextBoundaryObserver | None = None,
    ) -> None:
        self._directives = directives
        self._model_preflight = model_preflight
        self._tool_preflight = tool_preflight
        self._context_preparer = context_preparer
        self._error_factory = error_factory
        self._image_count = image_count
        self._boundary_observer = boundary_observer

    def bind(
        self,
        *,
        agent_provider: AgentProvider,
        budget: DirectiveBudget,
    ) -> BoundReActBoundaries:
        """Create request-local counters while allowing a repaired Agent replacement."""

        return BoundReActBoundaries(
            coordinator=self,
            agent_provider=agent_provider,
            budget=budget,
        )


@dataclass(slots=True)
class BoundReActBoundaries:
    """Request-local boundary callbacks consumed by the stream projector."""

    coordinator: ReActBoundaryCoordinator
    agent_provider: AgentProvider
    budget: DirectiveBudget
    model_call_count: int = 0
    pending_tool_result_reserve_tokens: int = 0
    _tool_boundary_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _active_tool_batch_decision: str | None = field(default=None, repr=False)

    async def before_model(self) -> int:
        agent = self.agent_provider()
        self.model_call_count += 1
        self.pending_tool_result_reserve_tokens = 0
        applied_count = await self.coordinator._directives.apply_before_model(
            agent=agent,
            budget=self.budget,
        )
        draft = await self.coordinator._context_preparer(agent, (), 0)
        if self.coordinator._boundary_observer is not None:
            await self.coordinator._boundary_observer(
                draft,
                "before-model",
                self.model_call_count,
            )
        decision = self.coordinator._model_preflight(
            usage=self.budget.snapshot(),
            text_values=agent_text_values(agent),
            image_count=self.coordinator._image_count,
        )
        if not decision.allowed:
            raise self.coordinator._error_factory(decision.reason_code)
        return applied_count

    async def before_tool_batch(
        self,
        *,
        tool_calls: tuple[tuple[str, str, int], ...],
    ) -> str | None:
        """Admit one AgentScope execution batch before any member can run."""

        if not tool_calls:
            return None
        async with self._tool_boundary_lock:
            agent = self.agent_provider()
            batch_reserve = sum(max(0, item[2]) for item in tool_calls)
            self.pending_tool_result_reserve_tokens += batch_reserve
            extra_text = tuple(
                value
                for tool_name, tool_arguments, _reserve in tool_calls
                for value in (tool_name, tool_arguments)
            )
            draft = await self.coordinator._context_preparer(
                agent,
                extra_text,
                self.pending_tool_result_reserve_tokens,
            )
            if self.coordinator._boundary_observer is not None:
                await self.coordinator._boundary_observer(
                    draft,
                    "before-tool",
                    self.model_call_count,
                )
            decision = self.coordinator._tool_preflight(
                usage=self.budget.snapshot(),
                text_values=(*agent_text_values(agent), *extra_text),
                image_count=self.coordinator._image_count,
                result_reserve_tokens=self.pending_tool_result_reserve_tokens,
            )
            if not decision.allowed:
                return decision.reason_code
            return None

    async def before_tool(
        self,
        *,
        tool_name: str,
        tool_arguments: str,
        result_reserve_tokens: int,
    ) -> None:
        """Compatibility adapter for non-AgentScope single-tool consumers."""

        if self._active_tool_batch_decision is not None:
            if self._active_tool_batch_decision:
                raise self.coordinator._error_factory(self._active_tool_batch_decision)
            return
        rejection_reason = await self.before_tool_batch(
            tool_calls=((tool_name, tool_arguments, result_reserve_tokens),),
        )
        if rejection_reason is not None:
            raise self.coordinator._error_factory(rejection_reason)

    def install_on_agent(
        self,
        agent: Any,
        *,
        result_reserve_by_tool: dict[str, int],
    ) -> None:
        """Install gates at AgentScope's true pre-model and pre-batch boundaries.

        AgentScope compresses before emitting ``ModelCallStartEvent`` and
        executes concurrency-safe calls inside a private batch generator.
        These request-local wrappers therefore run earlier than public stream
        projection without replacing AgentScope's reasoning or tool runtime.
        """

        if getattr(agent, _BOUNDARY_INSTALLED_ATTRIBUTE, False):
            return

        original_compressor = agent.compress_context
        original_concurrent = agent._execute_concurrent_tool_calls
        original_sequential = agent._execute_sequential_tool_calls
        setattr(agent, _ORIGINAL_COMPRESSOR_ATTRIBUTE, original_compressor)

        async def guarded_compress_context(
            context_config: Any = None,
            instructions: Any = None,
        ) -> None:
            configured_compressor = partial(
                original_compressor,
                context_config=context_config,
                instructions=instructions,
            )
            setattr(agent, _ORIGINAL_COMPRESSOR_ATTRIBUTE, configured_compressor)
            try:
                await self.before_model()
            finally:
                setattr(agent, _ORIGINAL_COMPRESSOR_ATTRIBUTE, original_compressor)

        def admitted_calls(
            tool_calls: list[ToolCallBlock],
        ) -> tuple[tuple[str, str, int], ...]:
            return tuple(
                (
                    call.name,
                    call.input,
                    max(0, result_reserve_by_tool.get(call.name, 0)),
                )
                for call in tool_calls
            )

        async def guarded_concurrent(
            tool_calls: list[ToolCallBlock],
        ) -> AsyncIterator[_AgentEvent]:
            rejection_reason = await self.before_tool_batch(tool_calls=admitted_calls(tool_calls))
            self._active_tool_batch_decision = rejection_reason or ""
            try:
                async for event in original_concurrent(tool_calls):
                    yield event
            finally:
                self._active_tool_batch_decision = None

        async def guarded_sequential(
            tool_calls: list[ToolCallBlock],
        ) -> AsyncIterator[_AgentEvent]:
            rejection_reason = await self.before_tool_batch(tool_calls=admitted_calls(tool_calls))
            self._active_tool_batch_decision = rejection_reason or ""
            try:
                async for event in original_sequential(tool_calls):
                    yield event
            finally:
                self._active_tool_batch_decision = None

        agent.compress_context = guarded_compress_context
        agent._execute_concurrent_tool_calls = guarded_concurrent
        agent._execute_sequential_tool_calls = guarded_sequential
        setattr(agent, _BOUNDARY_INSTALLED_ATTRIBUTE, True)
