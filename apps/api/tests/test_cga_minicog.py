"""Mini-Cog scoring permits only an explicit, bounded human clock-review score."""

import pytest

from gerclaw_api.modules.cga.minicog import MINICOG_FOLLOW_UP_MESSAGE, score_minicog


@pytest.mark.parametrize(
    ("recall", "clock", "total", "severity"),
    [
        (0, 0, 0, "possible_impairment"),
        (2, 0, 2, "possible_impairment"),
        (1, 2, 3, "screen_negative"),
        (3, 2, 5, "screen_negative"),
    ],
)
def test_minicog_scores_only_the_authoritative_two_parts(
    recall: int, clock: int, total: int, severity: str
) -> None:
    result = score_minicog(recalled_word_count=recall, reviewed_clock_score=clock)

    assert result.total_score == total
    assert result.severity == severity
    assert result.high_severity_follow_up is (total <= 2)
    assert (MINICOG_FOLLOW_UP_MESSAGE in result.safety_messages) is (total <= 2)


@pytest.mark.parametrize(
    ("recall", "clock"),
    [(-1, 0), (4, 0), (0, -1), (0, 3), (True, 0), (0, True)],
)
def test_minicog_rejects_untrusted_or_out_of_range_review_values(recall: int, clock: int) -> None:
    with pytest.raises(ValueError):
        score_minicog(recalled_word_count=recall, reviewed_clock_score=clock)
