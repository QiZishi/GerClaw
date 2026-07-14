"""Idempotent corpus reconciliation using real embedding and Qdrant services."""

from __future__ import annotations

import logging
from pathlib import Path

from gerclaw_api.metrics import RAG_INDEX_CHUNKS, RAG_INDEX_DOCUMENTS
from gerclaw_api.modules.rag.lexical import LexicalEncoder
from gerclaw_api.modules.rag.locking import RAGIndexLock
from gerclaw_api.modules.rag.models import EmbeddedChunk, IndexChunk, IndexSyncReport
from gerclaw_api.modules.rag.parser import MarkdownMedicalParser, MedicalMarkdownChunker
from gerclaw_api.modules.rag.providers import SiliconFlowEmbeddingModel
from gerclaw_api.modules.rag.store import QdrantHybridStore

LOGGER = logging.getLogger(__name__)


class CorpusIndexer:
    """Synchronize one immutable-file corpus into a versioned hybrid collection."""

    def __init__(
        self,
        *,
        parser: MarkdownMedicalParser,
        chunker: MedicalMarkdownChunker,
        embedding_model: SiliconFlowEmbeddingModel,
        store: QdrantHybridStore,
        index_lock: RAGIndexLock,
    ) -> None:
        self._parser = parser
        self._chunker = chunker
        self._embedding_model = embedding_model
        self._store = store
        self._index_lock = index_lock
        self.index_version = ":".join(
            (
                self._chunker.INDEX_VERSION,
                LexicalEncoder.VERSION,
                self._embedding_model.model,
                str(self._embedding_model.dimensions),
            )
        )

    async def embed_chunks(self, chunks: tuple[IndexChunk, ...]) -> tuple[EmbeddedChunk, ...]:
        """Embed all chunks and validate one-to-one ordering and dimensions."""

        response = await self._embedding_model([chunk.content for chunk in chunks])
        if len(response.embeddings) != len(chunks):
            raise RuntimeError("embedding response count did not match the document chunk count")
        return tuple(
            EmbeddedChunk(chunk=chunk, dense_vector=tuple(vector))
            for chunk, vector in zip(chunks, response.embeddings, strict=True)
        )

    async def index_path(self, path: Path) -> int:
        """Serialize and index one document through the production mutation path."""

        async with self._index_lock.hold() as generation_id:
            return await self._index_path(path, generation_id=generation_id)

    async def _index_path(self, path: Path, *, generation_id: str) -> int:
        """Parse, chunk, embed, and atomically-version one document as far as Qdrant permits."""

        document = await self._parser.parse(path)
        chunks = self._chunker.chunk(document)
        embedded = await self.embed_chunks(chunks)
        await self._store.replace_document(
            embedded,
            index_version=self.index_version,
            generation_id=generation_id,
        )
        return len(chunks)

    async def sync(self) -> IndexSyncReport:
        """Serialize a full-corpus reconciliation across every API/index worker."""

        async with self._index_lock.hold() as generation_id:
            return await self._sync(generation_id=generation_id)

    async def _sync(self, *, generation_id: str) -> IndexSyncReport:
        """Reconcile every source while retaining old data after pre-upsert failures."""

        paths = await self._parser.discover()
        await self._store.ensure_collection()
        abandoned_staging = await self._store.delete_incomplete_points()
        if abandoned_staging:
            LOGGER.warning(
                "rag_abandoned_staging_deleted",
                extra={"chunks_deleted": abandoned_staging},
            )
        existing = await self._store.manifest()
        inventory = await self._store.document_inventory()
        current_sources: set[str] = set()
        indexed = 0
        skipped = 0
        failed = 0
        chunks_written = 0
        failures: list[str] = []

        for position, path in enumerate(paths, start=1):
            source = path.relative_to(self._parser.root).as_posix()
            current_sources.add(source)
            try:
                document = await self._parser.parse(path)
                chunks = self._chunker.chunk(document)
                manifest = existing.get(source)
                if (
                    manifest is not None
                    and manifest.document_sha256 == document.sha256
                    and manifest.index_version == self.index_version
                    and manifest.chunk_count == len(chunks)
                ):
                    skipped += 1
                    RAG_INDEX_DOCUMENTS.labels(outcome="skipped").inc()
                else:
                    embedded = await self.embed_chunks(chunks)
                    await self._store.replace_document(
                        embedded,
                        index_version=self.index_version,
                        generation_id=generation_id,
                    )
                    indexed += 1
                    chunks_written += len(chunks)
                    RAG_INDEX_DOCUMENTS.labels(outcome="indexed").inc()
                    RAG_INDEX_CHUNKS.inc(len(chunks))
                if position % 10 == 0 or position == len(paths):
                    LOGGER.info(
                        "rag_index_progress",
                        extra={
                            "discovered": len(paths),
                            "processed": position,
                            "indexed": indexed,
                            "skipped": skipped,
                            "failed": failed,
                            "chunks_written": chunks_written,
                        },
                    )
            except Exception as error:  # one bad source must not discard other indexed documents
                failed += 1
                RAG_INDEX_DOCUMENTS.labels(outcome="failed").inc()
                if len(failures) < 100:
                    failures.append(f"{source}:{type(error).__name__}")
                LOGGER.exception("rag_document_index_failed", extra={"source": source})

        removed = sorted(
            {
                document_id
                for source, document_ids in inventory.items()
                if source not in current_sources
                for document_id in document_ids
            }
        )
        deleted = await self._store.delete_documents(removed)
        if deleted:
            RAG_INDEX_DOCUMENTS.labels(outcome="deleted").inc(deleted)
        return IndexSyncReport(
            discovered=len(paths),
            indexed=indexed,
            skipped=skipped,
            deleted=deleted,
            failed=failed,
            chunks_written=chunks_written,
            failures=tuple(failures),
        )
