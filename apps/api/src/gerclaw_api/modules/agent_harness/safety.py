"""Deterministic medical output guardrails and local-evidence projection."""

from __future__ import annotations

import re

from gerclaw_api.modules.contracts import Citation, SafetyDecision
from gerclaw_api.modules.rag.protocols import RetrievalResult

MEDICAL_DISCLAIMER = "内容由 AI 生成，仅供参考。身体不适请及时就医。"
HIGH_RISK_NOTICE = (
    "⚠️ 您描述的情况可能涉及紧急风险。请立即拨打 120 或尽快前往急诊，"
    "不要等待在线回复；如身边有人，请请其陪同并携带当前用药清单。"
)

_CLEARLY_NON_MEDICAL = re.compile(
    r"^(?:你好|您好|嗨|谢谢|多谢|再见|你是谁|你能做什么|怎么使用|帮助|help)[！!。.\s]*$",
    re.IGNORECASE,
)
_DETERMINISTIC_DIAGNOSIS_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Match the longer phrase first. Otherwise ``确诊`` can be found across the
    # middle of ``明确诊断`` (明[确诊]断) and corrupt the public sentence.
    (re.compile(r"(?:已经|已)?明确(?:临床)?诊断(?:为|是)"), "需由医生进一步评估是否为"),
    (re.compile(r"诊断结论(?:为|是)"), "需由医生进一步评估是否为"),
    (re.compile(r"(?<!明)(?:已经|已|明确|可以)?确诊(?:为|是)?"), "需由医生进一步评估是否为"),
    (re.compile(r"(?:已经|已|明确|可以)?诊断(?:为|是)"), "需由医生进一步评估是否为"),
    (re.compile(r"(?:您|患者|病人)(?:已经|已)?患有"), "您可能存在"),
    (re.compile(r"(?:您|患者|病人)(?:已经|已)?(?:得了|就是得了)"), "您可能存在"),
    (re.compile(r"(?:一定|肯定|必然)(?:是|患有|属于)"), "可能是"),
    (
        re.compile(r"这是(?!辅助|一条|建议|提示|参考|说明|可能|需要|为了|对)"),
        "这可能是",
    ),
    (re.compile(r"就是(?!说|建议|提示|参考|说明|可能|需要)"), "可能是"),
)
_HIGH_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("chest_pain", re.compile(r"胸痛|胸口.*(?:压榨|剧痛|疼)|心前区.*痛")),
    ("breathing_difficulty", re.compile(r"呼吸困难|喘不上气|无法呼吸|气促.*加重")),
    ("neurologic_deficit", re.compile(r"口角歪斜|言语不清|一侧.*无力|突发.*偏瘫")),
    ("altered_consciousness", re.compile(r"意识障碍|失去意识|昏迷|叫不醒")),
    ("major_bleeding", re.compile(r"大出血|大量出血|呕血|便血.*(?:很多|大量)")),
    ("suicide_risk", re.compile(r"自杀|不想活|结束生命|伤害自己")),
)


class EvidenceUnavailableError(RuntimeError):
    """Raised when a medical answer cannot be grounded in local evidence."""


def is_medical_message(text: str) -> bool:
    """Fail safe: only a narrow conversational allowlist bypasses evidence."""

    return _CLEARLY_NON_MEDICAL.fullmatch(text.strip()) is None


def detect_high_risk(text: str) -> list[str]:
    """Return stable red-flag codes without persisting the triggering text."""

    return [code for code, pattern in _HIGH_RISK_PATTERNS if pattern.search(text)]


def sanitize_medical_text(text: str) -> str:
    """Remove deterministic diagnosis assertions before any public emission."""

    sanitized = text
    for pattern, replacement in _DETERMINISTIC_DIAGNOSIS_REWRITES:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def citations_from_results(results: list[RetrievalResult]) -> list[Citation]:
    """Create stable public citations and deduplicate repeated agentic searches."""

    citations: list[Citation] = []
    seen: set[str] = set()
    for result in results:
        metadata = result.metadata
        chunk_id = metadata.get("chunk_id")
        document_id = metadata.get("document_id")
        title = metadata.get("title")
        chapter = metadata.get("chapter")
        chunk_index = metadata.get("chunk_index")
        total_chunks = metadata.get("total_chunks")
        if not isinstance(chunk_id, str) or not chunk_id:
            continue
        if not isinstance(document_id, str) or not document_id:
            continue
        if not isinstance(title, str) or not title:
            continue
        if chunk_id in seen:
            continue
        if not isinstance(chapter, str) or not chapter:
            chapter = "未标注章节"
        if isinstance(chunk_index, bool) or not isinstance(chunk_index, int):
            chunk_index = 0
        if isinstance(total_chunks, bool) or not isinstance(total_chunks, int):
            total_chunks = 1
        citations.append(
            Citation(
                source_id=chunk_id,
                title=title,
                locator=(
                    f"{result.source} | {chapter} | chunk {chunk_index + 1}/{max(total_chunks, 1)}"
                ),
                excerpt=result.content[:2_000],
                score=result.score,
                corpus="local_knowledge_base",
            )
        )
        seen.add(chunk_id)
        if len(citations) >= 50:
            break
    return citations


def build_evidence_context(citations: list[Citation]) -> str:
    """Render bounded, explicitly untrusted evidence for the model context."""

    sections: list[str] = []
    budget = 12_000
    for index, citation in enumerate(citations, start=1):
        excerpt = citation.excerpt[:3_000]
        entry = (
            f"[E{index}] {citation.title}\n来源：{citation.locator}\n"
            "<untrusted-medical-evidence>\n"
            f"{excerpt}\n"
            "</untrusted-medical-evidence>"
        )
        if sum(len(item) for item in sections) + len(entry) > budget:
            break
        sections.append(entry)
    return "\n\n".join(sections)


def safety_decision(
    high_risk_codes: list[str], *, deterministic_diagnosis_blocked: bool = False
) -> SafetyDecision:
    """Return the mandatory explicit safety decision persisted with every reply."""

    notices = [
        "medical_disclaimer_applied",
        (
            "deterministic_diagnosis_blocked"
            if deterministic_diagnosis_blocked
            else "deterministic_diagnosis_checked"
        ),
    ]
    if high_risk_codes:
        notices.append("high_risk_escalation_applied")
    else:
        notices.append("high_risk_escalation_checked")
    return SafetyDecision(
        reviewed=True,
        disclaimer_applied=True,
        deterministic_diagnosis_blocked=deterministic_diagnosis_blocked,
        high_risk_escalation_checked=True,
        notices=notices,
    )
