"""Dependency-injected Memory runtime construction."""

from __future__ import annotations

import uuid

from qdrant_client import AsyncQdrantClient

from gerclaw_api.config import Settings
from gerclaw_api.modules.memory.compressor import AgentScopeContextCompressor
from gerclaw_api.modules.memory.extractor import RealMemoryExtractor
from gerclaw_api.modules.memory.memory_module import ProductionMemoryModule
from gerclaw_api.modules.memory.store import QdrantMemoryStore
from gerclaw_api.modules.rag.providers import SiliconFlowEmbeddingModel
from gerclaw_api.repositories.memory import MemoryRepository
from gerclaw_api.services.model_router import FailoverChatModel


def create_memory_store(settings: Settings, qdrant_client: AsyncQdrantClient) -> QdrantMemoryStore:
    """Create the shared stateless vector boundary; user state stays in PostgreSQL."""

    return QdrantMemoryStore(
        qdrant_client,
        collection=settings.memory_collection_name,
        dimensions=settings.rag_embedding_dimensions,
        min_score=settings.memory_min_score,
    )


def create_memory_module(
    *,
    settings: Settings,
    repository: MemoryRepository,
    model: FailoverChatModel,
    embedding_model: SiliconFlowEmbeddingModel,
    vector_store: QdrantMemoryStore,
    tenant_id: str,
    actor_id: str,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    trace_id: str,
) -> ProductionMemoryModule:
    """Build one turn-scoped Memory graph from shared provider clients."""

    return ProductionMemoryModule(
        repository=repository,
        extractor=RealMemoryExtractor(
            model,
            min_confidence=settings.memory_extraction_min_confidence,
            max_facts=settings.memory_max_facts_per_turn,
        ),
        compressor=AgentScopeContextCompressor(model),
        embedding_model=embedding_model,
        vector_store=vector_store,
        namespace_secret=settings.auth_jwt_secret.get_secret_value().encode(),
        tenant_id=tenant_id,
        actor_id=actor_id,
        user_id=user_id,
        session_id=session_id,
        trace_id=trace_id,
        retrieval_top_k=settings.memory_retrieval_top_k,
        retrieval_candidates=settings.memory_retrieval_candidates,
    )
