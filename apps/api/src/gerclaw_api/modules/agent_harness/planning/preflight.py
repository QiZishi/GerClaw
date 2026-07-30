"""Fail-closed model budget and context preflight."""

from __future__ import annotations

from collections.abc import Iterable

from gerclaw_api.context_capacity import ContextWindowLimits
from gerclaw_api.modules.agent_harness.planning.contracts import (
    BudgetPreflightDecision,
    ModelCallEstimate,
)
from gerclaw_api.modules.runtime.budget import ExecutionUsage
from gerclaw_api.modules.runtime.models import ExecutionBudget
from gerclaw_api.token_estimation import estimate_text_tokens


def approximate_input_tokens(values: Iterable[str]) -> int:
    """Use the shared dependency-free UTF-8 approximation."""

    return estimate_text_tokens(values)


class ModelBudgetPreflight:
    """Check the next model side effect against remaining hard limits."""

    def __init__(
        self,
        *,
        execution_budget: ExecutionBudget,
        model_context_tokens: int,
        context_trigger_ratio: float | None = None,
        context_hard_stop_ratio: float | None = None,
        context_reserve_ratio: float | None = None,
    ) -> None:
        self._budget = execution_budget
        self._model_context_tokens = model_context_tokens
        self._context_trigger_ratio = context_trigger_ratio
        self._context_hard_stop_ratio = context_hard_stop_ratio
        self._context_reserve_ratio = context_reserve_ratio
        configured_ratios = (
            context_trigger_ratio,
            context_hard_stop_ratio,
            context_reserve_ratio,
        )
        if any(value is not None for value in configured_ratios) and any(
            value is None for value in configured_ratios
        ):
            raise ValueError("all context ratios must be provided together")

    def check(
        self,
        usage: ExecutionUsage,
        estimate: ModelCallEstimate,
    ) -> BudgetPreflightDecision:
        reason_code = "MODEL_PREFLIGHT_ALLOWED"
        if usage.model_calls + estimate.additional_model_calls > self._budget.max_model_calls:
            reason_code = "RUNTIME_MODEL_CALLS_EXCEEDED"
        elif usage.tool_calls + estimate.additional_tool_calls > self._budget.max_tool_calls:
            reason_code = "RUNTIME_TOOL_CALLS_EXCEEDED"
        elif usage.input_tokens + estimate.estimated_input_tokens > self._budget.max_input_tokens:
            reason_code = "RUNTIME_INPUT_TOKENS_EXCEEDED"
        elif usage.output_tokens + estimate.output_reserve_tokens > self._budget.max_output_tokens:
            reason_code = "RUNTIME_OUTPUT_TOKENS_EXCEEDED"
        elif estimate.estimated_input_tokens > self._hard_input_limit(
            estimate.output_reserve_tokens
        ):
            reason_code = "MODEL_CONTEXT_WINDOW_EXCEEDED"
        return BudgetPreflightDecision(
            allowed=reason_code == "MODEL_PREFLIGHT_ALLOWED",
            reason_code=reason_code,
            estimated_input_tokens=estimate.estimated_input_tokens,
            output_reserve_tokens=estimate.output_reserve_tokens,
        )

    def _hard_input_limit(self, output_reserve_tokens: int) -> int:
        if self._context_hard_stop_ratio is None:
            return self._model_context_tokens - output_reserve_tokens
        assert self._context_trigger_ratio is not None
        assert self._context_reserve_ratio is not None
        limits = ContextWindowLimits.resolve(
            model_context_tokens=self._model_context_tokens,
            trigger_ratio=self._context_trigger_ratio,
            hard_stop_ratio=self._context_hard_stop_ratio,
            reserve_ratio=self._context_reserve_ratio,
            output_reserve_tokens=output_reserve_tokens,
        )
        return limits.hard_stop_input_tokens
