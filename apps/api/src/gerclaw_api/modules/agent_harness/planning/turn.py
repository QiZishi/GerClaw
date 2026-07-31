"""One composition helper for route, plan, and model preflight."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from gerclaw_api.modules.agent_harness.config import ResolvedHarnessConfig
from gerclaw_api.modules.agent_harness.planning.contracts import (
    BudgetPreflightDecision,
    DynamicPlan,
    ModelCallEstimate,
    Planner,
    PlanningError,
    PlanRequest,
)
from gerclaw_api.modules.agent_harness.planning.planner import (
    DeterministicPlanner,
    requests_report,
)
from gerclaw_api.modules.agent_harness.planning.preflight import (
    ModelBudgetPreflight,
    approximate_input_tokens,
)
from gerclaw_api.modules.agent_harness.routing import (
    DeterministicRouter,
    RouteDecision,
    Router,
    RoutingInput,
    RoutingPolicy,
)
from gerclaw_api.modules.runtime.budget import ExecutionUsage
from gerclaw_api.modules.runtime.models import ExecutionBudget


class PreparedTurnPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route_decision: RouteDecision
    dynamic_plan: DynamicPlan


class TurnPlanningCoordinator:
    """Keep planning mechanics out of the production composition facade."""

    def __init__(
        self,
        *,
        router: Router,
        planner: Planner,
        preflight: ModelBudgetPreflight,
        output_reserve_tokens: int,
        input_overhead_tokens: int,
        image_input_estimate_tokens: int,
        route_decision: RouteDecision | None,
        dynamic_plan: DynamicPlan | None,
    ) -> None:
        self._router = router
        self._planner = planner
        self._preflight = preflight
        self._output_reserve_tokens = output_reserve_tokens
        self._input_overhead_tokens = input_overhead_tokens
        self._image_input_estimate_tokens = image_input_estimate_tokens
        self._route_decision = route_decision
        self._dynamic_plan = dynamic_plan

    @classmethod
    def from_config(
        cls,
        *,
        config: ResolvedHarnessConfig,
        execution_budget: ExecutionBudget,
        model_context_tokens: int,
        router: Router | None = None,
        planner: Planner | None = None,
        route_decision: RouteDecision | None = None,
        dynamic_plan: DynamicPlan | None = None,
    ) -> TurnPlanningCoordinator:
        return cls(
            router=router
            or DeterministicRouter(
                RoutingPolicy(
                    quick_max_characters=config.quick_route_max_characters,
                    deep_min_characters=config.deep_route_min_characters,
                    deep_attachment_count=config.deep_route_attachment_count,
                    deep_capability_count=config.deep_route_capability_count,
                )
            ),
            planner=planner
            or DeterministicPlanner(
                execution_budget=execution_budget,
                output_reserve_tokens=config.model_output_reserve_tokens,
            ),
            preflight=ModelBudgetPreflight(
                execution_budget=execution_budget,
                model_context_tokens=model_context_tokens,
                context_trigger_ratio=config.context_trigger_ratio,
                context_hard_stop_ratio=config.context_hard_stop_ratio,
                context_reserve_ratio=config.context_reserve_ratio,
            ),
            output_reserve_tokens=config.model_output_reserve_tokens,
            input_overhead_tokens=config.model_input_overhead_tokens,
            image_input_estimate_tokens=config.image_input_estimate_tokens,
            route_decision=route_decision,
            dynamic_plan=dynamic_plan,
        )

    def prepare(
        self,
        *,
        message: str,
        medical_content: bool,
        image_count: int,
        document_count: int,
        capabilities: tuple[str, ...],
        high_risk_detected: bool,
        selected_action: Literal["ask", "exam", "answer"] = "answer",
    ) -> PreparedTurnPlan:
        route = self._route_decision or self._router.decide(
            RoutingInput(
                message=message,
                has_images=image_count > 0,
                has_documents=document_count > 0,
                image_count=image_count,
                document_count=document_count,
                selected_capabilities=capabilities,
                medical_content=medical_content,
                high_risk_detected=high_risk_detected,
            )
        )
        plan = self._dynamic_plan or self._planner.build(
            PlanRequest(
                route=route.route,
                medical_content=medical_content,
                image_count=image_count,
                document_count=document_count,
                selected_capabilities=capabilities,
                available_capabilities=capabilities,
                report_requested=requests_report(message),
                selected_action=selected_action,
            )
        )
        if plan.route is not route.route:
            raise PlanningError("PLAN_ROUTE_MISMATCH")
        return PreparedTurnPlan(route_decision=route, dynamic_plan=plan)

    def check_model(
        self,
        *,
        usage: ExecutionUsage,
        text_values: tuple[str, ...],
        image_count: int,
        estimated_input_tokens: int | None = None,
    ) -> BudgetPreflightDecision:
        if estimated_input_tokens is None:
            estimated_input_tokens = (
                self._input_overhead_tokens
                + image_count * self._image_input_estimate_tokens
                + approximate_input_tokens(text_values)
            )
        else:
            estimated_input_tokens += approximate_input_tokens(text_values)
        return self._preflight.check(
            usage,
            ModelCallEstimate(
                estimated_input_tokens=estimated_input_tokens,
                output_reserve_tokens=self._output_reserve_tokens,
            ),
        )

    def check_tool(
        self,
        *,
        usage: ExecutionUsage,
        text_values: tuple[str, ...],
        image_count: int,
        result_reserve_tokens: int,
        estimated_input_tokens: int | None = None,
    ) -> BudgetPreflightDecision:
        """Reserve one tool result and the model call needed to consume it.

        The current tool proposal is already charged by the AgentScope stream
        before Runtime grants its one-shot execution permit.
        """

        if estimated_input_tokens is None:
            estimated_input_tokens = (
                self._input_overhead_tokens
                + image_count * self._image_input_estimate_tokens
                + approximate_input_tokens(text_values)
            )
        else:
            estimated_input_tokens += approximate_input_tokens(text_values)
        estimated_input_tokens += result_reserve_tokens
        return self._preflight.check(
            usage,
            ModelCallEstimate(
                estimated_input_tokens=estimated_input_tokens,
                output_reserve_tokens=self._output_reserve_tokens,
                additional_model_calls=1,
                additional_tool_calls=0,
            ),
        )
