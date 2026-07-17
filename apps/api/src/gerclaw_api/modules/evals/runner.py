"""Deterministic runner for policy-level golden cases without model calls."""

from __future__ import annotations

from collections.abc import Mapping

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
from gerclaw_api.security import JsonValue

_RAG_SOURCE_TYPES = frozenset({"guideline", "consensus", "textbook", "literature"})


def _has_complete_rag_provenance(metadata: Mapping[str, JsonValue]) -> bool:
    """Accept only citation metadata that can locate a returned evidence chunk."""

    document_id = metadata.get("document_id")
    chunk_id = metadata.get("chunk_id")
    required_text_fields = ("title", "chapter", "category")
    source_type = metadata.get("source_type")
    chunk_index = metadata.get("chunk_index")
    total_chunks = metadata.get("total_chunks")
    publish_year = metadata.get("publish_year")

    if not (
        isinstance(document_id, str)
        and len(document_id) == 64
        and all(character in "0123456789abcdefABCDEF" for character in document_id)
        and isinstance(chunk_id, str)
        and bool(chunk_id.strip())
        and all(
            isinstance(value := metadata.get(field), str) and value.strip()
            for field in required_text_fields
        )
        and isinstance(source_type, str)
        and source_type in _RAG_SOURCE_TYPES
        and isinstance(chunk_index, int)
        and not isinstance(chunk_index, bool)
        and chunk_index >= 0
        and isinstance(total_chunks, int)
        and not isinstance(total_chunks, bool)
        and total_chunks >= 1
        and chunk_index < total_chunks
    ):
        return False
    return publish_year is None or (
        isinstance(publish_year, int)
        and not isinstance(publish_year, bool)
        and 1900 <= publish_year <= 2100
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
    valid_results = [
        result for result in results if _has_complete_rag_provenance(result.metadata)
    ]
    returned_document_ids = {
        str(result.metadata["document_id"]).casefold() for result in valid_results
    }
    matched = len(returned_document_ids.intersection(case.expected_document_ids))
    returned_source_types = {
        str(result.metadata["source_type"])
        for result in valid_results
        if result.metadata.get("source_type") in case.required_source_types
    }
    matched_source_types = len(returned_source_types)
    passed = (
        not results
        if case.expect_no_evidence
        else (
            len(valid_results) == len(results)
            and matched >= case.minimum_expected_hits
            and (
                not case.required_source_types
                or set(case.required_source_types).issubset(returned_source_types)
            )
        )
    )
    return RAGRetrievalEvalCaseResult(
        case_id=case.case_id,
        passed=passed,
        expected_document_count=len(case.expected_document_ids),
        expected_no_evidence=case.expect_no_evidence,
        matched_expected_document_count=matched,
        returned_result_count=len(results),
        provenance_valid_result_count=len(valid_results),
        matched_required_source_type_count=matched_source_types,
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
