"""Opt-in smoke tests that call real configured providers and never use mocks."""

from __future__ import annotations

import asyncio
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
from gerclaw_api.modules.memory.store import memory_point_id
from gerclaw_api.modules.rag.providers import SiliconFlowEmbeddingModel, SiliconFlowReranker
from gerclaw_api.modules.search import capture_search_attempts, create_search_runtime
from gerclaw_api.modules.search.module import ProductionSearchModule
from gerclaw_api.modules.search.providers import SearchProviderUnavailable
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


class _AlwaysUnavailableSearchProvider:
    async def search(self, *_args: object, **_kwargs: object) -> list[object]:
        raise SearchProviderUnavailable("injected primary outage")

    async def extract_content(self, _url: str) -> str:
        raise SearchProviderUnavailable("injected primary outage")

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_real_agent_model_chain() -> None:
    settings = _settings()
    configs = settings.agent_model_configs
    assert len(configs) == 3, "primary and two backups must all be configured"

    for config in configs:
        model = build_agentscope_model(config)
        try:
            final = None
            async with asyncio.timeout(config.timeout_seconds):
                async for chunk in await model([UserMsg(name="user", content="只回复 GERCLAW_OK")]):
                    final = chunk
            assert final is not None
            assert "GERCLAW_OK" in str(final.content)
            assert final.usage is not None
        finally:
            await close_agentscope_model(model)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_model_generates_and_agentscope_executes_reviewed_skill(
    integration_client: tuple[AsyncClient, object],
) -> None:
    """Prove Skill drafting and the chat Skill viewer use real configured models."""

    client, app = integration_client
    generation_trace_id = "trace_real_skill_generate_0001"
    generated = await client.post(
        "/api/v1/skills/generate",
        headers={
            "X-Trace-ID": generation_trace_id,
            "X-Request-ID": "request_real_skill_generate_0001",
        },
        json={
            "description": (
                "生成一个名为“老年跌倒复诊准备”的声明式临床工作流，skill_id 必须使用 "
                "custom-fall-followup-safety。它不接收参数，tools 只能包含 search_knowledge，"
                "必须先用 search_knowledge "
                "检索本地知识库，核对跌倒红旗征象、药物因素和就医时机，输出供医生复核的清单；"
                "涉及停换药建议时必须给出本轮证据与适用条件，"
                "并保留高风险立即就医规则。"
            )
        },
        timeout=240,
    )
    assert generated.status_code == 200, generated.text
    draft = generated.json()
    definition = draft["definition"]
    assert draft["trace_id"] == generation_trace_id
    assert definition["origin"] == "generated"
    assert definition["source"] == "custom"
    assert definition["skill_id"] == "custom-fall-followup-safety"
    assert definition["tool_names"] == ["search_knowledge"]
    assert "source_markdown" in definition

    generation_trace = await client.get(f"/api/v1/traces/{generation_trace_id}")
    assert generation_trace.status_code == 200, generation_trace.text
    assert generation_trace.json()["status"] == "completed"
    assert generation_trace.json()["events"][-1]["event_type"] == "skill.execute"
    assert generation_trace.json()["events"][-1]["payload"]["operation"] == "generate"

    registered = await client.post(
        "/api/v1/skills",
        json={"source_markdown": definition["source_markdown"], "origin": "generated"},
    )
    assert registered.status_code == 201, registered.text
    skill_id = registered.json()["skill_id"]

    session_id = uuid.uuid4()
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    selection = await client.put(
        f"/api/v1/skills/sessions/{session_id}/selection",
        json={"skill_ids": [skill_id]},
    )
    assert selection.status_code == 200, selection.text

    chat_trace_id = "trace_real_skill_chat_0001"
    response = await client.post(
        "/api/v1/chat",
        headers={
            "X-Trace-ID": chat_trace_id,
            "X-Request-ID": "request_real_skill_chat_0001",
        },
        json={
            "session_id": str(session_id),
            "message": (
                "必须先调用 Skill 工具读取我已加载的“老年跌倒复诊准备”工作流，"
                "再按其中要求调用 search_knowledge 检索本地知识库，"
                "为一位近期跌倒的老人生成供医生核验的复诊准备清单。"
            ),
            "loaded_skills": [skill_id],
            "channel": "web",
            "workflow": "standard",
        },
        timeout=300,
    )
    assert response.status_code == 200, response.text
    events = _sse_events(response.text)
    assert events[-1][0] == "done", events[-3:]
    tool_calls = [
        data for name, data in events if name == "tool_call" and data.get("tool_name") == "Skill"
    ]
    assert tool_calls, [(name, data.get("tool_name")) for name, data in events]
    assert any(
        name == "tool_call" and data.get("tool_name") == "search_knowledge" for name, data in events
    )
    done = events[-1][1]
    assert done["references"]
    assert str(done["full_text"]).endswith("内容由 AI 生成，仅供参考。身体不适请及时就医。")

    chat_trace = await client.get(f"/api/v1/traces/{chat_trace_id}?limit=100")
    assert chat_trace.status_code == 200, chat_trace.text
    trace_payload = chat_trace.json()
    assert trace_payload["status"] == "completed"
    skill_events = [
        event for event in trace_payload["events"] if event["event_type"] == "skill.execute"
    ]
    assert skill_events
    assert skill_events[-1]["payload"]["skill"] == skill_id
    assert skill_events[-1]["payload"]["version"] == definition["version"]
    serialized = response.text + json.dumps(trace_payload, ensure_ascii=False)
    assert definition["source_markdown"] not in serialized
    assert all(
        config.api_key.get_secret_value() not in serialized
        and str(config.url) not in serialized
        and config.model_name not in serialized
        for config in app.state.settings.agent_model_configs
    )


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
    assert "memory.update" in trace_types
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_chat_agentscope_web_search_results_citations_and_trace(
    integration_client: tuple[AsyncClient, object],
) -> None:
    """Prove a real model selects the production web tool and emits auditable sources."""

    client, _app = integration_client
    session_id = uuid.uuid4()
    trace_id = "trace_real_web_search_0001"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    ).status_code == 201
    response = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": trace_id, "X-Request-ID": "request_real_web_search_0001"},
        json={
            "session_id": str(session_id),
            "message": (
                "请调用 web_search 搜索 WHO healthy ageing，"
                "只用一句话列出一个联网来源 [W1]；不要跳过工具调用。"
            ),
            "channel": "web",
            "workflow": "standard",
        },
        timeout=240,
    )
    assert response.status_code == 200, response.text
    events = _sse_events(response.text)
    assert events[-1][0] == "done", events[-2:]
    search_tool_results = [
        data
        for name, data in events
        if name == "tool_result" and data.get("tool_name") == "web_search"
    ]
    assert search_tool_results
    results = search_tool_results[0].get("results")
    assert isinstance(results, list) and results
    assert all(
        isinstance(item, dict)
        and item.get("provider") in {"anysearch", "tavily"}
        and item.get("authority_level") in {"S", "A", "B", "C"}
        and str(item.get("url", "")).startswith("https://")
        for item in results
    )
    references = events[-1][1]["references"]
    assert isinstance(references, list)
    assert any(isinstance(item, dict) and item.get("corpus") == "web" for item in references)
    assert any(
        isinstance(item, dict) and item.get("corpus") == "local_knowledge_base"
        for item in references
    )

    trace = await client.get(f"/api/v1/traces/{trace_id}?limit=100")
    assert trace.status_code == 200
    search_events = [
        item for item in trace.json()["events"] if item["event_type"] == "search.query"
    ]
    assert search_events
    telemetry = json.dumps(trace.json(), ensure_ascii=False)
    assert "healthy ageing" not in telemetry.casefold()
    assert all("snippet" not in item["payload"] for item in search_events)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_cross_session_evidenced_memory_recall_and_encrypted_storage(
    integration_client: tuple[AsyncClient, object],
) -> None:
    """Prove real-model extraction, cross-session recall, and PHI-free vector payloads."""

    client, app = integration_client
    first_session = uuid.uuid4()
    first_trace = "trace_real_memory_write_0001"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(first_session)})
    ).status_code == 201
    first_payload = {
        "session_id": str(first_session),
        "message": (
            "这是我的明确健康资料：我对青霉素过敏，曾出现皮疹；"
            "目前每天服用阿司匹林100mg。请调用 search_knowledge 检索老年用药风险依据，"
            "并告诉我需要向医生核验什么。"
        ),
        "channel": "web",
    }
    first = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": first_trace, "X-Request-ID": "request_real_memory_write"},
        json=first_payload,
        timeout=240,
    )
    first_events = _sse_events(first.text)
    assert first.status_code == 200, first.text
    assert first_events[-1][0] == "done", first_events[-2:]

    profile_response = await client.get("/api/v1/memory/profile")
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()
    facts = profile["facts"]
    assert facts
    serialized_facts = json.dumps(facts, ensure_ascii=False)
    assert "青霉素" in serialized_facts
    assert "阿司匹林" in serialized_facts
    confirmed = [fact for fact in facts if fact["status"] == "confirmed"]
    assert confirmed

    first_trace_response = await client.get(f"/api/v1/traces/{first_trace}?limit=100")
    assert first_trace_response.status_code == 200
    memory_events = [
        event
        for event in first_trace_response.json()["events"]
        if event["event_type"] == "memory.update"
    ]
    assert len(memory_events) == 1
    assert memory_events[0]["status"] == "succeeded"
    assert memory_events[0]["payload"]["event_count"] >= 1

    async with app.state.database.engine.connect() as connection:
        raw_rows = (
            await connection.execute(
                text(
                    "SELECT statement, details FROM memory_facts "
                    "WHERE tenant_id=:tenant ORDER BY created_at"
                ),
                {"tenant": "tenant_public0001"},
            )
        ).all()
        raw_profile = (
            await connection.execute(
                text("SELECT profile FROM health_profiles WHERE tenant_id=:tenant"),
                {"tenant": "tenant_public0001"},
            )
        ).scalar_one()
    assert raw_rows
    assert all(row.statement.startswith("enc:v1:") for row in raw_rows)
    assert all(row.details.startswith("enc:v1:") for row in raw_rows)
    assert raw_profile.startswith("enc:v1:")
    raw_ciphertext = raw_profile + "".join(row.statement + row.details for row in raw_rows)
    assert "青霉素" not in raw_ciphertext
    assert "阿司匹林" not in raw_ciphertext

    point_ids = [memory_point_id(uuid.UUID(fact["id"]), fact["revision"]) for fact in confirmed]
    vector_points = await app.state.qdrant.retrieve(
        collection_name=app.state.settings.memory_collection_name,
        ids=point_ids,
        with_payload=True,
        with_vectors=False,
    )
    assert vector_points
    vector_payload = json.dumps(
        [point.payload for point in vector_points], ensure_ascii=False, default=str
    )
    assert "青霉素" not in vector_payload
    assert "阿司匹林" not in vector_payload
    assert "statement" not in vector_payload
    assert "tenant_public0001" not in vector_payload

    replay = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": first_trace, "X-Request-ID": "request_real_memory_replay"},
        json=first_payload,
        timeout=30,
    )
    assert _sse_events(replay.text)[-1][1]["replayed"] is True
    replay_profile = (await client.get("/api/v1/memory/profile")).json()
    assert replay_profile["version"] == profile["version"]
    assert len(replay_profile["facts"]) == len(facts)

    second_session = uuid.uuid4()
    second_trace = "trace_real_memory_read_0001"
    assert (
        await client.post("/api/v1/sessions", json={"session_id": str(second_session)})
    ).status_code == 201
    second = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": second_trace, "X-Request-ID": "request_real_memory_read"},
        json={
            "session_id": str(second_session),
            "message": (
                "请先调用 search_memory 回忆我以前明确说过的药物过敏史和当前用药，"
                "再调用 search_knowledge 检索本地知识库中老年患者多重用药风险审查的依据，"
                "并列出需要我向医生再次核验的信息。"
            ),
            "channel": "web",
        },
        timeout=240,
    )
    second_events = _sse_events(second.text)
    assert second.status_code == 200, second.text
    assert second_events[-1][0] == "done", second_events[-2:]
    second_text = second_events[-1][1]["full_text"]
    assert isinstance(second_text, str)
    assert "青霉素" in second_text
    assert "阿司匹林" in second_text
    memory_tool_calls = [
        data
        for name, data in second_events
        if name == "tool_call" and data.get("tool_name") == "search_memory"
    ]
    assert memory_tool_calls
    assert second_events[-1][1]["references"]


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


