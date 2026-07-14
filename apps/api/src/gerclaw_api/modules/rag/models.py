"""Internal immutable records for deterministic RAG indexing and retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SourceType = Literal["guideline", "consensus", "textbook", "literature"]


@dataclass(frozen=True, slots=True)
class ParsedSection:
    """One Markdown heading section before bounded chunking."""

    chapter: str
    text: str


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Validated local Markdown document with relative provenance only."""

    document_id: str
    source: str
    title: str
    category: str
    source_type: SourceType
    publish_year: int | None
    sha256: str
    size_bytes: int
    modified_ns: int
    sections: tuple[ParsedSection, ...]


@dataclass(frozen=True, slots=True)
class IndexChunk:
    """One deterministic text unit ready for embedding."""

    chunk_id: str
    document_id: str
    document_sha256: str
    source: str
    title: str
    chapter: str
    category: str
    source_type: SourceType
    publish_year: int | None
    chunk_index: int
    total_chunks: int
    content: str


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """Index chunk paired with its validated dense vector."""

    chunk: IndexChunk
    dense_vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class StoredCandidate:
    """Hybrid Qdrant hit before external reranking."""

    chunk: IndexChunk
    hybrid_score: float


@dataclass(frozen=True, slots=True)
class DocumentManifest:
    """Minimal collection manifest used by incremental synchronization."""

    document_id: str
    source: str
    document_sha256: str
    chunk_count: int
    index_version: str


@dataclass(frozen=True, slots=True)
class IndexSyncReport:
    """Bounded result of a complete corpus reconciliation run."""

    discovered: int
    indexed: int
    skipped: int
    deleted: int
    failed: int
    chunks_written: int
    failures: tuple[str, ...]
