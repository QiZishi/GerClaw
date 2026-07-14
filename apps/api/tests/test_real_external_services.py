"""Opt-in smoke tests that call real configured providers and never use mocks."""

from __future__ import annotations

import base64
import json
import os
import uuid

import httpx
import pytest
from agentscope.message import UserMsg
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import text

from gerclaw_api.config import Settings
from gerclaw_api.modules.rag.providers import SiliconFlowEmbeddingModel, SiliconFlowReranker
from gerclaw_api.services.model_factory import build_agentscope_model, close_agentscope_model

pytestmark = pytest.mark.external


def _sse_events(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for frame in body.split("\n\n"):
        lines = frame.splitlines()
        event = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if event is not None and data is not None:
            parsed = json.loads(data)
            assert isinstance(parsed, dict)
            events.append((event, parsed))
    return events


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
        try:
            final = None
            async for chunk in await model([UserMsg(name="user", content="只回复 GERCLAW_OK")]):
                final = chunk
            assert final is not None
            assert "GERCLAW_OK" in str(final.content)
            assert final.usage is not None
        finally:
            await close_agentscope_model(model)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_chat_sse_agentic_rag_persistence_and_replay(
    integration_client: tuple[AsyncClient, object],
) -> None:
    """Exercise the full route with root-.env models and the indexed local corpus."""

    client, app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_real_chat_0001"
    session = await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    assert session.status_code == 201, session.text

    payload = {
        "session_id": str(session_id),
        "message": (
            "请先调用 search_knowledge 检索本地知识库中老年患者多重用药风险审查的依据, "
            "再给出需要医生核验的安全建议。"
        ),
        "channel": "web",
    }
    response = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": trace_id, "X-Request-ID": "request_real_chat_0001"},
        json=payload,
        timeout=180,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(response.text)
    names = [name for name, _data in events]
    assert names[0] == "agent_start"
    assert "thinking" in names
    assert "tool_call" in names
    assert "tool_result" in names
    assert "text_delta" in names, [
        (name, data.get("code")) for name, data in events if name in {"error", "done"}
    ]
    assert names[-1] == "done", [
        (name, data.get("code")) for name, data in events if name in {"error", "done"}
    ]
    assert "ThinkingBlock" not in response.text
    assert "chain_of_thought" not in response.text.casefold()

    done = events[-1][1]
    full_text = done["full_text"]
    references = done["references"]
    assert isinstance(full_text, str)
    assert full_text.endswith("内容由 AI 生成，仅供参考。身体不适请及时就医。")
    assert "确诊" not in full_text
    assert isinstance(references, list) and references
    assert all(
        isinstance(item, dict)
        and item.get("corpus") == "local_knowledge_base"
        and item.get("source_id")
        for item in references
    )

    history = await client.get(f"/api/v1/sessions/{session_id}/messages")
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["text"] == full_text
    assert [item["source_id"] for item in messages[1]["citations"]] == [
        item["source_id"] for item in references
    ]

    trace = await client.get(f"/api/v1/traces/{trace_id}?limit=100")
    assert trace.status_code == 200
    trace_payload = trace.json()
    assert trace_payload["status"] == "completed"
    trace_types = [event["event_type"] for event in trace_payload["events"]]
    assert "tool.call" in trace_types
    assert "model.call" in trace_types
    assert "rag.retrieve" in trace_types
    assert "safety.check" in trace_types
    telemetry = json.dumps(trace_payload, ensure_ascii=False)
    assert payload["message"] not in telemetry
    settings = app.state.settings
    provider_identity_leaked = any(
        config.api_key.get_secret_value() in response.text + telemetry
        or str(config.url) in response.text + telemetry
        or config.model_name in response.text + telemetry
        for config in settings.agent_model_configs
    )
    assert not provider_identity_leaked, "provider identity leaked into Chat SSE or Trace"

    replay = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": trace_id, "X-Request-ID": "request_real_chat_replay"},
        json=payload,
        timeout=30,
    )
    replay_events = _sse_events(replay.text)
    assert replay_events[-1][0] == "done"
    assert replay_events[-1][1]["replayed"] is True
    assert replay_events[-1][1]["full_text"] == full_text
    assert (
        len((await client.get(f"/api/v1/sessions/{session_id}/messages")).json()["messages"]) == 2
    )

    async with app.state.database.engine.connect() as connection:
        encrypted = (
            await connection.execute(
                text(
                    "SELECT content, metadata FROM messages "
                    "WHERE tenant_id=:tenant AND session_id=:session"
                ),
                {"tenant": "tenant_public0001", "session": session_id},
            )
        ).all()
    assert len(encrypted) == 2
    assert all(row.content.startswith("enc:v1:") for row in encrypted)
    assert all(row.metadata.startswith("enc:v1:") for row in encrypted)


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
