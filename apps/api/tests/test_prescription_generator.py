"""Focused contracts for evidence-bound five-prescription draft generation."""
# ruff: noqa: RUF001

from __future__ import annotations

import uuid
from hashlib import sha256
from types import SimpleNamespace
from typing import Any

import pytest

from gerclaw_api.modules.document.models import UploadedDocumentContext
from gerclaw_api.modules.prescription.generator import (
    EvidenceBoundPrescriptionGenerator,
    PrescriptionRedFlagError,
)
from gerclaw_api.modules.prescription.models import (
    FIVE_PRESCRIPTION_MODEL_OUTPUT_SCHEMA_VERSION,
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
from gerclaw_api.modules.search.models import SearchResult


class _Model:
    def __init__(self, content: GeneratedPrescriptionContent) -> None:
        self.content = content

    async def generate_structured_output(self, *_args: Any, **_kwargs: Any) -> object:
        return SimpleNamespace(content=self.content)


class _JsonFallbackModel(_Model):
    def __init__(
        self, content: GeneratedPrescriptionContent, *, response: str | None = None
    ) -> None:
        super().__init__(content)
        self.response = response or content.model_dump_json()
        self.fallback_messages: list[object] = []

    async def generate_structured_output(self, *_args: Any, **_kwargs: Any) -> object:
        raise RuntimeError("provider structured tools are unavailable")

    async def generate_text_output(self, messages: list[object]) -> str:
        self.fallback_messages = messages
        return self.response


class _RAG:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results

    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        assert query == "改善活动耐受 走路后容易疲劳"
        assert top_k == 8
        return self.results


class _OnlineSearch:
    async def search(
        self, query: str, max_results: int = 5, domain: str = "health"
    ) -> list[SearchResult]:
        assert query == "改善活动耐受 走路后容易疲劳"
        assert max_results == 5
        assert domain == "health"
        return [
            SearchResult(
                id="web_0123456789abcdef",
                title="联网循证资料",
                snippet="经校验的联网资料摘要。",
                url="https://example.com/evidence",
                source="example.com",
                authority_level="A",
                provider="anysearch",
            )
        ]


def _content() -> GeneratedPrescriptionContent:
    evidence_id = "ev_" + sha256(b"chunk-001").hexdigest()[:24]
    recommendation = PrescriptionRecommendation(
        content="待医生核对后执行。", evidence_ids=(evidence_id,)
    )
    return GeneratedPrescriptionContent(
        model_output_schema_version=FIVE_PRESCRIPTION_MODEL_OUTPUT_SCHEMA_VERSION,
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


def _prepared(
    *,
    concerns: str = "走路后容易疲劳",
    medications: str | None = None,
    uploaded_documents: tuple[UploadedDocumentContext, ...] = (),
) -> PreparedPrescriptionInput:
    answers = {"health_goal": "改善活动耐受", "current_concerns": concerns}
    if medications is not None:
        answers["current_medications"] = medications
    return PreparedPrescriptionInput(
        intake_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        definition_version="clinical-intake-v1",
        answers=answers,
        uploaded_documents=uploaded_documents,
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
async def test_generator_binds_uploaded_patient_material_as_distinct_evidence() -> None:
    document = UploadedDocumentContext(
        document_id=uuid.uuid4(), filename="patient-report.pdf", content="患者自述的检查资料"
    )
    draft = await EvidenceBoundPrescriptionGenerator(
        model=_Model(_content()), rag_module=_RAG([_result()])
    ).generate(_prepared(uploaded_documents=(document,)))  # type: ignore[arg-type]

    uploaded = [source for source in draft.evidence_sources if source.source == "患者上传资料"]
    assert len(uploaded) == 1
    assert uploaded[0].title == "患者上传资料 1"
    assert "patient-report.pdf" not in draft.model_dump_json()
    assert document.document_id in draft.uploaded_document_ids


@pytest.mark.asyncio
async def test_generator_can_use_same_session_uploaded_material_without_local_hits() -> None:
    document = UploadedDocumentContext(
        document_id=uuid.uuid4(), filename="patient-report.pdf", content="患者自述的检查资料"
    )
    uploaded_evidence_id = (
        "ev_" + sha256(f"uploaded-document:{document.document_id}".encode()).hexdigest()[:24]
    )
    payload = _content().model_dump(mode="json")
    for section_name in ("medication", "exercise", "nutrition", "psychological", "rehabilitation"):
        payload[section_name]["evidence_ids"] = [uploaded_evidence_id]
        for recommendation in payload[section_name]["recommendations"]:
            recommendation["evidence_ids"] = [uploaded_evidence_id]
    content = GeneratedPrescriptionContent.model_validate(payload)

    draft = await EvidenceBoundPrescriptionGenerator(
        model=_Model(content), rag_module=_RAG([])
    ).generate(_prepared(uploaded_documents=(document,)))  # type: ignore[arg-type]

    assert [source.source for source in draft.evidence_sources] == ["患者上传资料"]


@pytest.mark.asyncio
async def test_generator_binds_validated_online_search_as_distinct_evidence() -> None:
    draft = await EvidenceBoundPrescriptionGenerator(
        model=_Model(_content()),
        rag_module=_RAG([_result()]),
        online_search_module=_OnlineSearch(),
    ).generate(_prepared())  # type: ignore[arg-type]

    online = [source for source in draft.evidence_sources if source.source == "联网检索"]
    assert len(online) == 1
    assert online[0].title == "联网循证资料"
    assert online[0].url == "https://example.com/evidence"


@pytest.mark.asyncio
async def test_generator_embeds_deterministic_medication_review_outside_model_content() -> None:
    draft = await EvidenceBoundPrescriptionGenerator(
        model=_Model(_content()), rag_module=_RAG([_result()])
    ).generate(_prepared(medications="阿托伐他汀 20mg 每日一次\n地高辛 0.125mg 每日一次"))  # type: ignore[arg-type]

    assert draft.medication_review is not None
    assert draft.medication_review.ruleset_version == "medication-rules-v4"
    assert [finding.kind for finding in draft.medication_review.findings] == ["ddi"]
    assert draft.medication_review.findings[0].finding_id == "ddi_atorvastatin_digoxin"


@pytest.mark.asyncio
async def test_generator_allows_recording_user_provided_medication_doses() -> None:
    reported_medications = "阿托伐他汀 20mg 每日一次\n地高辛 0.125mg 每日一次"
    content = _content().model_copy(
        update={
            "medication": _content().medication.model_copy(
                update={"medication_items": (reported_medications,)}
            )
        }
    )

    draft = await EvidenceBoundPrescriptionGenerator(
        model=_Model(content), rag_module=_RAG([_result()])
    ).generate(_prepared(medications=reported_medications))  # type: ignore[arg-type]

    assert draft.medication.medication_items == (reported_medications,)


@pytest.mark.asyncio
async def test_generator_blocks_red_flag_input_before_retrieval() -> None:
    with pytest.raises(PrescriptionRedFlagError):
        await EvidenceBoundPrescriptionGenerator(
            model=_Model(_content()), rag_module=_RAG([_result()])
        ).generate(_prepared(concerns="突然胸痛"))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_generator_allows_evidence_bound_clinician_medication_candidate() -> None:
    proposal = _content().model_copy(
        update={
            "medication": _content().medication.model_copy(
                update={
                    "recommendations": (
                        _content()
                        .medication.recommendations[0]
                        .model_copy(update={"content": "待临床复核：开始服用某药。"}),
                    )
                }
            )
        }
    )
    draft = await EvidenceBoundPrescriptionGenerator(
        model=_Model(proposal), rag_module=_RAG([_result()])
    ).generate(_prepared())  # type: ignore[arg-type]
    assert draft.status == "needs_clinician_review"
    assert draft.medication.recommendations[0].content == "待临床复核：开始服用某药。"


@pytest.mark.asyncio
async def test_generator_degrades_to_review_baseline_for_uncited_medication_change() -> None:
    unsupported = _content().model_copy(
        update={
            "medication": _content().medication.model_copy(
                update={"medication_items": ("开始服用某药。",)}
            )
        }
    )
    draft = await EvidenceBoundPrescriptionGenerator(
        model=_Model(unsupported), rag_module=_RAG([_result()])
    ).generate(_prepared())  # type: ignore[arg-type]

    assert "基础待审核草案" in draft.health_assessment.summary
    assert "开始服用某药" not in draft.model_dump_json()


@pytest.mark.asyncio
async def test_generator_keeps_evidence_review_medication_precaution() -> None:
    content = _content().model_copy(
        update={
            "medication": _content().medication.model_copy(
                update={"precautions": ("涉及停用或减量时，请结合相应证据和完整病史复核。",)}
            )
        }
    )

    draft = await EvidenceBoundPrescriptionGenerator(
        model=_Model(content), rag_module=_RAG([_result()])
    ).generate(_prepared())  # type: ignore[arg-type]

    assert draft.health_assessment.summary == content.health_assessment.summary
    assert draft.medication.precautions == ("涉及停用或减量时，请结合相应证据和完整病史复核。",)


@pytest.mark.asyncio
async def test_generator_degrades_to_review_baseline_for_unknown_evidence_id() -> None:
    unknown_evidence = "ev_" + "b" * 24
    payload = _content().model_dump(mode="json")
    for section_name in ("medication", "exercise", "nutrition", "psychological", "rehabilitation"):
        payload[section_name]["evidence_ids"] = [unknown_evidence]
        for recommendation in payload[section_name]["recommendations"]:
            recommendation["evidence_ids"] = [unknown_evidence]
    content = GeneratedPrescriptionContent.model_validate(payload)

    draft = await EvidenceBoundPrescriptionGenerator(
        model=_Model(content), rag_module=_RAG([_result()])
    ).generate(_prepared(medications="阿托伐他汀 20mg 每日一次\n地高辛 0.125mg 每日一次"))  # type: ignore[arg-type]

    assert "基础待审核草案" in draft.health_assessment.summary
    assert draft.medication_review is not None
    assert draft.medication_review.findings[0].finding_id == "ddi_atorvastatin_digoxin"


@pytest.mark.asyncio
async def test_generator_uses_validated_json_only_after_structured_provider_failure() -> None:
    model = _JsonFallbackModel(_content())

    draft = await EvidenceBoundPrescriptionGenerator(
        model=model, rag_module=_RAG([_result()])
    ).generate(_prepared())  # type: ignore[arg-type]

    assert draft.status == "needs_clinician_review"
    assert draft.model_output_schema_version == FIVE_PRESCRIPTION_MODEL_OUTPUT_SCHEMA_VERSION
    assert len(model.fallback_messages) == 3
    assert "JSON Schema" in str(model.fallback_messages[1])


@pytest.mark.asyncio
async def test_generator_degrades_to_a_review_only_baseline_for_non_json_text() -> None:
    model = _JsonFallbackModel(_content(), response="这里不是 JSON")

    draft = await EvidenceBoundPrescriptionGenerator(
        model=model, rag_module=_RAG([_result()])
    ).generate(_prepared())  # type: ignore[arg-type]

    assert "基础待审核草案" in draft.health_assessment.summary


@pytest.mark.asyncio
async def test_generator_repairs_json_syntax_but_still_validates_full_contract() -> None:
    malformed = _content().model_dump_json().removesuffix("}") + ",}"
    model = _JsonFallbackModel(_content(), response=malformed)

    draft = await EvidenceBoundPrescriptionGenerator(
        model=model, rag_module=_RAG([_result()])
    ).generate(_prepared())  # type: ignore[arg-type]

    assert draft.rehabilitation.kind == "rehabilitation"


@pytest.mark.asyncio
async def test_generator_accepts_one_fenced_json_fallback_without_accepting_prose() -> None:
    response = "模型输出：\n```json\n" + _content().model_dump_json() + "\n```"
    model = _JsonFallbackModel(_content(), response=response)

    draft = await EvidenceBoundPrescriptionGenerator(
        model=model, rag_module=_RAG([_result()])
    ).generate(_prepared())  # type: ignore[arg-type]

    assert draft.exercise.kind == "exercise"


@pytest.mark.asyncio
async def test_generator_accepts_one_json_object_prefixed_with_provider_text() -> None:
    model = _JsonFallbackModel(
        _content(), response="以下是结构化结果：\n" + _content().model_dump_json()
    )

    draft = await EvidenceBoundPrescriptionGenerator(
        model=model, rag_module=_RAG([_result()])
    ).generate(_prepared())  # type: ignore[arg-type]

    assert draft.nutrition.kind == "nutrition"


@pytest.mark.asyncio
async def test_generator_returns_explicit_safe_baseline_when_all_model_formats_fail() -> None:
    model = _JsonFallbackModel(_content(), response="not a JSON object")

    draft = await EvidenceBoundPrescriptionGenerator(
        model=model, rag_module=_RAG([_result()])
    ).generate(_prepared())  # type: ignore[arg-type]

    assert "基础待审核草案" in draft.health_assessment.summary
    assert draft.medication.evidence_ids == (draft.evidence_sources[0].evidence_id,)
    assert draft.medication.medication_items[0].startswith("尚未提供")
