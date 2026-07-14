"""Chapter 4.7 RAG retrieval and indexing interface."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.security import JsonValue


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8_000)
    source: str = Field(min_length=1, max_length=1_024)
    score: float = Field(ge=0)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class IndexResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    document_id: str | None = None
    chunk_count: int = Field(default=0, ge=0)
    error_code: str | None = None


class RAGModule(Protocol):
    """Local-first hybrid retrieval, reranking, and document indexing boundary."""

    async def retrieve(
        self, query: str, top_k: int = 5, filters: dict[str, JsonValue] | None = None
    ) -> list[RetrievalResult]:
        """Retrieve reranked evidence with provenance."""

    async def index_document(self, file_path: str, doc_type: str) -> IndexResult:
        """Validate, chunk, embed, and index one document."""
