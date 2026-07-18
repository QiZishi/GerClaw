"""Deterministic aggregation for the administrator operational queue."""

from __future__ import annotations

from collections.abc import Iterable

from gerclaw_api.modules.observability_feedback.models import BadCaseAggregate, BadCaseSummary


def summarize_bad_cases(aggregates: Iterable[BadCaseAggregate]) -> BadCaseSummary:
    """Summarize pre-aggregated metadata without loading protected snapshots.

    The database query supplies only source, severity, status and a count.  This
    function deliberately has no access to trace input, feedback text, files,
    images, encrypted snapshots, or user identifiers, so the admin dashboard
    can prioritize queue work without becoming a patient-record viewer.
    """

    totals = {
        "total": 0,
        "open_count": 0,
        "triaged_count": 0,
        "resolved_count": 0,
        "dismissed_count": 0,
        "execution_failure_count": 0,
        "negative_feedback_count": 0,
        "high_priority_count": 0,
    }
    for aggregate in aggregates:
        count = aggregate.count
        totals["total"] += count
        totals[f"{aggregate.status}_count"] += count
        totals[f"{aggregate.source}_count"] += count
        if aggregate.severity in {"high", "critical"}:
            totals["high_priority_count"] += count
    return BadCaseSummary(**totals)
