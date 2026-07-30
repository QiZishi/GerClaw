"""Evidence admission tests at the RAG-to-Harness trust boundary."""

from __future__ import annotations

import pytest

from gerclaw_api.modules.agent_harness.evidence import (
    CitationMarkerValidationError,
    EvidenceAdmissionPolicy,
    ModelCitationBindingScope,
    audit_claim_evidence,
    bind_citation_markers,
    segment_has_admitted_model_marker,
)
from gerclaw_api.modules.contracts import Citation
from gerclaw_api.modules.rag.protocols import RetrievalResult


def _result(
    *,
    chunk_id: str,
    source_type: str,
    score: float,
    content: str,
    year: int = 2024,
) -> RetrievalResult:
    return RetrievalResult(
        content=content,
        source=f"证据/{chunk_id}.md",
        score=score,
        metadata={
            "document_id": f"doc-{chunk_id}",
            "chunk_id": chunk_id,
            "title": f"证据 {chunk_id}",
            "chapter": "建议",
            "category": "老年医学",
            "source_type": source_type,
            "publish_year": year,
            "chunk_index": 0,
            "total_chunks": 1,
            "hybrid_score": score,
            "rerank_score": score,
        },
    )


def test_admission_applies_absolute_threshold_and_authority_order() -> None:
    policy = EvidenceAdmissionPolicy(minimum_score=0.4, limit=5)
    admitted = policy.admit_local_results(
        [
            _result(
                chunk_id="literature-high",
                source_type="literature",
                score=0.95,
                content="研究证据",
            ),
            _result(
                chunk_id="guideline-pass",
                source_type="guideline",
                score=0.41,
                content="指南证据",
            ),
            _result(
                chunk_id="consensus-low",
                source_type="consensus",
                score=0.39,
                content="低相关共识",
            ),
        ]
    )

    assert [item.record.evidence_id for item in admitted] == [
        "guideline-pass",
        "literature-high",
    ]


def test_admission_deduplicates_ids_and_exact_adopted_text() -> None:
    policy = EvidenceAdmissionPolicy(minimum_score=0.2, limit=5)
    results = [
        _result(
            chunk_id="guideline",
            source_type="guideline",
            score=0.8,
            content="  同一条医学证据。 ",
        ),
        _result(
            chunk_id="literature",
            source_type="literature",
            score=0.9,
            content="同一条医学证据。",
        ),
        _result(
            chunk_id="guideline",
            source_type="guideline",
            score=0.7,
            content="重复 ID 的不同文本",
        ),
    ]

    citations = policy.citations_from_local_results(results)

    assert len(citations) == 1
    assert citations[0].source_id == "guideline"
    assert citations[0].excerpt == "同一条医学证据。"
    assert citations[0].score == 0.8


def test_admission_rejects_invalid_provenance_without_approximation() -> None:
    policy = EvidenceAdmissionPolicy(minimum_score=0.2, limit=5)
    invalid = _result(
        chunk_id="invalid",
        source_type="guideline",
        score=0.9,
        content="不得成为引用",
    )
    invalid.metadata.pop("chapter")

    assert policy.citations_from_local_results([invalid]) == []


def test_citation_markers_bind_only_to_admitted_terminal_positions() -> None:
    assert (
        bind_citation_markers(
            "本地建议 [E2], 联网补充 [W1]。",
            local_citation_count=2,
            web_citation_count=1,
            web_citation_offset=3,
        )
        == "本地建议 [C2], 联网补充 [C4]。"
    )
    for text in ("越界 [E3]", "越界 [W2]", "绕过 [C1]", "零编号 [E0]"):
        with pytest.raises(CitationMarkerValidationError):
            bind_citation_markers(
                text,
                local_citation_count=2,
                web_citation_count=1,
                web_citation_offset=3,
            )


def test_streaming_claim_requires_an_in_range_marker_in_the_same_segment() -> None:
    assert segment_has_admitted_model_marker(
        "明确诊断为冠心病 [E1]。",
        local_citation_count=1,
        web_citation_count=0,
    )
    assert not segment_has_admitted_model_marker(
        "明确诊断为冠心病。",
        local_citation_count=1,
        web_citation_count=0,
    )
    assert not segment_has_admitted_model_marker(
        "明确诊断为冠心病 [E2]。",
        local_citation_count=1,
        web_citation_count=0,
    )


def test_model_citation_scope_keeps_streaming_public_positions_stable() -> None:
    scope = ModelCitationBindingScope(
        local_citation_count=2,
        web_citation_count_provider=lambda: 1,
    )

    assert scope.segment_has_evidence("本地 [E1], 联网 [W1]。")
    assert scope.normalize_public_text("本地 [E1], 联网 [W1]。") == ("本地 [C1], 联网 [C3]。")
    with pytest.raises(CitationMarkerValidationError):
        scope.normalize_public_text("模型不得直接输出 [C1]。")


def test_claim_audit_binds_source_locator_and_exact_adopted_text_hash() -> None:
    citations = [
        Citation(
            source_id="chunk-1",
            title="指南",
            locator="指南.md | 建议 | chunk 1/1",
            excerpt="实际采用文本",
            score=0.9,
            corpus="local_knowledge_base",
        )
    ]
    audit = audit_claim_evidence(
        "高血压管理需要个体化 [C1]。另一个医学判断。",
        citations=citations,
        is_clinical_claim=lambda _segment: True,
    )

    assert audit.clinical_claim_count == 2
    assert audit.bound_claim_count == 1
    assert audit.all_clinical_claims_bound is False
    assert audit.claims[0].source_ids == ("chunk-1",)
    assert audit.claims[0].locators == ("指南.md | 建议 | chunk 1/1",)
    assert len(audit.claims[0].adopted_text_sha256[0]) == 64
    assert audit.claims[1].status == "unbound"
