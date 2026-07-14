"""Validated real SiliconFlow embedding and rerank providers."""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any

import httpx
from agentscope.credential import OpenAICredential
from agentscope.embedding import EmbeddingModelBase, EmbeddingResponse, EmbeddingUsage
from agentscope.message import TextBlock
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from gerclaw_api.metrics import RAG_PROVIDER_LATENCY, RAG_PROVIDER_REQUESTS


class RAGProviderError(RuntimeError):
    """Safe provider failure that never includes response bodies or credentials."""


class _RetryableProviderError(RAGProviderError):
    """Transient status that AgentScope's bounded retry loop may retry."""


class _EmbeddingItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int = Field(ge=0)
    embedding: list[float] = Field(min_length=1)


class _Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_tokens: int = Field(default=0, ge=0)


class _EmbeddingPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: list[_EmbeddingItem]
    usage: _Usage = Field(default_factory=_Usage)


class _RerankDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = ""


class _RerankItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int = Field(ge=0)
    relevance_score: float = Field(ge=0, le=1)
    document: _RerankDocument | None = None


class _RerankPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[_RerankItem]


class RerankScore(BaseModel):
    """Provider-independent candidate score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int = Field(ge=0)
    score: float = Field(ge=0, le=1)


def _check_status(response: httpx.Response, operation: str) -> None:
    if response.status_code == 429 or response.status_code >= 500:
        raise _RetryableProviderError(f"{operation} provider is temporarily unavailable")
    if response.status_code >= 400:
        raise RAGProviderError(f"{operation} provider rejected the request")


def _http_outcome(status_code: int) -> str:
    if status_code == 429:
        return "rate_limited"
    if status_code >= 500:
        return "unavailable"
    if status_code >= 400:
        return "rejected"
    return "invalid"


def _observe_provider(operation: str, outcome: str, started: float) -> None:
    RAG_PROVIDER_REQUESTS.labels(operation=operation, outcome=outcome).inc()
    RAG_PROVIDER_LATENCY.labels(operation=operation).observe(time.perf_counter() - started)


class SiliconFlowEmbeddingModel(EmbeddingModelBase[str | TextBlock]):
    """AgentScope-compatible BGE-M3 embedding model using the real provider API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model: str,
        dimensions: int,
        batch_size: int,
        concurrency: int,
        timeout_seconds: float,
        tokens_per_minute: int = 450_000,
        max_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        credential = OpenAICredential(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            name="siliconflow-rag",
        )
        super().__init__(
            credential=credential,
            model=model,
            dimensions=dimensions,
            parameters=None,
            context_size=8_192,
            batch_size=batch_size,
            max_retries=max_retries,
            retry_delay=1.0,
        )
        self._client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(
                max_connections=max(4, concurrency * 2),
                max_keepalive_connections=max(2, concurrency),
            ),
            transport=transport,
        )
        self._semaphore = asyncio.Semaphore(concurrency)
        self._rate_lock = asyncio.Lock()
        self._next_request_at = 0.0
        self._tokens_per_minute = tokens_per_minute

    @classmethod
    def _get_retryable_exceptions(cls) -> tuple[type[Exception], ...]:
        return (httpx.RequestError, _RetryableProviderError)

    async def _call_api(self, inputs: list[Any], **kwargs: Any) -> EmbeddingResponse:
        del kwargs
        texts = [value for value in inputs if isinstance(value, str)]
        if len(texts) != len(inputs) or any(not text.strip() for text in texts):
            raise RAGProviderError("embedding inputs must be non-empty text")
        started = time.perf_counter()
        async with self._semaphore:
            await self._throttle(texts)
            request_started = time.perf_counter()
            try:
                response = await self._client.post(
                    "embeddings",
                    json={"model": self.model, "input": texts, "encoding_format": "float"},
                )
            except httpx.RequestError:
                _observe_provider("embedding", "network_error", request_started)
                raise
            if response.status_code == 429:
                await self._defer_after_rate_limit()
        try:
            outcome = _http_outcome(response.status_code)
            _check_status(response, "embedding")
            try:
                payload = _EmbeddingPayload.model_validate(response.json())
            except (ValueError, ValidationError) as error:
                raise RAGProviderError("embedding provider returned an invalid response") from error
            if len(payload.data) != len(texts):
                raise RAGProviderError("embedding provider returned an unexpected vector count")
            vectors: list[list[float] | None] = [None] * len(texts)
            for item in payload.data:
                if item.index >= len(vectors) or vectors[item.index] is not None:
                    raise RAGProviderError("embedding provider returned invalid vector indexes")
                if len(item.embedding) != self.dimensions or not all(
                    math.isfinite(value) for value in item.embedding
                ):
                    raise RAGProviderError("embedding provider returned an invalid vector")
                vectors[item.index] = item.embedding
            if any(vector is None for vector in vectors):
                raise RAGProviderError("embedding provider omitted a vector")
            outcome = "success"
            return EmbeddingResponse(
                embeddings=[vector for vector in vectors if vector is not None],
                usage=EmbeddingUsage(
                    time=time.perf_counter() - started,
                    tokens=payload.usage.total_tokens,
                ),
                source="api",
            )
        finally:
            _observe_provider("embedding", outcome, request_started)

    async def _throttle(self, texts: list[str]) -> None:
        """Reserve provider capacity using a conservative UTF-8 token estimate."""

        estimated_tokens = sum(max(1, (len(text.encode("utf-8")) + 3) // 4) for text in texts)
        interval = estimated_tokens * 60.0 / self._tokens_per_minute
        async with self._rate_lock:
            now = time.monotonic()
            scheduled = max(now, self._next_request_at)
            self._next_request_at = scheduled + interval
        delay = scheduled - now
        if delay > 0:
            await asyncio.sleep(delay)

    async def _defer_after_rate_limit(self) -> None:
        """Share a bounded cooldown across concurrently queued batches."""

        async with self._rate_lock:
            self._next_request_at = max(self._next_request_at, time.monotonic() + 10.0)

    async def aclose(self) -> None:
        """Close pooled provider connections."""

        await self._client.aclose()


class SiliconFlowReranker:
    """Bounded BGE reranker with strict response-index validation."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float,
        max_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            transport=transport,
        )

    async def rerank(self, query: str, documents: list[str], *, top_n: int) -> list[RerankScore]:
        """Rerank a bounded candidate list without trusting provider document echoes."""

        if not query.strip() or not documents or top_n < 1 or top_n > len(documents):
            raise ValueError("rerank requires a query, candidates, and a valid top_n")
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                try:
                    request_started = time.perf_counter()
                    response = await self._client.post(
                        "rerank",
                        json={
                            "model": self.model,
                            "query": query,
                            "documents": documents,
                            "top_n": top_n,
                            "return_documents": False,
                        },
                    )
                except httpx.RequestError:
                    _observe_provider("rerank", "network_error", request_started)
                    raise
                try:
                    outcome = _http_outcome(response.status_code)
                    _check_status(response, "rerank")
                    try:
                        payload = _RerankPayload.model_validate(response.json())
                    except (ValueError, ValidationError) as error:
                        raise RAGProviderError(
                            "rerank provider returned an invalid response"
                        ) from error
                    seen: set[int] = set()
                    scores: list[RerankScore] = []
                    for item in payload.results:
                        if item.index >= len(documents) or item.index in seen:
                            raise RAGProviderError(
                                "rerank provider returned invalid candidate indexes"
                            )
                        if not math.isfinite(item.relevance_score):
                            raise RAGProviderError("rerank provider returned a non-finite score")
                        seen.add(item.index)
                        scores.append(RerankScore(index=item.index, score=item.relevance_score))
                    if not scores:
                        raise RAGProviderError("rerank provider returned no candidates")
                    outcome = "success"
                    return sorted(scores, key=lambda item: item.score, reverse=True)[:top_n]
                finally:
                    _observe_provider("rerank", outcome, request_started)
            except (httpx.RequestError, _RetryableProviderError) as error:
                last_error = error
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(min(4.0, 2.0**attempt))
        raise RAGProviderError(
            "rerank provider remained unavailable after bounded retries"
        ) from last_error

    async def aclose(self) -> None:
        """Close pooled provider connections."""

        await self._client.aclose()
