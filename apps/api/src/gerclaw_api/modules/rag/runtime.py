"""Dependency-injected construction and lifecycle for the RAG building blocks."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import SecretStr
from qdrant_client import AsyncQdrantClient

from gerclaw_api.config import Settings
from gerclaw_api.modules.rag.indexer import CorpusIndexer
from gerclaw_api.modules.rag.locking import PostgresAdvisoryRAGIndexLock
from gerclaw_api.modules.rag.module import HybridRAGModule
from gerclaw_api.modules.rag.parser import MarkdownMedicalParser, MedicalMarkdownChunker
from gerclaw_api.modules.rag.providers import SiliconFlowEmbeddingModel, SiliconFlowReranker
from gerclaw_api.modules.rag.store import QdrantHybridStore


@dataclass(slots=True)
class RAGRuntime:
    """Owned providers plus independently injectable module/indexer handles."""

    module: HybridRAGModule
    indexer: CorpusIndexer
    embedding_model: SiliconFlowEmbeddingModel
    reranker: SiliconFlowReranker
    store: QdrantHybridStore

    async def aclose(self) -> None:
        """Close external provider pools; Qdrant lifecycle belongs to the application."""

        await self.embedding_model.aclose()
        await self.reranker.aclose()


def create_rag_runtime(settings: Settings, qdrant_client: AsyncQdrantClient) -> RAGRuntime:
    """Construct the production RAG graph from validated environment settings."""

    if not settings.embedding_supports_batch:
        raise ValueError("configured embedding provider does not support required batch embeddings")
    if not settings.rerank_supports_relevance_scores:
        raise ValueError("configured rerank provider does not support required relevance scores")
    if (
        settings.siliconflow_url is None
        or settings.siliconflow_api_key is None
        or settings.embedding_model is None
        or settings.rerank_model is None
    ):
        raise ValueError("SiliconFlow embedding and rerank configuration is required for RAG")
    api_key = SecretStr(settings.siliconflow_api_key.get_secret_value())
    embedding = SiliconFlowEmbeddingModel(
        base_url=str(settings.siliconflow_url),
        api_key=api_key,
        model=settings.embedding_model,
        dimensions=settings.rag_embedding_dimensions,
        batch_size=settings.rag_embedding_batch_size,
        concurrency=settings.rag_embedding_concurrency,
        timeout_seconds=settings.external_request_timeout_seconds,
        tokens_per_minute=settings.rag_embedding_tokens_per_minute,
    )
    reranker = SiliconFlowReranker(
        base_url=str(settings.siliconflow_url),
        api_key=api_key,
        model=settings.rerank_model,
        timeout_seconds=settings.external_request_timeout_seconds,
    )
    parser = MarkdownMedicalParser(
        settings.knowledge_base_path,
        max_document_bytes=settings.rag_max_document_bytes,
    )
    chunker = MedicalMarkdownChunker(
        min_tokens=settings.rag_chunk_min_tokens,
        target_tokens=settings.rag_chunk_target_tokens,
        max_tokens=settings.rag_chunk_max_tokens,
        overlap_tokens=settings.rag_chunk_overlap_tokens,
    )
    store = QdrantHybridStore(
        qdrant_client,
        collection=settings.rag_collection_name,
        dimensions=settings.rag_embedding_dimensions,
        upsert_batch_size=settings.rag_upsert_batch_size,
    )
    indexer = CorpusIndexer(
        parser=parser,
        chunker=chunker,
        embedding_model=embedding,
        store=store,
        index_lock=PostgresAdvisoryRAGIndexLock(settings.database_url),
    )
    module = HybridRAGModule(
        parser=parser,
        embedding_model=embedding,
        reranker=reranker,
        store=store,
        indexer=indexer,
        retrieval_candidates=settings.rag_retrieval_candidates,
        rerank_candidates=settings.rag_rerank_candidates,
        min_rerank_score=settings.rag_min_rerank_score,
        capability_version=settings.rag_capability_version,
    )
    return RAGRuntime(
        module=module,
        indexer=indexer,
        embedding_model=embedding,
        reranker=reranker,
        store=store,
    )
