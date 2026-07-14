"""Provider response validation tests; paid-service success is covered separately."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from gerclaw_api.modules.rag.providers import (
    RAGProviderError,
    SiliconFlowEmbeddingModel,
    SiliconFlowReranker,
)


def _embedding(
    handler: httpx.AsyncBaseTransport,
) -> SiliconFlowEmbeddingModel:
    return SiliconFlowEmbeddingModel(
        base_url="https://provider.invalid/v1",
        api_key=SecretStr("tests-only-key"),
        model="BAAI/bge-m3",
        dimensions=4,
        batch_size=8,
        concurrency=2,
        timeout_seconds=2,
        max_retries=0,
        transport=handler,
    )


def _reranker(handler: httpx.AsyncBaseTransport) -> SiliconFlowReranker:
    return SiliconFlowReranker(
        base_url="https://provider.invalid/v1",
        api_key=SecretStr("tests-only-key"),
        model="BAAI/bge-reranker-v2-m3",
        timeout_seconds=2,
        max_retries=0,
        transport=handler,
    )


@pytest.mark.asyncio
async def test_embedding_validates_and_restores_provider_index_order() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer tests-only-key"
        assert body["input"] == ["第一条", "第二条"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0, 0.0]},
                ],
                "usage": {"total_tokens": 8},
            },
        )

    provider = _embedding(httpx.MockTransport(handler))
    try:
        response = await provider(["第一条", "第二条"])
        assert response.embeddings == [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
        assert response.usage.tokens == 8
    finally:
        await provider.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"index": 0, "embedding": [1.0, 0.0]}]},
        {"data": [{"index": 3, "embedding": [1.0, 0.0, 0.0, 0.0]}]},
        {"unexpected": []},
    ],
)
async def test_embedding_rejects_malformed_provider_payload(payload: dict[str, object]) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = _embedding(httpx.MockTransport(handler))
    try:
        with pytest.raises(RAGProviderError, match="embedding provider"):
            await provider(["有效文本"])
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_embedding_rejects_empty_input_before_network() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be reached")

    provider = _embedding(httpx.MockTransport(handler))
    try:
        with pytest.raises(RAGProviderError, match="non-empty text"):
            await provider([""])
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_reranker_sorts_scores_and_rejects_bad_indexes() -> None:
    valid = _reranker(
        httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "results": [
                        {"index": 0, "relevance_score": 0.2},
                        {"index": 1, "relevance_score": 0.9},
                    ]
                },
            )
        )
    )
    invalid = _reranker(
        httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"results": [{"index": 5, "relevance_score": 0.9}]},
            )
        )
    )
    try:
        result = await valid.rerank("用药风险", ["天气", "药物相互作用"], top_n=2)
        assert [item.index for item in result] == [1, 0]
        with pytest.raises(RAGProviderError, match="indexes"):
            await invalid.rerank("用药风险", ["证据"], top_n=1)
        with pytest.raises(ValueError, match="valid top_n"):
            await valid.rerank("", ["证据"], top_n=1)
    finally:
        await valid.aclose()
        await invalid.aclose()


@pytest.mark.asyncio
async def test_provider_maps_http_failures_to_safe_errors() -> None:
    rejected = _reranker(
        httpx.MockTransport(lambda _request: httpx.Response(401, text="secret details"))
    )
    unavailable = _reranker(httpx.MockTransport(lambda _request: httpx.Response(503)))
    try:
        with pytest.raises(RAGProviderError, match="rejected") as rejected_error:
            await rejected.rerank("查询", ["证据"], top_n=1)
        assert "secret details" not in str(rejected_error.value)
        with pytest.raises(RAGProviderError, match="bounded retries"):
            await unavailable.rerank("查询", ["证据"], top_n=1)
    finally:
        await rejected.aclose()
        await unavailable.aclose()
