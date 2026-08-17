"""Real-model, evidence-bound extraction of user-authored health memories."""

# ruff: noqa: RUF001 -- Chinese medical prompts intentionally use CJK punctuation.

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any, List, Optional, Protocol, Tuple

from agentscope.message import Msg, SystemMsg, UserMsg
from agentscope.model import StructuredResponse
from pydantic import BaseModel, ValidationError

from gerclaw_api.modules.memory.models import (
    MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
    ConflictResolutionRecord,
    ExtractedMemoryFact,
    MemoryExtraction,
    MemoryFactDetails,
    ProvenanceRecord,
)
from gerclaw_api.modules.validation import validate_versioned_model_output
from gerclaw_api.security import redact_text

_SYSTEM_PROMPT = """你是 GerClaw 的医疗记忆抽取器。只抽取用户在本条消息中明确自述的事实。

安全规则：
1. 禁止从症状推断诊断，禁止补全用户没有说出的药名、剂量、疾病或时间。
2. evidence_span 必须逐字复制自用户消息，且能独立证明该事实。
3. 否认、停药、已解决或更正使用 action=deactivate，不得写成仍然有效。
4. 过敏、慢病、用药、生命体征等只记录用户明确陈述；不确定内容降低 confidence。
5. 身份证、手机号、邮箱、地址、姓名等身份信息不得抽取。
6. 没有值得长期记忆的事实时返回空 facts。

category 使用固定枚举；memory_type 中长期稳定事实用 stable，持续变化状态用 evolving，
有明确时间的跌倒/急诊/手术等事件用 event。statement 使用"用户自述……"表述，不得升级为医生确诊。
"""

