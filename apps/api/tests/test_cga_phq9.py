"""PHQ-9 scoring is deterministic and never delegated to a language model."""

import pytest

from gerclaw_api.modules.cga.phq9 import (
    HIGH_SCORE_SAFETY_MESSAGE,
    PHQ9_QUESTIONS,
    URGENT_SAFETY_MESSAGE,
    risk_for_answer,
    score_phq9,
)


def _answers(score: int, *, ninth_score: int = 0) -> dict[str, int]:
    values = {question.id: 0 for question in PHQ9_QUESTIONS}
    remaining = score - ninth_score
    for question in PHQ9_QUESTIONS:
        if question.id == "phq9_9":
            continue
        step = min(3, remaining)
        values[question.id] = step
        remaining -= step
    if remaining:
        values["phq9_9"] = min(3, remaining)
        remaining -= values["phq9_9"]
    else:
        values["phq9_9"] = ninth_score
    assert remaining == 0
    return values


@pytest.mark.parametrize(
    ("total", "severity"),
    [
        (0, "minimal"),
        (4, "minimal"),
        (5, "mild"),
        (9, "mild"),
        (10, "moderate"),
        (14, "moderate"),
        (15, "moderately_severe"),
        (19, "moderately_severe"),
        (20, "severe"),
        (27, "severe"),
    ],
)
def test_phq9_boundary_scores_are_deterministic(total: int, severity: str) -> None:
    result = score_phq9(_answers(total))

    assert result.total_score == total
    assert result.severity == severity
    assert result.self_harm_signal is (total == 27)
    assert result.requires_immediate_safety_assessment is (total == 27)
    assert result.high_severity_follow_up is (total >= 20)
    assert (HIGH_SCORE_SAFETY_MESSAGE in result.safety_messages) is (total >= 20)
    assert "不能替代医生" in result.disclaimer


def test_phq9_self_harm_answer_is_an_immediate_high_risk_signal() -> None:
    result = score_phq9(_answers(1, ninth_score=1))

    assert result.self_harm_signal is True
    assert result.requires_immediate_safety_assessment is True
    assert result.high_severity_follow_up is False
    assert URGENT_SAFETY_MESSAGE in result.safety_messages
    assert risk_for_answer("phq9_9", 1) == (URGENT_SAFETY_MESSAGE,)
    assert risk_for_answer("phq9_8", 3) == ()


@pytest.mark.parametrize(
    "answers",
    [
        {},
        {question.id: 0 for question in PHQ9_QUESTIONS} | {"unknown": 0},
        {question.id: 0 for question in PHQ9_QUESTIONS} | {"phq9_1": 4},
        {question.id: 0 for question in PHQ9_QUESTIONS} | {"phq9_1": True},
    ],
)
def test_phq9_rejects_untrusted_client_scores(answers: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        score_phq9(answers)


def test_phq9_high_total_without_item_nine_is_not_an_immediate_safety_signal() -> None:
    result = score_phq9(_answers(20))

    assert result.self_harm_signal is False
    assert result.requires_immediate_safety_assessment is False
    assert result.high_severity_follow_up is True
