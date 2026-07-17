# ruff: noqa: RUF001
"""Medication-list reconciliation is strictly an input-quality boundary."""

from __future__ import annotations

import uuid

import pytest

from gerclaw_api.modules.medication_review.reconciliation import (
    MAX_MEDICATION_ENTRIES,
    MedicationReconciliationInputError,
    reconcile_medication_list,
)


def test_reconciliation_only_groups_exact_normalized_entries() -> None:
    result = reconcile_medication_list(
        intake_id=uuid.uuid4(),
        medication_list=(
            "阿司匹林｜100mg｜每日一次\n 阿司匹林 | 100mg | 每日一次 \n"
            "阿司匹林肠溶片｜100mg"
        ),
    )

    assert result.has_medication_list is True
    assert [entry.position for entry in result.entries] == [1, 2, 3]
    assert [(item.text, item.positions) for item in result.exact_duplicate_candidates] == [
        ("阿司匹林|100mg|每日一次", (1, 2))
    ]
    assert "不能判断药物相互作用" in result.notice


def test_reconciliation_supports_voice_fallback_separators_without_guessing() -> None:
    result = reconcile_medication_list(
        intake_id=uuid.uuid4(), medication_list="药物 A；药物B; 药物 A"
    )

    assert [entry.text for entry in result.entries] == ["药物 A", "药物B", "药物 A"]
    assert result.exact_duplicate_candidates[0].positions == (1, 3)


def test_reconciliation_does_not_create_a_clinical_result_for_empty_input() -> None:
    result = reconcile_medication_list(intake_id=uuid.uuid4(), medication_list=" \n； ")

    assert result.has_medication_list is False
    assert result.entries == ()
    assert result.exact_duplicate_candidates == ()


def test_reconciliation_rejects_an_unbounded_list() -> None:
    with pytest.raises(MedicationReconciliationInputError, match="too many"):
        reconcile_medication_list(
            intake_id=uuid.uuid4(),
            medication_list="\n".join(
                f"药物{index}" for index in range(MAX_MEDICATION_ENTRIES + 1)
            ),
        )
