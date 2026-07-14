"""Production local-first hybrid retrieval implementation."""

from __future__ import annotations

import logging
from pathlib import Path

from gerclaw_api.modules.rag.indexer import CorpusIndexer
from gerclaw_api.modules.rag.parser import MarkdownMedicalParser, RAGDocumentError
from gerclaw_api.modules.rag.protocols import (
    IndexResult,
    RAGFilters,
    RAGStatus,
    RetrievalResult,
)
from gerclaw_api.modules.rag.providers import (
    RAGProviderError,
    SiliconFlowEmbeddingModel,
    SiliconFlowReranker,
)
from gerclaw_api.modules.rag.store import QdrantHybridStore, RAGStoreError

LOGGER = logging.getLogger(__name__)


class RAGUnavailableError(RuntimeError):
    """Safe API-facing signal for an unavailable retrieval pipeline."""


class HybridRAGModule:
    """BGE-M3 dense + lexical sparse RRF + BGE rerank over the local corpus."""

    def __init__(
        self,
        *,
        parser: MarkdownMedicalParser,
        embedding_model: SiliconFlowEmbeddingModel,
        reranker: SiliconFlowReranker,
        store: QdrantHybridStore,
        indexer: CorpusIndexer,
        retrieval_candidates: int,
        rerank_candidates: int,
        min_rerank_score: float,
    ) -> None:
        self._parser = parser
        self._embedding_model = embedding_model
        self._reranker = reranker
        self._store = store
        self._indexer = indexer
        self._retrieval_candidates = retrieval_candidates
        self._rerank_candidates = rerank_candidates
        self._min_rerank_score = min_rerank_score

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: RAGFilters | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve and rerank bounded evidence; never fall back to invented knowledge."""

        normalized = query.strip()
        if not normalized or len(normalized) > 4_000:
            raise ValueError("RAG query must contain 1 to 4,000 characters")
        if not 1 <= top_k <= 20:
            raise ValueError("RAG top_k must be between 1 and 20")
        embedding = await self._embedding_model([normalized])
        candidates = await self._store.search(
            dense_vector=embedding.embeddings[0],
            lexical_query=normalized,
            limit=self._retrieval_candidates,
            filters=filters,
        )
        candidates = candidates[: self._rerank_candidates]
        if not candidates:
            return []
        scores = await self._reranker.rerank(
            normalized,
            [candidate.chunk.content for candidate in candidates],
            top_n=min(top_k, len(candidates)),
        )
        results: list[RetrievalResult] = []
        for score in scores:
            if score.score < self._min_rerank_score:
                continue
            candidate = candidates[score.index]
            chunk = candidate.chunk
            metadata = {
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "title": chunk.title,
                "chapter": chunk.chapter,
                "category": chunk.category,
                "source_type": chunk.source_type,
                "publish_year": chunk.publish_year,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "hybrid_score": round(candidate.hybrid_score, 8),
                "rerank_score": round(score.score, 8),
            }
            results.append(
                RetrievalResult(
                    content=chunk.content,
                    source=chunk.source,
                    score=score.score,
                    metadata=metadata,
                )
            )
        return results

    async def index_document(self, file_path: str, doc_type: str) -> IndexResult:
        """Index one local Markdown path through the same production pipeline."""

        if doc_type.casefold() not in {"markdown", "text/markdown", "md"}:
            return IndexResult(ok=False, error_code="RAG_DOCUMENT_TYPE_UNSUPPORTED")
        try:
            document = await self._parser.parse(Path(file_path))
            chunks = await self._indexer.index_path(Path(file_path))
        except RAGDocumentError:
            return IndexResult(ok=False, error_code="RAG_DOCUMENT_INVALID")
        except (RAGProviderError, RAGStoreError):
            LOGGER.exception("rag_document_index_dependency_failed")
            return IndexResult(ok=False, error_code="RAG_INDEX_UNAVAILABLE")
        except Exception:
            LOGGER.exception("rag_document_index_failed")
            return IndexResult(ok=False, error_code="RAG_INDEX_FAILED")
        return IndexResult(ok=True, document_id=document.document_id, chunk_count=chunks)

    async def status(self) -> RAGStatus:
        """Compare source file count with exact indexed-document count."""

        sources = len(await self._parser.discover())
        documents, chunks = await self._store.stats()
        return RAGStatus(
            ready=sources > 0 and sources == documents and chunks >= documents,
            collection=self._store.collection,
            source_documents=sources,
            indexed_documents=documents,
            indexed_chunks=chunks,
            embedding_model=self._embedding_model.model,
            rerank_model=self._reranker.model,
        )