@pytest.mark.asyncio
async def test_real_anysearch_jsonrpc_search_and_extract() -> None:
    """Use the root .env AnySearch endpoint through the production adapter."""

    settings = _settings()
    if settings.anysearch_url is None:
        pytest.skip("AnySearch configuration is not provided")
    runtime = create_search_runtime(settings)
    try:
        results = await runtime.primary.search(
            "WHO healthy ageing older adults",
            max_results=2,
            domain="health",
        )
        assert results
        assert all(str(item.url).startswith("https://") for item in results)
        assert all(item.title and item.snippet for item in results)
        content = await runtime.primary.extract_content(
            "https://www.who.int/news-room/questions-and-answers/item/healthy-ageing-and-functional-ability"
        )
        assert len(content) > 100
        assert "age" in content.casefold()
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_real_tavily_fallback_through_production_router() -> None:
    """Inject only the primary failure; the successful fallback is the real Tavily service."""

    settings = _settings()
    runtime = create_search_runtime(settings)
    if runtime.fallback is None:
        await runtime.aclose()
        pytest.skip("Tavily fallback configuration is not provided")
    module = ProductionSearchModule(
        primary=_AlwaysUnavailableSearchProvider(),  # type: ignore[arg-type]
        fallback=runtime.fallback,
        max_retries=1,
    )
    try:
        with capture_search_attempts() as attempts:
            results = await module.search(
                "WHO healthy ageing older adults",
                max_results=2,
                domain="health",
            )
        assert results
        assert all(item.provider == "tavily" for item in results)
        assert [item.provider for item in attempts] == [
            "anysearch",
            "anysearch",
            "tavily",
        ]
        assert attempts[-1].outcome == "success"
        content = await runtime.fallback.extract_content(
            "https://www.who.int/news-room/questions-and-answers/item/healthy-ageing-and-functional-ability"
        )
        assert len(content) > 100
    finally:
        await runtime.aclose()
