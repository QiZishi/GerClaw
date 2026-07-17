"""End-to-end security and observability flows against isolated real dependencies."""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from gerclaw_api.auth import create_access_token
from gerclaw_api.database.models import (
    BadCase,
    ExecutionTrace,
    ProviderEgressEvent,
    TraceEvent,
    UserFeedback,
)
from gerclaw_api.modules.rag.locking import PostgresAdvisoryRAGIndexLock
from gerclaw_api.modules.search.models import ProviderSearchResult
from gerclaw_api.modules.search.module import ProductionSearchModule
from gerclaw_api.modules.search.security import PublicURLGuard
from gerclaw_api.services.rate_limit import RateLimiter

TRACE_ID = "trace_integration_0001"


class _FailingRAGModule:
    async def retrieve(self, *_args: object, **_kwargs: object) -> list[object]:
        raise RuntimeError("injected provider failure")


class _StaticSearchProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.extract_calls: list[str] = []

    async def search(
        self, query: str, *, max_results: int, domain: str
    ) -> list[ProviderSearchResult]:
        del max_results, domain
        self.queries.append(query)
        return [
            ProviderSearchResult(
                title="WHO healthy ageing",
                snippet="WHO healthy ageing evidence.",
                url="https://www.who.int/healthy-ageing",
                published_date="2024-03-15",
                score=0.9,
            )
        ]

    async def extract_content(self, url: str) -> str:
        self.extract_calls.append(url)
        return "# WHO evidence"

    async def aclose(self) -> None:
        return None


