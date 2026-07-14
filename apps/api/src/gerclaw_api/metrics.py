"""Low-cardinality Prometheus metrics for the API edge."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "gerclaw_http_requests_total",
    "HTTP requests handled by GerClaw",
    ("method", "route", "status"),
)
HTTP_LATENCY = Histogram(
    "gerclaw_http_request_duration_seconds",
    "GerClaw HTTP request latency",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)


def render_metrics() -> tuple[bytes, str]:
    """Render the Prometheus text exposition payload and media type."""

    return generate_latest(), CONTENT_TYPE_LATEST
