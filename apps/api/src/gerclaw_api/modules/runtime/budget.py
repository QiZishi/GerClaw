"""Deterministic execution-budget accounting for every Runtime turn."""

from __future__ import annotations

import time
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.runtime.models import ExecutionBudget


class RuntimeBudgetExceededError(RuntimeError):
    """Raised with a stable public-safe limit code when a hard budget is exhausted."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ExecutionUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    steps: int = Field(ge=0)
    retries: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    output_bytes: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)


class RuntimeBudgetTracker:
    """Increment-only accounting; callers check before any next side effect."""

    def __init__(
        self,
        budget: ExecutionBudget,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._budget = budget
        self._clock = clock
        self._started = clock()
        self._steps = 0
        self._retries = 0
        self._model_calls = 0
        self._tool_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._output_bytes = 0

    def check_wall_clock(self) -> None:
        if self._clock() - self._started > self._budget.wall_clock_seconds:
            raise RuntimeBudgetExceededError("RUNTIME_WALL_CLOCK_EXCEEDED")

    def add_step(self) -> None:
        self._steps += 1
        self._check("steps", self._steps, self._budget.max_steps)

    def add_retry(self) -> None:
        self._retries += 1
        self._check("retries", self._retries, self._budget.max_retries)

    def add_model_call(self) -> None:
        self._model_calls += 1
        self._check("model_calls", self._model_calls, self._budget.max_model_calls)

    def add_tool_call(self) -> None:
        self._tool_calls += 1
        self._check("tool_calls", self._tool_calls, self._budget.max_tool_calls)

    def add_tokens(self, *, input_tokens: int, output_tokens: int) -> None:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token usage cannot be negative")
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens
        self._check("input_tokens", self._input_tokens, self._budget.max_input_tokens)
        self._check("output_tokens", self._output_tokens, self._budget.max_output_tokens)

    def add_output(self, value: str) -> None:
        self._output_bytes += len(value.encode("utf-8"))
        self._check("output_bytes", self._output_bytes, self._budget.max_output_bytes)

    def snapshot(self) -> ExecutionUsage:
        return ExecutionUsage(
            steps=self._steps,
            retries=self._retries,
            model_calls=self._model_calls,
            tool_calls=self._tool_calls,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            output_bytes=self._output_bytes,
            elapsed_seconds=max(0.0, self._clock() - self._started),
        )

    @staticmethod
    def _check(name: str, value: int, limit: int) -> None:
        if value > limit:
            raise RuntimeBudgetExceededError(f"RUNTIME_{name.upper()}_EXCEEDED")
