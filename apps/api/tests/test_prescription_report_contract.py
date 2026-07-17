"""Safety contracts for the generic five-prescription draft schema."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.prescription.models import (
    MEDICAL_DRAFT_DISCLAIMER,
    EvidenceSource,
    ExerciseDraft,
    ExercisePhase,
    FivePrescriptionDraft,
    HealthAssessmentDraft,
    MedicationDraft,
    NutritionDraft,
    PatientSummary,
    PrescriptionRecommendation,
    PsychologicalDraft,
    RehabilitationDraft,
)


def _recommendation() -> PrescriptionRecommendation:
    return PrescriptionRecommendation(
        content="待医生结合个体情况核对。",
        evidence_ids=("ev_12345678",),
    )


def _draft(**overrides: object) -> FivePrescriptionDraft:
    recommendation = _recommendation()
    payload: dict[str, object] = {
        "status": "needs_clinician_review",
        "patient_summary": PatientSummary(
            age=70,
            sex="unknown",
            health_goals=("改善日常活动能力",),
            current_concerns=("活动后容易疲劳",),
        ),
        "health_assessment": HealthAssessmentDraft(
            summary="基于当前已收集信息形成的待医生审核摘要。",
            key_issues=("活动耐受下降",),
        ),
        "medication": MedicationDraft(
            title="药物处方",
            goal="由医生核对现有用药安全性。",
            recommendations=(recommendation,),
            precautions=("不得自行调整药物。",),
            evidence_ids=("ev_12345678",),
        ),
        "exercise": ExerciseDraft(
            title="运动处方",
            goal="在医生确认后逐步恢复活动。",
            recommendations=(recommendation,),
            precautions=("出现不适立即停止并就医。",),
            evidence_ids=("ev_12345678",),
            contraindications=("出现急性不适时暂停。",),
            phases=(
                ExercisePhase(
                    name="准备",
                    duration="由医生评估后确定",
                    intensity="从可耐受强度开始",
                    instructions="先完成医生评估。",
                ),
            ),
        ),
        "nutrition": NutritionDraft(
            title="营养处方",
            goal="由营养专业人员评估后确定目标。",
            recommendations=(recommendation,),
            precautions=("合并疾病时需个体化调整。",),
            evidence_ids=("ev_12345678",),
            assessment_summary="营养资料需由专业人员补充评估。",
            monitoring=("按医生建议复查。",),
        ),
        "psychological": PsychologicalDraft(
            title="心理处方",
            goal="识别并支持情绪与睡眠困扰。",
            recommendations=(recommendation,),
            precautions=("出现自伤风险时立即寻求急救帮助。",),
            evidence_ids=("ev_12345678",),
            assessment_summary="需要专业人员进一步评估。",
            follow_up="按医生建议随访。",
        ),
        "rehabilitation": RehabilitationDraft(
            title="康复处方",
            goal="改善功能并降低活动风险。",
            recommendations=(recommendation,),
            precautions=("训练应在安全保护下循序渐进。",),
            evidence_ids=("ev_12345678",),
            rehabilitation_type="待功能评估后确定",
            functional_assessment="功能状态需由专业人员评估。",
            training_plan=("由康复人员制定个体化训练计划。",),
            safety_precautions=("出现不适立即停止训练。",),
        ),
        "evidence_sources": (
            EvidenceSource(
                evidence_id="ev_12345678",
                title="经审核循证资料",
                source="本地知识库",
                locator="待工作流写入确切定位信息",
            ),
        ),
    }
    payload.update(overrides)
    return FivePrescriptionDraft.model_validate(payload)


def test_generic_five_prescription_draft_requires_all_five_sections_and_disclaimer() -> None:
    draft = _draft()

    assert draft.template_version == "five-prescription-report-v1"
    assert draft.disclaimer == MEDICAL_DRAFT_DISCLAIMER
    assert draft.rehabilitation.rehabilitation_type
    assert draft.medication.review_required is True
    assert draft.psychological.review_required is True


def test_five_prescription_draft_rejects_untraceable_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence references"):
        _draft(
            evidence_sources=(
                EvidenceSource(
                    evidence_id="ev_other123",
                    title="不匹配的资料",
                    source="本地知识库",
                    locator="section",
                ),
            )
        )


def test_governance_pending_draft_cannot_claim_uploaded_document_as_evidence() -> None:
    with pytest.raises(ValidationError, match="uploaded-document provenance"):
        _draft(
            status="needs_medical_governance",
            uploaded_document_ids=(uuid.uuid4(),),
        )
