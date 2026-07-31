"""Boundary-level admission tests for execution-time user directives."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from importlib.metadata import version
from types import SimpleNamespace

import pytest
from agentscope.agent import Agent
from agentscope.message import (
    AssistantMsg,
    HintBlock,
    ToolCallBlock,
    ToolResultBlock,
    UserMsg,
)

from gerclaw_api.domain.run_schemas import RunDirectiveRead, RunDirectiveStatus
from gerclaw_api.modules.agent_harness.run_lifecycle.directive_runtime import (
    RuntimeDirectiveCoordinator,
    agent_model_input_tokens,
    agent_text_values,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.react_boundaries import (
    ReActBoundaryCoordinator,
    prepare_react_context,
)
from gerclaw_api.modules.runtime.budget import RuntimeBudgetExceededError
from tests.test_agent_harness import _directive


class _Budget:
    def snapshot(self) -> object:
        return object()


def test_agentscope_boundary_hooks_match_pinned_runtime() -> None:
    assert version("agentscope") == "2.0.4"
    assert tuple(inspect.signature(Agent.compress_context).parameters) == (
        "self",
        "context_config",
        "instructions",
    )
    assert tuple(inspect.signature(Agent._execute_concurrent_tool_calls).parameters) == (
        "self",
        "tool_calls",
    )
    assert tuple(inspect.signature(Agent._execute_sequential_tool_calls).parameters) == (
        "self",
        "tool_calls",
    )
    assert tuple(inspect.signature(Agent._prepare_model_input).parameters) == ("self",)


def test_capacity_projection_includes_summary_hint_and_tool_blocks() -> None:
    agent = SimpleNamespace(
        state=SimpleNamespace(
            summary="existing-summary",
            context=[
                AssistantMsg(
                    name="memory",
                    content=[HintBlock(hint="mem0-hint", source="mem0")],
                ),
                AssistantMsg(
                    name="assistant",
                    content=[
                        ToolCallBlock(
                            id="call-1",
                            name="search",
                            input='{"query":"fall risk"}',
                        )
                    ],
                ),
                AssistantMsg(
                    name="assistant",
                    content=[
                        ToolResultBlock(
                            id="call-1",
                            name="search",
                            output="tool-result-output",
                            state="success",
                        )
                    ],
                ),
            ],
        )
    )

    projection = "\n".join(agent_text_values(agent))

    assert "existing-summary" in projection
    assert "mem0-hint" in projection
    assert "fall risk" in projection
    assert "tool-result-output" in projection


@pytest.mark.asyncio
async def test_actual_agentscope_prepared_input_counter_is_used_when_available() -> None:
    observed: list[tuple[object, object]] = []

    class _Model:
        async def count_tokens(self, messages: object, tools: object) -> int:
            observed.append((messages, tools))
            return 987

    class _Agent:
        def __init__(self) -> None:
            self.model = _Model()

        async def _prepare_model_input(self) -> dict[str, object]:
            return {
                "messages": ["dynamic-system", "summary", "full-context"],
                "tools": [{"name": "governed_tool", "schema": {"type": "object"}}],
            }

    agent = _Agent()

    assert await agent_model_input_tokens(agent) == 987
    assert observed == [
        (
            ["dynamic-system", "summary", "full-context"],
            [{"name": "governed_tool", "schema": {"type": "object"}}],
        )
    ]


@pytest.mark.asyncio
async def test_model_boundary_passes_exact_prepared_input_count_to_hard_gate() -> None:
    observed: list[dict[str, object]] = []

    async def prepare(
        _agent: object,
        _extra: tuple[str, ...],
        _reserved_tokens: int,
    ) -> object:
        return SimpleNamespace()

    class _Model:
        async def count_tokens(self, _messages: object, _tools: object) -> int:
            return 731

    class _Agent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(summary="", context=[])
            self.model = _Model()

        async def _prepare_model_input(self) -> dict[str, object]:
            return {
                "messages": [UserMsg(name="system", content="dynamic prompt")],
                "tools": [{"name": "search", "parameters": {"type": "object"}}],
            }

    directives = RuntimeDirectiveCoordinator(
        loader=None,
        claimer=None,
        applier=None,
        preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        error_factory=RuntimeBudgetExceededError,
        risk_classifier=lambda _instructions: (),
        max_per_boundary=20,
        max_per_run=200,
        image_count=0,
    )
    agent = _Agent()
    boundaries = ReActBoundaryCoordinator(
        directives=directives,
        model_preflight=lambda **kwargs: (
            observed.append(dict(kwargs)) or SimpleNamespace(allowed=True, reason_code="")
        ),
        tool_preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        context_preparer=prepare,  # type: ignore[arg-type]
        error_factory=RuntimeBudgetExceededError,
        image_count=0,
    ).bind(agent_provider=lambda: agent, budget=_Budget())

    await boundaries.before_model()

    assert observed[0]["estimated_input_tokens"] == 731
    assert observed[0]["text_values"] == ()


@pytest.mark.asyncio
async def test_tool_fallback_does_not_double_count_prepared_tool_arguments() -> None:
    observed: list[dict[str, object]] = []
    tool_call = ToolCallBlock(
        id="call-fallback",
        name="search",
        input='{"query":"unique-fallback-argument"}',
    )

    class _Model:
        async def count_tokens(self, _messages: object, _tools: object) -> int:
            raise RuntimeError("local tokenizer unavailable")

    class _Agent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(
                summary="",
                context=[AssistantMsg(name="assistant", content=[tool_call])],
            )
            self.model = _Model()

        async def _prepare_model_input(self) -> dict[str, object]:
            return {
                "messages": self.state.context,
                "tools": [{"name": "search", "parameters": {"type": "object"}}],
            }

    async def prepare(
        _agent: object,
        _extra: tuple[str, ...],
        _reserved_tokens: int,
    ) -> object:
        return SimpleNamespace()

    directives = RuntimeDirectiveCoordinator(
        loader=None,
        claimer=None,
        applier=None,
        preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        error_factory=RuntimeBudgetExceededError,
        risk_classifier=lambda _instructions: (),
        max_per_boundary=20,
        max_per_run=200,
        image_count=0,
    )
    agent = _Agent()
    boundaries = ReActBoundaryCoordinator(
        directives=directives,
        model_preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        tool_preflight=lambda **kwargs: (
            observed.append(dict(kwargs)) or SimpleNamespace(allowed=True, reason_code="")
        ),
        context_preparer=prepare,  # type: ignore[arg-type]
        error_factory=RuntimeBudgetExceededError,
        image_count=0,
    ).bind(agent_provider=lambda: agent, budget=_Budget())

    await boundaries.before_tool_batch(
        tool_calls=(("search", tool_call.input, 128),),
    )

    values = observed[0]["text_values"]
    assert isinstance(values, tuple)
    assert tool_call.input not in values
    assert "\n".join(values).count("unique-fallback-argument") == 1


@pytest.mark.asyncio
async def test_react_context_preparer_accounts_for_required_extra_without_retaining_marker() -> (
    None
):
    class _Agent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(context=[])
            self.observed = ""

        async def compress_context(self) -> None:
            self.observed = self.state.context[-1].get_text_content()

    agent = _Agent()

    draft = await prepare_react_context(agent, ("用户追加要求", "工具参数"))

    assert "pending required input capacity" in agent.observed
    assert "用户追加要求" not in agent.observed
    assert "工具参数" not in agent.observed
    assert agent.state.context == []
    assert draft.required_input_hashes
    assert draft.compression_failed is False


@pytest.mark.asyncio
async def test_react_context_failure_uses_protected_extractive_fallback() -> None:
    class _Agent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(
                summary="",
                context=[
                    AssistantMsg(name="old", content="旧的低价值内容 " * 30),
                    AssistantMsg(name="clinical_state", content="已确认青霉素过敏"),
                    UserMsg(name="runtime_user_directive", content="新增要求:只列重点"),
                    UserMsg(name="user", content="当前问题"),
                ],
            )
            self.context_config = SimpleNamespace(trigger_ratio=0.8)
            self.model = SimpleNamespace(context_size=40)

        async def compress_context(self) -> None:
            raise RuntimeError("provider compression unavailable")

    agent = _Agent()
    draft = await prepare_react_context(agent, ("工具参数",), 8)

    assert draft.compression_failed is True
    assert draft.estimated_tokens_before > draft.estimated_tokens_after
    assert [message.name for message in agent.state.context] == [
        "clinical_state",
        "runtime_user_directive",
        "user",
    ]
    assert draft.omitted_context_ids
    assert all(message.name != "context_capacity_reserve" for message in agent.state.context)


@pytest.mark.asyncio
async def test_successful_compression_cannot_remove_high_value_context() -> None:
    protected = [
        AssistantMsg(name="memory", content="用户自述长期服用华法林"),
        AssistantMsg(name="clinical_state", content="已确认青霉素过敏"),
        UserMsg(name="runtime_user_directive", content="新增要求:只列重点"),
        AssistantMsg(name="output_contract_repair", content="修复本步骤输出"),
        UserMsg(name="user", content="当前问题"),
    ]

    class _Agent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(
                summary="",
                context=[
                    AssistantMsg(name="old", content="可压缩的旧内容"),
                    *protected,
                ],
            )

        async def compress_context(self) -> None:
            self.state.summary = "压缩后的摘要"
            self.state.context = []

    agent = _Agent()
    draft = await prepare_react_context(agent, ())

    assert agent.state.context == protected
    assert draft.compression_failed is False
    assert draft.omitted_context_ids
    assert len(draft.retained_context_ids) == len(protected)


@pytest.mark.asyncio
async def test_compression_lineage_keeps_identity_for_later_exact_duplicate() -> None:
    first = AssistantMsg(name="duplicate", content="相同内容", id="same-id")
    second = AssistantMsg(name="duplicate", content="相同内容", id="same-id")

    class _Agent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(summary="", context=[first, second])

        async def compress_context(self) -> None:
            self.state.context = [second]

    draft = await prepare_react_context(_Agent(), ())

    assert draft.retained_context_ids == (draft.source_context_ids[1],)
    assert draft.omitted_context_ids == (draft.source_context_ids[0],)


@pytest.mark.asyncio
async def test_cancelled_compression_atomically_restores_summary_and_context() -> None:
    original = AssistantMsg(name="assistant", content="未压缩事实")

    class _Agent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(summary="old-summary", context=[original])

        async def compress_context(self) -> None:
            self.state.summary = "new-summary-from-cancelled-compression"
            self.state.context = []
            raise asyncio.CancelledError

    agent = _Agent()

    with pytest.raises(asyncio.CancelledError):
        await prepare_react_context(agent, ())

    assert agent.state.summary == "old-summary"
    assert agent.state.context == [original]


@pytest.mark.asyncio
async def test_failed_compression_restores_summary_before_extractive_fallback() -> None:
    original = AssistantMsg(name="assistant", content="未压缩事实")

    class _Agent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(summary="old-summary", context=[original])
            self.context_config = SimpleNamespace(trigger_ratio=0.8)
            self.model = SimpleNamespace(context_size=100)

        async def compress_context(self) -> None:
            self.state.summary = "partial-summary-from-failed-compression"
            self.state.context = []
            raise RuntimeError("compression failed after mutation")

    agent = _Agent()

    await prepare_react_context(agent, ())

    assert agent.state.summary == "old-summary"
    assert agent.state.context == [original]


@pytest.mark.asyncio
async def test_tool_boundaries_accumulate_pending_result_reserve_until_next_model() -> None:
    observed_soft_reserves: list[int] = []
    observed_hard_reserves: list[int] = []

    async def prepare(
        _agent: object,
        _extra: tuple[str, ...],
        reserved_tokens: int,
    ) -> object:
        observed_soft_reserves.append(reserved_tokens)
        return SimpleNamespace()

    def tool_preflight(**kwargs: object) -> SimpleNamespace:
        observed_hard_reserves.append(int(kwargs["result_reserve_tokens"]))
        return SimpleNamespace(allowed=True, reason_code="")

    directives = RuntimeDirectiveCoordinator(
        loader=None,
        claimer=None,
        applier=None,
        preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        error_factory=RuntimeBudgetExceededError,
        risk_classifier=lambda _instructions: (),
        max_per_boundary=20,
        max_per_run=200,
        image_count=0,
    )
    agent = SimpleNamespace(state=SimpleNamespace(context=[]))
    boundaries = ReActBoundaryCoordinator(
        directives=directives,
        model_preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        tool_preflight=tool_preflight,
        context_preparer=prepare,  # type: ignore[arg-type]
        error_factory=RuntimeBudgetExceededError,
        image_count=0,
    ).bind(agent_provider=lambda: agent, budget=_Budget())

    await boundaries.before_tool(
        tool_name="one",
        tool_arguments="{}",
        result_reserve_tokens=100,
    )
    await boundaries.before_tool(
        tool_name="two",
        tool_arguments="{}",
        result_reserve_tokens=200,
    )
    await boundaries.before_model()
    await boundaries.before_tool(
        tool_name="three",
        tool_arguments="{}",
        result_reserve_tokens=50,
    )

    assert observed_soft_reserves == [100, 300, 0, 50]
    assert observed_hard_reserves == [100, 300, 50]


@pytest.mark.asyncio
async def test_installed_agent_boundaries_admit_whole_tool_batch_before_side_effect() -> None:
    events: list[str] = []
    observed_reserves: list[int] = []
    observed_values: list[tuple[str, ...]] = []

    class _Agent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(summary="", context=[])

        async def compress_context(
            self,
            context_config: object = None,
            instructions: object = None,
        ) -> None:
            del context_config, instructions
            events.append("compress")

        async def _execute_concurrent_tool_calls(
            self,
            _tool_calls: list[ToolCallBlock],
        ):
            events.append("concurrent-side-effect")
            yield "concurrent-result"

        async def _execute_sequential_tool_calls(
            self,
            _tool_calls: list[ToolCallBlock],
        ):
            events.append("sequential-side-effect")
            yield "sequential-result"

    def tool_preflight(**kwargs: object) -> SimpleNamespace:
        events.append("tool-preflight")
        observed_reserves.append(int(kwargs["result_reserve_tokens"]))
        observed_values.append(tuple(kwargs["text_values"]))  # type: ignore[arg-type]
        return SimpleNamespace(allowed=True, reason_code="")

    directives = RuntimeDirectiveCoordinator(
        loader=None,
        claimer=None,
        applier=None,
        preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        error_factory=RuntimeBudgetExceededError,
        risk_classifier=lambda _instructions: (),
        max_per_boundary=20,
        max_per_run=200,
        image_count=0,
    )
    agent = _Agent()
    boundaries = ReActBoundaryCoordinator(
        directives=directives,
        model_preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        tool_preflight=tool_preflight,
        context_preparer=prepare_react_context,
        error_factory=RuntimeBudgetExceededError,
        image_count=0,
    ).bind(agent_provider=lambda: agent, budget=_Budget())
    boundaries.install_on_agent(
        agent,
        result_reserve_by_tool={"one": 100, "two": 200},
    )
    calls = [
        ToolCallBlock(id="call-1", name="one", input='{"a":1}'),
        ToolCallBlock(id="call-2", name="two", input='{"b":2}'),
    ]

    results = [item async for item in agent._execute_concurrent_tool_calls(calls)]

    assert results == ["concurrent-result"]
    assert observed_reserves == [300]
    assert {"one", "two", '{"a":1}', '{"b":2}'}.issubset(set(observed_values[0]))
    assert events.index("tool-preflight") < events.index("concurrent-side-effect")


@pytest.mark.asyncio
async def test_installed_agent_boundary_runs_before_agentscope_model_compression() -> None:
    events: list[str] = []

    class _Agent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(summary="", context=[])

        async def compress_context(
            self,
            context_config: object = None,
            instructions: object = None,
        ) -> None:
            del context_config, instructions
            events.append("agentscope-compress")

        async def _execute_concurrent_tool_calls(self, _tool_calls: object):
            if False:
                yield None

        async def _execute_sequential_tool_calls(self, _tool_calls: object):
            if False:
                yield None

    directives = RuntimeDirectiveCoordinator(
        loader=None,
        claimer=None,
        applier=None,
        preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        error_factory=RuntimeBudgetExceededError,
        risk_classifier=lambda _instructions: (),
        max_per_boundary=20,
        max_per_run=200,
        image_count=0,
    )
    agent = _Agent()

    def model_preflight(**_kwargs: object) -> SimpleNamespace:
        events.append("model-preflight")
        return SimpleNamespace(allowed=True, reason_code="")

    boundaries = ReActBoundaryCoordinator(
        directives=directives,
        model_preflight=model_preflight,
        tool_preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        context_preparer=prepare_react_context,
        error_factory=RuntimeBudgetExceededError,
        image_count=0,
    ).bind(agent_provider=lambda: agent, budget=_Budget())
    boundaries.install_on_agent(agent, result_reserve_by_tool={})

    await agent.compress_context()

    assert events == ["agentscope-compress", "model-preflight"]
    assert boundaries.model_call_count == 1


@pytest.mark.asyncio
async def test_batch_preflight_failure_does_not_apply_any_claimed_directive() -> None:
    claimed = (
        _directive(
            status=RunDirectiveStatus.CLAIMED,
            instruction="第一条要求可放入上下文。",
            sequence=1,
            boundary_id="before-model-1",
        ),
        _directive(
            status=RunDirectiveStatus.CLAIMED,
            instruction="第二条让整个批次超过上下文预算。",
            sequence=2,
            boundary_id="before-model-1",
        ),
    )
    applied: list[uuid.UUID] = []

    async def load() -> tuple[RunDirectiveRead, ...]:
        return ()

    async def claim(
        _boundary_id: str,
        _limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        return claimed

    async def apply(
        directive_ids: tuple[uuid.UUID, ...],
        _boundary_id: str,
    ) -> None:
        applied.extend(directive_ids)

    coordinator = RuntimeDirectiveCoordinator(
        loader=load,
        claimer=claim,
        applier=apply,
        preflight=lambda **_kwargs: SimpleNamespace(
            allowed=False,
            reason_code="MODEL_CONTEXT_BUDGET_EXCEEDED",
        ),
        error_factory=RuntimeBudgetExceededError,
        risk_classifier=lambda _instructions: (),
        max_per_boundary=20,
        max_per_run=200,
        image_count=0,
    )
    agent = SimpleNamespace(state=SimpleNamespace(context=[]))

    with pytest.raises(
        RuntimeBudgetExceededError,
        match="MODEL_CONTEXT_BUDGET_EXCEEDED",
    ):
        await coordinator.prepare_initial(
            agent=agent,
            budget=_Budget(),
            user_message="原始要求",
        )

    assert applied == []


@pytest.mark.asyncio
async def test_explicit_run_budget_caps_claims_across_multiple_boundaries() -> None:
    next_sequence = 0
    requested_limits: list[int] = []
    applied: list[uuid.UUID] = []

    async def load() -> tuple[RunDirectiveRead, ...]:
        return ()

    async def claim(
        boundary_id: str,
        limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        nonlocal next_sequence
        requested_limits.append(limit)
        values: list[RunDirectiveRead] = []
        for _ in range(limit):
            next_sequence += 1
            values.append(
                _directive(
                    status=RunDirectiveStatus.CLAIMED,
                    instruction=f"第 {next_sequence} 条要求。",
                    sequence=next_sequence,
                    boundary_id=boundary_id,
                )
            )
        return tuple(values)

    async def apply(
        directive_ids: tuple[uuid.UUID, ...],
        _boundary_id: str,
    ) -> None:
        applied.extend(directive_ids)

    coordinator = RuntimeDirectiveCoordinator(
        loader=load,
        claimer=claim,
        applier=apply,
        preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        error_factory=RuntimeBudgetExceededError,
        risk_classifier=lambda _instructions: (),
        max_per_boundary=2,
        max_per_run=3,
        image_count=0,
    )
    agent = SimpleNamespace(state=SimpleNamespace(context=[]))

    _, first_count, _ = await coordinator.prepare_initial(
        agent=agent,
        budget=_Budget(),
        user_message="原始要求",
    )
    second_count = await coordinator.apply_after_tool(agent=agent, budget=_Budget())
    third_count = await coordinator.apply_after_tool(agent=agent, budget=_Budget())

    assert (first_count, second_count, third_count) == (2, 1, 0)
    assert requested_limits == [2, 1]
    assert len(applied) == 3


@pytest.mark.asyncio
async def test_before_model_boundary_uses_distinct_monotonic_identity() -> None:
    boundaries: list[str] = []

    async def load() -> tuple[RunDirectiveRead, ...]:
        return ()

    async def claim(
        boundary_id: str,
        _limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        boundaries.append(boundary_id)
        return ()

    async def apply(
        _directive_ids: tuple[uuid.UUID, ...],
        _boundary_id: str,
    ) -> None:
        raise AssertionError("empty claims must not be applied")

    coordinator = RuntimeDirectiveCoordinator(
        loader=load,
        claimer=claim,
        applier=apply,
        preflight=lambda **_kwargs: SimpleNamespace(allowed=True, reason_code=""),
        error_factory=RuntimeBudgetExceededError,
        risk_classifier=lambda _instructions: (),
        max_per_boundary=20,
        max_per_run=200,
        image_count=0,
    )
    agent = SimpleNamespace(state=SimpleNamespace(context=[]))

    await coordinator.prepare_initial(
        agent=agent,
        budget=_Budget(),
        user_message="原始要求",
    )
    await coordinator.apply_before_model(agent=agent, budget=_Budget())

    assert boundaries == ["before-model-1", "before-react-model-2"]


@pytest.mark.asyncio
async def test_directive_batch_prepares_context_before_hard_preflight_and_apply() -> None:
    events: list[str] = []
    claimed = _directive(
        status=RunDirectiveStatus.CLAIMED,
        instruction="继续保留用户新增要求。",
        boundary_id="before-model-1",
    )

    async def load() -> tuple[RunDirectiveRead, ...]:
        return ()

    async def claim(
        _boundary_id: str,
        _limit: int,
    ) -> tuple[RunDirectiveRead, ...]:
        return (claimed,)

    async def prepare(
        _agent: object,
        extra_text: tuple[str, ...],
        reserved_tokens: int,
    ) -> object:
        assert reserved_tokens == 0
        assert any("继续保留用户新增要求" in item for item in extra_text)
        events.append("prepare")
        return object()

    def preflight(**_kwargs: object) -> SimpleNamespace:
        events.append("preflight")
        return SimpleNamespace(allowed=True, reason_code="")

    async def apply(
        _directive_ids: tuple[uuid.UUID, ...],
        _boundary_id: str,
    ) -> None:
        events.append("apply")

    coordinator = RuntimeDirectiveCoordinator(
        loader=load,
        claimer=claim,
        applier=apply,
        preflight=preflight,
        error_factory=RuntimeBudgetExceededError,
        risk_classifier=lambda _instructions: (),
        context_preparer=prepare,
        max_per_boundary=20,
        max_per_run=200,
        image_count=0,
    )
    agent = SimpleNamespace(state=SimpleNamespace(context=[]))

    await coordinator.prepare_initial(
        agent=agent,
        budget=_Budget(),
        user_message="原始要求",
    )

    assert events == ["prepare", "preflight", "apply"]
