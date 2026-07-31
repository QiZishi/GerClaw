"""Fail-closed online/offline classification for generated Skill revisions."""

# ruff: noqa: RUF001 -- Chinese user-facing DSL guidance intentionally uses CJK punctuation.

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from gerclaw_api.modules.agent_harness.evolution_governance import (
    EvolutionGovernancePolicy,
    OnlineMutationRequest,
)
from gerclaw_api.modules.skill.models import (
    SkillDefinition,
    SkillEvolutionDecision,
)
from gerclaw_api.modules.skill.security import normalize_skill_text

_PRESENTATION_CATEGORIES = frozenset(
    {"presentation", "formatting", "accessibility", "communication"}
)
_RETRIEVAL_CATEGORIES = frozenset({"retrieval", "search", "knowledge", "evidence"})
_BOUNDED_RETRIEVAL_TOOLS = frozenset({"search_knowledge", "search_memory"})
_PRESENTATION_DESCRIPTIONS = frozenset(
    {
        "在不新增事实的前提下调整已有内容的易读格式",
    }
)
_RETRIEVAL_DESCRIPTIONS = frozenset(
    {
        "从已声明的受限来源检索并返回带定位信息的原文结果",
    }
)
_PRESENTATION_DIRECTIVES = frozenset(
    {
        "# 工作流",
        "保留原意。",
        "不添加新事实。",
        "使用简短句子。",
        "使用清晰标题。",
        "使用易读分段。",
        "使用项目符号。",
        "突出用户指定的重点。",
        "保持用户指定的语言。",
    }
)
_RETRIEVAL_DIRECTIVES = frozenset(
    {
        "# 工作流",
        "使用本地知识库。",
        "使用用户已确认的记忆。",
        "按用户提供的关键词检索。",
        "去除重复结果。",
        "按相关性排序。",
        "保留来源和定位信息。",
        "不改写来源内容。",
        "找不到时明确说明没有结果。",
    }
)
ONLINE_EVOLUTION_DSL_GUIDANCE = """
低风险在线演化只接受以下服务端固定 DSL：

- presentation 的 description 必须是“在不新增事实的前提下调整已有内容的易读格式”，
  instructions 逐行只能选用：# 工作流 / 保留原意。 / 不添加新事实。 /
  使用简短句子。 / 使用清晰标题。 / 使用易读分段。 / 使用项目符号。 /
  突出用户指定的重点。 / 保持用户指定的语言。
- retrieval 的 description 必须是“从已声明的受限来源检索并返回带定位信息的原文结果”，
  instructions 逐行只能选用：# 工作流 / 使用本地知识库。 / 使用用户已确认的记忆。 /
  按用户提供的关键词检索。 / 去除重复结果。 / 按相关性排序。 /
  保留来源和定位信息。 / 不改写来源内容。 / 找不到时明确说明没有结果。

上述固定句不得改写。修订时 name、category、tools 和 parameter schema 必须保持不变；
只有 SemVer 和固定指令集合可以变化。无法满足时应生成普通候选，由服务端转入离线轨。
"""

