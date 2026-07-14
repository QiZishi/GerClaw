"""Local medical Agentic RAG public surface."""

from gerclaw_api.modules.rag.agentscope_adapter import build_agentic_rag_middleware
from gerclaw_api.modules.rag.module import HybridRAGModule, RAGUnavailableError
from gerclaw_api.modules.rag.protocols import (
    IndexResult,
    RAGFilters,
    RAGModule,
    RAGStatus,
    RetrievalResult,
)
from gerclaw_api.modules.rag.runtime import RAGRuntime, create_rag_runtime

__all__ = [
    "HybridRAGModule",
    "IndexResult",
    "RAGFilters",
    "RAGModule",
    "RAGRuntime",
    "RAGStatus",
    "RAGUnavailableError",
    "RetrievalResult",
    "build_agentic_rag_middleware",
    "create_rag_runtime",
]
