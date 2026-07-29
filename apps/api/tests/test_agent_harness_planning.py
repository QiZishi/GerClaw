"""Dynamic planning, SAVI selection, and pre-model budget tests."""

from __future__ import annotations

import pytest

from gerclaw_api.modules.agent_harness.planning import (
    ActionCandidate,
    ActionKind,
    DeterministicPlanner,
    ModelBudgetPreflight,
    ModelCallEstimate,
    PlanningError,
    PlanRequest,
    SAVIActionSelector,
)
from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.modules.runtime.budget import RuntimeBudgetTracker
from gerclaw_api.modules.runtime.models import ExecutionBudget


def _planner(**budget_updates: int) -> DeterministicPlanner:
    budget = ExecutionBudget().model_copy(update=budget_updates)
    return DeterministicPlanner(
        execution_budget=budget,
        output_reserve_tokens=2_048,
    )


def test_dynamic_plan_changes_with_route_attachments_and_capabilities() -> None:
    planner = _planner()

    quick = planner.build(PlanRequest(route=RouteKind.QUICK))
    emergency = planner.build(PlanRequest(route=RouteKind.EMERGENCY))
    deep = planner.build(
        PlanRequest(
            route=RouteKind.DEEP,
            medical_content=True,
            document_count=2,
            selected_capabilities=("gerclaw.cga",),
            available_capabilities=("gerclaw.cga",),
            report_requested=True,
        )
    )

    assert [node.capability for node in quick.nodes] == ["answer.quick"]
    assert quick.nodes[0].budget.tool_calls == 0
    assert [node.capability for node in emergency.nodes] == ["safety.emergency"]
    assert emergency.nodes[0].budget.model_calls == 0
    assert [node.node_id for node in deep.nodes] == [
        "inspect_attachments",
        "retrieve_evidence",
        "capability_1",
        "compose_report",
    ]
    assert deep.nodes[-1].dependencies == (
        "inspect_attachments",
        "retrieve_evidence",
        "capability_1",
    )
    assert all(node.checkpoint for node in deep.nodes)


def test_dynamic_plan_rejects_unavailable_capability_and_aggregate_budget() -> None:
    with pytest.raises(PlanningError, match="PLAN_CAPABILITY_UNAVAILABLE"):
        _planner().build(
            PlanRequest(
                route=RouteKind.DEEP,
                selected_capabilities=("gerclaw.unknown",),
            )
        )
    with pytest.raises(PlanningError, match="PLAN_TOOL_CALL_BUDGET_EXCEEDED"):
        _planner(max_tool_calls=1).build(
            PlanRequest(
                route=RouteKind.DEEP,
                medical_content=True,
                document_count=1,
            )
        )


def test_savi_prioritizes_safety_and_treatment_prerequisites_without_probability() -> None:
    selector = SAVIActionSelector(minimum_score=1)
    candidates = (
        ActionCandidate(
            action_id="ask_duration",
            kind=ActionKind.ASK,
            public_summary="询问症状持续时间",
            hypothesis_links=("h1", "h2"),
            diagnostic_gain=3,
            token_cost=1,
        ),
        ActionCandidate(
            action_id="ask_allergy",
            kind=ActionKind.ASK,
            public_summary="确认药物过敏史",
            treatment_prerequisite=True,
            safety_gain=1,
            token_cost=3,
        ),
        ActionCandidate(
            action_id="exam_repeat",
            kind=ActionKind.EXAM,
            public_summary="重复已有检查",
            hypothesis_links=("h1",),
            already_known=True,
            diagnostic_gain=3,
        ),
    )

    selection = selector.select(candidates)

    assert selection.selected is not None
    assert selection.selected.candidate.action_id == "ask_allergy"
    assert selection.reason_code == "mandatory_prerequisite"
    assert selection.rejected_action_ids == ("exam_repeat",)


def test_savi_prefers_ask_over_equivalent_exam_and_stops_on_low_value() -> None:
    selector = SAVIActionSelector(minimum_score=2)
    ask = ActionCandidate(
        action_id="ask_onset",
        kind=ActionKind.ASK,
        public_summary="询问起病方式",
        hypothesis_links=("h1",),
        diagnostic_gain=2,
        token_cost=1,
    )
    exam = ActionCandidate(
        action_id="exam_onset",
        kind=ActionKind.EXAM,
        public_summary="安排低价值检查",
        hypothesis_links=("h1",),
        diagnostic_gain=3,
        action_cost=1,
        invasiveness=1,
    )
    answer = ActionCandidate(
        action_id="answer_now",
        kind=ActionKind.ANSWER,
        public_summary="基于已有信息回答",
    )

    selection = selector.select((exam, ask, answer))

    assert selection.should_stop
    assert selection.selected is not None
    assert selection.selected.candidate.kind is ActionKind.ANSWER
    assert selection.reason_code == "marginal_value_below_threshold"


@pytest.mark.parametrize(
    ("estimate", "expected_reason"),
    [
        (
            ModelCallEstimate(estimated_input_tokens=79_000, output_reserve_tokens=2_000),
            "MODEL_CONTEXT_WINDOW_EXCEEDED",
        ),
        (
            ModelCallEstimate(estimated_input_tokens=200, output_reserve_tokens=9_000),
            "RUNTIME_OUTPUT_TOKENS_EXCEEDED",
        ),
    ],
)
def test_model_preflight_fails_before_next_side_effect(
    estimate: ModelCallEstimate,
    expected_reason: str,
) -> None:
    budget = ExecutionBudget()
    usage = RuntimeBudgetTracker(budget).snapshot()
    decision = ModelBudgetPreflight(
        execution_budget=budget,
        model_context_tokens=32_768,
    ).check(usage, estimate)

    assert not decision.allowed
    assert decision.reason_code == expected_reason