_NEGATION_MARKERS = (
    "没有",
    "并无",
    "否认",
    "无过敏",
    "不过敏",
    "未患",
    "没患",
    "未服用",
    "没有服用",
    "没服用",
    "不服用",
    "未使用",
    "没有使用",
    "没使用",
    "未吃",
    "没吃",
    "不吃",
    "阴性",
    "否定",
    "未见",
    "不存在",
    "排除",
    "不再",
    "停药",
    "停用",
    "停止服用",
    "已经好了",
    "已恢复",
    "不是",
    "从未",
    "从没",
    "从无",
    "从不",
    "不患",
    "没得",
    "未确诊",
    "未诊断",
    "未跌倒",
    "无跌倒",
    "未做过",
    "不吸烟",
    "不抽烟",
    "不喝酒",
    "不饮酒",
    "不需要",
)
_NEGATION_PATTERNS = (
    re.compile(r"(?:从未|从没|从无|无|不)[^，,。；;！!？?\n]{0,24}(?:过敏|不耐受)"),
    re.compile(
        r"(?:从未|从没|从无|无|不|未|没)[^，,。；;！!？?\n]{0,24}"
        r"(?:服用|用药|使用|吃药|注射|吸入)"
    ),
    re.compile(
        r"(?:从未|从没|从无|从不|未|没有|没|无|不|不要)"
        r"[^，,。；;！!？?\n]{0,16}"
        r"(?:患|得|确诊|诊断|病史|跌倒|摔倒|手术|吸烟|抽烟|喝酒|饮酒|需要|助行)"
    ),
    re.compile(
        r"(?:^|[，,。；;：:！!？?\s])(?:我|本人|自己)"
        r"(?:目前|当前|现在|一直|明确|确实|曾经|曾|既往|表示){0,2}"
        r"(?:从未|从没|从无|从不|未|没有|没|无|不|不要)"
    ),
)
_CONTINUED_USE_PATTERNS = (
    re.compile(
        r"(?:目前|当前|现在|正在|一直|还在|仍|继续|持续)"
        r"(?:服用|使用|吃|口服|用药|注射|吸入)"
    ),
    re.compile(r"(?:每天|每日|定期|长期|常年)(?:服用|使用|吃|口服|用药)"),
    re.compile(
        r"(?:^|[，,。；;：:！!？?\s])(?:我|本人|自己)"
        r"(?:不是|并非)(?:每天|每日|经常|常|定期)"
        r"(?:吸烟|抽烟|喝酒|饮酒)"
    ),
)
_CATEGORY_ASSERTION_MARKERS = {
    "basic_info": ("岁", "年龄", "出生", "性别", "身高", "体重"),
    "allergy": ("过敏", "不耐受"),
    "condition": ("有", "患", "得", "诊断", "确诊", "病史", "查出"),
    "medication": (
        "服用",
        "口服",
        "吃",
        "用药",
        "使用",
        "注射",
        "吸入",
        "停用",
        "停药",
        "停止服用",
        "药",
    ),
    "vital_sign": ("血压", "心率", "血糖", "体温", "体重", "血氧"),
    "assessment": ("评估", "评分", "等级", "风险"),
    "event": ("发生", "跌倒", "摔倒", "住院", "急诊", "手术", "做过"),
    "social": ("独居", "同住", "吸烟", "抽烟", "喝酒", "饮酒", "助行", "照护"),
    "preference": ("喜欢", "偏好", "希望", "不喜欢"),
    "goal": ("目标", "希望", "想改善", "想达到"),
}
_FIRST_PERSON_ASSERTION_PATTERNS = (
    re.compile(
        r"(?:^|[，,。；;：:！!？?\s])(?:我(?:自己)?|本人|自己)"
        r"(?:目前|当前|现在|最近|去年|前年|今年|上月|上个月|正在|在|还|也|都|一直|常年|已经|已|曾经|曾|"
        r"既往|每天|每日|今天|昨天|今年|明确|确实|可能|也许|怀疑|不确定|"
        r"好像|大概|或许|疑似|现服){0,6}"
        r"(?:对|有|患有|患|得了|被诊断为|诊断为|确诊(?:过|为)?|查出(?:过)?|被查出|服用|口服|吃药|"
        r"用药|使用|注射|吸入|停用|停药|停止服用|发生|做过|跌倒|摔倒|住院|急诊|独居|同住|"
        r"吸烟|抽烟|喝酒|饮酒|需要|喜欢|偏好|希望|年龄|出生|身高|体重)"
    ),
    re.compile(r"(?:^|[，,。；;：:！!？?\s])(?:我|本人|自己)(?:今年)?\d{1,3}岁"),
    re.compile(
        r"(?:^|[，,。；;：:！!？?\s])我(?:和|与)[^，,。；;：:！!？?\n]{1,20}"
        r"(?:都|均)(?:有|患有|患|服用|使用|对)"
    ),
)
_COLLECTIVE_SELF_REPORT_PATTERNS = (_FIRST_PERSON_ASSERTION_PATTERNS[-1],)
_CATEGORY_SELF_REPORT_PATTERNS = {
    "basic_info": (
        re.compile(
            r"(?:^|[，,。；;：:！!？?\s])(?:我|本人|自己)(?:的)?"
            r"(?:年龄|出生日期|出生年份|性别|身高|体重)(?:是|为|有|：|:)?"
        ),
    ),
    "vital_sign": (
        re.compile(
            r"(?:^|[，,。；;：:！!？?\s])(?:我|本人|自己)(?:的)?"
            r"(?:血压|心率|血糖|体温|血氧|体重)(?:是|为|有|测得|：|:)?"
        ),
    ),
    "assessment": (
        re.compile(
            r"(?:^|[，,。；;：:！!？?\s])(?:我|本人|自己)(?:的)?"
            r"[^，,。；;：:！!？?\n]{0,30}(?:评估|评分|等级|风险)"
            r"(?:是|为|有|：|:)?"
        ),
    ),
    "event": (
        re.compile(
            r"(?:^|[，,。；;：:！!？?\s])(?:我|本人|自己)"
            r"(?:去年|前年|今年|上月|上个月|最近|曾经|曾|已经|已|既往){0,3}"
            r"(?:发生|做过|跌倒|摔倒|住院|急诊|手术)"
        ),
    ),
    "social": (
        re.compile(
            r"(?:^|[，,。；;：:！!？?\s])(?:我|本人|自己)"
            r"(?:目前|当前|现在|一直|是|为){0,3}"
            r"(?:独居|同住|吸烟|抽烟|喝酒|饮酒|使用助行器|需要照护)"
        ),
    ),
    "goal": (
        re.compile(
            r"(?:^|[，,。；;：:！!？?\s])(?:我|本人|自己)(?:的)?"
            r"(?:目标|愿望)(?:是|为|：|:)?"
        ),
    ),
}
_FIRST_PERSON_NEGATION_PATTERNS = (
    re.compile(
        r"(?:^|[，,。；;：:！!？?\s])(?:我|本人|自己)"
        r"(?:目前|当前|现在|一直|已经|已|曾经|曾|既往|明确|确实|表示|"
        r"可能|也许|怀疑|不确定|好像|大概|或许|疑似){0,4}"
        r"(?:从未|从没|从无|从不|未|没有|没|无|不|否认|停用|停药|停止服用|不再|已恢复|已经好了)"
    ),
)
_OMITTED_SELF_REPORT_PATTERNS = (
    re.compile(
        r"^(?:但是|而是|但|却|不过)?"
        r"(?:目前|当前|现在|正在|一直|已经|曾经|曾|既往|每天|每日|现服){0,3}"
        r"(?:服用|口服|吃药|用药|使用|注射|吸入|患有|诊断为|确诊为|有)"
    ),
    re.compile(
        r"^(?:但是|而是|但|却|不过)?(?:目前|当前|现在|曾经|曾|既往)?"
        r"对.{1,120}(?:过敏|不耐受)"
    ),
    re.compile(r"^(?:但是|而是|但|却|不过)[^，,。；;！!？?\n]{1,120}(?:过敏|不耐受)"),
    re.compile(
        r"^(?:目前|当前|现在|正在)(?:出现|发生)[^，,。；;！!？?\n]{1,120}"
        r"(?:过敏|不耐受)"
    ),
    re.compile(r"^[^，,。；;！!？?\n]{1,80}过敏史(?:阴性|阳性)$"),
)
_DEACTIVATION_MARKERS = (
    "没有",
    "并无",
    "否认",
    "未服用",
    "没有服用",
    "没服用",
    "不服用",
    "未使用",
    "没有使用",
    "没使用",
    "未吃",
    "没吃",
    "不吃",
    "阴性",
    "否定",
    "未见",
    "不存在",
    "排除",
    "不再",
    "停药",
    "停用",
    "停止服用",
    "已经好了",
    "已恢复",
    "不是",
)
_OTHER_SUBJECT_MARKERS = (
    "我父亲",
    "我母亲",
    "我爸爸",
    "我妈妈",
    "我爸",
    "我妈",
    "我爷爷",
    "我奶奶",
    "我外公",
    "我外婆",
    "我祖父",
    "我祖母",
    "家人",
    "老伴",
    "妻子",
    "丈夫",
    "儿子",
    "女儿",
    "朋友",
    "家属",
)
_OTHER_SUBJECT_PATTERNS = (
    re.compile(
        r"(?:我|本人|自己)(?:的)?"
        r"(?:父亲|母亲|爸爸|妈妈|爸|妈|爷爷|奶奶|外公|外婆|祖父|祖母|"
        r"老伴|妻子|丈夫|爱人|儿子|女儿|孙子|孙女|家人|亲属|朋友|同事)"
    ),
    re.compile(
        r"(?:^|[，,。；;：:！!？?\s])(?:他|她)"
        r"(?:的|有|患有|服用|使用|对|目前|曾经|正在|被诊断|确诊)"
    ),
)
_CLAUSE_BOUNDARIES = frozenset("，,。；;：:！!？?\n")
_TRANSITION_MARKERS = ("但是", "而是", "但", "却", "不过")
_STATUS_SAFETY_RANK = {"confirmed": 0, "pending": 1, "inactive": 2}
_LITERAL_ENTITY_EXEMPT_CATEGORIES = frozenset({"basic_info", "vital_sign", "assessment"})
_EVIDENCED_DETAIL_FIELDS = (
    "value",
    "unit",
    "dose",
    "frequency",
    "route",
    "reaction",
    "code",
    "level",
)
_SEVERITY_MARKERS = {
    "mild": ("mild", "轻度", "轻微"),
    "moderate": ("moderate", "中度", "中等"),
    "severe": ("severe", "重度", "严重"),
}
_SOURCE_STATUS_MARKERS = {
    "active": ("active", "目前", "当前", "正在", "现服", "服用", "使用"),
    "stopped": ("stopped", "停药", "停用", "停止服用", "不再"),
    "resolved": ("resolved", "已经好了", "已恢复", "已解决"),
    "historical": ("historical", "曾", "既往", "病史", "史"),
}
_MEDICATION_MARKERS = (
    "服用",
    "口服",
    "吃",
    "用药",
    "使用",
    "注射",
    "吸入",
    "停用",
    "停药",
    "停止服用",
    "药",
)
_UNCERTAINTY_MARKERS = (
    "可能",
    "也许",
    "怀疑",
    "疑似",
    "不确定",
    "好像",
    "大概",
    "或许",
    "尚未确诊",
    "待查",
    "待确认",
    "据说",
    "听说",
    "是不是",
)
_NON_FACT_MARKERS = (
    "是否",
    "吗",
    "？",
    "?",
    "应该",
    "怎么",
    "如何",
    "如果",
    "假如",
    "准备",
    "计划",
    "打算",
    "考虑",
    "想服用",
    "想吃",
    "想要",
    "不要",
    "能否",
    "需不需要",
    "想了解",
    "想咨询",
)


