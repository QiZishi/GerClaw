"""Medical safety and evidence projection tests."""

from __future__ import annotations

import pytest

from gerclaw_api.modules.agent_harness.safety import (
    MEDICAL_DISCLAIMER,
    build_evidence_context,
    citations_from_results,
    detect_high_risk,
    is_medical_message,
    safety_decision,
    sanitize_medical_text,
)
from gerclaw_api.modules.rag.protocols import RetrievalResult


def _result(index: int, *, valid: bool = True) -> RetrievalResult:
    metadata = (
        {
            "chunk_id": f"chunk-{index}",
            "document_id": f"document-{index}",
            "title": f"老年医学指南 {index}",
            "chapter": "风险评估",
            "chunk_index": index,
            "total_chunks": 60,
        }
        if valid
        else {"chunk_id": index, "title": "bad"}
    )
    return RetrievalResult(
        content=("循证医学内容。" * 100),
        source=f"跌倒/指南-{index}.md",
        score=0.9,
        metadata=metadata,
    )


def test_medical_classifier_fails_safe_outside_small_talk() -> None:
    assert not is_medical_message("您好！")
    assert not is_medical_message("谢谢")
    assert is_medical_message("老人最近总是头晕怎么办")
    assert is_medical_message("计算 1+1")


def test_red_flags_use_stable_codes_without_echoing_input() -> None:
    codes = detect_high_risk("突然胸痛、喘不上气，还说不想活")
    assert codes == ["chest_pain", "breathing_difficulty", "suicide_risk"]
    assert detect_high_risk("普通问候") == []


@pytest.mark.parametrize(
    ("unsafe", "forbidden"),
    [
        ("您已经确诊为冠心病。", "确诊"),
        ("明确诊断为冠心病。", "诊断"),
        ("诊断是糖尿病。", "诊断"),
        ("诊断结论为高血压。", "诊断结论"),
        ("您患有高血压。", "患有"),
        ("患者得了糖尿病。", "得了"),
        ("肯定患有高血压。", "肯定"),
        ("这是冠心病。", "这是"),
        ("就是肺炎。", "就是"),
    ],
)
def test_deterministic_diagnosis_language_is_removed(unsafe: str, forbidden: str) -> None:
    sanitized = sanitize_medical_text(unsafe)
    assert forbidden not in sanitized
    assert "进一步评估" in sanitized or "可能" in sanitized
    assert "明需" not in sanitized
    assert "评估是否为断" not in sanitized


def test_diagnosis_rewrite_does_not_corrupt_explicit_diagnosis_phrase() -> None:
    assert sanitize_medical_text("明确诊断为冠心病。") == "需由医生进一步评估是否为冠心病。"


def test_citation_projection_deduplicates_and_bounds_results() -> None:
    results = [_result(index) for index in range(55)]
    results.insert(1, results[0])
    results.append(_result(99, valid=False))
    citations = citations_from_results(results)
    assert len(citations) == 50
    assert citations[0].source_id == "chunk-0"
    assert citations[0].locator == "跌倒/指南-0.md | 风险评估 | chunk 1/60"
    assert len(citations[0].excerpt) <= 2_000
    assert citations[0].corpus == "local_knowledge_base"


def test_citation_projection_normalizes_optional_locator_metadata() -> None:
    result = _result(1)
    result.metadata.update({"chapter": None, "chunk_index": True, "total_chunks": "many"})
    citation = citations_from_results([result])[0]
    assert "未标注章节" in citation.locator
    assert citation.locator.endswith("chunk 1/1")


def test_evidence_context_is_bounded_and_marks_content_untrusted() -> None:
    citations = citations_from_results([_result(index) for index in range(20)])
    context = build_evidence_context(citations)
    assert len(context) <= 12_000
    assert "[E1]" in context
    assert "<untrusted-medical-evidence>" in context
    assert "来源：" in context


def test_safety_decision_always_applies_disclaimer_and_red_flag_check() -> None:
    routine = safety_decision([])
    urgent = safety_decision(["chest_pain"], deterministic_diagnosis_blocked=True)
    assert routine.disclaimer_applied
    assert not routine.deterministic_diagnosis_blocked
    assert urgent.deterministic_diagnosis_blocked
    assert "deterministic_diagnosis_checked" in routine.notices
    assert "deterministic_diagnosis_blocked" in urgent.notices
    assert "high_risk_escalation_checked" in routine.notices
    assert "high_risk_escalation_applied" in urgent.notices
    assert MEDICAL_DISCLAIMER.endswith("及时就医。")
