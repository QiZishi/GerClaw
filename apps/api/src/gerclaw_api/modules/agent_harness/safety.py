"""Deterministic medical output guardrails and local-evidence projection."""

from __future__ import annotations

import re

from gerclaw_api.modules.contracts import Citation, SafetyDecision
from gerclaw_api.modules.rag.protocols import RetrievalResult
from gerclaw_api.modules.validation import (
    RAGEvidenceContractValidationError,
    validate_local_rag_evidence_provenance,
)

MEDICAL_DISCLAIMER = "内容由 AI 生成，仅供参考。身体不适请及时就医。"
_MODEL_DISCLAIMER_FRAGMENTS = (
    "内容由 AI 生成，仅供参考。",
    "身体不适请及时就医。",
)
HIGH_RISK_NOTICE = (
    "⚠️ 您描述的情况可能涉及紧急风险。请立即拨打 120 或尽快前往急诊，"
    "不要等待在线回复；如身边有人，请请其陪同并携带当前用药清单。"
)
PATIENT_CLINICAL_RISK_NOTICE = (
    "⚠️ 请勿自行开始、停用、替换药物或调整剂量；请结合上述依据与医生复核。"
)

_CLEARLY_NON_MEDICAL = re.compile(
    r"^(?:你好|您好|嗨|谢谢|多谢|再见|你是谁|你能做什么|怎么使用|帮助|help)[！!。.\s]*$",
    re.IGNORECASE,
)
_SYSTEM_CAPABILITY_EXPLANATION = re.compile(
    r"^(?:(?:请(?:问|用一句话)?(?:说明|介绍|解释)?|为什么|为何)[，,:：\s]*)?"
    r"(?:"
    r"(?:(?:当前|本)?(?:系统|平台|GerClaw).{0,80}(?:功能|能力|限制|边界|使用|上传))"
    r"|(?:上传(?:资料|文档|文件).{0,48}(?:不能|不可以|为何|为什么).{0,32}(?:确诊依据|诊断依据))"
    r")[？?。！!\s]*$",
    re.IGNORECASE,
)
_MEDICAL_SIGNAL = re.compile(
    r"(?:"
    r"健康|医疗|就医|医生|病历|检查(?:单|报告)?|化验|检验|影像|"
    r"症状|不适|疼痛|头晕|乏力|胸痛|呼吸|发热|咳嗽|失眠|跌倒|"
    r"血压|血糖|心率|心脏|心血管|肺|肝|肾|胃|肠|脑|骨|关节|"
    r"药(?:物|品|方|量)?|用药|处方|剂量|停药|加药|换药|相互作用|"
    r"诊断|治疗|康复|营养|运动|慢病|疾病|病情|高血压|糖尿病|"
    r"冠心病|老年|老人|患者|护理"
    r")",
    re.IGNORECASE,
)
_MALFORMED_LIMITATION_DIAGNOSIS = re.compile(
    r"(?P<prefix>(?:不能|无法|不应|不得)[^。！？!?；;\n]{0,80}?)"
    r"(?:明确(?:临床)?诊断|诊断结论|诊断)(?:为|是)结论"
)
_DETERMINISTIC_DIAGNOSIS_ASSERTIONS: tuple[re.Pattern[str], ...] = (
    # Match the longer phrase first. Otherwise ``确诊`` can be found across the
    # middle of ``明确诊断`` (明[确诊]断) and corrupt the public sentence.
    re.compile(
        r"(?:已经|已)?明确(?:临床)?诊断(?:为|是)\s*"
        r"(?P<condition>[^。！？!?；;，,\n]+)"
    ),
    re.compile(r"诊断结论(?:为|是)\s*(?P<condition>[^。！？!?；;，,\n]+)"),
    re.compile(
        r"(?<!明)(?:已经|已|明确|可以)?确诊(?:为|是)\s*"
        r"(?P<condition>[^。！？!?；;，,\n]+)"
    ),
    re.compile(
        r"(?:已经|已|明确|可以)?诊断(?:为|是)\s*"
        r"(?P<condition>[^。！？!?；;，,\n]+)"
    ),
)
_DETERMINISTIC_DIAGNOSIS_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    # ``确诊依据`` / ``确诊标准`` describe evidence or a process, not an
    # assertion about a patient.  Rewriting the word inside such a compound
    # makes otherwise safe explanations unreadable.
    (
        re.compile(
            r"(?<!明)(?:已经|已|明确|可以)?确诊"
            r"(?![为是依据标准检查流程方法率时间病例证据技术工具能力路径结果前后中])"
        ),
        "尚需由医生进一步评估",
    ),
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
_RED_FLAG_CLAUSE_BOUNDARY = re.compile(r"[。！？!?；;，,\n]")
_RED_FLAG_NEGATION = re.compile(
    r"(?:没有|没|无(?!论)|否认|未(?:见|出现|发生)|不伴|不存在|从未)"
    r"[^。！？!?；;，,\n]{0,16}$"
)
_RED_FLAG_CONTRAST = re.compile(r"但(?:是)?|然而|却|仍(?:然)?")
_EMBEDDED_CITATION_MARKER = re.compile(r"\[(?:E|W|K|R)\d{1,4}\]", re.IGNORECASE)
_PATIENT_RISK_NOTICE_TRIGGER = re.compile(
    r"(?:"
    r"开始(?:服用|使用)?|停用|加用|减量|增量|调整(?:药物)?剂量|换药|替换(?:药物)?|"
    r"确诊(?:为|是)?|(?:明确(?:临床)?诊断|诊断结论|诊断)(?:为|是)|"
    r"(?:您|患者|病人)(?:已经|已)?(?:患有|得了|就是得了)"
    r")"
)