async def _public_resolver(_host: str, _port: int) -> list[str]:
    return ["93.184.216.34"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_advisory_lock_serializes_independent_rag_index_workers(
    integration_client: tuple[AsyncClient, object],
) -> None:
    """Two independent connections must never mutate the RAG collection concurrently."""

    _client, app = integration_client
    database_url = app.state.settings.database_url
    first_lock = PostgresAdvisoryRAGIndexLock(database_url)
    second_lock = PostgresAdvisoryRAGIndexLock(database_url)
    first_acquired = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()
    second_acquired = asyncio.Event()

    async def first_worker() -> None:
        async with first_lock.hold():
            first_acquired.set()
            await release_first.wait()

    async def second_worker() -> None:
        second_started.set()
        async with second_lock.hold():
            second_acquired.set()

    first_task = asyncio.create_task(first_worker())
    await asyncio.wait_for(first_acquired.wait(), timeout=3)
    second_task = asyncio.create_task(second_worker())
    await asyncio.wait_for(second_started.wait(), timeout=1)
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(second_acquired.wait(), timeout=0.1)
    finally:
        release_first.set()
    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=3)
    assert second_acquired.is_set()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_lock_session_loss_cancels_the_active_rag_writer(
    integration_client: tuple[AsyncClient, object],
) -> None:
    """A live writer must fail-stop when PostgreSQL releases its dead lock session."""

    _client, app = integration_client
    index_lock = PostgresAdvisoryRAGIndexLock(app.state.settings.database_url)
    body_entered = asyncio.Event()
    never_complete = asyncio.Event()
    writer_cancelled = asyncio.Event()

    async def writer() -> None:
        try:
            async with index_lock.hold():
                body_entered.set()
                await never_complete.wait()
        except asyncio.CancelledError:
            writer_cancelled.set()
            raise

    writer_task = asyncio.create_task(writer())
    await asyncio.wait_for(body_entered.wait(), timeout=3)
    async with app.state.database.engine.connect() as connection:
        lock_pid = await connection.scalar(
            text(
                "SELECT pid FROM pg_locks "
                "WHERE locktype='advisory' AND granted AND pid <> pg_backend_pid() "
                "ORDER BY pid DESC LIMIT 1"
            )
        )
        assert isinstance(lock_pid, int)
        assert (
            await connection.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": lock_pid})
            is True
        )
        await connection.commit()

    await asyncio.wait_for(writer_cancelled.wait(), timeout=2)
    result = (await asyncio.gather(writer_task, return_exceptions=True))[0]
    assert isinstance(result, asyncio.CancelledError)

    # The terminated session released the advisory lock and a replacement worker can proceed.
    async with PostgresAdvisoryRAGIndexLock(app.state.settings.database_url).hold():
        pass


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_agentic_rag_api_trace_and_agentscope_tool(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client

    status = await client.get("/api/v1/rag/status")
    assert status.status_code == 200, status.text
    assert status.json()["ready"] is True
    assert status.json()["source_documents"] >= 400
    assert status.json()["source_documents"] == status.json()["indexed_documents"]

    response = await client.post(
        "/api/v1/rag/retrieve",
        headers={"X-Trace-ID": "trace_rag_integration_0001"},
        json={"query": "老年患者多重用药的风险评估与审查要点", "top_k": 3},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["trace_id"] == "trace_rag_integration_0001"
    assert 1 <= len(payload["results"]) <= 3
    assert "不构成诊断" in payload["medical_disclaimer"]
    assert all(not item["source"].startswith("/") for item in payload["results"])
    assert all(item["metadata"]["chunk_id"] for item in payload["results"])

    trace = await client.get(f"/api/v1/traces/{payload['trace_id']}")
    assert trace.status_code == 200, trace.text
    assert trace.json()["status"] == "completed"
    assert trace.json()["events"][0]["event_type"] == "rag.retrieve"
    assert trace.json()["events"][0]["payload"]["document_count"] >= 1

    replay = await client.post(
        "/api/v1/rag/retrieve",
        headers={"X-Trace-ID": "trace_rag_integration_0001"},
        json={"query": "老年患者多重用药的风险评估与审查要点", "top_k": 3},
    )
    assert replay.status_code == 200, replay.text
    replayed_trace = await client.get("/api/v1/traces/trace_rag_integration_0001")
    assert len(replayed_trace.json()["events"]) == 1

    tools = await app.state.agentic_rag_middleware.list_tools()
    assert [tool.name for tool in tools] == ["search_knowledge"]
    tool_result = await tools[0].call(query="老年综合评估包括哪些核心内容")
    assert tool_result.is_last is True
    assert any(
        "medical-knowledge-evidence" in getattr(block, "text", "") for block in tool_result.content
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_api_redacts_phi_enforces_scope_and_persists_safe_trace(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    provider = _StaticSearchProvider()
    runtime = app.state.search_runtime
    working_module = runtime.module
    runtime.module = ProductionSearchModule(
        primary=provider,
        fallback=None,
        url_guard=PublicURLGuard(_public_resolver),
    )
    try:
        search_request = {
            "query": "患者姓名:张三, 手机号13800138000 老年健康最新指南",
            "max_results": 3,
            "domain": "health",
        }
        response = await client.post(
            "/api/v1/search/query",
            headers={"X-Trace-ID": "trace_search_integration_0001"},
            json=search_request,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["results"][0]["provider"] == "anysearch"
        assert payload["results"][0]["authority_level"] == "S"
        assert "张三" not in provider.queries[0]
        assert "13800138000" not in provider.queries[0]

        trace = await client.get("/api/v1/traces/trace_search_integration_0001")
        assert trace.status_code == 200
        trace_payload = trace.json()
        assert trace_payload["status"] == "completed"
        assert trace_payload["events"][0]["event_type"] == "search.query"
        assert trace_payload["events"][0]["payload"] == {
            "module": "search",
            "operation": "search",
            "provider": "anysearch",
            "outcome": "success",
            "retry_index": 0,
            "result_count": 1,
            "success": True,
        }
        telemetry = json.dumps(trace_payload, ensure_ascii=False)
        assert "张三" not in telemetry
        assert "13800138000" not in telemetry
        assert "WHO healthy ageing evidence" not in telemetry

        async with app.state.database.session() as session:
            events = list(
                (
                    await session.scalars(
                        select(ProviderEgressEvent).where(
                            ProviderEgressEvent.tenant_id == "tenant_public0001",
                            ProviderEgressEvent.actor_id == "usr_patient_integration0001",
                        )
                    )
                ).all()
            )
        assert len(events) == 1
        assert events[0].processor == "anysearch"
        assert events[0].purpose == "external_search_query"
        assert events[0].policy_version == "1.1.0"
        assert events[0].outcome == "succeeded"
        event_json = json.dumps(events[0].findings, ensure_ascii=False)
        assert "张三" not in event_json
        assert "13800138000" not in event_json

        replay = await client.post(
            "/api/v1/search/query",
            headers={"X-Trace-ID": "trace_search_integration_0001"},
            json=search_request,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["results"] == payload["results"]
        replayed_trace = await client.get("/api/v1/traces/trace_search_integration_0001")
        assert len(replayed_trace.json()["events"]) == 1

        async with app.state.database.session() as session:
            replay_events = list(
                (
                    await session.scalars(
                        select(ProviderEgressEvent).where(
                            ProviderEgressEvent.tenant_id == "tenant_public0001",
                            ProviderEgressEvent.actor_id == "usr_patient_integration0001",
                        )
                    )
                ).all()
            )
        assert len(replay_events) == 2
        assert {event.outcome for event in replay_events} == {"succeeded"}

        conflict = await client.post(
            "/api/v1/search/query",
            headers={"X-Trace-ID": "trace_search_integration_0001"},
            json={**search_request, "query": "different evidence request"},
        )
        assert conflict.status_code == 409

        rejected = await client.post(
            "/api/v1/search/extract",
            headers={"X-Trace-ID": "trace_search_ssrf_0001"},
            json={"url": "https://127.0.0.1/latest/meta-data"},
        )
        assert rejected.status_code == 400
        assert rejected.json()["error"]["code"] == "SEARCH_URL_REJECTED"
        rejected_trace = await client.get("/api/v1/traces/trace_search_ssrf_0001")
        assert rejected_trace.json()["status"] == "failed"
        assert provider.extract_calls == []

        no_scope = create_access_token(
            app.state.settings,
            actor_id="usr_patient_integration0001",
            tenant_id="tenant_public0001",
            scopes={"trace:read"},
        )
        forbidden = await client.get(
            "/api/v1/search/status",
            headers={"Authorization": f"Bearer {no_scope}"},
        )
        assert forbidden.status_code == 403
    finally:
        runtime.module = working_module


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rag_dependency_failure_persists_failed_trace_and_bad_case(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    runtime = app.state.rag_runtime
    working_module = runtime.module
    runtime.module = _FailingRAGModule()
    try:
        response = await client.post(
            "/api/v1/rag/retrieve",
            headers={"X-Trace-ID": "trace_rag_failure_0001"},
            json={"query": "故障注入时不得伪造医学证据", "top_k": 3},
        )
    finally:
        runtime.module = working_module

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RAG_UNAVAILABLE"
    trace = await client.get("/api/v1/traces/trace_rag_failure_0001")
    assert trace.status_code == 200
    assert trace.json()["status"] == "failed"
    assert trace.json()["events"][0]["status"] == "failed"
    async with app.state.database.session() as session:
        bad_cases = await session.scalar(
            select(func.count())
            .select_from(BadCase)
            .where(BadCase.trace_id == "trace_rag_failure_0001")
        )
        assert bad_cases == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_trace_feedback_bad_case_encryption_and_readiness_flow(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client

    live = await client.get("/health/live")
    ready = await client.get("/health/ready")
    metrics = await client.get("/metrics")
    assert live.status_code == 200
    assert ready.status_code == 200
    assert metrics.status_code == 200
    assert ready.json()["checks"]["knowledge_base"]["markdown_documents"] >= 400
    assert ready.json()["checks"]["agentscope"]["version"] == "2.0.4"
    assert live.headers["x-request-id"].startswith("req_")
    assert live.headers["cache-control"] == "no-store"

    start_headers = {
        "X-Request-ID": "request_integration_001",
        "X-Trace-ID": TRACE_ID,
    }
    start_payload = {
        "execution_type": "agent.turn",
        "attributes": {"channel": "web", "model": "qwen-plus"},
    }
    start = await client.post("/api/v1/traces", headers=start_headers, json=start_payload)
    replay = await client.post("/api/v1/traces", headers=start_headers, json=start_payload)
    assert start.status_code == 201, start.text
    assert replay.status_code == 201
    assert start.json()["trace_id"] == TRACE_ID
    assert start.headers["x-trace-id"] == TRACE_ID
    assert start.json()["tenant_id"] == "tenant_public0001"
    assert start.json()["actor_id"] == "usr_patient_integration0001"

    event_payload = {
        "event_id": "event_integration_0001",
        "event_type": "tool.call",
        "status": "succeeded",
        "payload": {"tool_name": "medication.review", "success": True},
        "duration_ms": 12,
    }
    event = await client.post(f"/api/v1/traces/{TRACE_ID}/events", json=event_payload)
    event_replay = await client.post(f"/api/v1/traces/{TRACE_ID}/events", json=event_payload)
    assert event.status_code == 201, event.text
    assert event_replay.json()["id"] == event.json()["id"]
    assert event.json()["sequence"] == 1

    finish_payload = {
        "idempotency_key": "finish_integration_0001",
        "status": "failed",
        "error_code": "tool_timeout",
        "error_summary": "联系 13900139000, 地址北京市朝阳区幸福路1号",
    }
    finish = await client.post(f"/api/v1/traces/{TRACE_ID}/finish", json=finish_payload)
    finish_replay = await client.post(f"/api/v1/traces/{TRACE_ID}/finish", json=finish_payload)
    assert finish.status_code == 200, finish.text
    assert finish_replay.status_code == 200
    assert "13900139000" not in finish.json()["error_summary"]

    feedback_payload = {
        "idempotency_key": "idem_integration_0001",
        "trace_id": TRACE_ID,
        "rating": "negative",
        "categories": ["unsafe_answer"],
        "comment": "患者张三, 邮箱 patient@example.com, 住北京市朝阳区幸福路1号",
        "metadata": {"channel": "web"},
    }
    feedback = await client.post("/api/v1/feedback", json=feedback_payload)
    feedback_replay = await client.post("/api/v1/feedback", json=feedback_payload)
    assert feedback.status_code == 201, feedback.text
    assert feedback_replay.status_code == 201
    assert feedback.json()["id"] == feedback_replay.json()["id"]

    detail = await client.get(f"/api/v1/traces/{TRACE_ID}?limit=1")
    assert detail.status_code == 200
    assert len(detail.json()["events"]) == 1
    assert detail.headers["x-trace-id"] == TRACE_ID

    other_account_token = create_access_token(
        app.state.settings,
        actor_id="usr_account_0123456789abcdef0123456789abcdef",
        tenant_id="tenant_public0001",
        scopes={"trace:read"},
        role="patient",
        account_role="patient",
    )
    other_account = await client.get(
        f"/api/v1/traces/{TRACE_ID}",
        headers={"Authorization": f"Bearer {other_account_token}"},
    )
    assert other_account.status_code == 404
    assert other_account.json()["error"]["code"] == "TRACE_NOT_FOUND"

    administrator_token = create_access_token(
        app.state.settings,
        actor_id="usr_account_fedcba9876543210fedcba9876543210",
        tenant_id="tenant_public0001",
        scopes={"trace:read", "account:admin"},
        role="admin",
        account_role="admin",
    )
    administrator = await client.get(
        f"/api/v1/traces/{TRACE_ID}",
        headers={"Authorization": f"Bearer {administrator_token}"},
    )
    assert administrator.status_code == 200
    assert administrator.json()["trace_id"] == TRACE_ID

    bad_case_queue = await client.get(
        "/api/v1/auth/admin/bad-cases",
        headers={"Authorization": f"Bearer {administrator_token}"},
    )
    assert bad_case_queue.status_code == 200
    assert len(bad_case_queue.json()["cases"]) == 2
    assert "snapshot" not in bad_case_queue.json()["cases"][0]
    reviewed_case = await client.patch(
        f"/api/v1/auth/admin/bad-cases/{bad_case_queue.json()['cases'][0]['id']}",
        headers={"Authorization": f"Bearer {administrator_token}"},
        json={"status": "triaged"},
    )
    assert reviewed_case.status_code == 200
    assert reviewed_case.json()["status"] == "triaged"
    assert reviewed_case.json()["resolved_at"] is None

    async with app.state.database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ExecutionTrace)) == 1
        assert await session.scalar(select(func.count()).select_from(TraceEvent)) == 1
        assert await session.scalar(select(func.count()).select_from(UserFeedback)) == 1
        assert await session.scalar(select(func.count()).select_from(BadCase)) == 2
        raw_trace = (
            await session.execute(
                text(
                    "SELECT error_summary FROM execution_traces "
                    "WHERE tenant_id=:tenant AND trace_id=:trace"
                ),
                {"tenant": "tenant_public0001", "trace": TRACE_ID},
            )
        ).scalar_one()
        raw_feedback = (
            await session.execute(
                text(
                    "SELECT comment FROM user_feedback WHERE tenant_id=:tenant AND trace_id=:trace"
                ),
                {"tenant": "tenant_public0001", "trace": TRACE_ID},
            )
        ).scalar_one()
        raw_bad_cases = (
            await session.execute(
                text("SELECT snapshot FROM bad_cases WHERE tenant_id=:tenant AND trace_id=:trace"),
                {"tenant": "tenant_public0001", "trace": TRACE_ID},
            )
        ).scalars()
        assert raw_trace.startswith("enc:v1:")
        assert raw_feedback.startswith("enc:v1:")
        assert all(snapshot.startswith("enc:v1:") for snapshot in raw_bad_cases)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_enforces_auth_tenant_payload_and_body_boundaries(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    settings = app.state.settings
    assert (
        await client.post(
            "/api/v1/traces",
            headers={"Authorization": ""},
            json={"execution_type": "agent.turn"},
        )
    ).status_code == 401

    invalid = await client.post(
        "/api/v1/traces",
        headers={"X-Trace-ID": "trace_invalid_0001"},
        json={"execution_type": "agent.turn", "attributes": {"name": "张三"}},
    )
    cot = await client.post(
        "/api/v1/traces",
        headers={"X-Trace-ID": "trace_invalid_0002"},
        json={"execution_type": "agent.turn", "attributes": {"raw_chain_of_thought": "x"}},
    )
    oversized = await client.post(
        "/api/v1/traces",
        content=b"x" * (settings.max_request_body_bytes + 1),
        headers={"Content-Type": "application/json"},
    )
    assert invalid.status_code == 422
    assert cot.status_code == 422
    assert oversized.status_code == 413

    start = await client.post(
        "/api/v1/traces",
        headers={"X-Trace-ID": TRACE_ID},
        json={"execution_type": "agent.turn"},
    )
    assert start.status_code == 201
    other_token = create_access_token(
        settings,
        actor_id="usr_patient_other0001",
        tenant_id="tenant_other0001",
        scopes={"trace:read", "trace:write", "feedback:write"},
    )
    cross_tenant = await client.get(
        f"/api/v1/traces/{TRACE_ID}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert cross_tenant.status_code == 404

    finish = {
        "idempotency_key": "finish_integration_0002",
        "status": "failed",
        "error_code": "first_error",
    }
    assert (await client.post(f"/api/v1/traces/{TRACE_ID}/finish", json=finish)).status_code == 200
    finish["error_code"] = "second_error"
    assert (await client.post(f"/api/v1/traces/{TRACE_ID}/finish", json=finish)).status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_idempotency_and_redis_rate_limit(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    trace_payload = {"execution_type": "agent.turn", "attributes": {"channel": "web"}}
    headers = {"X-Trace-ID": "trace_concurrent_0001"}

    trace_responses = await asyncio.gather(
        *(client.post("/api/v1/traces", headers=headers, json=trace_payload) for _ in range(12))
    )
    assert {response.status_code for response in trace_responses} == {201}
    assert len({response.json()["trace_id"] for response in trace_responses}) == 1

    feedback_payload = {
        "idempotency_key": "idem_concurrent_0001",
        "trace_id": "trace_concurrent_0001",
        "rating": "negative",
        "categories": ["incorrect_answer"],
    }
    feedback_responses = await asyncio.gather(
        *(client.post("/api/v1/feedback", json=feedback_payload) for _ in range(12))
    )
    assert {response.status_code for response in feedback_responses} == {201}
    assert len({response.json()["id"] for response in feedback_responses}) == 1

    async with app.state.database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ExecutionTrace)) == 1
        assert await session.scalar(select(func.count()).select_from(UserFeedback)) == 1
        assert await session.scalar(select(func.count()).select_from(BadCase)) == 1

    await app.state.redis.flushdb()
    app.state.rate_limiter = RateLimiter(app.state.redis, limit=2, window_seconds=60)
    first = await client.get(f"/api/v1/traces/{headers['X-Trace-ID']}")
    second = await client.get(f"/api/v1/traces/{headers['X-Trace-ID']}")
    third = await client.get(f"/api/v1/traces/{headers['X-Trace-ID']}")
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert int(third.headers["retry-after"]) >= 1
