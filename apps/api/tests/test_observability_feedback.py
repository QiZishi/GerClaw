"""Operational Bad Case metrics must remain content-free and deterministic."""

from gerclaw_api.modules.observability_feedback import BadCaseAggregate, summarize_bad_cases


def test_bad_case_summary_counts_status_source_and_high_priority() -> None:
    summary = summarize_bad_cases(
        [
            BadCaseAggregate(
                source="execution_failure", severity="critical", status="open", count=2
            ),
            BadCaseAggregate(
                source="negative_feedback", severity="medium", status="triaged", count=3
            ),
            BadCaseAggregate(
                source="negative_feedback", severity="low", status="resolved", count=4
            ),
            BadCaseAggregate(
                source="execution_failure", severity="high", status="dismissed", count=1
            ),
        ]
    )

    assert summary.model_dump() == {
        "total": 10,
        "open_count": 2,
        "triaged_count": 3,
        "resolved_count": 4,
        "dismissed_count": 1,
        "execution_failure_count": 3,
        "negative_feedback_count": 7,
        "high_priority_count": 3,
    }


def test_bad_case_summary_is_zeroed_for_an_empty_queue() -> None:
    assert summarize_bad_cases([]).model_dump() == {
        "total": 0,
        "open_count": 0,
        "triaged_count": 0,
        "resolved_count": 0,
        "dismissed_count": 0,
        "execution_failure_count": 0,
        "negative_feedback_count": 0,
        "high_priority_count": 0,
    }
