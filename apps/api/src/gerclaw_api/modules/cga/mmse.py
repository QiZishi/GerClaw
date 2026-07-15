# ruff: noqa: RUF001
"""Versioned MMSE scoring core with an explicit reviewed-item boundary.

Source: ``问卷量表/05-MMSE简易智能精神状态检查量表.md``.  Several MMSE
items require observation, drawing, reading or task execution.  This module
therefore accepts only a future authorised, auditable set of item results; it
does not assess free text, images, audio or actions itself.
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
    *, reviewed_item_scores: Mapping[str, int], education_level: EducationLevel
) -> MmseScore:
    """Score thirty pre-reviewed binary MMSE items and report source thresholds."""

    unexpected = set(reviewed_item_scores) - MMSE_ITEM_IDS
    missing = MMSE_ITEM_IDS - set(reviewed_item_scores)
    if unexpected or missing:
        raise ValueError(
            "MMSE requires exactly the thirty server-defined reviewed item identifiers"
        )
    for item_id, value in reviewed_item_scores.items():
        if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
            raise ValueError(f"{item_id} must be a reviewed binary score")
    if education_level not in {"none", "primary_or_less", "secondary_or_more"}:
        raise ValueError("education_level is invalid")

    total_score = sum(reviewed_item_scores.values())
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
