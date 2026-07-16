"""Deterministic runner for policy-level golden cases without model calls."""

from __future__ import annotations

from gerclaw_api.modules.agent_harness.safety import (
    HIGH_RISK_NOTICE,
    MEDICAL_DISCLAIMER,
    detect_high_risk,
    safety_decision,
)
from gerclaw_api.modules.contracts import AgentResponse
from gerclaw_api.modules.evals.golden_cases import SAFETY_GOLDEN_CASES
from gerclaw_api.modules.evals.models import EvalCase, EvalCaseResult


def run_case(case: EvalCase) -> EvalCaseResult:
    """Evaluate one synthetic safety decision and its public-output invariant."""

    actual_codes = tuple(detect_high_risk(case.synthetic_input))
    actual_emergency = bool(actual_codes)
    if actual_emergency:
        AgentResponse(
            text=f"{HIGH_RISK_NOTICE}\n\n{MEDICAL_DISCLAIMER}",
            citations=[],
            safety=safety_decision(list(actual_codes)),
            medical_content=True,
            emergency_short_circuit=True,
        )
    else:
        decision = safety_decision([])
        if "high_risk_escalation_checked" not in decision.notices:
            raise AssertionError("non-emergency safety decision lost its checked marker")

    passed = (
        actual_codes == case.expected_high_risk_codes
        and actual_emergency == case.expected_emergency_short_circuit
    )
    return EvalCaseResult(
        case_id=case.case_id,
        passed=passed,
        expected_high_risk_codes=case.expected_high_risk_codes,
        actual_high_risk_codes=actual_codes,
        expected_emergency_short_circuit=case.expected_emergency_short_circuit,
        actual_emergency_short_circuit=actual_emergency,
        policy_version=case.policy_version,
    )


def run_golden_cases() -> tuple[EvalCaseResult, ...]:
    """Run the committed, synthetic safety baseline in a deterministic order."""

    results = tuple(run_case(case) for case in SAFETY_GOLDEN_CASES)
    if not all(result.passed for result in results):
        failed = ", ".join(result.case_id for result in results if not result.passed)
        raise AssertionError(f"safety golden cases failed: {failed}")
    return results