class StructuredMemoryModel(Protocol):
    """Narrow AgentScope structured-output surface used by the extractor."""

    async def generate_structured_output(
        self,
        messages: list[Msg],
        structured_model: type[BaseModel] | dict[Any, Any],
        **kwargs: Any,
    ) -> StructuredResponse: ...


class MemoryExtractionError(RuntimeError):
    """Safe failure that never includes model output or user text."""


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def _evidence_contexts(source: str, evidence: str) -> list[str]:
    """Return every source clause containing an exact evidence occurrence."""

    contexts: list[str] = []
    search_from = 0
    while (position := source.find(evidence, search_from)) >= 0:
        left = position
        while left > 0 and source[left - 1] not in _CLAUSE_BOUNDARIES:
            left -= 1
        right = position + len(evidence)
        while right < len(source) and source[right] not in _CLAUSE_BOUNDARIES:
            right += 1
        clause = source[left:right]
        relative_start = position - left
        relative_end = relative_start + len(evidence)
        preceding = [
            (clause.rfind(marker, 0, relative_start), len(marker)) for marker in _TRANSITION_MARKERS
        ]
        preceding = [
            item for item in preceding if item[0] >= 0 and clause[item[0] : item[0] + 3] != "不过敏"
        ]
        if preceding:
            transition_start, _transition_length = max(preceding)
            clause = clause[transition_start:]
            relative_end -= transition_start
        following = [clause.find(marker, relative_end) for marker in _TRANSITION_MARKERS]
        following = [
            item for item in following if item >= 0 and clause[item : item + 3] != "不过敏"
        ]
        if following:
            clause = clause[: min(following)]
        contexts.append(clause.strip())
        search_from = position + 1
    return contexts


