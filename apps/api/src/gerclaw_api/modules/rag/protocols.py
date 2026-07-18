"""Chapter 4.7 RAG retrieval and indexing interface."""

from __future__ import annotations

import string
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.security import JsonValue


class RetrievalResult(BaseModel):
    """One reranked local evidence chunk with a stable citation locator."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8_000)
    source: str = Field(min_length=1, max_length=1_024)
    score: float = Field(ge=0, le=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_absolute_source(self) -> RetrievalResult:
        if self.source.startswith(("/", "\\")) or ".." in self.source.split("/"):
            raise ValueError("retrieval source must be a safe knowledge-base-relative path")
        return self


class RAGFilters(BaseModel):
    """Allowlisted Qdrant filters; callers cannot inject arbitrary payload paths."""

    model_config = ConfigDict(extra="forbid")

    categories: list[str] = Field(default_factory=list, max_length=10)
    source_types: list[Literal["guideline", "consensus", "textbook", "literature"]] = Field(
        default_factory=list,
        max_length=4,
    )
    publish_year_min: int | None = Field(default=None, ge=1900, le=2100)
    publish_year_max: int | None = Field(default=None, ge=1900, le=2100)
    document_ids: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_ranges_and_identifiers(self) -> RAGFilters:
        if (
            self.publish_year_min is not None
            and self.publish_year_max is not None
            and self.publish_year_min > self.publish_year_max
        ):
            raise ValueError("publish_year_min cannot exceed publish_year_max")
        if any(not value.strip() or len(value) > 128 for value in self.categories):
            raise ValueError("categories must contain bounded non-empty values")
        if any(
            len(value) != 64 or any(character not in string.hexdigits for character in value)
            for value in self.document_ids
        ):
            raise ValueError("document_ids must be 64-character hexadecimal identifiers")
        return self


class RAGStatus(BaseModel):
    """Safe operational status for the local medical corpus."""

    model_config = ConfigDict(extra="forbid")

    ready: bool
    collection: str
    source_documents: int = Field(ge=0)
    indexed_documents: int = Field(ge=0)
    indexed_chunks: int = Field(ge=0)
    capability_version: str = Field(default="rag-capabilities-v1", pattern=r"^[a-z][a-z0-9_.-]+$")
    embedding_model: str
    rerank_model: str
    retrieval_mode: Literal["agentic_hybrid_rrf_rerank"] = "agentic_hybrid_rrf_rerank"


class IndexResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    document_id: str | None = None
    chunk_count: int = Field(default=0, ge=0)
    error_code: str | None = None


class RAGModule(Protocol):
    """Local-first hybrid retrieval, reranking, and document indexing boundary."""

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: RAGFilters | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve reranked evidence with provenance."""

    async def index_document(self, file_path: str, doc_type: str) -> IndexResult:
        """Validate, chunk, embed, and index one document."""

    async def status(self) -> RAGStatus:
        """Return source/index parity without exposing connection details."""
