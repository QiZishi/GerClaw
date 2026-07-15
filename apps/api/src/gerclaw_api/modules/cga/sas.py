# ruff: noqa: RUF001
"""Versioned SAS definition and deterministic anxiety screening calculation.

The definition is transcribed from ``问卷量表/02-SAS焦虑自评量表.md``.  It has
no model, network, or database dependency: an LLM must never assign scores or
alter its result.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

SAS_SCALE_ID = "sas"
SAS_VERSION = "2026-07-16"
SAS_REVERSE_ITEMS = frozenset({"sas_5", "sas_9", "sas_13", "sas_17", "sas_19"})
SAS_DISCLAIMER = "本结果是筛查结果，不能替代医生的临床诊断。"
SAS_HIGH_SCORE_MESSAGE = "筛查分数较高，建议尽快联系精神科或心理健康专业人员进一步评估。"


@dataclass(frozen=True)
class SasQuestion:
    id: str
    position: int
    text: str
    reverse_scored: bool = False


SAS_QUESTIONS: tuple[SasQuestion, ...] = (
    SasQuestion("sas_1", 1, "我觉得比平常容易紧张或着急"),
    SasQuestion("sas_2", 2, "我无缘无故地感到害怕"),
    SasQuestion("sas_3", 3, "我容易心里烦乱或觉得惊恐"),
    SasQuestion("sas_4", 4, "我觉得我可能将要发疯"),
    SasQuestion("sas_5", 5, "我觉得一切都很好，也不会发生什么不幸", True),
    SasQuestion("sas_6", 6, "我手脚发抖打颤"),
    SasQuestion("sas_7", 7, "我因为头痛、颈痛和背痛而苦恼"),
    SasQuestion("sas_8", 8, "我感觉容易衰弱和疲乏"),
    SasQuestion("sas_9", 9, "我觉得心平气和，并且容易安静坐着", True),
    SasQuestion("sas_10", 10, "我觉得心跳得很快"),
    SasQuestion("sas_11", 11, "我因为阵阵头晕而苦恼"),
    SasQuestion("sas_12", 12, "我有晕倒发作，或觉得要晕倒似的"),
    SasQuestion("sas_13", 13, "我吸气呼气都感到很容易", True),
    SasQuestion("sas_14", 14, "我的手脚麻木和刺痛"),
    SasQuestion("sas_15", 15, "我因为胃痛和消化不良而苦恼"),
    SasQuestion("sas_16", 16, "我常常要小便"),
    SasQuestion("sas_17", 17, "我的手脚常常是干燥温暖的", True),
    SasQuestion("sas_18", 18, "我脸红发热"),
    SasQuestion("sas_19", 19, "我容易入睡并且一夜睡得很好", True),
    SasQuestion("sas_20", 20, "我做恶梦"),
)
SAS_QUESTION_IDS = frozenset(question.id for question in SAS_QUESTIONS)
SAS_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "没有或很少"),
    (2, "有时有"),
    (3, "大部分时间"),
    (4, "绝大部分时间"),
)
SasSeverity = Literal["none", "mild", "moderate", "severe"]


@dataclass(frozen=True)
class SasScore:
    raw_score: int
    standard_score: int
    severity: SasSeverity
    high_severity_follow_up: bool
    safety_messages: tuple[str, ...]
    disclaimer: str = SAS_DISCLAIMER


def score_sas(answers: Mapping[str, int]) -> SasScore:
    """Return the only permitted SAS raw and standard scores for all 20 items."""

    unexpected = set(answers) - SAS_QUESTION_IDS
    missing = SAS_QUESTION_IDS - set(answers)
    if unexpected or missing:
        raise ValueError("SAS answers must contain exactly the twenty defined question identifiers")
    raw_score = 0
    for question in SAS_QUESTIONS:
        value = answers[question.id]
        if isinstance(value, bool) or not isinstance(value, int) or value not in range(1, 5):
            raise ValueError(f"{question.id} must be an integer score from 1 through 4")
        raw_score += 5 - value if question.reverse_scored else value
    standard_score = int(
        (Decimal(raw_score) * Decimal("1.25")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    severity = _severity(standard_score)
    high_severity = severity == "severe"
    return SasScore(
        raw_score=raw_score,
        standard_score=standard_score,
        severity=severity,
        high_severity_follow_up=high_severity,
        safety_messages=(SAS_HIGH_SCORE_MESSAGE,) if high_severity else (),
    )


def _severity(standard_score: int) -> SasSeverity:
    if standard_score < 50:
        return "none"
    if standard_score < 60:
        return "mild"
    if standard_score < 70:
        return "moderate"
    return "severe"