_CONTROL_PATTERN = re.compile(
    r"(?:"
    r"\b(?:tool|permission|authorization|authentication|credential|secret|"
    r"system\s*prompt|developer\s*message|shell|python|javascript|network|"
    r"webhook|runtime|router|planner|harness)\b|"
    r"工具|权限|授权|认证|凭据|密钥|系统提示|开发者消息|脚本|代码执行|"
    r"网络请求|运行时|路由器|规划器|编排器|写入记忆|删除记忆"
    r")",
    re.IGNORECASE,
)
_CLINICAL_PATTERN = re.compile(
    r"(?:"
    r"\b(?:patient|doctor|clinical|medical|health|diagnos(?:is|e)|symptom|"
    r"disease|treatment|therapy|medication|medicine|drug|dose|dosage|"
    r"prescription|emergency|red[\s_-]*flag|blood\s*pressure|lab(?:oratory)?|"
    r"contraindication|allergy)\b|"
    r"患者|医生|临床|医疗|健康|诊断|症状|疾病|治疗|用药|药物|剂量|处方|"
    r"急诊|急救|红旗|血压|检查结果|检验结果|禁忌|过敏|随访|评估"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _Classification:
    object_kind: Literal[
        "skill.presentation",
        "skill.retrieval",
        "skill.clinical",
        "skill.tooling",
    ]
    authority: Literal[
        "presentation_only",
        "bounded_retrieval",
        "clinical_guidance",
        "control_plane",
    ]
    reason_codes: tuple[str, ...]


class SkillEvolutionPolicy:
    """Classify actual definitions; request labels never grant mutation authority."""

    __slots__ = ("_governance",)

    def __init__(self, governance: EvolutionGovernancePolicy | None = None) -> None:
        self._governance = governance or EvolutionGovernancePolicy()

    def decide(
        self,
        current: SkillDefinition,
        candidate: SkillDefinition,
        *,
        expected_revision: int,
        apply_if_low_risk: bool,
    ) -> SkillEvolutionDecision:
        classification = self._classify(current, candidate)
        rule = self._governance.rule_for(classification.object_kind)
        if rule.track == "mutable":
            self._governance.classify_online_mutation(
                OnlineMutationRequest(
                    object_kind=classification.object_kind,
                    requested_authority=classification.authority,
                    expected_revision=expected_revision,
                )
            )
            disposition = "online_applied" if apply_if_low_risk else "manual_review_draft"
            resulting_revision = expected_revision + 1 if apply_if_low_risk else None
        else:
            disposition = "offline_review_required"
            resulting_revision = None
        return SkillEvolutionDecision(
            track=rule.track,
            object_kind=classification.object_kind,
            authority=classification.authority,
            disposition=disposition,
            reason_codes=classification.reason_codes,
            expected_revision=expected_revision,
            resulting_revision=resulting_revision,
        )

    def online_registration_allowed(self, candidate: SkillDefinition) -> bool:
        """Admit only a complete low-authority DSL as a first active revision."""

        classification = self._classify_registration(candidate)
        rule = self._governance.rule_for(classification.object_kind)
        if rule.track != "mutable":
            return False
        self._governance.classify_online_mutation(
            OnlineMutationRequest(
                object_kind=classification.object_kind,
                requested_authority=classification.authority,
                expected_revision=1,
            )
        )
        return True

    @staticmethod
    def _classify(
        current: SkillDefinition,
        candidate: SkillDefinition,
    ) -> _Classification:
        if current.tool_names != candidate.tool_names:
            return _Classification(
                "skill.tooling",
                "control_plane",
                ("SKILL_TOOL_CAPABILITY_CHANGED",),
            )
        if current.parameter_schema != candidate.parameter_schema:
            return _Classification(
                "skill.tooling",
                "control_plane",
                ("SKILL_PARAMETER_AUTHORITY_CHANGED",),
            )

        if _is_bounded_presentation(current, candidate):
            return _Classification(
                "skill.presentation",
                "presentation_only",
                ("SKILL_PRESENTATION_DSL_ONLY",),
            )
        if _is_bounded_retrieval(current, candidate):
            return _Classification(
                "skill.retrieval",
                "bounded_retrieval",
                ("SKILL_BOUNDED_RETRIEVAL_DSL_ONLY",),
            )

        searchable = "\n".join((_normalized_content(current), _normalized_content(candidate)))
        if _CONTROL_PATTERN.search(searchable):
            return _Classification(
                "skill.tooling",
                "control_plane",
                ("SKILL_CONTROL_PLANE_CONTENT",),
            )
        if _CLINICAL_PATTERN.search(searchable):
            return _Classification(
                "skill.clinical",
                "clinical_guidance",
                ("SKILL_CLINICAL_CONTENT",),
            )

        return _Classification(
            "skill.clinical",
            "clinical_guidance",
            ("SKILL_UNCLASSIFIED_FAIL_CLOSED",),
        )

    @staticmethod
    def _classify_registration(candidate: SkillDefinition) -> _Classification:
        if _is_exact_presentation_definition(candidate):
            return _Classification(
                "skill.presentation",
                "presentation_only",
                ("SKILL_PRESENTATION_DSL_ONLY",),
            )
        if _is_exact_retrieval_definition(candidate):
            return _Classification(
                "skill.retrieval",
                "bounded_retrieval",
                ("SKILL_BOUNDED_RETRIEVAL_DSL_ONLY",),
            )
        searchable = _normalized_content(candidate)
        if _CONTROL_PATTERN.search(searchable) or candidate.tool_names:
            return _Classification(
                "skill.tooling",
                "control_plane",
                ("SKILL_CONTROL_PLANE_CONTENT",),
            )
        if _CLINICAL_PATTERN.search(searchable):
            return _Classification(
                "skill.clinical",
                "clinical_guidance",
                ("SKILL_CLINICAL_CONTENT",),
            )
        return _Classification(
            "skill.clinical",
            "clinical_guidance",
            ("SKILL_UNCLASSIFIED_FAIL_CLOSED",),
        )


def _normalized_content(definition: SkillDefinition) -> str:
    """Inspect descriptive/instruction content without matching YAML control keys."""

    parts = definition.source_markdown.split("---", 2)
    instructions = parts[2] if len(parts) == 3 else definition.source_markdown
    return normalize_skill_text(
        "\n".join(
            (
                definition.name,
                definition.description,
                definition.category,
                instructions,
            )
        )
    ).casefold()


def _instruction_lines(definition: SkillDefinition) -> tuple[str, ...]:
    parts = definition.source_markdown.split("---", 2)
    body = parts[2] if len(parts) == 3 else definition.source_markdown
    return tuple(
        normalize_skill_text(line).strip()
        for line in body.splitlines()
        if normalize_skill_text(line).strip()
    )


def _uses_exact_directive_dsl(
    definition: SkillDefinition,
    *,
    descriptions: frozenset[str],
    directives: frozenset[str],
    required: frozenset[str],
) -> bool:
    lines = _instruction_lines(definition)
    return (
        definition.description in descriptions
        and len(lines) == len(set(lines))
        and frozenset(lines) <= directives
        and required <= frozenset(lines)
    )


def _is_bounded_presentation(
    current: SkillDefinition,
    candidate: SkillDefinition,
) -> bool:
    return (
        current.category.casefold() in _PRESENTATION_CATEGORIES
        and candidate.category == current.category
        and candidate.name == current.name
        and not current.tool_names
        and not candidate.tool_names
        and _is_exact_presentation_definition(current)
        and _is_exact_presentation_definition(candidate)
        and _instruction_lines(current) != _instruction_lines(candidate)
    )


def _is_bounded_retrieval(
    current: SkillDefinition,
    candidate: SkillDefinition,
) -> bool:
    return (
        current.category.casefold() in _RETRIEVAL_CATEGORIES
        and candidate.category == current.category
        and candidate.name == current.name
        and _is_exact_retrieval_definition(current)
        and _is_exact_retrieval_definition(candidate)
        and _instruction_lines(current) != _instruction_lines(candidate)
    )


def _is_exact_presentation_definition(definition: SkillDefinition) -> bool:
    return (
        definition.category.casefold() in _PRESENTATION_CATEGORIES
        and not definition.tool_names
        and _uses_exact_directive_dsl(
            definition,
            descriptions=_PRESENTATION_DESCRIPTIONS,
            directives=_PRESENTATION_DIRECTIVES,
            required=frozenset({"# 工作流", "保留原意。", "不添加新事实。"}),
        )
    )


def _is_exact_retrieval_definition(definition: SkillDefinition) -> bool:
    tools = frozenset(definition.tool_names)
    required = {
        "# 工作流",
        "按用户提供的关键词检索。",
        "保留来源和定位信息。",
        "不改写来源内容。",
    }
    if "search_knowledge" in tools:
        required.add("使用本地知识库。")
    if "search_memory" in tools:
        required.add("使用用户已确认的记忆。")
    lines = frozenset(_instruction_lines(definition))
    return (
        definition.category.casefold() in _RETRIEVAL_CATEGORIES
        and bool(tools)
        and tools <= _BOUNDED_RETRIEVAL_TOOLS
        and ("使用本地知识库。" in lines) == ("search_knowledge" in tools)
        and ("使用用户已确认的记忆。" in lines) == ("search_memory" in tools)
        and _uses_exact_directive_dsl(
            definition,
            descriptions=_RETRIEVAL_DESCRIPTIONS,
            directives=_RETRIEVAL_DIRECTIVES,
            required=frozenset(required),
        )
    )
