"""Deterministic dynamic DAG construction from validated route facts."""

from __future__ import annotations

import re

from gerclaw_api.modules.agent_harness.planning.contracts import (
    DynamicPlan,
    PlanningError,
    PlanNode,
    PlanNodeBudget,
    PlanRequest,
)
from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.modules.runtime.models import ExecutionBudget

_BUILTIN_CAPABILITIES = frozenset(
    {
        "answer.compose",
        "answer.quick",
        "attachment.inspect",
        "evidence.retrieve",
        "report.compose",
        "safety.emergency",
    }
)
_REPORT_REQUEST = re.compile(r"(?:生成|形成|撰写|整理).{0,12}(?:报告|文档)")


def requests_report(message: str) -> bool:
    return _REPORT_REQUEST.search(message) is not None


class DeterministicPlanner:
    """Build only nodes that correspond to the route and available capabilities."""

    def __init__(
        self,
        *,
        execution_budget: ExecutionBudget,
        output_reserve_tokens: int,
    ) -> None:
        self._execution_budget = execution_budget
        self._output_reserve_tokens = output_reserve_tokens

    def build(self, request: PlanRequest) -> DynamicPlan:
        available = _BUILTIN_CAPABILITIES | set(request.available_capabilities)
        missing = set(request.selected_capabilities) - available
        if missing:
            raise PlanningError(f"PLAN_CAPABILITY_UNAVAILABLE:{','.join(sorted(missing))}")

        if request.route is RouteKind.EMERGENCY:
            return DynamicPlan(
                route=request.route,
                nodes=(
                    PlanNode(
                        node_id="emergency_notice",
                        capability="safety.emergency",
                        public_summary="正在优先处理紧急安全风险",
                        output_schema={"type": "object", "required": ["content"]},
                        checkpoint=True,
                    ),
                ),
            )

        if request.route is RouteKind.QUICK:
            return DynamicPlan(
                route=request.route,
                nodes=(
                    PlanNode(
                        node_id="quick_answer",
                        capability="answer.quick",
                        budget=PlanNodeBudget(
                            model_calls=1,
                            output_tokens=self._output_reserve_tokens,
                        ),
                        public_summary="正在整理简短回答",
                        output_schema={"type": "object", "required": ["text"]},
                        checkpoint=True,
                    ),
                ),
            )

        nodes: list[PlanNode] = []
        prerequisites: list[str] = []
        if request.document_count or request.image_count:
            nodes.append(
                PlanNode(
                    node_id="inspect_attachments",
                    capability="attachment.inspect",
                    budget=PlanNodeBudget(tool_calls=1),
                    public_summary="正在核对上传资料",
                    output_schema={"type": "object", "required": ["observations"]},
                    checkpoint=True,
                )
            )
            prerequisites.append("inspect_attachments")
        if request.medical_content:
            nodes.append(
                PlanNode(
                    node_id="retrieve_evidence",
                    capability="evidence.retrieve",
                    budget=PlanNodeBudget(tool_calls=1),
                    public_summary="正在检索医学证据",
                    output_schema={"type": "array", "items": {"type": "object"}},
                    checkpoint=True,
                )
            )
            prerequisites.append("retrieve_evidence")

        for position, capability in enumerate(request.selected_capabilities, start=1):
            node_id = f"capability_{position}"
            nodes.append(
                PlanNode(
                    node_id=node_id,
                    dependencies=tuple(prerequisites),
                    capability=capability,
                    budget=PlanNodeBudget(tool_calls=1),
                    public_summary="正在执行已选择的专业能力",
                    output_schema={"type": "object"},
                    checkpoint=True,
                )
            )
            prerequisites.append(node_id)

        answer_capability = (
            "report.compose"
            if request.route is RouteKind.DEEP and request.report_requested
            else "answer.compose"
        )
        nodes.append(
            PlanNode(
                node_id="compose_report" if answer_capability == "report.compose" else "answer",
                dependencies=tuple(prerequisites),
                capability=answer_capability,
                budget=PlanNodeBudget(
                    model_calls=1,
                    output_tokens=self._output_reserve_tokens,
                ),
                public_summary=(
                    "正在生成可编辑报告"
                    if answer_capability == "report.compose"
                    else "正在整理回答"
                ),
                output_schema={"type": "object", "required": ["text"]},
                checkpoint=True,
            )
        )
        self._validate_aggregate_budget(nodes)
        return DynamicPlan(route=request.route, nodes=tuple(nodes))

    def _validate_aggregate_budget(self, nodes: list[PlanNode]) -> None:
        model_calls = sum(node.budget.model_calls for node in nodes)
        tool_calls = sum(node.budget.tool_calls for node in nodes)
        output_tokens = sum(node.budget.output_tokens for node in nodes)
        if model_calls > self._execution_budget.max_model_calls:
            raise PlanningError("PLAN_MODEL_CALL_BUDGET_EXCEEDED")
        if tool_calls > self._execution_budget.max_tool_calls:
            raise PlanningError("PLAN_TOOL_CALL_BUDGET_EXCEEDED")
        if output_tokens > self._execution_budget.max_output_tokens:
            raise PlanningError("PLAN_OUTPUT_TOKEN_BUDGET_EXCEEDED")
