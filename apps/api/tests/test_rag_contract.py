"""RAG protocol surface and trust-boundary validation."""

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.rag.protocols import RAGFilters, RAGModule, RetrievalResult


def test_rag_exposes_retrieval_and_indexing_with_provenance() -> None:
    assert hasattr(RAGModule, "retrieve")
    assert hasattr(RAGModule, "index_document")
    result = RetrievalResult(content="evidence", source="local.md#one", score=0.8)
    assert result.source.startswith("local")


@pytest.mark.parametrize("source", ["/etc/passwd", "../private.md", "safe/../../private.md"])
def test_retrieval_result_rejects_unsafe_source_paths(source: str) -> None:
    with pytest.raises(ValidationError):
        RetrievalResult(content="evidence", source=source, score=0.8)


def test_rag_filters_reject_arbitrary_payloads_and_non_hex_document_ids() -> None:
    with pytest.raises(ValidationError):
        RAGFilters.model_validate({"payload_path": "tenant_secret"})
    with pytest.raises(ValidationError, match="hexadecimal"):
        RAGFilters(document_ids=["z" * 64])
    with pytest.raises(ValidationError, match="cannot exceed"):
        RAGFilters(publish_year_min=2025, publish_year_max=2020)
