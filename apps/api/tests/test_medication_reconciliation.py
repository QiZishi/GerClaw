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
from gerclaw_api.modules.medication_review.rules_engine import (
    MedicationRulesInputError,
    review_medication_list,
)


def test_reconciliation_only_groups_exact_normalized_entries() -> None:
    result = reconcile_medication_list(
        intake_id=uuid.uuid4(),
        medication_list=(
            "阿司匹林｜100mg｜每日一次\n 阿司匹林 | 100mg | 每日一次 \n阿司匹林肠溶片｜100mg"
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


def test_rule_review_emits_source_traceable_ddi_and_dose_findings() -> None:
    result = review_medication_list(
        intake_id=uuid.uuid4(),
        patient_age=76,
        medication_list="瑞舒伐他汀 40mg 每日一次\n环孢素\n阿托伐他汀\n地高辛",
    )

    assert result.ruleset_version == "medication-rules-v4"
    assert result.coverage.beers == "limited_source_traceable"
    assert result.sources[0].content_sha256 == (
        "940965391565b0de32f3aba51c5a323542f5af9b18162c5075130ba63437feeb"
    )
    assert [finding.finding_id for finding in result.findings] == [
        "ddi_rosuvastatin_cyclosporine",
        "ddi_atorvastatin_cyclosporine",
        "ddi_atorvastatin_digoxin",
        "dose_rosuvastatin_max_daily_20mg_1",
    ]
    assert result.findings[2].severity == "major"
    assert result.findings[2].age_escalated is True
    assert result.findings[0].source_ids == ("cad_rehab_primary_care",)


def test_rule_review_detects_normalized_generic_duplicates_and_polypharmacy() -> None:
    result = review_medication_list(
        intake_id=uuid.uuid4(),
        medication_list="阿托伐他汀 10mg 每日一次\natorvastatin 10mg qd\n药物甲\n药物乙\n药物丙",
    )

    assert [finding.kind for finding in result.findings] == ["duplicate", "polypharmacy"]
    assert result.unrecognized_entry_count == 3
    assert result.findings[0].involved_generic_names == ("阿托伐他汀",)
    assert result.findings[0].source_ids == ()


def test_rule_review_emits_limited_beers_signal_only_for_age_qualified_input() -> None:
    result = review_medication_list(
        intake_id=uuid.uuid4(), patient_age=70, medication_list="地西泮 2mg 每晚一次"
    )

    assert [(finding.kind, finding.finding_id) for finding in result.findings] == [
        ("beers", "beers_benzodiazepines_insomnia_older_adults")
    ]
    assert result.findings[0].source_ids == ("insomnia_bz_older_adults",)
    assert "不能确定该药的实际适应证" in result.findings[0].conclusion


def test_rule_review_v3_emits_evidence_bound_new_high_risk_pairs() -> None:
    result = review_medication_list(
        intake_id=uuid.uuid4(),
        patient_age=78,
        medication_list=(
            "硝酸甘油 0.5mg 必要时使用\n"
            "西地那非 50mg\n"
            "氯吡格雷 75mg 每日一次\n"
            "奥美拉唑 20mg 每日一次\n"
            "地高辛 0.125mg 每日一次\n"
            "胺碘酮 200mg 每日一次\n"
            "瑞格列奈 1mg 每日三次\n"
            "吉非罗齐 600mg 每日两次"
        ),
    )

    findings = {finding.finding_id: finding for finding in result.findings}
    assert result.ruleset_version == "medication-rules-v4"
    assert set(findings) == {
        "ddi_nitroglycerin_sildenafil",
        "ddi_clopidogrel_omeprazole",
        "ddi_digoxin_amiodarone",
        "ddi_repaglinide_gemfibrozil",
        "polypharmacy_5_to_9",
    }
    assert findings["ddi_nitroglycerin_sildenafil"].severity == "contraindicated"
    assert findings["ddi_digoxin_amiodarone"].source_ids == ("frailty_polypharmacy_2022",)
    assert findings["ddi_clopidogrel_omeprazole"].source_ids == (
        "stable_cad_primary_care",
        "frailty_polypharmacy_2022",
    )
    assert "患者不要自行" not in findings["ddi_clopidogrel_omeprazole"].clinician_action


def test_rule_review_v3_covers_exact_local_daily_dose_limits() -> None:
    result = review_medication_list(
        intake_id=uuid.uuid4(),
        patient_age=75,
        medication_list=(
            "比索洛尔 12mg 每日一次\n硝苯地平 130mg 每日一次\n左旋氨氯地平 6mg 每日一次"
        ),
    )

    assert result.ruleset_version == "medication-rules-v4"
    assert [finding.finding_id for finding in result.findings] == [
        "dose_bisoprolol_max_daily_10mg_1",
        "dose_levamlodipine_max_daily_5mg_3",
        "dose_nifedipine_max_daily_120mg_2",
    ]
    assert all(finding.source_ids == ("stable_cad_primary_care",) for finding in result.findings)
    assert result.findings[1].age_escalated is True


def test_rule_review_does_not_infer_beers_signal_without_age_context() -> None:
    result = review_medication_list(intake_id=uuid.uuid4(), medication_list="地西泮 2mg 每晚一次")

    assert not [finding for finding in result.findings if finding.kind == "beers"]


def test_rule_review_rejects_empty_list() -> None:
    with pytest.raises(MedicationRulesInputError, match="required"):
        review_medication_list(intake_id=uuid.uuid4(), medication_list=" \n")