def _compact(value: str) -> str:
    return "".join(
        character for character in _normalized(value).casefold() if not character.isspace()
    )


def _is_evidenced(evidence: str, value: str) -> bool:
    compact_value = _compact(value)
    return bool(compact_value) and compact_value in _compact(evidence)


def _evidences_datetime(evidence: str, value: datetime) -> bool:
    year, month, day = value.year, value.month, value.day
    variants = (
        f"{year:04d}-{month:02d}-{day:02d}",
        f"{year:04d}/{month:02d}/{day:02d}",
        f"{year:04d}.{month:02d}.{day:02d}",
        f"{year}年{month}月{day}日",
        f"{year}年{month:02d}月{day:02d}日",
    )
    return any(item in evidence for item in variants)


def _matches_any_pattern(contexts: list[str], patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(context) for context in contexts for pattern in patterns)


def evidence_has_negation(
    text: str,
    *,
    category: str | None = None,
    entity: str | None = None,
) -> bool:
    """Detect negation only when its scope targets this category/entity."""

    normalized = _normalized(text)
    if _matches_any_pattern([normalized], _CONTINUED_USE_PATTERNS):
        return False
    if category is not None and entity:
        compact = _compact(normalized)
        target = re.escape(_compact(entity))
        bounded = r"[^，,。；;：:！!？?\n]{0,16}"
        if category == "allergy":
            if re.search(rf"(?:不是|并非)(?:对)?{target}(?:不过敏|不耐受阴性)", compact):
                return False
            return bool(
                re.search(
                    rf"(?:没有|并无|无|否认|从未|从没|从无)(?:对)?{bounded}{target}"
                    rf"{bounded}(?:过敏|不耐受)",
                    compact,
                )
                or re.search(rf"(?:对)?{target}(?:不过敏|过敏史阴性|不耐受阴性)", compact)
                or re.search(
                    rf"(?:对)?{target}{bounded}(?:没有|无|未见|未发现)"
                    rf"{bounded}(?:过敏|不耐受)",
                    compact,
                )
            )
        if category == "condition":
            return bool(
                re.search(
                    rf"(?:没有|并无|无|否认|从未患|未患|没患|不患|没得|"
                    rf"未确诊|未诊断|排除|不存在){bounded}{target}",
                    compact,
                )
                or re.search(
                    rf"{target}{bounded}(?:阴性|未见|排除|不存在|已经好了|已恢复|"
                    rf"(?:尚未|还未|没有|未){bounded}(?:确诊|诊断))",
                    compact,
                )
            )
        if category == "medication":
            return bool(
                re.search(
                    rf"(?:未|没有|并未|并没有|没|不|从未|从没|从不)(?:再)?"
                    rf"(?:服用|使用|吃|口服|注射|吸入){bounded}{target}",
                    compact,
                )
                or re.search(
                    rf"(?:停用|停药|停止服用|不再服用|不再使用){bounded}{target}",
                    compact,
                )
                or re.search(rf"{target}{bounded}(?:已?停药|已?停用|停止服用|不再服用)", compact)
            )
        if category == "event":
            return bool(
                re.search(
                    rf"(?:未|没有|并无|无|否认|从未|从没)(?:发生|有|做过)?"
                    rf"{bounded}{target}",
                    compact,
                )
                or re.search(rf"{target}(?:史)?(?:阴性|未见)", compact)
            )
        if category == "social":
            return bool(
                re.search(
                    rf"(?:不|从不|未|没有|并无|无)(?:再)?(?:需要|使用)?{target}",
                    compact,
                )
            )
        return bool(re.search(rf"(?:没有|并无|否认|无|未见|不存在|排除){bounded}{target}", compact))
    return any(marker in normalized for marker in _NEGATION_MARKERS) or _matches_any_pattern(
        [normalized], _NEGATION_PATTERNS
    )


