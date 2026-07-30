"""C3 differential and STEP treatment prerequisite tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gerclaw_api.modules.agent_harness.clinical_state import (
    C3DifferentialValidator,
    ClinicalFact,
    ClinicalState,
    ClinicalStateError,
    DifferentialAssessment,
    DifferentialCandidate,
    DifferentialPriority,
    FactProvenance,
    STEPTreatmentGate,
    TreatmentContext,
    TreatmentGateMode,
    TreatmentIntent,
)


def _fact(
    fact_id: str,
    category: str,
    value: str,
    *,
    status: str = "reported",
) -> ClinicalFact:
    source_type = "trusted_tool" if status == "confirmed" else "user"
    return ClinicalFact.model_validate(
        {
            "fact_id": fact_id,
            "category": category,
            "value": value,
            "status": status,
            "provenance": (
                FactProvenance(
                    source_type=source_type,
                    source_id=f"source-{fact_id}",
                    observed_at=datetime.now(UTC),
                ),
            ),
        }
    )


def test_c3_preserves_support_opposition_missing_and_residual_without_fixed_count() -> None:
    state = ClinicalState(
        facts=(
            _fact("symptom_dizziness", "symptom", "头晕"),
            _fact("test_glucose", "test", "血糖正常", status="confirmed"),
            _fact("symptom_gait", "symptom", "步态不稳"),
        )
    )
    assessment = DifferentialAssessment(
        candidates=(
            DifferentialCandidate(
                candidate_id="orthostatic_direction",
                label="体位性因素方向",
                priority=DifferentialPriority.CONSIDER,
                supporting_fact_ids=("symptom_dizziness",),
                opposing_fact_ids=("test_glucose",),
                residual_fact_ids=("symptom_gait",),
                missing_information=("症状是否与体位变化相关",),
            ),
        )
    )

    validated = C3DifferentialValidator().validate(state, assessment)

    assert len(validated.candidates) == 1
    assert not validated.is_diagnosis
    assert validated.candidates[0].residual_fact_ids == ("symptom_gait",)


def test_c3_rejects_missing_references_and_conflicted_support() -> None:
    validator = C3DifferentialValidator()
    missing = DifferentialAssessment(
        candidates=(
            DifferentialCandidate(
                candidate_id="missing_fact",
                label="待核验方向",
                priority=DifferentialPriority.CONSIDER,
                supporting_fact_ids=("not_found",),
            ),
        )
    )
    with pytest.raises(ClinicalStateError, match="DIFFERENTIAL_FACT_NOT_FOUND"):
        validator.validate(ClinicalState(), missing)

    conflicted = ClinicalState(
        facts=(_fact("medication_dose", "medication", "剂量存在冲突", status="conflicted"),),
        conflicts=("medication_dose",),
    )
    conflicted_assessment = DifferentialAssessment(
        candidates=(
            DifferentialCandidate(
                candidate_id="drug_effect",
                label="药物相关方向",
                priority=DifferentialPriority.CONSIDER,
                supporting_fact_ids=("medication_dose",),
            ),
        )
    )
    with pytest.raises(ClinicalStateError, match="CONFLICT_USED_AS_SUPPORT"):
        validator.validate(conflicted, conflicted_assessment)


def test_step_blocks_emergency_before_treatment() -> None:
    red_flag = _fact("red_flag_chest_pain", "red_flag", "突发胸痛")
    context = TreatmentContext(
        intent=TreatmentIntent.GENERAL,
        clinical_state=ClinicalState(facts=(red_flag,)),
    )

    decision = STEPTreatmentGate().evaluate(context)

    assert not decision.actionable_treatment_allowed
    assert decision.mode is TreatmentGateMode.EMERGENCY_BLOCK
    assert decision.warning_codes == ("emergency_escalation_required",)


def test_step_requires_age_allergy_medication_comorbidity_monitoring_and_follow_up() -> None:
    medication = _fact("medications", "medication", "阿托伐他汀")
    context = TreatmentContext(
        intent=TreatmentIntent.FIVE_PRESCRIPTION,
        clinical_state=ClinicalState(
            facts=(medication,),
            unknowns=("年龄", "过敏史", "基础病"),
        ),
        medication_fact_ids=("medications",),
        uncertainties=("年龄、过敏史和基础病尚待确认",),
        monitoring_conditions=("记录症状和用药反应",),
        follow_up_conditions=("由医生复核后再调整",),
    )

    decision = STEPTreatmentGate().evaluate(context)

    assert not decision.actionable_treatment_allowed
    assert decision.mode is TreatmentGateMode.PREREQUISITES_REQUIRED
    assert decision.missing_prerequisites == (
        "age",
        "allergies",
        "comorbidities",
        "resolve_uncertainties",
    )


def test_step_allows_only_complete_source_linked_review_context() -> None:
    facts = (
        _fact("age", "demographic", "78"),
        _fact("allergy_none", "negative_evidence", "已明确否认药物过敏"),
        _fact("medications", "medication", "当前用药已核对"),
        _fact("history", "history", "高血压病史"),
        _fact("renal_test", "test", "肾功能已核对", status="confirmed"),
    )
    context = TreatmentContext(
        intent=TreatmentIntent.MEDICATION,
        clinical_direction_ids=("blood_pressure_review",),
        clinical_state=ClinicalState(facts=facts),
        age_fact_id="age",
        allergy_fact_ids=("allergy_none",),
        medication_fact_ids=("medications",),
        comorbidity_fact_ids=("history",),
        test_fact_ids=("renal_test",),
        monitoring_conditions=("监测血压和不良反应",),
        follow_up_conditions=("两周内由医生复核",),
    )

    decision = STEPTreatmentGate().evaluate(context)

    assert decision.actionable_treatment_allowed
    assert decision.mode is TreatmentGateMode.REVIEW_DRAFT
    assert decision.missing_prerequisites == ()
