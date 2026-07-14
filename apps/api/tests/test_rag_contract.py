"""RAG protocol surface must match design requirement §4.7."""

from gerclaw_api.modules.rag.protocols import RAGModule, RetrievalResult


def test_rag_exposes_retrieval_and_indexing_with_provenance() -> None:
    assert hasattr(RAGModule, "retrieve")
    assert hasattr(RAGModule, "index_document")
    result = RetrievalResult(content="evidence", source="local.md#one", score=0.8)
    assert result.source.startswith("local")
