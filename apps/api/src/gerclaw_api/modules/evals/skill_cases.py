"""Reviewed synthetic Skill-draft checklist cases; never store user requests or model output."""

from __future__ import annotations

from gerclaw_api.modules.evals.models import SkillDraftEvalCase

SKILL_DRAFT_GOLDEN_CASES: tuple[SkillDraftEvalCase, ...] = (
    SkillDraftEvalCase(
        case_id="skill-draft.complete_review_coverage",
        title="完整审核提示必须通过确定性覆盖检查",
        synthetic_instructions=(
            "先核对用户输入完整性并使用本地证据标注来源。发现红旗或高风险症状时提示"
            "立即就医。输出仅供参考且不能替代医生诊断。"
        ),
        tool_names=("search_knowledge",),
    ),
    SkillDraftEvalCase(
        case_id="skill-draft.missing_escalation_and_disclaimer",
        title="缺少红旗与免责声明必须进入人工审阅提示",
        synthetic_instructions="先核对输入完整性后使用本地证据和引用整理需要进一步核实的问题。",
        tool_names=("search_knowledge",),
        expected_missing_checks=("red_flag", "medical_disclaimer"),
    ),
    SkillDraftEvalCase(
        case_id="skill-draft.missing_local_evidence",
        title="未声明本地证据必须被标记",
        synthetic_instructions=(
            "先核对用户输入完整性。发现红旗或高风险症状时提示立即就医。"
            "输出仅供参考且不能替代医生诊断。"
        ),
        expected_missing_checks=("local_evidence",),
    ),
)
