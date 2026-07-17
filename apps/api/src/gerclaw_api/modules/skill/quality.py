"""Deterministic review cues for untrusted model-generated Skill drafts."""

from __future__ import annotations

from gerclaw_api.modules.skill.models import SkillDefinition, SkillDraftQualityReport
from gerclaw_api.modules.skill.security import normalize_skill_text


def evaluate_skill_draft(definition: SkillDefinition) -> SkillDraftQualityReport:
    """Return stable checklist codes without storing or echoing draft content.

    This is deliberately a lightweight coverage check, not a medical evaluator.
    The draft has already passed structural and safety policy validation when it
    reaches here; the caller must still read and explicitly save it.
    """

    source = normalize_skill_text(definition.source_markdown).casefold()
    missing: list[str] = []
    if not _contains_any(source, ("核对", "验证", "完整性", "输入")):
        missing.append("input_check")
    if "search_knowledge" not in definition.tool_names and not _contains_any(
        source, ("本地证据", "本地知识", "证据", "引用", "来源")
    ):
        missing.append("local_evidence")
    if not _contains_any(source, ("红旗", "高风险", "紧急", "立即就医", "急诊")):
        missing.append("red_flag")
    if not _contains_any(source, ("免责声明", "仅供参考", "不能替代", "不替代")):
        missing.append("medical_disclaimer")
    return SkillDraftQualityReport(missing_checks=tuple(missing))


def _contains_any(source: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in source for phrase in phrases)
