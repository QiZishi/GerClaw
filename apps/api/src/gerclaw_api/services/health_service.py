"""Cached readiness checks for real runtime dependencies."""

from __future__ import annotations

import asyncio
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from gerclaw_api.config import Settings
from gerclaw_api.database.session import Database
from gerclaw_api.modules.rag.protocols import RAGModule


class DependencyHealthService:
    """Probe PostgreSQL, Redis, Qdrant, AgentScope, and the local corpus."""

    def __init__(
        self,
        *,
        settings: Settings,
        database: Database,
        redis_client: Redis,
        qdrant_client: AsyncQdrantClient,
        rag_module: RAGModule,
    ) -> None:
        self._settings = settings
        self._database = database
        self._redis = redis_client
        self._qdrant = qdrant_client
        self._rag = rag_module
        self._cache: tuple[float, dict[str, Any]] | None = None
        self._lock = asyncio.Lock()

    async def check(self) -> dict[str, Any]:
        """Return a bounded, cached readiness report without leaking connection data."""

        now = time.monotonic()
        if (
            self._cache is not None
            and now - self._cache[0] < self._settings.readiness_cache_seconds
        ):
            return self._cache[1]
        async with self._lock:
            now = time.monotonic()
            if (
                self._cache is not None
                and now - self._cache[0] < self._settings.readiness_cache_seconds
            ):
                return self._cache[1]
            results = await asyncio.gather(
                self._probe("postgres", self._database.ping),
                self._probe("redis", self._ping_redis),
                self._probe("qdrant", self._ping_qdrant),
                self._probe("knowledge_base", self._check_knowledge_base),
                self._probe("rag_index", self._check_rag_index),
                self._probe("agentscope", self._check_agentscope),
            )
            checks = {name: state for name, state in results}
            report: dict[str, Any] = {
                "status": "ready" if all(state["ok"] for state in checks.values()) else "not_ready",
                "checks": checks,
            }
            self._cache = (time.monotonic(), report)
            return report

    @staticmethod
    async def _probe(name: str, operation: Any) -> tuple[str, dict[str, Any]]:
        try:
            detail = await asyncio.wait_for(operation(), timeout=3.0)
            state: dict[str, Any] = {"ok": True}
            if isinstance(detail, dict):
                state.update(detail)
            return name, state
        except Exception as error:  # health endpoints must aggregate all failures
            return name, {"ok": False, "error": type(error).__name__}

    async def _ping_redis(self) -> None:
        await self._redis.ping()

    async def _ping_qdrant(self) -> None:
        await self._qdrant.get_collections()

    async def _check_knowledge_base(self) -> dict[str, int]:
        path = self._settings.knowledge_base_path
        count = await asyncio.to_thread(self._count_markdown_files, path)
        if count == 0:
            raise RuntimeError("knowledge base has no Markdown documents")
        return {"markdown_documents": count}

    async def _check_agentscope(self) -> dict[str, str]:
        try:
            installed = await asyncio.to_thread(version, "agentscope")
        except PackageNotFoundError as error:
            raise RuntimeError("AgentScope is not installed") from error
        if installed != self._settings.agentscope_required_version:
            raise RuntimeError("AgentScope runtime version mismatch")
        return {"version": installed}

    async def _check_rag_index(self) -> dict[str, Any]:
        status = await self._rag.status()
        return {
            "ok": status.ready,
            "source_documents": status.source_documents,
            "indexed_documents": status.indexed_documents,
            "indexed_chunks": status.indexed_chunks,
            "retrieval_mode": status.retrieval_mode,
        }

    @staticmethod
    def _count_markdown_files(path: Path) -> int:
        if not path.is_dir():
            raise FileNotFoundError(path.name)
        return sum(1 for item in path.rglob("*.md") if item.is_file())
