"""Evidence admission tests at the RAG-to-Harness trust boundary."""

from __future__ import annotations

import pytest

from gerclaw_api.modules.agent_harness.evidence import (
    CitationMarkerValidationError,
    EvidenceAdmissionPolicy,
    ModelCitationBindingScope,
    audit_claim_evidence,
    bind_citation_markers,
    bind_turn_evidence,
    prune_unbound_clinical_claims,
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
    assert (
        bind_citation_markers(
            "越界 [E3]\uff0c联网 [W2]\uff0c绕过 [C1]\uff0c零编号 [E0]。",
            local_citation_count=2,
            web_citation_count=1,
            web_citation_offset=3,
        )
        == "越界\uff0c联网\uff0c绕过\uff0c零编号。"
    )
    assert (
        bind_citation_markers(
            "允许空格 [ E2 ]。",
            local_citation_count=2,
            web_citation_count=0,
            web_citation_offset=2,
        )
        == "允许空格 [C2]。"
    )
    assert (
        bind_citation_markers(
            "上传资料 [A1]。",
            local_citation_count=2,
            web_citation_count=1,
            web_citation_offset=2,
            attachment_citation_count=1,
            attachment_citation_offset=3,
        )
        == "上传资料 [C4]。"
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
    assert segment_has_admitted_model_marker(
        "图片观察 [A1]。",
        local_citation_count=0,
        web_citation_count=0,
        attachment_citation_count=1,
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
    assert scope.normalize_public_text("模型不得直接输出 [C1]。") == "模型不得直接输出。"


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


def test_prune_unbound_claims_preserves_supported_and_nonclinical_segments() -> None:
    citations = [
        Citation(
            source_id="source-1",
            title="指南",
            locator="https://example.test/guideline",
            excerpt="实际采用文本",
            score=0.9,
            corpus="local_knowledge_base",
        )
    ]

    text, removed_count = prune_unbound_clinical_claims(
        "血压管理应结合日常记录 [C1]。\n建议直接停药。\n祝您生活愉快。",
        citations=citations,
        is_clinical_claim=lambda segment: "血压" in segment or "停药" in segment,
    )

    assert removed_count == 1
    assert "血压管理应结合日常记录 [C1]。" in text
    assert "停药" not in text
    assert "祝您生活愉快。" in text


def test_turn_binding_projects_only_adopted_sources_and_renumbers_markers() -> None:
    initial = [
        Citation(
            source_id=f"local-{index}",
            title=f"本地资料 {index}",
            locator=f"local-{index}.md",
            excerpt=f"本地原文 {index}",
            score=0.9,
            corpus="local_knowledge_base",
        )
        for index in (1, 2)
    ]
    attachment = Citation(
        source_id="attachment-1",
        title="用户上传资料",
        locator="attachment.pdf | 第 1 页",
        excerpt="血压记录为 146/82 mmHg。",
        score=1.0,
        corpus="uploaded_document",
    )

    bound = bind_turn_evidence(
        "上传记录显示收缩压为 146 mmHg [A1]。",
        initial_local=initial,
        additional_local=[],
        web=[],
        attachments=[attachment],
        is_clinical_claim=lambda _segment: True,
        adopted_only=True,
    )

    assert bound.text == "上传记录显示收缩压为 146 mmHg [C1]。"
    assert bound.citations == (attachment,)
    assert bound.claim_audit.claims[0].source_ids == ("attachment-1",)

def test_invalid_model_citation_is_rejected_at_terminal_binding() -> None:
    with pytest.raises(CitationMarkerValidationError):
        bind_turn_evidence(
            "无依据的临床结论 [C2]。",
            initial_local=[
                Citation(
                    source_id="local-1",
                    title="本地指南",
                    locator="本地指南.md | 建议 | chunk 1/1",
                    excerpt="本地知识库证据。",
                    score=0.9,
                    corpus="local_knowledge_base",
                )
            ],
            additional_local=[],
            web=[],
            attachments=[],
            is_clinical_claim=lambda _segment: True,
            markers_already_bound=True,
        )


def test_unbound_deterministic_clinical_claim_is_removed_from_public_text() -> None:
    text, removed_count = prune_unbound_clinical_claims(
        "明确诊断为冠心病。\n请由医生进一步核实。",
        citations=[],
        is_clinical_claim=lambda segment: "明确诊断" in segment,
    )

    assert removed_count == 1
    assert "明确诊断" not in text
    assert text == "请由医生进一步核实。"


def test_turn_binding_preserves_local_web_and_uploaded_source_provenance() -> None:
    local = Citation(
        source_id="local-1",
        title="本地指南",
        locator="本地指南.md | 建议 | chunk 1/1",
        excerpt="本地知识库证据。",
        score=0.9,
        corpus="local_knowledge_base",
    )
    web = Citation(
        source_id="web-1",
        title="联网检索结果",
        locator="https://example.test/evidence",
        excerpt="联网搜索证据。",
        score=0.8,
        corpus="web",
    )
    uploaded = Citation(
        source_id="upload-1",
        title="用户上传资料",
        locator="检查报告.pdf | 第 1 页",
        excerpt="上传资料证据。",
        score=1.0,
        corpus="uploaded_document",
    )

    bound = bind_turn_evidence(
        "本地建议 [E1]。联网补充 [W1]。上传记录 [A1]。",
        initial_local=[local],
        additional_local=[],
        web=[web],
        attachments=[uploaded],
        is_clinical_claim=lambda _segment: True,
        adopted_only=True,
    )

    assert bound.text == "本地建议 [C1]。联网补充 [C2]。上传记录 [C3]。"
    assert [citation.corpus for citation in bound.citations] == [
        "local_knowledge_base",
        "web",
        "uploaded_document",
    ]
    assert [claim.source_ids for claim in bound.claim_audit.claims] == [
        ("local-1",),
        ("web-1",),
        ("upload-1",),
    ]


def test_low_score_local_evidence_cannot_support_a_deterministic_claim() -> None:
    policy = EvidenceAdmissionPolicy(minimum_score=0.7, limit=5)
    citations = policy.citations_from_local_results(
        [
            _result(
                chunk_id="below-threshold",
                source_type="guideline",
                score=0.69,
                content="分数不足的本地证据。",
            )
        ]
    )

    bound = bind_turn_evidence(
        "明确诊断为冠心病 [E1]。",
        initial_local=citations,
        additional_local=[],
        web=[],
        attachments=[],
        is_clinical_claim=lambda _segment: True,
    )

    text, removed_count = prune_unbound_clinical_claims(
        bound.text,
        citations=list(bound.citations),
        is_clinical_claim=lambda _segment: True,
    )

    assert citations == []
    assert bound.claim_audit.claims[0].status == "unbound"
    assert removed_count == 1
    assert text == ""

def test_threshold_score_local_evidence_keeps_its_bound_claim() -> None:
    policy = EvidenceAdmissionPolicy(minimum_score=0.7, limit=5)
    citations = policy.citations_from_local_results(
        [
            _result(
                chunk_id="at-threshold",
                source_type="guideline",
                score=0.7,
                content="指南建议结合患者情况进行血压管理。",
            )
        ]
    )

    bound = bind_turn_evidence(
        "指南建议结合患者情况进行血压管理 [E1]。",
        initial_local=citations,
        additional_local=[],
        web=[],
        attachments=[],
        is_clinical_claim=lambda _segment: True,
        adopted_only=True,
    )

    assert len(citations) == 1
    assert bound.text == "指南建议结合患者情况进行血压管理 [C1]。"
    assert bound.claim_audit.all_clinical_claims_bound is True
    assert bound.citations[0].source_id == "at-threshold"
