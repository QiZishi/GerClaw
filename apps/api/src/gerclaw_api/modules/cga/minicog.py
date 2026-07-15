# ruff: noqa: RUF001
"""Versioned Mini-Cog scoring core with an explicit human clock-review boundary.

The source is ``问卷量表/04-Mini-Cog简易认知量表.md``.  Clock drawing is
not machine-scored here: its 0--2 result must come from a future authorised,
audited human review workflow that owns the drawing artifact.  This pure module
only validates that reviewed input and calculates the screening total.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MINICOG_SCALE_ID = "minicog"
MINICOG_VERSION = "2026-07-16"
MINICOG_WORDS = ("苹果", "手表", "国旗")
MINICOG_DISCLAIMER = "本结果是认知筛查结果，不能替代医生的临床诊断。"
MINICOG_FOLLOW_UP_MESSAGE = "筛查结果提示可能存在认知问题，建议由专业人员进一步评估确认。"
MiniCogSeverity = Literal["possible_impairment", "screen_negative"]


@dataclass(frozen=True)
class MiniCogScore:
    recalled_word_count: int
    reviewed_clock_score: int
    total_score: int
    severity: MiniCogSeverity
    high_severity_follow_up: bool
    safety_messages: tuple[str, ...]
    disclaimer: str = MINICOG_DISCLAIMER


def score_minicog(*, recalled_word_count: int, reviewed_clock_score: int) -> MiniCogScore:
    """Calculate Mini-Cog only from recall count and an audited human clock review."""

    _validate_score("recalled_word_count", recalled_word_count, maximum=3)
    _validate_score("reviewed_clock_score", reviewed_clock_score, maximum=2)
    total_score = recalled_word_count + reviewed_clock_score
    possible_impairment = total_score <= 2
    return MiniCogScore(
        recalled_word_count=recalled_word_count,
        reviewed_clock_score=reviewed_clock_score,
        total_score=total_score,
        severity="possible_impairment" if possible_impairment else "screen_negative",
        high_severity_follow_up=possible_impairment,
        safety_messages=(MINICOG_FOLLOW_UP_MESSAGE,) if possible_impairment else (),
    )


def _validate_score(name: str, value: int, *, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value not in range(maximum + 1):
        raise ValueError(f"{name} must be an integer from 0 through {maximum}")
