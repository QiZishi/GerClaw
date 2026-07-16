"""Deterministic runner for policy-level golden cases without model calls."""

from __future__ import annotations

from gerclaw_api.modules.agent_harness.safety import (
    HIGH_RISK_NOTICE,
    MEDICAL_DISCLAIMER,
    detect_high_risk,
    safety_decision,
    sanitize_medical_text,
)
from gerclaw_api.modules.contracts import AgentResponse
from gerclaw_api.modules.evals.golden_cases import (
    OUTPUT_SAFETY_GOLDEN_CASES,
    SAFETY_GOLDEN_CASES,
)
from gerclaw_api.modules.evals.models import (
    EvalCase,
    EvalCaseResult,
    OutputSafetyEvalCase,
    OutputSafetyEvalCaseResult,
)


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


def run_output_safety_case(case: OutputSafetyEvalCase) -> OutputSafetyEvalCaseResult:
    """Evaluate a reviewed synthetic public-output safety transformation."""

    return OutputSafetyEvalCaseResult(
        case_id=case.case_id,
        passed=sanitize_medical_text(case.synthetic_output) == case.expected_public_output,
        policy_version=case.policy_version,
    )


def run_output_safety_golden_cases() -> tuple[OutputSafetyEvalCaseResult, ...]:
    """Run output-policy cases without persisting or echoing synthetic text."""

    results = tuple(run_output_safety_case(case) for case in OUTPUT_SAFETY_GOLDEN_CASES)
    if not all(result.passed for result in results):
        failed = ", ".join(result.case_id for result in results if not result.passed)
        raise AssertionError(f"output safety golden cases failed: {failed}")
    return results
