"""RAG indexing and retrieval orchestration tests around validated boundaries."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from gerclaw_api.modules.rag.indexer import CorpusIndexer
from gerclaw_api.modules.rag.locking import InProcessRAGIndexLock
from gerclaw_api.modules.rag.models import (
    DocumentManifest,
    EmbeddedChunk,
    IndexChunk,
    StoredCandidate,
)
from gerclaw_api.modules.rag.module import HybridRAGModule
from gerclaw_api.modules.rag.parser import MarkdownMedicalParser, MedicalMarkdownChunker
from gerclaw_api.modules.rag.providers import RerankScore


class DeterministicEmbedding:
    model = "test-embedding"
    dimensions = 4

    def __init__(self, *, mismatch: bool = False) -> None:
        self.calls = 0
        self._mismatch = mismatch

    async def __call__(self, inputs: list[str]) -> Any:
        self.calls += 1
        count = max(0, len(inputs) - 1) if self._mismatch else len(inputs)
        return SimpleNamespace(embeddings=[[1.0, 0.0, 0.0, 0.0] for _ in range(count)])


class RecordingStore:
    collection = "test_rag"

    def __init__(self) -> None:
        self.manifests: dict[str, DocumentManifest] = {}
        self.replacements: list[tuple[EmbeddedChunk, ...]] = []
        self.deleted: list[str] = []
        self.candidates: list[StoredCandidate] = []

    async def ensure_collection(self) -> None:
        return None

    async def manifest(self) -> dict[str, DocumentManifest]:
        return dict(self.manifests)

    async def replace_document(
        self,
        chunks: tuple[EmbeddedChunk, ...],
        *,
        index_version: str,
        generation_id: str,
    ) -> None:
        assert generation_id
        self.replacements.append(chunks)
        first = chunks[0].chunk
        self.manifests[first.source] = DocumentManifest(
            document_id=first.document_id,
            source=first.source,
            document_sha256=first.document_sha256,
            chunk_count=len(chunks),
            index_version=index_version,
        )

    async def delete_documents(self, document_ids: list[str]) -> int:
        self.deleted.extend(document_ids)
        wanted = set(document_ids)
        self.manifests = {
            source: manifest
            for source, manifest in self.manifests.items()
            if manifest.document_id not in wanted
        }
        return len(wanted)

    async def delete_incomplete_points(self) -> int:
        return 0

    async def document_inventory(self) -> dict[str, set[str]]:
        inventory: dict[str, set[str]] = {}
        for manifest in self.manifests.values():
            inventory.setdefault(manifest.source, set()).add(manifest.document_id)
        return inventory

    async def search(self, **_kwargs: Any) -> list[StoredCandidate]:
        return list(self.candidates)

    async def stats(self) -> tuple[int, int]:
        return len(self.manifests), sum(item.chunk_count for item in self.manifests.values())


class DeterministicReranker:
    model = "test-reranker"

    async def rerank(self, _query: str, documents: list[str], *, top_n: int) -> list[RerankScore]:
        scores = [
            RerankScore(index=index, score=0.2 + index * 0.7) for index in range(len(documents))
        ]
        return sorted(scores, key=lambda item: item.score, reverse=True)[:top_n]


def _chunker() -> MedicalMarkdownChunker:
    return MedicalMarkdownChunker(
        min_tokens=128,
        target_tokens=192,
        max_tokens=256,
        overlap_tokens=32,
    )


def _candidate(index: int, content: str) -> StoredCandidate:
    document_id = hashlib.sha256(f"doc-{index}".encode()).hexdigest()
    chunk = IndexChunk(
        chunk_id=hashlib.sha256(f"chunk-{index}".encode()).hexdigest(),
        document_id=document_id,
        document_sha256="a" * 64,
        source=f"指南/文档{index}.md",
        title=f"文档{index}",
        chapter="风险评估",
        category="指南",
        source_type="guideline",
        publish_year=2024,
        chunk_index=0,
        total_chunks=1,
        content=content,
    )
    return StoredCandidate(chunk=chunk, hybrid_score=0.9 - index * 0.1)


@pytest.mark.asyncio
async def test_indexer_sync_is_incremental_and_removes_deleted_sources(tmp_path: Path) -> None:
    first = tmp_path / "用药指南.md"
    second = tmp_path / "营养指南.md"
    first.write_text("# 用药指南\n\n## 审查\n\n" + "评估药物相互作用。" * 80, encoding="utf-8")
    second.write_text("# 营养指南\n\n## 筛查\n\n" + "评估营养不良风险。" * 80, encoding="utf-8")
    parser = MarkdownMedicalParser(tmp_path, max_document_bytes=1_000_000)
    embedding = DeterministicEmbedding()
    store = RecordingStore()
    indexer = CorpusIndexer(
        parser=parser,
        chunker=_chunker(),
        embedding_model=embedding,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        index_lock=InProcessRAGIndexLock(),
    )

    initial = await indexer.sync()
    repeated = await indexer.sync()
    first.write_text("# 用药指南\n\n## 审查\n\n" + "评估处方级联风险。" * 80, encoding="utf-8")
    changed = await indexer.sync()
    second.unlink()
    removed = await indexer.sync()

    assert (initial.discovered, initial.indexed, initial.failed) == (2, 2, 0)
    assert repeated.skipped == 2
    assert changed.indexed == 1 and changed.skipped == 1
    assert removed.deleted == 1
    assert embedding.calls == 3
    assert len(store.manifests) == 1


@pytest.mark.asyncio
async def test_indexer_rejects_embedding_count_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "指南.md"
    source.write_text("# 指南\n\n" + "医学证据。" * 100, encoding="utf-8")
    parser = MarkdownMedicalParser(tmp_path, max_document_bytes=1_000_000)
    document = await parser.parse(source)
    chunks = _chunker().chunk(document)
    indexer = CorpusIndexer(
        parser=parser,
        chunker=_chunker(),
        embedding_model=DeterministicEmbedding(mismatch=True),  # type: ignore[arg-type]
        store=RecordingStore(),  # type: ignore[arg-type]
        index_lock=InProcessRAGIndexLock(),
    )

    with pytest.raises(RuntimeError, match="count did not match"):
        await indexer.embed_chunks(chunks)


@pytest.mark.asyncio
async def test_hybrid_module_reranks_filters_and_reports_status(tmp_path: Path) -> None:
    source = tmp_path / "指南.md"
    source.write_text("# 指南\n\n医学内容", encoding="utf-8")
    parser = MarkdownMedicalParser(tmp_path, max_document_bytes=1_000_000)
    embedding = DeterministicEmbedding()
    store = RecordingStore()
    store.candidates = [
        _candidate(0, "天气内容"),
        _candidate(1, "老年多重用药风险审查"),
    ]
    indexer = CorpusIndexer(
        parser=parser,
        chunker=_chunker(),
        embedding_model=embedding,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        index_lock=InProcessRAGIndexLock(),
    )
    module = HybridRAGModule(
        parser=parser,
        embedding_model=embedding,  # type: ignore[arg-type]
        reranker=DeterministicReranker(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        indexer=indexer,
        retrieval_candidates=10,
        rerank_candidates=5,
        min_rerank_score=0.5,
    )

    results = await module.retrieve("多重用药风险", top_k=2)

    assert len(results) == 1
    assert results[0].content == "老年多重用药风险审查"
    assert results[0].metadata["rerank_score"] == 0.9
    assert (await module.status()).ready is False

    store.candidates = []
    assert await module.retrieve("无结果查询") == []
    with pytest.raises(ValueError, match="1 to 4,000"):
        await module.retrieve("   ")
    with pytest.raises(ValueError, match="top_k"):
        await module.retrieve("有效查询", top_k=21)


@pytest.mark.asyncio
async def test_hybrid_module_indexes_only_valid_local_markdown(tmp_path: Path) -> None:
    source = tmp_path / "指南.md"
    source.write_text("# 指南\n\n" + "医学内容。" * 100, encoding="utf-8")
    parser = MarkdownMedicalParser(tmp_path, max_document_bytes=1_000_000)
    embedding = DeterministicEmbedding()
    store = RecordingStore()
    indexer = CorpusIndexer(
        parser=parser,
        chunker=_chunker(),
        embedding_model=embedding,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        index_lock=InProcessRAGIndexLock(),
    )
    module = HybridRAGModule(
        parser=parser,
        embedding_model=embedding,  # type: ignore[arg-type]
        reranker=DeterministicReranker(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        indexer=indexer,
        retrieval_candidates=10,
        rerank_candidates=5,
        min_rerank_score=0,
    )

    unsupported = await module.index_document(str(source), "application/pdf")
    invalid = await module.index_document(str(tmp_path / "missing.md"), "markdown")
    success = await module.index_document(str(source), "markdown")

    assert unsupported.error_code == "RAG_DOCUMENT_TYPE_UNSUPPORTED"
    assert invalid.error_code == "RAG_DOCUMENT_INVALID"
    assert success.ok is True and success.document_id and success.chunk_count > 0