def _has_explicit_self_report(contexts: list[str], category: str) -> bool:
    markers = _CATEGORY_ASSERTION_MARKERS.get(category, ())
    first_person_assertion = _matches_any_pattern(
        contexts, _FIRST_PERSON_ASSERTION_PATTERNS
    ) and any(marker in context for context in contexts for marker in markers)
    category_assertion = _matches_any_pattern(
        contexts, _CATEGORY_SELF_REPORT_PATTERNS.get(category, ())
    )
    return (
        first_person_assertion
        or category_assertion
        or _matches_any_pattern(contexts, _OMITTED_SELF_REPORT_PATTERNS)
    )


def _sanitize_candidate(
    fact: ExtractedMemoryFact,
    evidence: str,
) -> ExtractedMemoryFact | None:
    """Remove unsupported optional fields and reject an unbound fact identity."""

    entity_is_literal = _is_evidenced(evidence, fact.entity)
    if fact.category not in _LITERAL_ENTITY_EXEMPT_CATEGORIES and not entity_is_literal:
        return None
    if fact.category == "allergy" and not any(
        marker in evidence for marker in ("过敏", "不耐受", "allergy")
    ):
        return None
    if fact.category == "medication" and not any(
        marker in evidence for marker in _MEDICATION_MARKERS
    ):
        return None
    if fact.category not in {"allergy", "medication"} and any(
        marker in evidence for marker in ("过敏", "不耐受", "allergy")
    ):
        return None

    updates: dict[str, str | None] = {}
    for field_name in _EVIDENCED_DETAIL_FIELDS:
        raw_value = getattr(fact.details, field_name)
        if isinstance(raw_value, str) and raw_value and not _is_evidenced(evidence, raw_value):
            updates[field_name] = None

    severity = fact.details.severity
    if severity in {"mild", "moderate", "severe"} and not any(
        marker in evidence for marker in _SEVERITY_MARKERS[severity]
    ):
        updates["severity"] = None
    source_status = fact.details.source_status
    if source_status != "unknown" and not any(
        marker in evidence for marker in _SOURCE_STATUS_MARKERS[source_status]
    ):
        updates["source_status"] = "unknown"

    details = MemoryFactDetails.model_validate(
        {**fact.details.model_dump(mode="python"), **updates}
    )
    if fact.category == "basic_info" and details.value is None:
        return None
    if fact.category == "vital_sign" and (details.value is None or details.unit is None):
        return None
    if (
        fact.category == "assessment"
        and not entity_is_literal
        and not any((details.value, details.code, details.level))
    ):
        return None

    occurred_at = fact.occurred_at
    if occurred_at is not None and not _evidences_datetime(evidence, occurred_at):
        occurred_at = None
    return fact.model_copy(update={"details": details, "occurred_at": occurred_at})


