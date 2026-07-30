"""Boundary-level admission tests for execution-time user directives."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from gerclaw_api.domain.run_schemas import RunDirectiveRead, RunDirectiveStatus
from gerclaw_api.modules.agent_harness.run_lifecycle.directive_runtime import (
    RuntimeDirectiveCoordinator,
)
from gerclaw_api.modules.runtime.budget import RuntimeBudgetExceededError
from tests.test_agent_harness import _directive


class _Budget:
    def snapshot(self) -> object:
        return object()


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
