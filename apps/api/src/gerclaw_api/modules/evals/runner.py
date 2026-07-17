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
    PrivacyRedactionEvalCase,
    PrivacyRedactionEvalCaseResult,
    RAGEvaluationRunConfig,
    RAGEvaluationRunReport,
    RAGRetrievalEvalCase,
    RAGRetrievalEvalCaseResult,
)
from gerclaw_api.modules.evals.privacy_cases import PRIVACY_REDACTION_GOLDEN_CASES
from gerclaw_api.modules.privacy_redaction.models import EgressPurpose
from gerclaw_api.modules.privacy_redaction.policy import (
    redact_external_search_query,
    redact_external_tts_text,
)
from gerclaw_api.modules.rag.protocols import RAGModule


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


def run_privacy_redaction_case(
    case: PrivacyRedactionEvalCase,
) -> PrivacyRedactionEvalCaseResult:
    """Evaluate one synthetic privacy egress canary without exposing its text."""

    if case.purpose is EgressPurpose.EXTERNAL_SEARCH_QUERY:
        actual = redact_external_search_query(case.synthetic_input)
    else:
        actual = redact_external_tts_text(case.synthetic_input)
    return PrivacyRedactionEvalCaseResult(
        case_id=case.case_id,
        passed=(
            actual.text == case.expected_redacted_text
            and actual.findings == case.expected_findings
            and actual.policy_version == case.policy_version
        ),
        purpose=case.purpose,
        policy_version=actual.policy_version,
        expected_findings=case.expected_findings,
        actual_findings=actual.findings,
    )


def run_privacy_redaction_golden_cases() -> tuple[PrivacyRedactionEvalCaseResult, ...]:
    """Run the committed policy canaries without model, database, or provider calls."""

    results = tuple(run_privacy_redaction_case(case) for case in PRIVACY_REDACTION_GOLDEN_CASES)
    if not all(result.passed for result in results):
        failed = ", ".join(result.case_id for result in results if not result.passed)
        raise AssertionError(f"privacy redaction golden cases failed: {failed}")
    return results


async def run_rag_retrieval_case(
    module: RAGModule,
    case: RAGRetrievalEvalCase,
    *,
    top_k: int,
) -> RAGRetrievalEvalCaseResult:
    """Evaluate one reviewed synthetic case without retaining its query or results."""

    results = await module.retrieve(case.synthetic_query, top_k=top_k)
    returned_document_ids = {
        value.casefold()
        for result in results
        if isinstance((value := result.metadata.get("document_id")), str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    }
    matched = len(returned_document_ids.intersection(case.expected_document_ids))
    passed = not results if case.expect_no_evidence else matched >= case.minimum_expected_hits
    return RAGRetrievalEvalCaseResult(
        case_id=case.case_id,
        passed=passed,
        expected_document_count=len(case.expected_document_ids),
        expected_no_evidence=case.expect_no_evidence,
        matched_expected_document_count=matched,
        returned_result_count=len(results),
        index_version=case.index_version,
    )


async def run_opt_in_rag_retrieval_evaluation(
    module: RAGModule,
    cases: tuple[RAGRetrievalEvalCase, ...],
    *,
    config: RAGEvaluationRunConfig,
) -> RAGEvaluationRunReport:
    """Run a bounded external RAG evaluation only after an explicit opt-in."""

    if not config.allow_external_rag:  # pragma: no cover - enforced by Pydantic Literal
        raise ValueError("external RAG evaluation requires an explicit opt-in")
    if not cases:
        raise ValueError("external RAG evaluation requires at least one reviewed synthetic case")
    if len(cases) > config.max_cases:
        raise ValueError("external RAG evaluation exceeds the approved case budget")
    if any(case.index_version != config.index_version for case in cases):
        raise ValueError("all retrieval cases must match the approved index version")

    results: list[RAGRetrievalEvalCaseResult] = []
    for case in cases:
        results.append(await run_rag_retrieval_case(module, case, top_k=config.top_k))
    return RAGEvaluationRunReport(
        index_version=config.index_version,
        case_count=len(results),
        passed_count=sum(result.passed for result in results),
        top_k=config.top_k,
        results=tuple(results),
    )
