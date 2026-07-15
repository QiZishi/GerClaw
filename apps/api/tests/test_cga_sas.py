"""SAS scoring follows the versioned local questionnaire without model involvement."""

import pytest

from gerclaw_api.modules.cga.sas import (
    SAS_HIGH_SCORE_MESSAGE,
    SAS_QUESTIONS,
    score_sas,
)


def _answers(value: int) -> dict[str, int]:
    return {question.id: value for question in SAS_QUESTIONS}


@pytest.mark.parametrize(
    ("answers", "raw", "standard", "severity"),
    [
        (_answers(1), 35, 44, "none"),
        (_answers(2), 45, 56, "mild"),
        (_answers(3), 55, 69, "moderate"),
        (_answers(4), 65, 81, "severe"),
    ],
)
def test_sas_reverse_items_and_standard_score_are_deterministic(
    answers: dict[str, int], raw: int, standard: int, severity: str
) -> None:
    result = score_sas(answers)

    assert result.raw_score == raw
    assert result.standard_score == standard
    assert result.severity == severity


def test_sas_high_score_uses_round_half_up_and_requests_follow_up() -> None:
    answers = _answers(4)
    for question_id in ("sas_5", "sas_9", "sas_13", "sas_17", "sas_19"):
        answers[question_id] = 1

    result = score_sas(answers)

    assert result.raw_score == 80
    assert result.standard_score == 100
    assert result.severity == "severe"
    assert result.high_severity_follow_up is True
    assert SAS_HIGH_SCORE_MESSAGE in result.safety_messages
    assert "不能替代医生" in result.disclaimer


@pytest.mark.parametrize(
    "answers",
    [
        {},
        _answers(1) | {"unknown": 1},
        _answers(1) | {"sas_1": 0},
        _answers(1) | {"sas_1": True},
    ],
)
def test_sas_rejects_untrusted_or_incomplete_answers(answers: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        score_sas(answers)
