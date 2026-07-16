"""Regression tests for the synthetic deterministic Eval Harness baseline."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.evals.models import EvalCase, OutputSafetyEvalCase
from gerclaw_api.modules.evals.runner import (
    run_case,
    run_golden_cases,
    run_output_safety_case,
    run_output_safety_golden_cases,
)


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
