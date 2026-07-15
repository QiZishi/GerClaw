# ruff: noqa: RUF001
"""Versioned PHQ-9 definition and deterministic screening score calculation.

This module deliberately has no model, network, or database dependency.  A
language model may later help guide a conversation, but it must never produce
or alter the score calculated here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

PHQ9_SCALE_ID = "phq9"
PHQ9_VERSION = "2026-07-16"
PHQ9_MAX_SCORE = 27
PHQ9_URGENT_ITEM_ID = "phq9_9"

SCREENING_DISCLAIMER = "本结果是筛查结果，不能替代医生的临床诊断。"
URGENT_SAFETY_MESSAGE = (
    "您提到可能有伤害自己的想法。这很重要，请立即告诉可信赖的家人或医生；"
    "如有紧急危险，请联系当地急救服务或尽快前往医院。"
)
HIGH_SCORE_SAFETY_MESSAGE = "筛查分数较高，建议尽快联系医生进行进一步评估。"


@dataclass(frozen=True)
class Phq9Question:
    """One immutable question whose score is constrained to the PHQ-9 range."""

    id: str
    position: int
    text: str
    sensitive_prefix: str | None = None


PHQ9_QUESTIONS: tuple[Phq9Question, ...] = (
    Phq9Question("phq9_1", 1, "过去两周内，做事时提不起兴趣或乐趣"),
    Phq9Question("phq9_2", 2, "过去两周内，感到心情低落、沮丧或绝望"),
    Phq9Question("phq9_3", 3, "过去两周内，入睡困难、睡不安稳或睡眠过多"),
    Phq9Question("phq9_4", 4, "过去两周内，感觉疲倦或没有活力"),
    Phq9Question("phq9_5", 5, "过去两周内，食欲不振或暴饮暴食"),
    Phq9Question("phq9_6", 6, "过去两周内，觉得自己很糟，或觉得自己很失败，或让家人失望"),
    Phq9Question("phq9_7", 7, "过去两周内，对事物专注有困难（如阅读报纸或看电视）"),
    Phq9Question("phq9_8", 8, "过去两周内，动作或说话缓慢到他人已察觉，或正好相反—烦躁或坐立不安"),
    Phq9Question(
        "phq9_9",
        9,
        "过去两周内，有不如死掉或用某种方式伤害自己的念头",
        "接下来这个问题有点直接，但对您的健康很重要。",
    ),
)

PHQ9_QUESTION_IDS = frozenset(question.id for question in PHQ9_QUESTIONS)
Phq9Severity = Literal["minimal", "mild", "moderate", "moderately_severe", "severe"]


@dataclass(frozen=True)
class Phq9Score:
    """Deterministic PHQ-9 result safe to persist or return to a patient."""

    total_score: int
    severity: Phq9Severity
    urgent: bool
    safety_messages: tuple[str, ...]
    disclaimer: str = SCREENING_DISCLAIMER


def score_phq9(answers: Mapping[str, int]) -> Phq9Score:
    """Validate all nine answers and return the only permitted PHQ-9 score."""

    unexpected = set(answers) - PHQ9_QUESTION_IDS
    missing = PHQ9_QUESTION_IDS - set(answers)
    if unexpected or missing:
        raise ValueError(
            "PHQ-9 answers must contain exactly the nine defined question identifiers"
        )
    for question_id, value in answers.items():
        if isinstance(value, bool) or not isinstance(value, int) or value not in range(4):
            raise ValueError(f"{question_id} must be an integer score from 0 through 3")

    total = sum(answers.values())
    severity = _severity(total)
    self_harm_signal = answers[PHQ9_URGENT_ITEM_ID] >= 1
    high_total = total >= 20
    messages: list[str] = []
    if self_harm_signal:
        messages.append(URGENT_SAFETY_MESSAGE)
    if high_total:
        messages.append(HIGH_SCORE_SAFETY_MESSAGE)
    return Phq9Score(
        total_score=total,
        severity=severity,
        urgent=self_harm_signal or high_total,
        safety_messages=tuple(messages),
    )


def risk_for_answer(question_id: str, value: int) -> tuple[str, ...]:
    """Return immediate safety text before the assessment is complete."""

    if question_id not in PHQ9_QUESTION_IDS:
        raise ValueError("unknown PHQ-9 question")
    if isinstance(value, bool) or not isinstance(value, int) or value not in range(4):
        raise ValueError("PHQ-9 answer must be an integer score from 0 through 3")
    return (URGENT_SAFETY_MESSAGE,) if question_id == PHQ9_URGENT_ITEM_ID and value >= 1 else ()


def _severity(total: int) -> Phq9Severity:
    if total <= 4:
        return "minimal"
    if total <= 9:
        return "mild"
    if total <= 14:
        return "moderate"
    if total <= 19:
        return "moderately_severe"
    return "severe"