def _generate_provenance(
    fact: ExtractedMemoryFact,
    confidence: float,
    model_name: str = "unknown",
) -> ProvenanceRecord:
    """生成provenance记录，记录事实来源信息。

    注意：verification_status 始终为 unverified，因为自动验证属于
    GerClaw 医疗安全边界，不能仅基于置信度自动通过。
    用户需通过 revision-fenced decision 明确确认后才变为 manual_verified。
    """

    # 根据类别确定来源类型（ProvenanceRecord.source_type Literal 允许值）
    source_type_mapping: dict[str, str] = {
        "allergy": "user_report",
        "medication": "medication_list",
        "vital_sign": "clinical_document",
        "condition": "user_report",
        "event": "user_report",
        "basic_info": "user_report",
        "assessment": "clinical_document",
    }

    return ProvenanceRecord(
        source_type=source_type_mapping.get(fact.category, "user_report"),
        extraction_method="llm_extraction",
        confidence_score=confidence,
        # 安全边界：提取器不自动验证，需用户 decision 确认
        verification_status="unverified",
        extraction_model=model_name,
        notes=f"从用户输入中提取，类别: {fact.category}",
    )


def _detect_conflicts(
    fact: ExtractedMemoryFact,
    existing_facts: List[ExtractedMemoryFact],
    contexts: List[str],
) -> Optional[ConflictResolutionRecord]:
    """检测新事实与现有事实之间的冲突。

    注意：ExtractedMemoryFact 在提取阶段尚无持久化 ID，
    因此使用 category+entity+statement 的确定性哈希生成 UUID，
    保证同一冲突的 ID 始终一致。
    """

    if not existing_facts:
        return None

    # 查找同类别同实体的现有事实
    conflicting_facts = [
        existing for existing in existing_facts
        if existing.category == fact.category and existing.entity == fact.entity
    ]

    if not conflicting_facts:
        return None

    # 检测冲突类型
    has_negation = any(
        evidence_has_negation(context, category=fact.category, entity=fact.entity)
        for context in contexts
    )

    if has_negation:
        conflict_type = "negation"
        resolution_strategy = "user_review"
        resolution_reason = "检测到否定证据，需要用户确认"
    elif fact.action == "deactivate":
        conflict_type = "deactivation"
        resolution_strategy = "user_review"
        resolution_reason = "事实被标记为停用，需要用户确认"
    else:
        # 检查是否是更新
        existing = conflicting_facts[0]
        if existing.statement != fact.statement:
            conflict_type = "update"
            resolution_strategy = "latest_wins"
            resolution_reason = "检测到陈述更新，采用最新版本"
        else:
            return None

    # 使用确定性哈希生成 UUID（category+entity+statement），避免随机 ID
    def _fact_deterministic_uuid(f: ExtractedMemoryFact) -> uuid.UUID:
        seed = f"{f.category}|{f.entity}|{f.statement}"
        return uuid.uuid5(uuid.NAMESPACE_URL, seed)

    return ConflictResolutionRecord(
        conflict_type=conflict_type,
        conflicting_fact_ids=[_fact_deterministic_uuid(f) for f in conflicting_facts],
        resolution_strategy=resolution_strategy,
        resolution_reason=resolution_reason,
        original_values={
            "statements": [f.statement for f in conflicting_facts],
            "statuses": [f.action for f in conflicting_facts],
        },
        merged_values={
            "statement": fact.statement,
            "action": fact.action,
        },
    )


