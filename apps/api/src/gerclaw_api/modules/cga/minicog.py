# ruff: noqa: RUF001
"""Versioned Mini-Cog self-report screening definition and score calculation.

The source is ``问卷量表/04-Mini-Cog简易认知量表.md``.  The web flow guides a
person through word recall and a paper clock task, then records only their
selected screening responses.  It neither analyses a drawing nor claims a
clinician has observed it; the returned result remains a self-report screening
result that needs professional confirmation when positive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MINICOG_SCALE_ID = "minicog"
MINICOG_VERSION = "2026-07-16"
MINICOG_WORDS = ("苹果", "手表", "国旗")
MINICOG_DISCLAIMER = "本结果基于本人作答的认知筛查，不能替代医生的临床诊断。"
MINICOG_FOLLOW_UP_MESSAGE = "筛查结果提示可能存在认知问题，建议由专业人员进一步评估确认。"
MiniCogSeverity = Literal["possible_impairment", "screen_negative"]


@dataclass(frozen=True)
class MiniCogQuestion:
    id: str
    position: int
    text: str


MINICOG_QUESTIONS: tuple[MiniCogQuestion, ...] = (
    MiniCogQuestion(
        "minicog_prepare",
        1,
        "请先记住三个词：苹果、手表、国旗。稍后系统会请您回忆它们。准备好后请选择“已记住”。",
    ),
    MiniCogQuestion(
        "minicog_clock",
        2,
        "请在纸上画一个时钟，写上1到12并把指针指向11点10分。完成后，请根据实际完成情况选择最符合的一项。",
    ),
    MiniCogQuestion(
        "minicog_recall",
        3,
        "现在请回忆刚才记住的三个词：苹果、手表、国旗。您能回忆出几个？",
    ),
)
MINICOG_QUESTION_IDS = frozenset(question.id for question in MINICOG_QUESTIONS)
MINICOG_OPTIONS: dict[str, tuple[tuple[int, str], ...]] = {
    "minicog_prepare": ((0, "已记住，继续"),),
    "minicog_clock": (
        (0, "表盘或时间尚未完成，或我不确定"),
        (1, "数字和表盘完整，指针位置不确定"),
        (2, "数字和表盘完整，指针指向11点10分"),
    ),
    "minicog_recall": (
        (0, "没有回忆出来"),
        (1, "回忆出1个"),
        (2, "回忆出2个"),
        (3, "回忆出3个"),
    ),
}


@dataclass(frozen=True)
class MiniCogScore:
    recalled_word_count: int
    reported_clock_score: int
    total_score: int
    severity: MiniCogSeverity
    high_severity_follow_up: bool
    safety_messages: tuple[str, ...]
    disclaimer: str = MINICOG_DISCLAIMER


def score_minicog(*, recalled_word_count: int, reported_clock_score: int) -> MiniCogScore:
    """Calculate the bounded score from the caller's selected screen responses."""

    _validate_score("recalled_word_count", recalled_word_count, maximum=3)
    _validate_score("reported_clock_score", reported_clock_score, maximum=2)
    total_score = recalled_word_count + reported_clock_score
    possible_impairment = total_score <= 2
    return MiniCogScore(
        recalled_word_count=recalled_word_count,
        reported_clock_score=reported_clock_score,
        total_score=total_score,
        severity="possible_impairment" if possible_impairment else "screen_negative",
        high_severity_follow_up=possible_impairment,
        safety_messages=(MINICOG_FOLLOW_UP_MESSAGE,) if possible_impairment else (),
    )


def _validate_score(name: str, value: int, *, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value not in range(maximum + 1):
        raise ValueError(f"{name} must be an integer from 0 through {maximum}")
