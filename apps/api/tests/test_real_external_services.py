"""Opt-in smoke tests that call real configured providers and never use mocks."""

from __future__ import annotations

import base64
import os

import httpx
import pytest
from agentscope.message import UserMsg
from pydantic import SecretStr

from gerclaw_api.config import Settings
from gerclaw_api.modules.rag.providers import SiliconFlowEmbeddingModel, SiliconFlowReranker
from gerclaw_api.services.model_factory import build_agentscope_model

pytestmark = pytest.mark.external


def _settings() -> Settings:
    if os.getenv("GERCLAW_RUN_EXTERNAL") != "1":
        pytest.skip("set GERCLAW_RUN_EXTERNAL=1 to call real paid external services")
    return Settings()


def _auth_headers(settings: Settings) -> dict[str, str]:
    if settings.mimo_api_key is None:
        pytest.skip("MIMO_API_KEY is not configured")
    secret = settings.mimo_api_key.get_secret_value()
    if settings.mimo_auth_header == "api-key":
        return {"api-key": secret, "Content-Type": "application/json"}
    return {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_real_agent_model_chain() -> None:
    settings = _settings()
    configs = settings.agent_model_configs
    assert len(configs) == 3, "primary and two backups must all be configured"

    for config in configs:
        model = build_agentscope_model(config)
        final = None
        async for chunk in await model([UserMsg(name="user", content="只回复 GERCLAW_OK")]):
            final = chunk
        assert final is not None
        assert "GERCLAW_OK" in str(final.content)
        assert final.usage is not None


@pytest.mark.asyncio
async def test_real_mimo_tts_to_asr_roundtrip() -> None:
    settings = _settings()
    if any(
        value is None
        for value in (
            settings.mimo_tts_url,
            settings.mimo_asr_url,
            settings.tts_model,
            settings.asr_model,
            settings.tts_voice,
        )
    ):
        pytest.skip("MiMo ASR/TTS configuration is incomplete")

    headers = _auth_headers(settings)
    timeout = settings.external_request_timeout_seconds
    async with httpx.AsyncClient(timeout=timeout) as client:
        tts_response = await client.post(
            f"{str(settings.mimo_tts_url).rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": settings.tts_model,
                "messages": [{"role": "assistant", "content": "您好, GerClaw真实语音服务测试。"}],
                "audio": {"format": "wav", "voice": settings.tts_voice},
                "stream": False,
            },
        )
        tts_response.raise_for_status()
        audio_base64 = tts_response.json()["choices"][0]["message"]["audio"]["data"]
        audio = base64.b64decode(audio_base64, validate=True)
        assert len(audio) > 44

        asr_response = await client.post(
            f"{str(settings.mimo_asr_url).rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": settings.asr_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"data": audio_base64, "format": "wav"},
                            }
                        ],
                    }
                ],
                "asr_options": {"language": "zh"},
                "stream": False,
            },
        )
        asr_response.raise_for_status()
        transcript = asr_response.json()["choices"][0]["message"]["content"]
        assert isinstance(transcript, str) and transcript.strip()
        # ASR may render the English product name phonetically, so validate the
        # stable Chinese semantics instead of requiring an exact brand spelling.
        semantic_markers = {"您好", "你好", "语音", "服务", "测试"}
        assert sum(marker in transcript for marker in semantic_markers) >= 2


@pytest.mark.asyncio
async def test_real_siliconflow_embedding_and_rerank() -> None:
    settings = _settings()
    if any(
        value is None
        for value in (
            settings.siliconflow_api_key,
            settings.siliconflow_url,
            settings.embedding_model,
            settings.rerank_model,
        )
    ):
        pytest.skip("SiliconFlow embedding/rerank configuration is not provided")
    secret = SecretStr(settings.siliconflow_api_key.get_secret_value())
    embedding = SiliconFlowEmbeddingModel(
        base_url=str(settings.siliconflow_url),
        api_key=secret,
        model=settings.embedding_model,
        dimensions=settings.rag_embedding_dimensions,
        batch_size=64,
        concurrency=1,
        timeout_seconds=settings.external_request_timeout_seconds,
    )
    reranker = SiliconFlowReranker(
        base_url=str(settings.siliconflow_url),
        api_key=secret,
        model=settings.rerank_model,
        timeout_seconds=settings.external_request_timeout_seconds,
    )
    try:
        texts = [f"老年综合评估真实批次验证 {index}" for index in range(64)]
        embedded = await embedding(texts)
        assert len(embedded.embeddings) == 64
        assert all(
            len(vector) == settings.rag_embedding_dimensions for vector in embedded.embeddings
        )

        results = await reranker.rerank(
            "老年用药风险",
            ["药物相互作用审查", "天气预报"],
            top_n=2,
        )
        assert len(results) == 2
        assert results[0].index == 0
    finally:
        await embedding.aclose()
        await reranker.aclose()


@pytest.mark.asyncio
async def test_real_tavily_search() -> None:
    settings = _settings()
    if settings.tavily_url is None or settings.tavily_api_key is None:
        pytest.skip("Tavily configuration is not provided")
    async with httpx.AsyncClient(timeout=settings.external_request_timeout_seconds) as client:
        response = await client.post(
            f"{str(settings.tavily_url).rstrip('/')}/search",
            json={
                "api_key": settings.tavily_api_key.get_secret_value(),
                "query": "WHO healthy ageing",
                "max_results": 2,
            },
        )
        response.raise_for_status()
        assert len(response.json().get("results", [])) > 0
