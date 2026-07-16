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
CHAT_TURNS = Counter(
    "gerclaw_chat_turns_total",
    "Agent Harness turns by bounded terminal outcome",
    ("outcome",),
)
CHAT_TURN_LATENCY = Histogram(
    "gerclaw_chat_turn_duration_seconds",
    "End-to-end Agent Harness turn latency",
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)
AGENT_MODEL_ATTEMPTS = Counter(
    "gerclaw_agent_model_attempts_total",
    "Real agent model attempts by configured slot and bounded outcome",
    ("preference", "outcome"),
)
SEARCH_EXECUTIONS = Counter(
    "gerclaw_search_executions_total",
    "Online evidence searches by bounded terminal outcome",
    ("outcome",),
)
SEARCH_LATENCY = Histogram(
    "gerclaw_search_duration_seconds",
    "End-to-end online evidence search latency including fallback",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 15, 30),
)
SEARCH_PROVIDER_REQUESTS = Counter(
    "gerclaw_search_provider_requests_total",
    "Online search provider requests by bounded outcome",
    ("provider", "operation", "outcome"),
)
SEARCH_PROVIDER_LATENCY = Histogram(
    "gerclaw_search_provider_request_duration_seconds",
    "Online search provider request latency",
    ("provider", "operation"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
VOICE_PROVIDER_REQUESTS = Counter(
    "gerclaw_voice_provider_requests_total",
    "Voice provider requests by operation and bounded outcome",
    ("operation", "outcome"),
)
VOICE_PROVIDER_LATENCY = Histogram(
    "gerclaw_voice_provider_request_duration_seconds",
    "Voice provider request latency without audio, transcript, or text labels",
    ("operation",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
RISK_ALERTS = Counter(
    "gerclaw_risk_alerts_total",
    "Deterministic safety-alert lifecycle events without patient identifiers or content",
    ("source", "severity", "outcome"),
)


def render_metrics() -> tuple[bytes, str]:
    """Render the Prometheus text exposition payload and media type."""

    return generate_latest(), CONTENT_TYPE_LATEST
