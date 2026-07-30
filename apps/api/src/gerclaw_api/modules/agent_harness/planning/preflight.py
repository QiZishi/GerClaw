"""Fail-closed model budget and context preflight."""

from __future__ import annotations

from collections.abc import Iterable

from gerclaw_api.modules.agent_harness.planning.contracts import (
    BudgetPreflightDecision,
    ModelCallEstimate,
)
from gerclaw_api.modules.agent_harness.token_estimation import estimate_text_tokens
from gerclaw_api.modules.runtime.budget import ExecutionUsage
from gerclaw_api.modules.runtime.models import ExecutionBudget


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
    ) -> None:
        self._budget = execution_budget
        self._model_context_tokens = model_context_tokens

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
        elif (
            estimate.estimated_input_tokens + estimate.output_reserve_tokens
            > self._model_context_tokens
        ):
            reason_code = "MODEL_CONTEXT_WINDOW_EXCEEDED"
        return BudgetPreflightDecision(
            allowed=reason_code == "MODEL_PREFLIGHT_ALLOWED",
            reason_code=reason_code,
            estimated_input_tokens=estimate.estimated_input_tokens,
            output_reserve_tokens=estimate.output_reserve_tokens,
        )
