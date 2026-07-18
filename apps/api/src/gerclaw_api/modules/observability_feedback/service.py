"""Deterministic aggregation for the administrator operational queue."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from gerclaw_api.modules.observability_feedback.models import (
    BadCaseAggregate,
    BadCaseSummary,
    BadCaseTrend,
    BadCaseTrendAggregate,
    BadCaseTrendPoint,
)


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


def summarize_bad_case_trend(
    aggregates: Iterable[BadCaseTrendAggregate], *, end_day: date
) -> BadCaseTrend:
    days = [end_day - timedelta(days=offset) for offset in range(6, -1, -1)]
    totals = {
        day: {
            "total": 0,
            "execution_failure_count": 0,
            "negative_feedback_count": 0,
        }
        for day in days
    }
    for aggregate in aggregates:
        values = totals.get(aggregate.day)
        if values is not None:
            values["total"] += aggregate.count
            values[f"{aggregate.source}_count"] += aggregate.count
    return BadCaseTrend(points=[BadCaseTrendPoint(day=day, **totals[day]) for day in days])
