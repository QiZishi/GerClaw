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
RAG_RETRIEVALS = Counter(
    "gerclaw_rag_retrievals_total",
    "Local medical RAG retrieval executions",
    ("outcome",),
)
RAG_RETRIEVAL_LATENCY = Histogram(
    "gerclaw_rag_retrieval_duration_seconds",
    "End-to-end dense, sparse, and rerank retrieval latency",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
RAG_PROVIDER_REQUESTS = Counter(
    "gerclaw_rag_provider_requests_total",
    "RAG provider HTTP attempts by bounded outcome",
    ("operation", "outcome"),
)
RAG_PROVIDER_LATENCY = Histogram(
    "gerclaw_rag_provider_request_duration_seconds",
    "RAG provider HTTP request latency excluding local queueing",
    ("operation",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
RAG_INDEX_DOCUMENTS = Counter(
    "gerclaw_rag_index_documents_total",
    "Knowledge-base documents handled by the one-shot indexer",
    ("outcome",),
)
RAG_INDEX_CHUNKS = Counter(
    "gerclaw_rag_index_chunks_total",
    "Knowledge-base chunks written by the one-shot indexer",
)


def render_metrics() -> tuple[bytes, str]:
    """Render the Prometheus text exposition payload and media type."""

    return generate_latest(), CONTENT_TYPE_LATEST
