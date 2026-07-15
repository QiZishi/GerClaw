"""MMSE scores are deterministic only after auditable item-level review."""

import pytest

from gerclaw_api.modules.cga.mmse import MMSE_FOLLOW_UP_MESSAGE, MMSE_ITEM_IDS, score_mmse


def _scores(total: int) -> dict[str, int]:
    return {item_id: int(index < total) for index, item_id in enumerate(sorted(MMSE_ITEM_IDS))}


@pytest.mark.parametrize(
    ("total", "education", "severity", "positive"),
    [
        (30, "secondary_or_more", "normal", False),
        (27, "secondary_or_more", "normal", False),
        (24, "secondary_or_more", "mild_impairment", True),
        (21, "primary_or_less", "mild_impairment", False),
        (20, "primary_or_less", "moderate_impairment", True),
        (17, "none", "moderate_impairment", True),
        (9, "none", "severe_impairment", True),
    ],
)
def test_mmse_uses_source_severity_and_education_thresholds(
    total: int, education: str, severity: str, positive: bool
) -> None:
    result = score_mmse(reviewed_item_scores=_scores(total), education_level=education)  # type: ignore[arg-type]

    assert result.total_score == total
    assert result.severity == severity
    assert result.education_adjusted_screen_positive is positive
    assert (MMSE_FOLLOW_UP_MESSAGE in result.safety_messages) is positive


@pytest.mark.parametrize(
    ("scores", "education"),
    [
        ({}, "none"),
        (_scores(1) | {"unknown": 1}, "none"),
        (_scores(1) | {"mmse_1": 2}, "none"),
        (_scores(1) | {"mmse_1": True}, "none"),
        (_scores(1), "unknown"),
    ],
)
def test_mmse_rejects_unreviewed_or_invalid_input(scores: dict[str, int], education: str) -> None:
    with pytest.raises(ValueError):
        score_mmse(reviewed_item_scores=scores, education_level=education)  # type: ignore[arg-type]