def _determine_fallback_reason(
    fact: ExtractedMemoryFact,
    has_negation: bool,
    has_uncertainty: bool,
    has_self_report: bool,
    has_deactivation: bool,
) -> Optional[str]:
    """确定降级原因"""

    if has_negation:
        return "检测到否定证据"
    if has_uncertainty:
        return "信息存在不确定性"
    if not has_self_report:
        return "缺乏明确的自我报告"
    if has_deactivation:
        return "事实被标记为停用"
    if fact.confidence < 0.7:
        return f"置信度过低: {fact.confidence:.2f}"
    return None


class RealMemoryExtractor:
    """Use configured AgentScope failover while enforcing source evidence in code."""

    def __init__(
        self,
        model: StructuredMemoryModel,
        *,
        min_confidence: float,
        max_facts: int,
        model_name: str = "unknown",
    ) -> None:
        self._model = model
        self._min_confidence = min_confidence
        self._max_facts = max_facts
        self._model_name = model_name
        self._existing_facts: List[ExtractedMemoryFact] = []

    async def extract(
        self,
        user_text: str,
    ) -> Tuple[List[Tuple[ExtractedMemoryFact, str]], Optional[str]]:
        """Return candidates paired with deterministic confirmed/pending/inactive status."""

        safe_text = _normalized(redact_text(user_text))
        if not safe_text or len(safe_text) > 4_000:
            raise ValueError("memory extraction input must contain 1 to 4,000 characters")

        error_message = None
        try:
            response = await self._model.generate_structured_output(
                [
                    SystemMsg(name="memory_policy", content=_SYSTEM_PROMPT),
                    UserMsg(
                        name="user",
                        content=(
                            f"<untrusted-user-statement>\n{safe_text}\n</untrusted-user-statement>"
                        ),
                    ),
                ],
                MemoryExtraction,
            )
            extraction = validate_versioned_model_output(
                response.content,
                output_model=MemoryExtraction,
                schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            )
        except (ValidationError, ValueError) as error:
            raise MemoryExtractionError("memory model returned an invalid schema") from error
        except Exception as error:
            error_message = str(error)
            raise MemoryExtractionError("memory model extraction failed") from error

        validated: dict[
            tuple[str, str, str], tuple[tuple[int, int, float], ExtractedMemoryFact, str]
        ] = {}
        for fact in extraction.facts:
            evidence = _normalized(fact.evidence_span)
            if not evidence or evidence not in safe_text:
                continue
            evidence_occurrences = _evidence_contexts(safe_text, evidence)
            contexts = [
                local_context
                for occurrence in evidence_occurrences
                for local_context in (
                    _evidence_contexts(occurrence, fact.entity)
                    if fact.entity in occurrence
                    else [occurrence]
                )
            ]
            sanitized = _sanitize_candidate(fact, evidence)
            if sanitized is None:
                continue
            fact = sanitized
            event_identity = ""
            if fact.category == "event" or fact.memory_type == "event":
                event_identity = (
                    fact.occurred_at.isoformat()
                    if fact.occurred_at is not None
                    else f"{safe_text.rfind(evidence)}:{_compact(evidence)}"
                )
            key = (fact.category, _normalized(fact.entity).casefold(), event_identity)
            # An exact substring can still omit its negating prefix or suffix,
            # e.g. source "没有青霉素过敏" with evidence "青霉素过敏".
            # Inspect every containing clause and conservatively withhold
            # confirmation when any occurrence is negated or ambiguous.
            has_negation = any(
                evidence_has_negation(
                    context,
                    category=fact.category,
                    entity=fact.entity,
                )
                for context in contexts
            )
            has_uncertainty = any(
                marker in context for context in contexts for marker in _UNCERTAINTY_MARKERS
            )
            is_non_fact = any(
                marker in context for context in contexts for marker in _NON_FACT_MARKERS
            )
            continued_use = _matches_any_pattern(contexts, _CONTINUED_USE_PATTERNS)
            has_self_report = (
                _has_explicit_self_report(contexts, fact.category)
                or continued_use
                or (
                    has_negation and _matches_any_pattern(contexts, _FIRST_PERSON_NEGATION_PATTERNS)
                )
            )
            has_deactivation = any(
                marker in context for context in contexts for marker in _DEACTIVATION_MARKERS
            )
            has_other_subject = any(
                marker in context for context in contexts for marker in _OTHER_SUBJECT_MARKERS
            ) or _matches_any_pattern(contexts, _OTHER_SUBJECT_PATTERNS)
            collective_self_report = _matches_any_pattern(
                contexts, _COLLECTIVE_SELF_REPORT_PATTERNS
            )
            if (
                (has_other_subject and not collective_self_report)
                or is_non_fact
                or not has_self_report
            ):
                continue
            if has_negation:
                # Negative evidence can retire an active fact, but can never be
                # represented as a positive fact that a later API call confirms.
                fact = fact.model_copy(update={"action": "deactivate"})
            elif continued_use:
                fact = fact.model_copy(update={"action": "upsert"})
            if has_uncertainty:
                status = "pending"
            elif has_negation or (fact.action == "deactivate" and has_deactivation):
                status = "inactive"
            elif fact.action == "deactivate" or has_negation:
                status = "pending"
            elif has_self_report and fact.confidence >= self._min_confidence:
                status = "confirmed"
            else:
                status = "pending"

            # 生成provenance记录
            provenance = _generate_provenance(
                fact=fact,
                confidence=fact.confidence,
                model_name=self._model_name,
            )

            # 检测冲突
            conflict_resolution = _detect_conflicts(
                fact=fact,
                existing_facts=self._existing_facts,
                contexts=contexts,
            )

            # 确定降级原因
            fallback_reason = _determine_fallback_reason(
                fact=fact,
                has_negation=has_negation,
                has_uncertainty=has_uncertainty,
                has_self_report=has_self_report,
                has_deactivation=has_deactivation,
            )

            # 更新fact，添加新字段
            fact = fact.model_copy(update={
                "provenance": provenance,
                "conflict_resolution": conflict_resolution,
                "fallback_reason": fallback_reason,
            })

            rank = (
                safe_text.rfind(evidence),
                _STATUS_SAFETY_RANK[status],
                fact.confidence,
            )
            current = validated.get(key)
            if current is None or rank > current[0]:
                validated[key] = (rank, fact, status)

        # 更新现有事实列表
        for key, (rank, fact, status) in validated.items():
            if status == "confirmed":
                self._existing_facts.append(fact)

        ordered = sorted(
            validated.items(),
            key=lambda item: (item[1][0][0], item[0]),
        )

        result = [(fact, status) for _key, (_rank, fact, status) in ordered[: self._max_facts]]

        # 如果没有提取到任何事实，返回一个待确认的事实
        if not result:
            fallback_fact = ExtractedMemoryFact(
                category="basic_info",
                memory_type="stable",
                entity="用户输入",
                statement="用户输入了健康相关信息（无明确事实）",
                evidence_span=safe_text[:50] if len(safe_text) > 50 else safe_text,
                action="upsert",
                confidence=0.2,
                details=MemoryFactDetails(),
                provenance=ProvenanceRecord(
                    source_type="user_report",
                    extraction_method="llm_extraction",
                    confidence_score=0.2,
                    verification_status="unverified",
                    notes="LLM未提取到明确事实",
                ),
                fallback_reason="LLM未提取到明确事实，返回待确认信息",
            )
            result = [(fallback_fact, "pending")]

        return result, error_message
