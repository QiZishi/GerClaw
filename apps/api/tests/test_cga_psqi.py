"""PSQI scoring follows the local source and never trusts a model for calculation."""

import pytest

from gerclaw_api.modules.cga.psqi import PSQI_HIGH_SCORE_MESSAGE, PSQI_QUESTIONS, score_psqi


def _answers() -> dict[str, int]:
    answers = {question.id: 0 for question in PSQI_QUESTIONS}
    answers.update({"psqi_1": 23 * 60, "psqi_3": 7 * 60, "psqi_4": 8 * 60})
    return answers


def test_psqi_calculates_all_seven_components_for_restful_sleep() -> None:
    result = score_psqi(_answers())

    assert result.total_score == 0
    assert result.component_scores == {
        "sleep_quality": 0,
        "sleep_latency": 0,
        "sleep_duration": 0,
        "sleep_efficiency": 0,
        "sleep_disturbance": 0,
        "hypnotic_medication": 0,
        "daytime_dysfunction": 0,
    }
    assert result.severity == "good"
    assert result.high_severity_follow_up is False


def test_psqi_handles_midnight_clock_math_and_high_score_follow_up() -> None:
    answers = _answers()
    answers.update({"psqi_1": 23 * 60, "psqi_3": 7 * 60, "psqi_4": 4 * 60})
    for question in PSQI_QUESTIONS:
        if question.input_kind == "ordinal":
            answers[question.id] = 3

    result = score_psqi(answers)

    assert result.total_score == 21
    assert result.component_scores["sleep_efficiency"] == 3
    assert result.severity == "poor"
    assert result.high_severity_follow_up is True
    assert PSQI_HIGH_SCORE_MESSAGE in result.safety_messages
    assert "不能替代医生" in result.disclaimer


@pytest.mark.parametrize(
    ("sleep_minutes", "expected"),
    [(421, 0), (420, 1), (361, 1), (360, 2), (300, 2), (299, 3)],
)
def test_psqi_sleep_duration_source_thresholds(sleep_minutes: int, expected: int) -> None:
    answers = _answers() | {"psqi_4": sleep_minutes}

    assert score_psqi(answers).component_scores["sleep_duration"] == expected


@pytest.mark.parametrize(
    ("sleep_minutes", "expected"),
    [(409, 0), (408, 1), (360, 1), (359, 2), (312, 2), (311, 3)],
)
def test_psqi_sleep_efficiency_source_thresholds(sleep_minutes: int, expected: int) -> None:
    answers = _answers() | {"psqi_4": sleep_minutes}

    assert score_psqi(answers).component_scores["sleep_efficiency"] == expected


@pytest.mark.parametrize(
    ("latency", "frequency", "expected"),
    [(0, 0, 0), (1, 0, 1), (2, 0, 1), (3, 0, 2), (3, 1, 2), (3, 2, 3), (3, 3, 3)],
)
def test_psqi_sleep_latency_source_thresholds(latency: int, frequency: int, expected: int) -> None:
    answers = _answers() | {"psqi_2": latency, "psqi_5a": frequency}

    assert score_psqi(answers).component_scores["sleep_latency"] == expected


@pytest.mark.parametrize(
    ("total", "expected"),
    [(0, 0), (1, 1), (9, 1), (10, 2), (18, 2), (19, 3), (27, 3)],
)
def test_psqi_sleep_disturbance_source_thresholds(total: int, expected: int) -> None:
    answers = _answers()
    remaining = total
    for question_id in (f"psqi_5{letter}" for letter in "bcdefghij"):
        value = min(3, remaining)
        answers[question_id] = value
        remaining -= value

    assert score_psqi(answers).component_scores["sleep_disturbance"] == expected


@pytest.mark.parametrize(
    ("alertness", "motivation", "expected"),
    [(0, 0, 0), (1, 0, 1), (2, 0, 1), (3, 0, 2), (3, 1, 2), (3, 2, 3), (3, 3, 3)],
)
def test_psqi_daytime_dysfunction_source_thresholds(
    alertness: int, motivation: int, expected: int
) -> None:
    answers = _answers() | {"psqi_8": alertness, "psqi_9": motivation}

    assert score_psqi(answers).component_scores["daytime_dysfunction"] == expected


@pytest.mark.parametrize(
    "answers",
    [
        {},
        _answers() | {"unknown": 0},
        _answers() | {"psqi_5a": True},
        _answers() | {"psqi_1": 1_440},
        _answers() | {"psqi_4": 0},
        _answers() | {"psqi_1": 0, "psqi_3": 0},
        _answers() | {"psqi_4": 600},
    ],
)
def test_psqi_rejects_incomplete_untrusted_or_impossible_answers(answers: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        score_psqi(answers)
