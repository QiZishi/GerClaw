"""Boundary-level admission tests for execution-time user directives."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from agentscope.message import AssistantMsg, UserMsg

from gerclaw_api.domain.run_schemas import RunDirectiveRead, RunDirectiveStatus
from gerclaw_api.modules.agent_harness.run_lifecycle.directive_runtime import (
    RuntimeDirectiveCoordinator,
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

    assert "用户追加要求" in agent.observed
    assert "工具参数" in agent.observed
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
