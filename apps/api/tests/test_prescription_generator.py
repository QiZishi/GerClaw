"""Focused contracts for evidence-bound five-prescription draft generation."""
# ruff: noqa: RUF001

from __future__ import annotations

import uuid
from hashlib import sha256
from types import SimpleNamespace
from typing import Any

import pytest

from gerclaw_api.modules.prescription.generator import (
    EvidenceBoundPrescriptionGenerator,
    PrescriptionGenerationError,
    PrescriptionRedFlagError,
)
from gerclaw_api.modules.prescription.models import (
    ExerciseDraft,
    ExercisePhase,
    GeneratedPrescriptionContent,
    HealthAssessmentDraft,
    MedicationDraft,
    NutritionDraft,
    PatientSummary,
    PreparedPrescriptionInput,
    PrescriptionRecommendation,
    PsychologicalDraft,
    RehabilitationDraft,
)
from gerclaw_api.modules.rag.protocols import RetrievalResult


class _Model:
    def __init__(self, content: GeneratedPrescriptionContent) -> None:
        self.content = content

    async def generate_structured_output(self, *_args: Any, **_kwargs: Any) -> object:
        return SimpleNamespace(content=self.content)


class _RAG:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results

    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        assert query == "改善活动耐受 走路后容易疲劳"
        assert top_k == 8
        return self.results


def _content() -> GeneratedPrescriptionContent:
    evidence_id = "ev_" + sha256(b"chunk-001").hexdigest()[:24]
    recommendation = PrescriptionRecommendation(
        content="待医生核对后执行。", evidence_ids=(evidence_id,)
    )
    return GeneratedPrescriptionContent(
        patient_summary=PatientSummary(
            health_goals=("改善活动耐受",), current_concerns=("走路后容易疲劳",)
        ),
        health_assessment=HealthAssessmentDraft(
            summary="当前资料提示需要进一步评估活动耐受。", key_issues=("活动后疲劳",)
        ),
        medication=MedicationDraft(
            title="用药核对",
            goal="由医生或药师核对现有用药。",
            recommendations=(recommendation,),
            precautions=("不自行调整药物。",),
            evidence_ids=(evidence_id,),
            medication_items=("当前用药信息待核对；未执行 DDI、Beers 和剂量规则校验。",),
            monitoring_requirements=("携带完整药盒或处方供医生核对。",),
        ),
        exercise=ExerciseDraft(
            title="运动建议",
            goal="在专业人员确认后逐步活动。",
            recommendations=(recommendation,),
            precautions=("出现不适立即停止并就医。",),
            evidence_ids=(evidence_id,),
            contraindications=("急性不适时暂停运动。",),
            phases=(
                ExercisePhase(
                    name="准备",
                    duration="5分钟",
                    intensity="从舒适强度开始",
                    instructions="有人陪同下慢走。",
                ),
            ),
        ),
        nutrition=NutritionDraft(
            title="营养建议",
            goal="补充完整饮食信息后由专业人员制定目标。",
            recommendations=(recommendation,),
            precautions=("合并疾病时需个体化调整。",),
            evidence_ids=(evidence_id,),
            assessment_summary="当前营养资料有限，需要进一步评估。",
            monitoring=("按医生建议复查。",),
        ),
        psychological=PsychologicalDraft(
            title="心理支持",
            goal="识别并支持睡眠和情绪困扰。",
            recommendations=(recommendation,),
            precautions=("出现自伤风险时立即寻求急救帮助。",),
            evidence_ids=(evidence_id,),
            assessment_summary="需要专业人员进一步评估。",
            follow_up="按医生建议随访。",
        ),
        rehabilitation=RehabilitationDraft(
            title="康复建议",
            goal="改善功能并降低活动风险。",
            recommendations=(recommendation,),
            precautions=("训练应在安全保护下循序渐进。",),
            evidence_ids=(evidence_id,),
            rehabilitation_type="待功能评估后确定",
            functional_assessment="需评估步行和平衡能力。",
            training_plan=("由康复人员制定个体化训练计划。",),
            safety_precautions=("出现不适立即停止训练。",),
        ),
    )


def _prepared(*, concerns: str = "走路后容易疲劳") -> PreparedPrescriptionInput:
    return PreparedPrescriptionInput(
        intake_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        definition_version="clinical-intake-v1",
        answers={"health_goal": "改善活动耐受", "current_concerns": concerns},
        uploaded_documents=(),
    )


def _result() -> RetrievalResult:
    return RetrievalResult(
        content="synthetic evidence",
        source="reviewed/source.md",
        score=0.9,
        metadata={
            "document_id": "a" * 64,
            "chunk_id": "chunk-001",
            "title": "审核资料",
            "chapter": "建议",
            "category": "rehabilitation",
            "source_type": "guideline",
            "chunk_index": 0,
            "total_chunks": 1,
            "publish_year": 2024,
        },
    )


@pytest.mark.asyncio
async def test_generator_attaches_server_owned_evidence_and_review_status() -> None:
    draft = await EvidenceBoundPrescriptionGenerator(
        model=_Model(_content()), rag_module=_RAG([_result()])
    ).generate(_prepared())  # type: ignore[arg-type]

    assert draft.status == "needs_clinician_review"
    assert draft.evidence_sources[0].title == "审核资料"
    assert draft.evidence_sources[0].evidence_id.startswith("ev_")
    assert "synthetic evidence" not in draft.model_dump_json()


@pytest.mark.asyncio
async def test_generator_blocks_red_flag_input_before_retrieval() -> None:
    with pytest.raises(PrescriptionRedFlagError):
        await EvidenceBoundPrescriptionGenerator(
            model=_Model(_content()), rag_module=_RAG([_result()])
        ).generate(_prepared(concerns="突然胸痛"))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_generator_rejects_ungoverned_medication_directive() -> None:
    unsafe = _content().model_copy(
        update={
            "medication": _content().medication.model_copy(
                update={"medication_items": ("开始服用某药。",)}
            )
        }
    )
    with pytest.raises(PrescriptionGenerationError, match="ungoverned safety"):
        await EvidenceBoundPrescriptionGenerator(
            model=_Model(unsafe), rag_module=_RAG([_result()])
        ).generate(_prepared())  # type: ignore[arg-type]
