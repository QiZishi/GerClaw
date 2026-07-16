"""Regression tests for the synthetic deterministic Eval Harness baseline."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.evals.models import (
    EvalCase,
    OutputSafetyEvalCase,
    RAGEvaluationRunConfig,
    RAGRetrievalEvalCase,
)
from gerclaw_api.modules.evals.runner import (
    run_case,
    run_golden_cases,
    run_opt_in_rag_retrieval_evaluation,
    run_output_safety_case,
    run_output_safety_golden_cases,
)
from gerclaw_api.modules.rag.protocols import RetrievalResult


class _RAG:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        self.calls.append((query, top_k))
        return self.results


def test_safety_golden_cases_pass_without_external_execution() -> None:
    results = run_golden_cases()

    assert len(results) == 6
    assert all(result.passed for result in results)
    assert results[0].actual_high_risk_codes == ("chest_pain", "breathing_difficulty")
    assert results[-1].actual_emergency_short_circuit is False


def test_output_safety_golden_cases_pass_without_echoing_synthetic_text() -> None:
    results = run_output_safety_golden_cases()

    assert len(results) == 3
    assert all(result.passed for result in results)
    assert not hasattr(results[0], "synthetic_output")
    assert not hasattr(results[0], "expected_public_output")


def test_eval_case_rejects_unknown_fields_and_unreviewed_provenance() -> None:
    with pytest.raises(ValidationError):
        EvalCase(
            case_id="safety.invalid_case",
            title="invalid",
            synthetic_input="synthetic",
            expected_emergency_short_circuit=False,
            provenance="raw_user_feedback",
            raw_trace_id="trace_should_not_be_stored",
        )
    with pytest.raises(ValidationError):
        OutputSafetyEvalCase(
            case_id="output-safety.invalid_case",
            title="invalid",
            synthetic_output="synthetic",
            expected_public_output="synthetic",
            provenance="raw_user_feedback",
            raw_model_output="must_not_be_stored",
        )
    with pytest.raises(ValidationError):
        RAGRetrievalEvalCase(
            case_id="rag-retrieval.invalid_case",
            title="invalid",
            synthetic_query="synthetic",
            expected_document_ids=("not-a-document-id",),
            minimum_expected_hits=1,
            index_version="corpus-v1",
            raw_user_query="must_not_be_stored",
        )


def test_eval_case_detects_a_policy_regression_without_echoing_input() -> None:
    result = run_case(
        EvalCase(
            case_id="safety.expected_but_missing",
            title="regression sentinel",
            synthetic_input="普通问候",
            expected_high_risk_codes=("chest_pain",),
            expected_emergency_short_circuit=True,
        )
    )

    assert result.passed is False
    assert not hasattr(result, "synthetic_input")


def test_output_safety_eval_detects_a_policy_regression_without_echoing_text() -> None:
    result = run_output_safety_case(
        OutputSafetyEvalCase(
            case_id="output-safety.expected_but_missing",
            title="regression sentinel",
            synthetic_output="上传资料不能直接作为确诊依据。",
            expected_public_output="不应出现的结果。",
        )
    )

    assert result.passed is False
    assert not hasattr(result, "synthetic_output")


@pytest.mark.asyncio
async def test_opt_in_rag_evaluation_is_bounded_and_never_echoes_query_or_content() -> None:
    document_id = "a" * 64
    rag = _RAG(
        [
            RetrievalResult(
                content="synthetic local evidence",
                source="reviewed/source.md",
                score=0.9,
                metadata={"document_id": document_id},
            )
        ]
    )
    case = RAGRetrievalEvalCase(
        case_id="rag-retrieval.reviewed_match",
        title="reviewed synthetic retrieval match",
        synthetic_query="synthetic retrieval query",
        expected_document_ids=(document_id,),
        minimum_expected_hits=1,
        index_version="corpus-v1",
    )

    report = await run_opt_in_rag_retrieval_evaluation(
        rag,  # type: ignore[arg-type]
        (case,),
        config=RAGEvaluationRunConfig(
            allow_external_rag=True,
            index_version="corpus-v1",
            top_k=3,
            max_cases=1,
        ),
    )

    assert report.passed_count == 1
    assert rag.calls == [("synthetic retrieval query", 3)]
    serialized = report.model_dump_json()
    assert "synthetic retrieval query" not in serialized
    assert "synthetic local evidence" not in serialized
    assert "reviewed/source.md" not in serialized


@pytest.mark.asyncio
async def test_opt_in_rag_evaluation_rejects_unapproved_budget_or_index_version() -> None:
    document_id = "b" * 64
    case = RAGRetrievalEvalCase(
        case_id="rag-retrieval.reviewed_budget",
        title="reviewed synthetic retrieval budget",
        synthetic_query="synthetic retrieval query",
        expected_document_ids=(document_id,),
        minimum_expected_hits=1,
        index_version="corpus-v1",
    )
    rag = _RAG([])
    no_match = await run_opt_in_rag_retrieval_evaluation(
        rag,  # type: ignore[arg-type]
        (case,),
        config=RAGEvaluationRunConfig(
            allow_external_rag=True,
            index_version="corpus-v1",
        ),
    )
    assert no_match.passed_count == 0
    assert no_match.results[0].matched_expected_document_count == 0
    with pytest.raises(ValueError, match="case budget"):
        await run_opt_in_rag_retrieval_evaluation(
            rag,  # type: ignore[arg-type]
            (case, case),
            config=RAGEvaluationRunConfig(
                allow_external_rag=True,
                index_version="corpus-v1",
                max_cases=1,
            ),
        )
    with pytest.raises(ValueError, match="index version"):
        await run_opt_in_rag_retrieval_evaluation(
            rag,  # type: ignore[arg-type]
            (case,),
            config=RAGEvaluationRunConfig(
                allow_external_rag=True,
                index_version="corpus-v2",
            ),
        )
