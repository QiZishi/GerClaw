"""Tests for cached dependency readiness aggregation."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import pytest

from gerclaw_api.modules.rag.protocols import RAGStatus
from gerclaw_api.services.health_service import DependencyHealthService
from tests.conftest import make_settings


class HealthyDatabase:
    async def ping(self) -> None:
        return None


class FailingDatabase:
    async def ping(self) -> None:
        raise ConnectionError("not reachable")


class HealthyRedis:
    async def ping(self) -> bool:
        return True


class HealthyQdrant:
    async def get_collections(self) -> object:
        return object()


class HealthyRAG:
    async def status(self) -> RAGStatus:
        return RAGStatus(
            ready=True,
            collection="test_rag",
            source_documents=2,
            indexed_documents=2,
            indexed_chunks=4,
            embedding_model="BAAI/bge-m3",
            rerank_model="BAAI/bge-reranker-v2-m3",
        )


class HealthyMemory:
    collection = "test_memory"

    def __init__(self) -> None:
        self.ensure_calls = 0
        self.force_checks: list[bool] = []

    async def ensure_collection(self, *, force: bool = False) -> None:
        self.ensure_calls += 1
        self.force_checks.append(force)

    async def count(self) -> int:
        return 3


@pytest.mark.asyncio
async def test_readiness_reports_configured_corpus_and_runtime_versions(tmp_path: Path) -> None:
    (tmp_path / "one.md").write_text("one", encoding="utf-8")
    (tmp_path / "two.md").write_text("two", encoding="utf-8")
    memory = HealthyMemory()
    service = DependencyHealthService(
        settings=make_settings(readiness_cache_seconds=60, knowledge_base_path=tmp_path),
        database=HealthyDatabase(),  # type: ignore[arg-type]
        redis_client=HealthyRedis(),  # type: ignore[arg-type]
        qdrant_client=HealthyQdrant(),  # type: ignore[arg-type]
        rag_module=HealthyRAG(),  # type: ignore[arg-type]
        memory_store=memory,  # type: ignore[arg-type]
    )

    first = await service.check()
    second = await service.check()

    assert first is second
    assert first["status"] == "ready"
    assert first["checks"]["agentscope"]["version"] == version("agentscope")
    assert first["checks"]["knowledge_base"]["markdown_documents"] == 2
    assert first["checks"]["rag_index"]["indexed_documents"] == 2
    assert first["checks"]["memory_index"] == {
        "ok": True,
        "collection": "test_memory",
        "vector_points": 3,
        "payload_contains_phi": False,
    }
    assert memory.ensure_calls == 1
    assert memory.force_checks == [True]


@pytest.mark.asyncio
async def test_readiness_aggregates_dependency_failure_without_leaking_url() -> None:
    service = DependencyHealthService(
        settings=make_settings(),
        database=FailingDatabase(),  # type: ignore[arg-type]
        redis_client=HealthyRedis(),  # type: ignore[arg-type]
        qdrant_client=HealthyQdrant(),  # type: ignore[arg-type]
        rag_module=HealthyRAG(),  # type: ignore[arg-type]
        memory_store=HealthyMemory(),  # type: ignore[arg-type]
    )

    report = await service.check()

    assert report["status"] == "not_ready"
    assert report["checks"]["postgres"] == {
        "ok": False,
        "error": "ConnectionError",
    }
    assert "change-me" not in str(report)