class EvidenceUnavailableError(RuntimeError):
    """Raised when a medical answer cannot be grounded in traceable evidence."""


def is_medical_message(text: str) -> bool:
    """Identify requests that need the medical evidence-and-risk output path.

    General conversation and neutral image interpretation are not medical merely
    because they are sent through a healthcare product.  Medical terms opt a
    request into the evidence requirement; high-risk detection remains an
    independent safety short-circuit.
    """

    candidate = text.strip()
    if _CLEARLY_NON_MEDICAL.fullmatch(candidate) is not None:
        return False
    if _SYSTEM_CAPABILITY_EXPLANATION.fullmatch(candidate) is not None:
        return False
    return _MEDICAL_SIGNAL.search(candidate) is not None


def detect_high_risk(text: str) -> list[str]:
    """Return stable red-flag codes without persisting the triggering text."""

    codes: list[str] = []
    for code, pattern in _HIGH_RISK_PATTERNS:
        for match in pattern.finditer(text):
            prefix_start = 0
            for boundary in _RED_FLAG_CLAUSE_BOUNDARY.finditer(text, 0, match.start()):
                prefix_start = boundary.end()
            prefix = text[prefix_start : match.start()]
            negation = _RED_FLAG_NEGATION.search(prefix)
            if (
                negation is not None
                and _RED_FLAG_CONTRAST.search(prefix[negation.start() :]) is None
            ):
                continue
            codes.append(code)
            break
    return codes


def sanitize_medical_text(
    text: str,
    *,
    allow_evidence_backed_clinical_conclusion: bool = False,
) -> str:
    """Normalize model text before public emission.

    The Harness owns the single, final disclaimer.  Removing a model-invented
    copy here prevents a duplicate footer in streamed UI. A clinical conclusion
    is not deleted merely because it is direct: it may remain when the Runtime
    has already obtained traceable local, web, or user-provided evidence for
    this turn. Without that evidence, deterministic diagnostic language is
    rewritten to prevent unsupported certainty.
    """

    def rewrite_malformed_limitation(match: re.Match[str]) -> str:
        prefix = re.sub(r"最终的?$", "", match.group("prefix").strip())
        return f"{prefix}最终临床判断"

    def rewrite_assertion(match: re.Match[str]) -> str:
        condition = match.group("condition").strip()
        return f"提示{condition}的可能性，建议由医生进一步评估"

    sanitized = text.replace(MEDICAL_DISCLAIMER, "")
    for fragment in _MODEL_DISCLAIMER_FRAGMENTS:
        sanitized = sanitized.replace(fragment, "")
    sanitized = _MALFORMED_LIMITATION_DIAGNOSIS.sub(rewrite_malformed_limitation, sanitized)
    if allow_evidence_backed_clinical_conclusion:
        return sanitized
    for pattern in _DETERMINISTIC_DIAGNOSIS_ASSERTIONS:
        sanitized = pattern.sub(rewrite_assertion, sanitized)
    for pattern, replacement in _DETERMINISTIC_DIAGNOSIS_REWRITES:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def requires_patient_clinical_risk_notice(text: str) -> bool:
    """Keep one concise risk footer for patient-facing actionable conclusions."""

    return _PATIENT_RISK_NOTICE_TRIGGER.search(text) is not None


def citations_from_results(results: list[RetrievalResult]) -> list[Citation]:
    """Create stable public citations and deduplicate repeated agentic searches."""

    citations: list[Citation] = []
    seen: set[str] = set()
    for result in results:
        try:
            provenance = validate_local_rag_evidence_provenance(result.metadata)
        except RAGEvidenceContractValidationError:
            continue
        chunk_id = provenance.chunk_id
        if chunk_id in seen:
            continue
        citations.append(
            Citation(
                source_id=chunk_id,
                title=provenance.title,
                locator=(
                    f"{result.source} | {provenance.chapter} | chunk "
                    f"{provenance.chunk_index + 1}/{provenance.total_chunks}"
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
        excerpt = _EMBEDDED_CITATION_MARKER.sub("", citation.excerpt[:3_000])
        entry = (
            f"[E{index}] {citation.title}\n来源：{citation.locator}\n"
            f"引用时只使用本段标题的 [E{index}]，不要复制正文中的原始编号。\n"
            "<untrusted-medical-evidence>\n"
            f"{excerpt}\n"
            "</untrusted-medical-evidence>"
        )
        if sum(len(item) for item in sections) + len(entry) > budget:
            break
        sections.append(entry)
    return "\n\n".join(sections)


def safety_decision(
    high_risk_codes: list[str],
    *,
    deterministic_diagnosis_blocked: bool = False,
    evidence_backed_clinical_conclusion_allowed: bool = False,
    patient_clinical_risk_notice_applied: bool = False,
    evidence_unavailable: bool = False,
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
    if evidence_unavailable:
        notices.append("evidence_unavailable_clarification")
    if evidence_backed_clinical_conclusion_allowed:
        notices.append("evidence_backed_clinical_conclusion_allowed")
    if patient_clinical_risk_notice_applied:
        notices.append("patient_clinical_risk_notice_applied")
    return SafetyDecision(
        reviewed=True,
        disclaimer_applied=True,
        deterministic_diagnosis_blocked=deterministic_diagnosis_blocked,
        high_risk_escalation_checked=True,
        notices=notices,
    )
