"""Hybrid Qdrant storage tests using the real in-process Qdrant engine."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client import AsyncQdrantClient, models

from gerclaw_api.modules.rag.indexer import CorpusIndexer
from gerclaw_api.modules.rag.locking import InProcessRAGIndexLock
from gerclaw_api.modules.rag.models import EmbeddedChunk, IndexChunk
from gerclaw_api.modules.rag.parser import MarkdownMedicalParser, MedicalMarkdownChunker
from gerclaw_api.modules.rag.protocols import RAGFilters
from gerclaw_api.modules.rag.store import QdrantHybridStore, RAGStoreError

_GENERATION_OLD = "1" * 32
_GENERATION_NEW = "2" * 32
_GENERATION_WRITER_A = "a" * 32
_GENERATION_WRITER_B = "b" * 32


class _DeterministicEmbedding:
    model = "test-embedding"
    dimensions = 4

    async def __call__(self, inputs: list[str]) -> Any:
        return SimpleNamespace(embeddings=[[1.0, 0.0, 0.0, 0.0] for _ in inputs])


def _embedded(
    *,
    document: str,
    sha: str,
    index: int,
    total: int,
    content: str,
    category: str = "老年用药",
) -> EmbeddedChunk:
    chunk_id = hashlib.sha256(f"{document}:{sha}:{index}:{content}".encode()).hexdigest()
    chunk = IndexChunk(
        chunk_id=chunk_id,
        document_id=hashlib.sha256(document.encode()).hexdigest(),
        document_sha256=sha,
        source=f"{category}/{document}.md",
        title=document,
        chapter=f"章节 {index + 1}",
        category=category,
        source_type="guideline",
        publish_year=2024,
        chunk_index=index,
        total_chunks=total,
        content=content,
    )
    vector = (1.0, 0.0, 0.0, 0.0) if index == 0 else (0.0, 1.0, 0.0, 0.0)
    return EmbeddedChunk(chunk=chunk, dense_vector=vector)


@pytest.mark.asyncio
async def test_index_lock_prevents_failed_worker_from_deleting_successful_generation(
    tmp_path: Path,
) -> None:
    """A failed writer must release the lock before another writer stages the same IDs."""

    source = tmp_path / "并发索引指南.md"
    source.write_text(
        "# 并发索引指南\n\n## 证据\n\n" + "老年医学循证内容。" * 800, encoding="utf-8"
    )
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantHybridStore(
        client,
        collection="serialized_failure",
        dimensions=4,
        upsert_batch_size=1,
    )
    parser = MarkdownMedicalParser(tmp_path, max_document_bytes=1_000_000)
    chunker = MedicalMarkdownChunker(
        min_tokens=64,
        target_tokens=96,
        max_tokens=128,
        overlap_tokens=16,
    )
    indexer = CorpusIndexer(
        parser=parser,
        chunker=chunker,
        embedding_model=_DeterministicEmbedding(),  # type: ignore[arg-type]
        store=store,
        index_lock=InProcessRAGIndexLock(),
    )
    original_upsert = client.upsert
    first_batch_written = asyncio.Event()
    continue_failed_worker = asyncio.Event()
    calls: dict[str, int] = {}

    async def fail_worker_a_second_batch(*args: object, **kwargs: object) -> object:
        task = asyncio.current_task()
        name = task.get_name() if task is not None else "unknown"
        calls[name] = calls.get(name, 0) + 1
        if name == "index-worker-a" and calls[name] == 2:
            raise RuntimeError("injected concurrent writer interruption")
        result = await original_upsert(*args, **kwargs)  # type: ignore[arg-type]
        if name == "index-worker-a" and calls[name] == 1:
            first_batch_written.set()
            await continue_failed_worker.wait()
        return result

    client.upsert = fail_worker_a_second_batch  # type: ignore[method-assign]
    first_task = asyncio.create_task(indexer.index_path(source), name="index-worker-a")
    try:
        await asyncio.wait_for(first_batch_written.wait(), timeout=2)
        second_task = asyncio.create_task(indexer.index_path(source), name="index-worker-b")
        await asyncio.sleep(0)
        continue_failed_worker.set()
        first_result, second_result = await asyncio.gather(
            first_task,
            second_task,
            return_exceptions=True,
        )

        assert isinstance(first_result, RuntimeError)
        assert isinstance(second_result, int) and second_result > 1
        manifest = await store.manifest()
        assert manifest["并发索引指南.md"].chunk_count == second_result
        assert await store.stats() == (1, second_result)
        hits = await store.search(
            dense_vector=[1.0, 0.0, 0.0, 0.0],
            lexical_query="老年医学循证内容",
            limit=3,
            filters=None,
        )
        assert hits
    finally:
        continue_failed_worker.set()
        client.upsert = original_upsert  # type: ignore[method-assign]
        await client.close()


@pytest.mark.asyncio
async def test_late_cancelled_writer_upsert_cannot_overwrite_the_new_generation() -> None:
    """A remotely committed old upsert uses fenced IDs and remains non-searchable."""

    client = AsyncQdrantClient(location=":memory:")
    store = QdrantHybridStore(client, collection="late_upsert", dimensions=4, upsert_batch_size=1)
    writer_a = tuple(
        _embedded(
            document="远端晚提交指南",
            sha="a" * 64,
            index=index,
            total=3,
            content=f"旧 writer 暂存证据 {index}",
        )
        for index in range(3)
    )
    writer_b = tuple(
        _embedded(
            document="远端晚提交指南",
            sha="b" * 64,
            index=index,
            total=3,
            content=f"新 writer 完整证据 {index}",
        )
        for index in range(3)
    )
    original_upsert = client.upsert
    request_accepted = asyncio.Event()
    commit_late = asyncio.Event()
    remote_commit: asyncio.Task[object] | None = None

    async def accept_then_commit_after_cancellation(*args: object, **kwargs: object) -> object:
        nonlocal remote_commit

        async def commit() -> object:
            await commit_late.wait()
            return await original_upsert(*args, **kwargs)  # type: ignore[arg-type]

        remote_commit = asyncio.create_task(commit())
        request_accepted.set()
        await asyncio.Future()

    try:
        client.upsert = accept_then_commit_after_cancellation  # type: ignore[method-assign]
        cancelled_writer = asyncio.create_task(
            store.replace_document(
                writer_a,
                index_version="test-fenced",
                generation_id=_GENERATION_WRITER_A,
            )
        )
        await asyncio.wait_for(request_accepted.wait(), timeout=2)
        cancelled_writer.cancel()
        result = (await asyncio.gather(cancelled_writer, return_exceptions=True))[0]
        assert isinstance(result, asyncio.CancelledError)

        client.upsert = original_upsert  # type: ignore[method-assign]
        await store.replace_document(
            writer_b,
            index_version="test-fenced",
            generation_id=_GENERATION_WRITER_B,
        )
        commit_late.set()
        assert remote_commit is not None
        await remote_commit

        assert await store.stats() == (1, 3)
        manifest = await store.manifest()
        assert manifest["老年用药/远端晚提交指南.md"].document_sha256 == "b" * 64
        hits = await store.search(
            dense_vector=[1.0, 0.0, 0.0, 0.0],
            lexical_query="新 writer 完整证据",
            limit=10,
            filters=None,
        )
        assert hits and all("新 writer" in hit.chunk.content for hit in hits)
        assert await store.delete_incomplete_points() == 1
        assert await store.delete_incomplete_points() == 0
        assert await store.stats() == (1, 3)
    finally:
        commit_late.set()
        client.upsert = original_upsert  # type: ignore[method-assign]
        if remote_commit is not None:
            await asyncio.gather(remote_commit, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_late_cancelled_writer_delete_cannot_remove_future_generation() -> None:
    """Stale cleanup snapshots explicit IDs before delete, fencing future points."""

    client = AsyncQdrantClient(location=":memory:")
    store = QdrantHybridStore(client, collection="late_delete", dimensions=4, upsert_batch_size=1)
    old = (
        _embedded(
            document="延迟删除指南",
            sha="1" * 64,
            index=0,
            total=1,
            content="历史完整证据",
        ),
    )
    writer_a = tuple(
        _embedded(
            document="延迟删除指南",
            sha="a" * 64,
            index=index,
            total=2,
            content=f"旧 writer 激活证据 {index}",
        )
        for index in range(2)
    )
    writer_b = tuple(
        _embedded(
            document="延迟删除指南",
            sha="b" * 64,
            index=index,
            total=3,
            content=f"新 writer 最终证据 {index}",
        )
        for index in range(3)
    )
    original_delete = client.delete
    request_accepted = asyncio.Event()
    commit_late = asyncio.Event()
    remote_commit: asyncio.Task[object] | None = None

    async def accept_snapshot_then_delete_late(*args: object, **kwargs: object) -> object:
        nonlocal remote_commit

        async def commit() -> object:
            await commit_late.wait()
            return await original_delete(*args, **kwargs)  # type: ignore[arg-type]

        remote_commit = asyncio.create_task(commit())
        request_accepted.set()
        await asyncio.Future()

    try:
        await store.replace_document(
            old,
            index_version="test-old",
            generation_id=_GENERATION_OLD,
        )
        client.delete = accept_snapshot_then_delete_late  # type: ignore[method-assign]
        cancelled_writer = asyncio.create_task(
            store.replace_document(
                writer_a,
                index_version="test-fenced",
                generation_id=_GENERATION_WRITER_A,
            )
        )
        await asyncio.wait_for(request_accepted.wait(), timeout=2)
        cancelled_writer.cancel()
        result = (await asyncio.gather(cancelled_writer, return_exceptions=True))[0]
        assert isinstance(result, asyncio.CancelledError)

        client.delete = original_delete  # type: ignore[method-assign]
        await store.replace_document(
            writer_b,
            index_version="test-fenced",
            generation_id=_GENERATION_WRITER_B,
        )
        assert await store.stats() == (1, 3)
        commit_late.set()
        assert remote_commit is not None
        await remote_commit

        assert await store.stats() == (1, 3)
        manifest = await store.manifest()
        assert manifest["老年用药/延迟删除指南.md"].document_sha256 == "b" * 64
        hits = await store.search(
            dense_vector=[1.0, 0.0, 0.0, 0.0],
            lexical_query="新 writer 最终证据",
            limit=10,
            filters=None,
        )
        assert hits and all("新 writer" in hit.chunk.content for hit in hits)
    finally:
        commit_late.set()
        client.delete = original_delete  # type: ignore[method-assign]
        if remote_commit is not None:
            await asyncio.gather(remote_commit, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_removed_source_deletes_all_points_when_safe_manifest_is_ambiguous(
    tmp_path: Path,
) -> None:
    """Removed detection uses full inventory even when two generations block safe skip."""

    source = tmp_path / "已撤回医学指南.md"
    source.write_text("# 已撤回医学指南\n\n" + "第一版医学证据。" * 300, encoding="utf-8")
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantHybridStore(
        client,
        collection="removed_ambiguous",
        dimensions=4,
        upsert_batch_size=4,
    )
    indexer = CorpusIndexer(
        parser=MarkdownMedicalParser(tmp_path, max_document_bytes=1_000_000),
        chunker=MedicalMarkdownChunker(
            min_tokens=64,
            target_tokens=96,
            max_tokens=128,
            overlap_tokens=16,
        ),
        embedding_model=_DeterministicEmbedding(),  # type: ignore[arg-type]
        store=store,
        index_lock=InProcessRAGIndexLock(),
    )
    try:
        first = await indexer.sync()
        assert first.indexed == 1 and first.failed == 0
        source.write_text("# 已撤回医学指南\n\n" + "第二版医学证据。" * 300, encoding="utf-8")
        original_cleanup = store._delete_stale_points

        async def unavailable_cleanup(*_args: object, **_kwargs: object) -> None:
            raise TimeoutError("injected cleanup outage before source removal")

        store._delete_stale_points = unavailable_cleanup  # type: ignore[method-assign]
        ambiguous = await indexer.sync()
        assert ambiguous.failed == 1
        assert await store.manifest() == {}
        assert (await store.stats())[0] == 2
        inventory = await store.document_inventory()
        assert set(inventory) == {"已撤回医学指南.md"}
        assert len(inventory["已撤回医学指南.md"]) == 1

        store._delete_stale_points = original_cleanup  # type: ignore[method-assign]
        source.unlink()
        removed = await indexer.sync()

        assert removed.discovered == 0
        assert removed.deleted == 1
        assert removed.failed == 0
        assert await store.stats() == (0, 0)
        assert await store.manifest() == {}
        assert await store.document_inventory() == {}
        assert not await store.search(
            dense_vector=[1.0, 0.0, 0.0, 0.0],
            lexical_query="已撤回医学指南",
            limit=10,
            filters=None,
        )
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_store_replaces_searches_filters_and_deletes_documents() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantHybridStore(client, collection="test_rag", dimensions=4, upsert_batch_size=1)
    first = (
        _embedded(
            document="多重用药指南",
            sha="a" * 64,
            index=0,
            total=2,
            content="老年患者多重用药应审查药物相互作用。",
        ),
        _embedded(
            document="多重用药指南",
            sha="a" * 64,
            index=1,
            total=2,
            content="结合肾功能调整药物剂量并评估跌倒风险。",
        ),
    )
    second = (
        _embedded(
            document="营养支持指南",
            sha="b" * 64,
            index=0,
            total=1,
            content="老年营养不良需要筛查和个体化营养支持。",
            category="老年营养",
        ),
    )
    try:
        await store.replace_document(first, index_version="test-v1", generation_id=_GENERATION_OLD)
        await store.replace_document(second, index_version="test-v1", generation_id=_GENERATION_OLD)

        assert await store.stats() == (2, 3)
        manifest = await store.manifest()
        assert set(manifest) == {"老年用药/多重用药指南.md", "老年营养/营养支持指南.md"}
        assert manifest["老年用药/多重用药指南.md"].chunk_count == 2

        hits = await store.search(
            dense_vector=[1.0, 0.0, 0.0, 0.0],
            lexical_query="老年多重用药风险",
            limit=5,
            filters=RAGFilters(categories=["老年用药"], publish_year_min=2020),
        )
        assert hits
        assert all(hit.chunk.category == "老年用药" for hit in hits)
        assert hits[0].chunk.source == "老年用药/多重用药指南.md"

        replacement = (
            _embedded(
                document="多重用药指南",
                sha="c" * 64,
                index=0,
                total=1,
                content="新版指南要求同步评估处方级联和抗胆碱能负荷。",
            ),
        )
        await store.replace_document(
            replacement, index_version="test-v2", generation_id=_GENERATION_NEW
        )
        assert await store.stats() == (2, 2)
        assert (await store.manifest())["老年用药/多重用药指南.md"].document_sha256 == "c" * 64

        assert await store.delete_documents([second[0].chunk.document_id]) == 1
        assert await store.delete_documents([]) == 0
        assert await store.stats() == (1, 1)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_store_rejects_inconsistent_vectors_and_collection_schema() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantHybridStore(client, collection="valid", dimensions=4, upsert_batch_size=10)
    invalid = _embedded(
        document="用药指南",
        sha="d" * 64,
        index=0,
        total=1,
        content="证据",
    )
    try:
        with pytest.raises(ValueError, match="at least one"):
            await store.replace_document((), index_version="test-v1", generation_id=_GENERATION_OLD)
        with pytest.raises(RAGStoreError, match="inconsistent"):
            await store.replace_document(
                (EmbeddedChunk(chunk=invalid.chunk, dense_vector=(1.0, 0.0)),),
                index_version="test-v1",
                generation_id=_GENERATION_OLD,
            )

        await client.create_collection(
            collection_name="wrong",
            vectors_config={"dense": models.VectorParams(size=3, distance=models.Distance.COSINE)},
            sparse_vectors_config={
                "lexical": models.SparseVectorParams(index=models.SparseIndexParams())
            },
        )
        wrong = QdrantHybridStore(client, collection="wrong", dimensions=4, upsert_batch_size=10)
        with pytest.raises(RAGStoreError, match="dimensions"):
            await wrong.ensure_collection()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_store_recovers_after_partial_generation_upsert_failure() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantHybridStore(client, collection="recoverable", dimensions=4, upsert_batch_size=1)
    old = (
        _embedded(
            document="跌倒风险指南",
            sha="e" * 64,
            index=0,
            total=2,
            content="旧版证据一。",
        ),
        _embedded(
            document="跌倒风险指南",
            sha="e" * 64,
            index=1,
            total=2,
            content="旧版证据二。",
        ),
    )
    replacement = tuple(
        _embedded(
            document="跌倒风险指南",
            sha="f" * 64,
            index=index,
            total=3,
            content=f"新版证据 {index}",
        )
        for index in range(3)
    )
    try:
        await store.replace_document(old, index_version="test-v1", generation_id=_GENERATION_OLD)
        original_upsert = client.upsert
        calls = 0

        async def fail_second_batch(*args: object, **kwargs: object) -> object:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected qdrant interruption")
            return await original_upsert(*args, **kwargs)  # type: ignore[arg-type]

        client.upsert = fail_second_batch  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="injected qdrant interruption"):
            await store.replace_document(
                replacement, index_version="test-v2", generation_id=_GENERATION_NEW
            )

        client.upsert = original_upsert  # type: ignore[method-assign]
        manifest_after_failure = await store.manifest()
        assert manifest_after_failure["老年用药/跌倒风险指南.md"].document_sha256 == "e" * 64
        assert await store.stats() == (1, 2)

        await store.replace_document(
            replacement, index_version="test-v2", generation_id=_GENERATION_NEW
        )
        recovered = await store.manifest()
        assert recovered["老年用药/跌倒风险指南.md"].document_sha256 == "f" * 64
        assert recovered["老年用药/跌倒风险指南.md"].chunk_count == 3
        assert await store.stats() == (1, 3)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_store_preserves_new_generation_when_stale_delete_ack_is_lost() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantHybridStore(client, collection="lost_ack", dimensions=4, upsert_batch_size=1)
    old = (
        _embedded(
            document="用药安全指南",
            sha="1" * 64,
            index=0,
            total=1,
            content="旧版用药证据。",
        ),
    )
    replacement = tuple(
        _embedded(
            document="用药安全指南",
            sha="2" * 64,
            index=index,
            total=3,
            content=f"新版用药证据 {index}。",
        )
        for index in range(3)
    )
    try:
        await store.replace_document(old, index_version="test-v1", generation_id=_GENERATION_OLD)
        original_cleanup = store._delete_stale_points
        calls = 0

        async def delete_then_lose_ack(*args: object, **kwargs: object) -> None:
            nonlocal calls
            calls += 1
            await original_cleanup(*args, **kwargs)  # type: ignore[arg-type]
            if calls == 1:
                raise TimeoutError("injected lost acknowledgement")

        store._delete_stale_points = delete_then_lose_ack  # type: ignore[method-assign]
        await store.replace_document(
            replacement, index_version="test-v2", generation_id=_GENERATION_NEW
        )

        assert calls == 2
        manifest = await store.manifest()
        assert manifest["老年用药/用药安全指南.md"].document_sha256 == "2" * 64
        assert await store.stats() == (1, 3)
        hits = await store.search(
            dense_vector=[1.0, 0.0, 0.0, 0.0],
            lexical_query="新版用药证据",
            limit=3,
            filters=None,
        )
        assert hits
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_store_retries_a_complete_generation_with_pending_stale_cleanup() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantHybridStore(
        client,
        collection="pending_cleanup",
        dimensions=4,
        upsert_batch_size=1,
    )
    old = (
        _embedded(
            document="慢病管理指南",
            sha="3" * 64,
            index=0,
            total=1,
            content="旧版慢病证据。",
        ),
    )
    replacement = tuple(
        _embedded(
            document="慢病管理指南",
            sha="4" * 64,
            index=index,
            total=2,
            content=f"新版慢病证据 {index}。",
        )
        for index in range(2)
    )
    try:
        await store.replace_document(old, index_version="test-v1", generation_id=_GENERATION_OLD)
        original_cleanup = store._delete_stale_points

        async def unavailable_cleanup(*_args: object, **_kwargs: object) -> None:
            raise TimeoutError("injected cleanup outage")

        store._delete_stale_points = unavailable_cleanup  # type: ignore[method-assign]
        with pytest.raises(RAGStoreError, match="cleanup remains pending"):
            await store.replace_document(
                replacement, index_version="test-v2", generation_id=_GENERATION_NEW
            )

        assert await store.stats() == (2, 3)
        assert await store.manifest() == {}
        assert await store.search(
            dense_vector=[1.0, 0.0, 0.0, 0.0],
            lexical_query="慢病证据",
            limit=3,
            filters=None,
        )

        store._delete_stale_points = original_cleanup  # type: ignore[method-assign]
        await store.replace_document(
            replacement, index_version="test-v2", generation_id=_GENERATION_NEW
        )
        recovered = await store.manifest()
        assert recovered["老年用药/慢病管理指南.md"].document_sha256 == "4" * 64
        assert await store.stats() == (1, 2)
    finally:
        await client.close()
