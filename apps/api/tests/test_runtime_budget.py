from __future__ import annotations

from collections.abc import Callable

import pytest

from gerclaw_api.modules.runtime.budget import (
    RuntimeBudgetExceededError,
    RuntimeBudgetTracker,
)
from gerclaw_api.modules.runtime.models import ExecutionBudget


def test_budget_accounts_multibyte_output_and_calls() -> None:
    now = [10.0]
    tracker = RuntimeBudgetTracker(
        ExecutionBudget(
            wall_clock_seconds=5,
            max_steps=1,
            max_model_calls=1,
            max_tool_calls=1,
            max_input_tokens=256,
            max_output_tokens=256,
            max_output_bytes=1_000,
        ),
        clock=lambda: now[0],
    )
    tracker.add_step()
    tracker.add_model_call()
    tracker.add_tool_call()
    tracker.add_tokens(input_tokens=10, output_tokens=20)
    tracker.add_output("老人")
    usage = tracker.snapshot()
    assert usage.output_bytes == 6
    assert usage.model_calls == 1
    now[0] = 16.0
    with pytest.raises(RuntimeBudgetExceededError) as error:
        tracker.check_wall_clock()
    assert error.value.code == "RUNTIME_WALL_CLOCK_EXCEEDED"


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (lambda value: value.add_step(), "RUNTIME_STEPS_EXCEEDED"),
        (lambda value: value.add_retry(), "RUNTIME_RETRIES_EXCEEDED"),
        (lambda value: value.add_model_call(), "RUNTIME_MODEL_CALLS_EXCEEDED"),
        (lambda value: value.add_tool_call(), "RUNTIME_TOOL_CALLS_EXCEEDED"),
    ],
)
def test_budget_fails_with_stable_limit_code(
    operation: Callable[[RuntimeBudgetTracker], None], expected: str
) -> None:
    tracker = RuntimeBudgetTracker(
        ExecutionBudget(
            max_steps=1,
            max_retries=0,
            max_model_calls=1,
            max_tool_calls=1,
        )
    )
    if expected != "RUNTIME_RETRIES_EXCEEDED":
        operation(tracker)
    with pytest.raises(RuntimeBudgetExceededError) as error:
        operation(tracker)
    assert error.value.code == expected


def test_budget_rejects_negative_usage_and_token_overrun() -> None:
    tracker = RuntimeBudgetTracker(ExecutionBudget(max_input_tokens=256))
    with pytest.raises(ValueError, match="negative"):
        tracker.add_tokens(input_tokens=-1, output_tokens=0)
    with pytest.raises(RuntimeBudgetExceededError) as error:
        tracker.add_tokens(input_tokens=257, output_tokens=0)
    assert error.value.code == "RUNTIME_INPUT_TOKENS_EXCEEDED"
