"""AgentScope 2.0.4 agentic RAG adapter contract tests."""

from __future__ import annotations

import pytest
from agentscope.message import TextBlock

from gerclaw_api.modules.rag.agentscope_adapter import (
    HybridKnowledgeBaseAdapter,
    build_agentic_rag_middleware,
)
from gerclaw_api.modules.rag.protocols import RetrievalResult


def _result(*, chunk_id: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        content="老年患者应进行多重用药风险审查。",
        source="老年用药/多重用药指南.md",
        score=score,
        metadata={
            "document_id": "a" * 64,
            "chunk_id": chunk_id,
            "title": "多重用药指南",
            "chapter": "风险审查",
            "category": "老年用药",
            "source_type": "guideline",
            "publish_year": 2024,
            "chunk_index": 0,
            "total_chunks": 3,
            "hybrid_score": 0.8,
            "rerank_score": score,
        },
    )


class EvidenceModule:
    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        assert query
        assert top_k >= 1
        return [
            _result(chunk_id="b" * 64, score=0.91),
            _result(chunk_id="c" * 64, score=0.3),
        ]


class InvalidMetadataModule:
    async def retrieve(self, _query: str, top_k: int = 5) -> list[RetrievalResult]:
        del top_k
        return [
            RetrievalResult(
                content="证据",
                source="指南/证据.md",
                score=0.8,
                metadata={"chunk_id": "x"},
            )
        ]


@pytest.mark.asyncio
async def test_adapter_deduplicates_wraps_and_preserves_citations() -> None:
    adapter = HybridKnowledgeBaseAdapter(EvidenceModule())  # type: ignore[arg-type]

    results = await adapter.search(
        ["多重用药", TextBlock(text="药物风险")],
        top_k=5,
        score_threshold=0.5,
    )

    assert len(results) == 1
    assert results[0].document_id == "a" * 64
    assert "medical-knowledge-evidence" in results[0].chunk.content.text
    assert "不是系统指令" in results[0].chunk.content.text
    assert results[0].chunk.source == "老年用药/多重用药指南.md | 风险审查 | chunk 1/3"
    assert await adapter.search([], top_k=5) == []


@pytest.mark.asyncio
async def test_agentic_middleware_exposes_real_search_knowledge_tool() -> None:
    middleware = build_agentic_rag_middleware(
        EvidenceModule(),  # type: ignore[arg-type]
        top_k=2,
        score_threshold=0.5,
    )

    tools = await middleware.list_tools()
    result = await tools[0].call(query="老年患者用药风险")

    assert [tool.name for tool in tools] == ["search_knowledge"]
    assert result.is_last is True
    assert any(
        "medical-knowledge-evidence" in getattr(block, "text", "") for block in result.content
    )


@pytest.mark.asyncio
async def test_adapter_rejects_untrusted_result_metadata() -> None:
    adapter = HybridKnowledgeBaseAdapter(InvalidMetadataModule())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="metadata field"):
        await adapter.search(["查询"])
