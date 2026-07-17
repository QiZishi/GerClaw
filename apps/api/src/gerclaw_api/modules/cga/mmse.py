# ruff: noqa: RUF001
"""Versioned MMSE self-report screening definition and deterministic scoring.

Source: ``问卷量表/05-MMSE简易智能精神状态检查量表.md``.  The browser records
whether the participant reports completing each standard item.  It does not
pretend to observe an action, read handwriting, or assess an uploaded drawing;
the resulting score is a self-report screening result and not a diagnosis.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

MMSE_SCALE_ID = "mmse"
MMSE_VERSION = "2026-07-16"
MMSE_ITEM_IDS = frozenset(f"mmse_{position}" for position in range(1, 31))
MMSE_DISCLAIMER = "本结果是认知筛查结果，不能替代医生的临床诊断。"
MMSE_FOLLOW_UP_MESSAGE = "筛查结果提示认知功能可能受影响，建议由专业人员进一步评估确认。"
EducationLevel = Literal["none", "primary_or_less", "secondary_or_more"]
MmseSeverity = Literal["normal", "mild_impairment", "moderate_impairment", "severe_impairment"]


@dataclass(frozen=True)
class MmseQuestion:
    id: str
    position: int
    text: str


MMSE_EDUCATION_ID = "mmse_education"
MMSE_EDUCATION_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "未受过学校教育"),
    (1, "小学或受教育年限不超过6年"),
    (2, "中学或以上"),
)
MMSE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "未完成、答错或不确定"),
    (1, "已完成或答对"),
)
_MMSE_ITEM_TEXTS = (
    "今天是星期几？",
    "今天是几号？",
    "现在是几月份？",
    "现在是什么季节？",
    "今年是哪一年？",
    "现在我们在哪里（省、市）？",
    "现在我们在什么地方（区、县）？",
    "现在我们在什么街道（乡、村）？",
    "这里是什么地方（地址名称）？",
    "现在在第几层楼？",
    "请复述“皮球”。",
    "请复述“国旗”。",
    "请复述“树木”。",
    "请计算100减7。",
    "请继续从上一个答案减7。",
    "请继续从上一个答案减7。",
    "请继续从上一个答案减7。",
    "请继续从上一个答案减7。",
    "请回忆“皮球”。",
    "请回忆“国旗”。",
    "请回忆“树木”。",
    "请辨认手表。",
    "请辨认钢笔。",
    "请复述“四十四只石狮子”。",
    "请阅读“闭上你的眼睛”并按意思完成动作。",
    "请用右手拿纸。",
    "请将纸对折。",
    "请将纸放在自己大腿上。",
    "请写一句完整的句子。",
    "请照样画出图形。",
)
MMSE_QUESTIONS: tuple[MmseQuestion, ...] = (
    MmseQuestion(MMSE_EDUCATION_ID, 1, "请先选择您的受教育情况，用于解释本次筛查分界值。"),
    *tuple(
        MmseQuestion(f"mmse_{position}", position + 1, text)
        for position, text in enumerate(_MMSE_ITEM_TEXTS, start=1)
    ),
)


@dataclass(frozen=True)
class MmseScore:
    total_score: int
    severity: MmseSeverity
    education_level: EducationLevel
    education_threshold: int
    education_adjusted_screen_positive: bool
    high_severity_follow_up: bool
    safety_messages: tuple[str, ...]
    disclaimer: str = MMSE_DISCLAIMER


def score_mmse(
    *, reported_item_scores: Mapping[str, int], education_level: EducationLevel
) -> MmseScore:
    """Score thirty bounded participant-reported MMSE item results."""

    unexpected = set(reported_item_scores) - MMSE_ITEM_IDS
    missing = MMSE_ITEM_IDS - set(reported_item_scores)
    if unexpected or missing:
        raise ValueError("MMSE requires exactly the thirty server-defined item identifiers")
    for item_id, value in reported_item_scores.items():
        if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
            raise ValueError(f"{item_id} must be a binary score")
    if education_level not in {"none", "primary_or_less", "secondary_or_more"}:
        raise ValueError("education_level is invalid")

    total_score = sum(reported_item_scores.values())
    severity = _severity(total_score)
    threshold = {"none": 17, "primary_or_less": 20, "secondary_or_more": 24}[education_level]
    screen_positive = total_score <= threshold
    return MmseScore(
        total_score=total_score,
        severity=severity,
        education_level=education_level,
        education_threshold=threshold,
        education_adjusted_screen_positive=screen_positive,
        high_severity_follow_up=screen_positive,
        safety_messages=(MMSE_FOLLOW_UP_MESSAGE,) if screen_positive else (),
    )


def _severity(total_score: int) -> MmseSeverity:
    if total_score >= 27:
        return "normal"
    if total_score >= 21:
        return "mild_impairment"
    if total_score >= 10:
        return "moderate_impairment"
    return "severe_impairment"
