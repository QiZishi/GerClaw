# ruff: noqa: RUF001
"""Versioned PSQI definition and deterministic sleep-quality calculation.

This module transcribes ``问卷量表/03-PSQI匹兹堡睡眠质量指数量表.md``.
It deliberately contains no model, network, or persistence dependency.  PSQI
uses clock times and durations in addition to ordinal options, so it is kept
out of the four-choice assessment state machine until that richer input
contract is implemented end-to-end.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

PSQI_SCALE_ID = "psqi"
PSQI_VERSION = "2026-07-16"
PSQI_DISCLAIMER = "本结果是睡眠质量筛查结果，不能替代医生的临床诊断。"
PSQI_HIGH_SCORE_MESSAGE = "睡眠质量筛查分数较高，建议咨询医生或睡眠健康专业人员。"


@dataclass(frozen=True)
class PsqiQuestion:
    id: str
    position: int
    text: str
    input_kind: Literal["clock_minutes", "duration_minutes", "ordinal"]


PSQI_QUESTIONS: tuple[PsqiQuestion, ...] = (
    PsqiQuestion("psqi_1", 1, "过去1个月，您通常上床睡觉的时间", "clock_minutes"),
    PsqiQuestion("psqi_2", 2, "过去1个月，您每晚通常要多长时间才能入睡", "ordinal"),
    PsqiQuestion("psqi_3", 3, "过去1个月，您每天早上通常什么时候起床", "clock_minutes"),
    PsqiQuestion("psqi_4", 4, "过去1个月，您每晚实际睡眠的时长", "duration_minutes"),
    PsqiQuestion("psqi_5a", 5, "不能在30分钟内入睡", "ordinal"),
    PsqiQuestion("psqi_5b", 6, "在晚上睡眠中醒来或早醒", "ordinal"),
    PsqiQuestion("psqi_5c", 7, "晚上有无起床上洗手间", "ordinal"),
    PsqiQuestion("psqi_5d", 8, "不舒服的呼吸", "ordinal"),
    PsqiQuestion("psqi_5e", 9, "大声咳嗽或打鼾", "ordinal"),
    PsqiQuestion("psqi_5f", 10, "感到寒冷", "ordinal"),
    PsqiQuestion("psqi_5g", 11, "感到太热", "ordinal"),
    PsqiQuestion("psqi_5h", 12, "做噩梦", "ordinal"),
    PsqiQuestion("psqi_5i", 13, "出现疼痛", "ordinal"),
    PsqiQuestion("psqi_5j", 14, "其他影响睡眠的事情", "ordinal"),
    PsqiQuestion("psqi_6", 15, "对过去1个月睡眠质量总的评价", "ordinal"),
    PsqiQuestion("psqi_7", 16, "近1个月使用催眠药物的情况", "ordinal"),
    PsqiQuestion("psqi_8", 17, "开车、吃饭或参加社会活动时难以保持清醒", "ordinal"),
    PsqiQuestion("psqi_9", 18, "积极完成事情有无困难", "ordinal"),
    PsqiQuestion("psqi_10", 19, "您是与人同睡一床或有室友", "ordinal"),
)
PSQI_QUESTION_IDS = frozenset(question.id for question in PSQI_QUESTIONS)
PSQI_SLEEP_DISRUPTION_IDS = tuple(f"psqi_5{letter}" for letter in "bcdefghij")
PsqiSeverity = Literal["good", "fair", "average", "poor"]


@dataclass(frozen=True)
class PsqiScore:
    total_score: int
    component_scores: dict[str, int]
    severity: PsqiSeverity
    high_severity_follow_up: bool
    safety_messages: tuple[str, ...]
    disclaimer: str = PSQI_DISCLAIMER


def score_psqi(answers: Mapping[str, int]) -> PsqiScore:
    """Validate all 19 self-report values and calculate all seven PSQI factors."""

    _validate_answers(answers)
    bedtime = answers["psqi_1"]
    wake_time = answers["psqi_3"]
    time_in_bed = (wake_time - bedtime) % 1_440
    actual_sleep = answers["psqi_4"]
    if time_in_bed == 0:
        raise ValueError("bedtime and wake time must define a non-zero interval")
    if actual_sleep > time_in_bed:
        raise ValueError("actual sleep duration cannot exceed time in bed")

    component_scores = {
        "sleep_quality": answers["psqi_6"],
        "sleep_latency": _band(answers["psqi_2"] + answers["psqi_5a"], (0, 2, 4)),
        "sleep_duration": _duration_band(actual_sleep),
        "sleep_efficiency": _efficiency_band(actual_sleep * 100 / time_in_bed),
        "sleep_disturbance": _band(
            sum(answers[key] for key in PSQI_SLEEP_DISRUPTION_IDS), (0, 9, 18)
        ),
        "hypnotic_medication": answers["psqi_7"],
        "daytime_dysfunction": _band(answers["psqi_8"] + answers["psqi_9"], (0, 2, 4)),
    }
    total_score = sum(component_scores.values())
    severity = _severity(total_score)
    high_severity = total_score >= 16
    return PsqiScore(
        total_score=total_score,
        component_scores=component_scores,
        severity=severity,
        high_severity_follow_up=high_severity,
        safety_messages=(PSQI_HIGH_SCORE_MESSAGE,) if high_severity else (),
    )


def _validate_answers(answers: Mapping[str, int]) -> None:
    unexpected = set(answers) - PSQI_QUESTION_IDS
    missing = PSQI_QUESTION_IDS - set(answers)
    if unexpected or missing:
        raise ValueError(
            "PSQI answers must contain exactly the nineteen defined self-report identifiers"
        )
    for question in PSQI_QUESTIONS:
        value = answers[question.id]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{question.id} must be an integer")
        if question.input_kind == "ordinal" and value not in range(4):
            raise ValueError(f"{question.id} must be an ordinal score from 0 through 3")
        if question.input_kind == "clock_minutes" and value not in range(1_440):
            raise ValueError(f"{question.id} must be minutes after midnight")
        if question.input_kind == "duration_minutes" and value not in range(1, 1_440):
            raise ValueError(f"{question.id} must be a positive duration in minutes")


def _band(value: int, bounds: tuple[int, int, int]) -> int:
    """Map inclusive source ranges 0 / 1..b1 / b1+1..b2 / b2+1..b3 to 0..3."""

    first, second, third = bounds
    if value <= first:
        return 0
    if value <= second:
        return 1
    if value <= third:
        return 2
    return 3


def _duration_band(minutes: int) -> int:
    if minutes > 420:
        return 0
    if minutes > 360:
        return 1
    if minutes >= 300:
        return 2
    return 3


def _efficiency_band(percent: float) -> int:
    if percent > 85:
        return 0
    if percent >= 75:
        return 1
    if percent >= 65:
        return 2
    return 3


def _severity(total_score: int) -> PsqiSeverity:
    if total_score <= 5:
        return "good"
    if total_score <= 10:
        return "fair"
    if total_score <= 15:
        return "average"
    return "poor"
