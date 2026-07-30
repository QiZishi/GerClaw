"""Dynamic planning, SAVI selection, and pre-model budget tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.agent_harness.clinical_state import (
    ClinicalFact,
    ClinicalState,
    DifferentialCandidate,
    DifferentialPriority,
    FactProvenance,
)
from gerclaw_api.modules.agent_harness.planning import (
    ActionCandidate,
    ActionKind,
    ClinicalDecisionCoordinator,
    DeterministicPlanner,
    DynamicPlan,
    DynamicPlanExecutor,
    ModelBudgetPreflight,
    ModelCallEstimate,
    PlanExecutionSnapshot,
    PlanningError,
    PlanNode,
    PlanNodeStatus,
    PlanRequest,
    SAVIActionSelector,
    validate_plan_execution_transition,
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


def _reported_state(*, unknowns: tuple[str, ...] = ()) -> ClinicalState:
    return ClinicalState(
        facts=(
            ClinicalFact(
                fact_id="fact_dizziness",
                category="chief_complaint",
                value="老人最近头晕",
                status="reported",
                provenance=(
                    FactProvenance(
                        source_type="user",
                        source_id="message-1",
                        observed_at=datetime(2026, 7, 29, tzinfo=UTC),
                    ),
                ),
            ),
        ),
        unknowns=unknowns,
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
    )
    assert deep.nodes[2].required is False
    assert all(node.checkpoint for node in deep.nodes)


def test_treatment_unknown_forces_ask_and_builds_clarification_only_plan() -> None:
    decision = ClinicalDecisionCoordinator(minimum_score=1).prepare(
        state=_reported_state(),
        message="这些药需要怎么调整剂量?",
        has_attachments=False,
    )

    assert decision.action_selection.selected is not None
    assert decision.action_selection.selected.candidate.kind is ActionKind.ASK
    assert decision.action_selection.reason_code == "mandatory_prerequisite"
    assert decision.clarification_questions == (
        "年龄",
        "药物过敏史(包括明确无药物过敏)",
        "完整当前用药名称、剂量和频次",
        "重要基础病以及近期肝肾功能情况",
    )

    plan = _planner().build(
        PlanRequest(
            route=RouteKind.STANDARD,
            medical_content=True,
            selected_action="ask",
        )
    )
    assert [node.capability for node in plan.nodes] == ["clinical.ask"]
    assert plan.nodes[0].budget.model_calls == 0
    assert plan.nodes[0].budget.tool_calls == 0


def test_diagnostic_direction_is_source_linked_and_never_a_diagnosis() -> None:
    decision = ClinicalDecisionCoordinator(minimum_score=1).prepare(
        state=_reported_state(),
        message="老人最近头晕可能是什么原因?",
        has_attachments=False,
    )

    candidate = decision.differential_assessment.candidates[0]
    assert candidate.supporting_fact_ids == ("fact_dizziness",)
    assert candidate.missing_information
    assert decision.differential_assessment.is_diagnosis is False

    with pytest.raises(ValidationError, match="cannot assert a diagnosis"):
        DifferentialCandidate(
            candidate_id="unsafe",
            label="老人就是脑梗方向",
            priority=DifferentialPriority.CONSIDER,
            supporting_fact_ids=("fact_dizziness",),
        )


def test_dynamic_plan_executor_enforces_dependencies_and_skips_optional_nodes() -> None:
    plan = _planner().build(
        PlanRequest(
            route=RouteKind.DEEP,
            medical_content=True,
            selected_capabilities=("gerclaw.cga",),
            available_capabilities=("gerclaw.cga",),
        )
    )
    executor = DynamicPlanExecutor(plan)

    with pytest.raises(PlanningError, match="PLAN_DEPENDENCY_INCOMPLETE"):
        executor.start_capability("answer.compose")

    evidence_node = executor.start_capability("evidence.retrieve")
    executor.complete(evidence_node)
    answer_node = executor.start_capability("answer.compose")
    executor.complete(answer_node)
    snapshot = executor.finalize()

    assert snapshot.statuses["retrieve_evidence"] is PlanNodeStatus.COMPLETED
    assert snapshot.statuses["capability_1"] is PlanNodeStatus.SKIPPED
    assert snapshot.statuses["answer"] is PlanNodeStatus.COMPLETED


def test_dynamic_plan_executor_completes_only_observed_optional_capability() -> None:
    plan = _planner().build(
        PlanRequest(
            route=RouteKind.DEEP,
            selected_capabilities=("risk-assessment",),
            available_capabilities=("risk-assessment",),
        )
    )
    executor = DynamicPlanExecutor(plan)

    assert executor.complete_optional_capability("unknown-skill") is False
    assert executor.complete_optional_capability("risk-assessment") is True
    assert executor.complete_optional_capability("risk-assessment") is False
    answer_node = executor.start_capability("answer.compose")
    executor.complete(answer_node)

    assert executor.finalize().statuses["capability_1"] is PlanNodeStatus.COMPLETED


def test_dynamic_plan_executor_retries_failed_node_from_serialized_checkpoint() -> None:
    plan = _planner().build(PlanRequest(route=RouteKind.QUICK))
    executor = DynamicPlanExecutor(plan)

    node_id = executor.start_capability("answer.quick")
    executor.fail(node_id, "MODEL_OUTPUT_SCHEMA_INVALID")
    failed = PlanExecutionSnapshot.model_validate(
        executor.snapshot().model_dump(mode="json")
    )

    restored = DynamicPlanExecutor(plan, snapshot=failed)
    assert restored.start_capability("answer.quick") == node_id
    restored.complete(node_id)
    completed = restored.finalize()

    assert completed.statuses[node_id] is PlanNodeStatus.COMPLETED
    assert completed.attempts[node_id] == 2
    assert node_id not in completed.error_codes


def test_dynamic_plan_executor_completes_required_node_through_declared_fallback() -> None:
    plan = DynamicPlan(
        route=RouteKind.STANDARD,
        nodes=(
            PlanNode(
                node_id="primary",
                capability="evidence.retrieve",
                public_summary="正在检索医学证据",
                fallback=("local_fallback",),
                checkpoint=True,
            ),
            PlanNode(
                node_id="local_fallback",
                required=False,
                capability="answer.compose",
                public_summary="正在使用已有资料整理回答",
                checkpoint=True,
            ),
        ),
    )
    executor = DynamicPlanExecutor(plan)

    primary = executor.start_capability("evidence.retrieve")
    assert executor.fail(primary, "EVIDENCE_PROVIDER_UNAVAILABLE") == (
        "local_fallback",
    )
    fallback = executor.start_fallback(primary)
    executor.complete(fallback)
    snapshot = executor.finalize()

    assert snapshot.statuses["primary"] is PlanNodeStatus.FAILED
    assert snapshot.statuses["local_fallback"] is PlanNodeStatus.COMPLETED
    assert snapshot.fallbacks_used == {"primary": ("local_fallback",)}


def test_dynamic_plan_rejects_fallback_cycle_and_snapshot_identity_drift() -> None:
    with pytest.raises(ValidationError, match="acyclic"):
        DynamicPlan(
            nodes=(
                PlanNode(
                    node_id="first",
                    capability="first.run",
                    public_summary="正在执行第一步",
                    fallback=("second",),
                ),
                PlanNode(
                    node_id="second",
                    capability="second.run",
                    public_summary="正在执行第二步",
                    fallback=("first",),
                ),
            )
        )

    plan = _planner().build(PlanRequest(route=RouteKind.QUICK))
    other_plan = DynamicPlan(
        route=RouteKind.QUICK,
        nodes=(
            PlanNode(
                node_id="other",
                capability="answer.quick",
                public_summary="正在整理回答",
            ),
        ),
    )
    with pytest.raises(PlanningError, match="PLAN_EXECUTION_SNAPSHOT_MISMATCH"):
        DynamicPlanExecutor(
            plan,
            snapshot=PlanExecutionSnapshot.initial(other_plan),
        )


def test_plan_execution_transition_accepts_one_node_and_rejects_snapshot_drift() -> None:
    plan = _planner().build(PlanRequest(route=RouteKind.QUICK))
    executor = DynamicPlanExecutor(plan)
    initial = executor.snapshot()
    executor.start_capability("answer.quick")
    running = executor.snapshot()

    transition = validate_plan_execution_transition(plan, initial, running)
    assert len(transition) == 1
    assert transition[0].node_id == "quick_answer"
    assert transition[0].previous_status is PlanNodeStatus.PENDING
    assert transition[0].status is PlanNodeStatus.RUNNING
    assert transition[0].attempt == 1

    drifted = running.model_copy(update={"attempts": {"quick_answer": 2}})
    with pytest.raises(PlanningError, match="TRANSITION_INVALID"):
        validate_plan_execution_transition(plan, initial, drifted)


def test_plan_execution_snapshot_binds_full_plan_identity() -> None:
    original = DynamicPlan(
        route=RouteKind.QUICK,
        nodes=(
            PlanNode(
                node_id="answer",
                capability="answer.quick",
                public_summary="正在整理简短回答",
            ),
        ),
    )
    executor = DynamicPlanExecutor(original)
    node_id = executor.start_capability("answer.quick")
    executor.complete(node_id)
    completed = executor.finalize()
    changed_capability = DynamicPlan(
        route=RouteKind.QUICK,
        nodes=(
            PlanNode(
                node_id="answer",
                capability="clinical.required.action",
                public_summary="正在执行临床必要动作",
            ),
        ),
    )

    with pytest.raises(PlanningError, match="PLAN_EXECUTION_SNAPSHOT_MISMATCH"):
        DynamicPlanExecutor(changed_capability, snapshot=completed)


def test_plan_execution_uses_next_fallback_after_previous_fallback_fails() -> None:
    plan = DynamicPlan(
        nodes=(
            PlanNode(
                node_id="primary",
                capability="primary.run",
                public_summary="正在执行主要路径",
                fallback=("fallback_one", "fallback_two"),
            ),
            PlanNode(
                node_id="fallback_one",
                required=False,
                capability="fallback.one",
                public_summary="正在执行第一备用路径",
            ),
            PlanNode(
                node_id="fallback_two",
                required=False,
                capability="fallback.two",
                public_summary="正在执行第二备用路径",
            ),
        )
    )
    executor = DynamicPlanExecutor(plan)
    primary = executor.start_capability("primary.run")
    executor.fail(primary, "PRIMARY_UNAVAILABLE")
    first = executor.start_fallback(primary)
    assert first == "fallback_one"
    executor.fail(first, "FIRST_FALLBACK_UNAVAILABLE")

    assert executor.failover_candidates(primary) == ("fallback_two",)
    second = executor.start_fallback(primary)
    executor.complete(second)
    snapshot = executor.finalize()
    assert snapshot.fallbacks_used["primary"] == (
        "fallback_one",
        "fallback_two",
    )


def test_plan_execution_serializes_fallbacks_and_preserves_recovery_on_finalize() -> None:
    plan = DynamicPlan(
        nodes=(
            PlanNode(
                node_id="primary",
                capability="primary.run",
                public_summary="正在执行主要路径",
                fallback=("fallback_one", "fallback_two"),
            ),
            PlanNode(
                node_id="fallback_one",
                required=False,
                capability="fallback.one",
                public_summary="正在执行第一备用路径",
            ),
            PlanNode(
                node_id="fallback_two",
                required=False,
                capability="fallback.two",
                public_summary="正在执行第二备用路径",
            ),
        )
    )
    executor = DynamicPlanExecutor(plan)
    primary = executor.start_capability("primary.run")
    executor.fail(primary, "PRIMARY_UNAVAILABLE")
    before_finalize = executor.snapshot()

    with pytest.raises(PlanningError, match="PLAN_REQUIRED_NODE_INCOMPLETE"):
        executor.finalize()
    assert executor.snapshot() == before_finalize

    first = executor.start_fallback(primary)
    assert executor.failover_candidates(primary) == ()
    with pytest.raises(PlanningError, match="PLAN_FALLBACK_UNAVAILABLE"):
        executor.start_fallback(primary)
    executor.complete(first)
    assert executor.failover_candidates(primary) == ()
    with pytest.raises(PlanningError, match="PLAN_FALLBACK_UNAVAILABLE"):
        executor.start_fallback(primary)
    with pytest.raises(PlanningError, match="PLAN_CAPABILITY_NOT_PENDING"):
        executor.start_capability("primary.run")


def test_plan_transition_rejects_fallback_checkpoint_bypass_and_nonserial_history() -> None:
    plan = DynamicPlan(
        nodes=(
            PlanNode(
                node_id="primary",
                capability="primary.run",
                public_summary="正在执行主要路径",
                fallback=("fallback_one", "fallback_two"),
            ),
            PlanNode(
                node_id="fallback_one",
                required=False,
                capability="fallback.one",
                public_summary="正在执行第一备用路径",
            ),
            PlanNode(
                node_id="fallback_two",
                required=False,
                capability="fallback.two",
                public_summary="正在执行第二备用路径",
            ),
        )
    )
    executor = DynamicPlanExecutor(plan)
    primary = executor.start_capability("primary.run")
    executor.fail(primary, "PRIMARY_UNAVAILABLE")
    failed_primary = executor.snapshot()
    bypassed = failed_primary.model_copy(
        update={
            "statuses": {
                **failed_primary.statuses,
                "fallback_one": PlanNodeStatus.COMPLETED,
            },
            "attempts": {
                **failed_primary.attempts,
                "fallback_one": 1,
            },
            "fallbacks_used": {"primary": ("fallback_one",)},
        }
    )

    with pytest.raises(PlanningError, match="PLAN_EXECUTION_FALLBACK_MISMATCH"):
        validate_plan_execution_transition(plan, failed_primary, bypassed)

    for nonserial_status in (
        PlanNodeStatus.RUNNING,
        PlanNodeStatus.COMPLETED,
    ):
        nonserial = PlanExecutionSnapshot(
            plan_fingerprint=failed_primary.plan_fingerprint,
            statuses={
                "primary": PlanNodeStatus.FAILED,
                "fallback_one": nonserial_status,
                "fallback_two": PlanNodeStatus.FAILED,
            },
            attempts={
                "primary": 1,
                "fallback_one": 1,
                "fallback_two": 1,
            },
            error_codes={
                "primary": "PRIMARY_UNAVAILABLE",
                "fallback_two": "SECOND_FALLBACK_UNAVAILABLE",
            },
            fallbacks_used={"primary": ("fallback_one", "fallback_two")},
        )
        with pytest.raises(PlanningError, match="PLAN_EXECUTION_FALLBACK_MISMATCH"):
            DynamicPlanExecutor(plan, snapshot=nonserial)


def test_plan_execution_attempt_limit_stops_before_running_and_failed_needs_error() -> None:
    plan = _planner().build(PlanRequest(route=RouteKind.QUICK))
    initial = PlanExecutionSnapshot.initial(plan)
    exhausted = initial.model_copy(
        update={
            "statuses": {"quick_answer": PlanNodeStatus.FAILED},
            "attempts": {"quick_answer": 50},
            "error_codes": {"quick_answer": "MODEL_RETRY_EXHAUSTED"},
        }
    )
    executor = DynamicPlanExecutor(plan, snapshot=exhausted)

    with pytest.raises(PlanningError, match="PLAN_NODE_ATTEMPT_BUDGET_EXCEEDED"):
        executor.start_capability("answer.quick")
    assert executor.snapshot() == exhausted

    with pytest.raises(ValidationError, match="requires exactly one error code"):
        PlanExecutionSnapshot(
            plan_fingerprint=initial.plan_fingerprint,
            statuses={"quick_answer": PlanNodeStatus.FAILED},
            attempts={"quick_answer": 1},
        )


def test_plan_transition_rejects_dependency_and_required_checkpoint_bypasses() -> None:
    plan = DynamicPlan(
        nodes=(
            PlanNode(
                node_id="prerequisite",
                capability="evidence.retrieve",
                public_summary="正在准备前置信息",
            ),
            PlanNode(
                node_id="required_action",
                dependencies=("prerequisite",),
                capability="answer.compose",
                public_summary="正在执行必要步骤",
            ),
        )
    )
    initial = PlanExecutionSnapshot.initial(plan)
    for illegal_status in (
        PlanNodeStatus.RUNNING,
        PlanNodeStatus.COMPLETED,
        PlanNodeStatus.SKIPPED,
    ):
        illegal = initial.model_copy(
            update={
                "statuses": {
                    **initial.statuses,
                    "required_action": illegal_status,
                },
                "attempts": {
                    **initial.attempts,
                    "required_action": (
                        0 if illegal_status is PlanNodeStatus.SKIPPED else 1
                    ),
                },
            }
        )
        with pytest.raises(PlanningError):
            validate_plan_execution_transition(plan, initial, illegal)


def test_plan_transition_expands_atomic_optional_skips_and_checks_fallback_prefix() -> None:
    plan = DynamicPlan(
        nodes=(
            PlanNode(
                node_id="primary",
                capability="primary.run",
                public_summary="正在执行主要步骤",
                fallback=("fallback_one", "fallback_two"),
            ),
            PlanNode(
                node_id="fallback_one",
                required=False,
                capability="fallback.one",
                public_summary="正在执行第一备用步骤",
            ),
            PlanNode(
                node_id="fallback_two",
                required=False,
                capability="fallback.two",
                public_summary="正在执行第二备用步骤",
            ),
        )
    )
    executor = DynamicPlanExecutor(plan)
    primary = executor.start_capability("primary.run")
    executor.complete(primary)
    before_finalize = executor.snapshot()
    finalized = executor.finalize()

    transitions = validate_plan_execution_transition(
        plan,
        before_finalize,
        finalized,
    )
    assert [(item.node_id, item.status) for item in transitions] == [
        ("fallback_one", PlanNodeStatus.SKIPPED),
        ("fallback_two", PlanNodeStatus.SKIPPED),
    ]

    initial = PlanExecutionSnapshot.initial(plan)
    out_of_order_history = PlanExecutionSnapshot(
        plan_fingerprint=initial.plan_fingerprint,
        statuses={
            "primary": PlanNodeStatus.FAILED,
            "fallback_one": PlanNodeStatus.PENDING,
            "fallback_two": PlanNodeStatus.COMPLETED,
        },
        attempts={
            "primary": 1,
            "fallback_one": 0,
            "fallback_two": 1,
        },
        error_codes={"primary": "PRIMARY_UNAVAILABLE"},
        fallbacks_used={"primary": ("fallback_two",)},
    )
    with pytest.raises(PlanningError, match="PLAN_EXECUTION_FALLBACK_MISMATCH"):
        DynamicPlanExecutor(plan, snapshot=out_of_order_history)


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
