"""Strict HTTP contracts for non-clinical prescription and medication intake."""
# ruff: noqa: RUF001

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.modules.document.models import UploadedDocumentContext
from gerclaw_api.modules.input_output import ImageInput
from gerclaw_api.modules.input_output.clinical_intake import ClinicalIntakeKind
from gerclaw_api.modules.medication_review.models import MedicationReviewDraft

FIVE_PRESCRIPTION_TEMPLATE_VERSION: Final[Literal["five-prescription-report-v1"]] = (
    "five-prescription-report-v1"
)
PRESCRIPTION_INPUT_TEMPLATE_VERSION: Final[Literal["five-prescription-input-v1"]] = (
    "five-prescription-input-v1"
)
FIVE_PRESCRIPTION_MODEL_OUTPUT_SCHEMA_VERSION: Final[
    Literal["five-prescription-model-output-v1"]
] = "five-prescription-model-output-v1"
PRESCRIPTION_INTAKE_MODEL_OUTPUT_SCHEMA_VERSION: Final[
    Literal["prescription-intake-model-output-v1"]
] = "prescription-intake-model-output-v1"
MEDICAL_DRAFT_DISCLAIMER: Final[
    Literal["AI生成建议仅供参考，不能替代专业医生诊断、治疗建议或处方；如有不适请及时就医。"]
] = "AI生成建议仅供参考，不能替代专业医生诊断、治疗建议或处方；如有不适请及时就医。"


class PrescriptionGenerationCancelRead(BaseModel):
    """Bounded acknowledgement for an owner-scoped draft cancellation request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str = Field(pattern=r"^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$")
    status: Literal["cancellation_requested"] = "cancellation_requested"


class EvidenceSource(BaseModel):
    """One traceable local, online, or same-session patient evidence record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(pattern=r"^ev_[a-z0-9]{8,64}$")
    title: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=200)
    locator: str = Field(min_length=1, max_length=500)
    url: str | None = Field(default=None, max_length=2_000)


class PrescriptionRecommendation(BaseModel):
    """A draft recommendation citing local, online, or patient evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(min_length=1, max_length=2_000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)


class PrescriptionSection(BaseModel):
    """The common, evidence-bound section shape used by all five prescriptions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["medication", "exercise", "nutrition", "psychological", "rehabilitation"]
    title: str = Field(min_length=1, max_length=100)
    goal: str = Field(min_length=1, max_length=1_000)
    recommendations: tuple[PrescriptionRecommendation, ...] = Field(min_length=1, max_length=20)
    precautions: tuple[str, ...] = Field(min_length=1, max_length=20)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=20)


class MedicationDraft(PrescriptionSection):
    """Medication section shape only; dose safety remains a separately governed rule set."""

    kind: Literal["medication"] = "medication"
    title: Literal["药物处方"] = "药物处方"
    medication_items: tuple[str, ...] = Field(default_factory=tuple, max_length=30)
    monitoring_requirements: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    review_required: Literal[True] = True


class ExercisePhase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=100)
    duration: str = Field(min_length=1, max_length=200)
    intensity: str = Field(min_length=1, max_length=500)
    instructions: str = Field(min_length=1, max_length=2_000)


class ExerciseDraft(PrescriptionSection):
    kind: Literal["exercise"] = "exercise"
    title: Literal["运动处方"] = "运动处方"
    contraindications: tuple[str, ...] = Field(min_length=1, max_length=20)
    phases: tuple[ExercisePhase, ...] = Field(min_length=1, max_length=6)


class NutritionDraft(PrescriptionSection):
    kind: Literal["nutrition"] = "nutrition"
    title: Literal["营养处方"] = "营养处方"
    assessment_summary: str = Field(min_length=1, max_length=2_000)
    target_energy_kcal: int | None = Field(default=None, ge=1, le=10_000)
    target_protein_g: int | None = Field(default=None, ge=1, le=1_000)
    monitoring: tuple[str, ...] = Field(min_length=1, max_length=20)


class PsychologicalDraft(PrescriptionSection):
    kind: Literal["psychological"] = "psychological"
    title: Literal["心理处方"] = "心理处方"
    assessment_summary: str = Field(min_length=1, max_length=2_000)
    follow_up: str = Field(min_length=1, max_length=1_000)
    review_required: Literal[True] = True


class RehabilitationDraft(PrescriptionSection):
    """Evidence-bound rehabilitation assessment, dose plan, aids and safety contract."""

    kind: Literal["rehabilitation"] = "rehabilitation"
    title: Literal["康复处方"] = "康复处方"
    rehabilitation_type: str = Field(min_length=1, max_length=200)
    functional_assessment: str = Field(min_length=1, max_length=2_000)
    training_plan: tuple[str, ...] = Field(min_length=1, max_length=20)
    assistive_devices: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    safety_precautions: tuple[str, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_rehabilitation_plan(self) -> RehabilitationDraft:
        """Reject renamed categories and non-actionable one-line training slogans.

        A concrete training item needs a frequency plus duration or intensity.
        When the patient evidence is insufficient, the model may instead state
        exactly which professional assessment must precede dose design.  This
        preserves an honest, useful rehabilitation section without inventing a
        Barthel/Berg/6MWT score or silently replacing rehabilitation with sleep.
        """

        if self.rehabilitation_type.strip() in {
            "药物处方",
            "运动处方",
            "营养处方",
            "心理处方",
            "睡眠处方",
        }:
            raise ValueError(
                "rehabilitation_type must describe rehabilitation, not another section"
            )

        collections = (
            self.training_plan,
            self.assistive_devices,
            self.safety_precautions,
        )
        if any(any(not item.strip() for item in items) for items in collections):
            raise ValueError("rehabilitation list items must not be blank")
        if any(len(set(items)) != len(items) for items in collections):
            raise ValueError("rehabilitation list items must be unique")

        pending_markers = ("待评估", "评估后", "完成评估", "专业人员制定", "康复人员制定")
        frequency_markers = ("每日", "每天", "每周", "每月", "次/", "次／", "频次")
        duration_markers = ("分钟", "小时", "秒", "时长")
        intensity_markers = ("强度", "心率", "RPE", "RM", "可耐受", "抗阻", "助力")
        for item in self.training_plan:
            if any(marker in item for marker in pending_markers):
                continue
            has_frequency = any(marker in item for marker in frequency_markers)
            has_dose = any(marker in item for marker in duration_markers + intensity_markers)
            if not (has_frequency and has_dose):
                raise ValueError(
                    "rehabilitation training items require frequency and duration/intensity, "
                    "or an explicit pending assessment"
                )
        return self


class PatientSummary(BaseModel):
    """Minimal patient context; no diagnostic conclusion is allowed in this projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    age: int | None = Field(default=None, ge=0, le=130)
    sex: Literal["female", "male", "other", "unknown"] = "unknown"
    health_goals: tuple[str, ...] = Field(min_length=1, max_length=20)
    current_concerns: tuple[str, ...] = Field(min_length=1, max_length=20)


class HealthAssessmentDraft(BaseModel):
    """Non-diagnostic assessment summary for a clinician to review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1, max_length=3_000)
    key_issues: tuple[str, ...] = Field(min_length=1, max_length=20)
    risk_factors: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    clinician_review_required: Literal[True] = True


class FivePrescriptionDraft(BaseModel):
    """Strict, evidence-bound draft structure; never a patient-executable prescription."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_version: Literal["five-prescription-report-v1"] = FIVE_PRESCRIPTION_TEMPLATE_VERSION
    # The model's strict projection is versioned independently from the
    # owner-visible report template.  The server preserves this value to make
    # later trace/evaluation comparisons unambiguous.
    model_output_schema_version: Literal["five-prescription-model-output-v1"] = (
        FIVE_PRESCRIPTION_MODEL_OUTPUT_SCHEMA_VERSION
    )
    status: Literal["needs_medical_governance", "needs_clinician_review"]
    patient_summary: PatientSummary
    health_assessment: HealthAssessmentDraft
    medication: MedicationDraft
    exercise: ExerciseDraft
    nutrition: NutritionDraft
    psychological: PsychologicalDraft
    rehabilitation: RehabilitationDraft
    # Server-owned deterministic output.  The structured model never supplies
    # this field or controls the rules, sources, coverage, or conclusions.
    medication_review: MedicationReviewDraft | None = None
    evidence_sources: tuple[EvidenceSource, ...] = Field(min_length=1, max_length=100)
    uploaded_document_ids: tuple[uuid.UUID, ...] = Field(default_factory=tuple, max_length=10)
    uploaded_image_evidence_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=10)
    disclaimer: Literal[
        "AI生成建议仅供参考，不能替代专业医生诊断、治疗建议或处方；如有不适请及时就医。"
    ] = MEDICAL_DRAFT_DISCLAIMER

    @model_validator(mode="after")
    def validate_evidence_references(self) -> FivePrescriptionDraft:
        # A generic/governance-pending projection has not passed the
        # owner/session-bound document resolution performed by the real draft
        # workflow.  It therefore cannot claim patient-material provenance.
        # Only the server-built, clinician-review draft may carry those IDs.
        if self.status == "needs_medical_governance" and self.uploaded_document_ids:
            raise ValueError("governance-pending drafts cannot claim uploaded-document provenance")
        available = {source.evidence_id for source in self.evidence_sources}
        sections: tuple[PrescriptionSection, ...] = (
            self.medication,
            self.exercise,
            self.nutrition,
            self.psychological,
            self.rehabilitation,
        )
        referenced: set[str] = set()
        for section in sections:
            referenced.update(section.evidence_ids)
            for recommendation in section.recommendations:
                referenced.update(recommendation.evidence_ids)
        if not referenced.issubset(available):
            raise ValueError("prescription evidence references must resolve to evidence_sources")
        if not set(self.uploaded_image_evidence_ids).issubset(available):
            raise ValueError("uploaded image evidence must resolve to evidence_sources")
        return self


class PrescriptionDraftReviewRequest(BaseModel):
    """A doctor's evidence-bound amendment and review, never a treatment order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Literal["approved", "returned"]
    review_note: str = Field(min_length=1, max_length=5_000)
    amended_markdown: str | None = Field(default=None, min_length=1, max_length=50_000)
    amendment_evidence_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100)

    @model_validator(mode="after")
    def validate_amendment_pair(self) -> PrescriptionDraftReviewRequest:
        has_markdown = self.amended_markdown is not None and bool(self.amended_markdown.strip())
        if has_markdown != bool(self.amendment_evidence_ids):
            raise ValueError("an amendment must include one or more evidence IDs")
        if self.amended_markdown is not None and not has_markdown:
            raise ValueError("amended_markdown must not be blank")
        if len(set(self.amendment_evidence_ids)) != len(self.amendment_evidence_ids):
            raise ValueError("amendment evidence IDs must be unique")
        return self


class PrescriptionDraftReviewRead(BaseModel):
    """Owner- and reviewer-visible encrypted review projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    review_id: uuid.UUID
    draft_id: uuid.UUID
    doctor_actor_id: str = Field(pattern=r"^usr_account_[a-f0-9]{32}$")
    decision: Literal["approved", "returned"]
    review_note: str = Field(min_length=1, max_length=5_000)
    amended_markdown: str | None = Field(default=None, max_length=50_000)
    amendment_evidence_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    revision: int = Field(ge=1)
    reviewed_at: datetime


class PrescriptionDraftRead(BaseModel):
    """One caller-owned persisted draft; the nested report stays encrypted at rest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    draft_id: uuid.UUID
    intake_id: uuid.UUID
    created_at: datetime
    draft: FivePrescriptionDraft
    reviews: tuple[PrescriptionDraftReviewRead, ...] = Field(default_factory=tuple, max_length=100)


class PrescriptionDraftHistoryRead(BaseModel):
    """Bounded newest-first history for one owned prescription intake."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[PrescriptionDraftRead, ...] = Field(default_factory=tuple, max_length=20)


class DoctorPrescriptionDraftRead(PrescriptionDraftRead):
    """A specifically consented doctor's bounded draft-review projection."""


class DoctorPrescriptionDraftListRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[DoctorPrescriptionDraftRead, ...] = Field(default_factory=tuple, max_length=20)


class GeneratedPrescriptionContent(BaseModel):
    """Model-owned clinical draft fields; evidence and document provenance stay server-owned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_output_schema_version: Literal["five-prescription-model-output-v1"]
    patient_summary: PatientSummary
    health_assessment: HealthAssessmentDraft
    medication: MedicationDraft
    exercise: ExerciseDraft
    nutrition: NutritionDraft
    psychological: PsychologicalDraft
    rehabilitation: RehabilitationDraft


class ClinicalIntakeFieldRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    label: str = Field(min_length=1, max_length=200)
    required: bool
    max_length: int = Field(ge=1, le=2_000)
    placeholder: str = Field(min_length=1, max_length=300)


class ClinicalIntakeStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID
    kind: ClinicalIntakeKind


class ClinicalIntakeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    answers: dict[str, str] = Field(default_factory=dict, max_length=3)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=10)
    conversation_turn_increment: Literal[1] | None = None


class PrescriptionConversationTurnRequest(BaseModel):
    """One bounded, chat-native turn for five-prescription information completion."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=4_000)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=10)
    images: list[ImageInput] = Field(default_factory=list, max_length=10)


class PrescriptionIntakeExtraction(BaseModel):
    """Strict model projection; the service owns all persistence and readiness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_output_schema_version: Literal["prescription-intake-model-output-v1"]
    answer_updates: dict[str, str] = Field(default_factory=dict, max_length=3)
    follow_up_question: str | None = Field(default=None, min_length=1, max_length=300)


class PrescriptionConversationTurnRead(BaseModel):
    """Safe caller-visible result of a model-assisted intake turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intake: ClinicalIntakeRead
    assistant_message: str = Field(min_length=1, max_length=300)
    ready_to_generate: bool


class ClinicalIntakeRead(BaseModel):
    """Caller-owned intake state. It deliberately contains no clinical output."""

    model_config = ConfigDict(extra="forbid")

    intake_id: uuid.UUID
    session_id: uuid.UUID
    kind: ClinicalIntakeKind
    definition_version: str = Field(min_length=1, max_length=32)
    status: Literal["collecting", "information_complete_pending_governance"]
    revision: int = Field(ge=1)
    conversation_turns: int = Field(ge=0, le=5)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=300)
    fields: list[ClinicalIntakeFieldRead] = Field(min_length=1, max_length=5)
    answers: dict[str, str] = Field(default_factory=dict, max_length=3)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    image_evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    missing_required_fields: list[str] = Field(default_factory=list, max_length=3)
    governance_notice: str = Field(min_length=1, max_length=500)
    updated_at: datetime


class PreparedPrescriptionInput(BaseModel):
    """Private, complete input for a future governed prescription workflow.

    This contract deliberately has no HTTP route. It may contain the caller's
    encrypted intake answers and MinerU/local extracted text, so a future
    Runtime workflow must keep it inside the verified tenant/actor/session
    boundary and must not log, trace, index, or emit it as evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_template_version: Literal["five-prescription-input-v1"] = (
        PRESCRIPTION_INPUT_TEMPLATE_VERSION
    )
    intake_id: uuid.UUID
    session_id: uuid.UUID
    definition_version: str = Field(min_length=1, max_length=32)
    answers: dict[str, str] = Field(min_length=2, max_length=3)
    uploaded_documents: tuple[UploadedDocumentContext, ...] = Field(max_length=10)
    uploaded_images: tuple[ImageInput, ...] = Field(default_factory=tuple, max_length=10)


class PrescriptionInputReadiness(BaseModel):
    """Owner-visible preparation state that exposes no intake or document text.

    ``clinical_output_enabled`` deliberately remains false: a reviewed draft is
    available, but executable clinical output is not.  Keeping these two states
    explicit prevents callers from mistaking draft generation for prescription
    authorization.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    intake_id: uuid.UUID
    input_template_version: Literal["five-prescription-input-v1"] = (
        PRESCRIPTION_INPUT_TEMPLATE_VERSION
    )
    definition_version: str = Field(min_length=1, max_length=32)
    answer_field_count: int = Field(ge=2, le=3)
    uploaded_document_count: int = Field(ge=0, le=10)
    uploaded_image_count: int = Field(default=0, ge=0, le=10)
    review_draft_enabled: Literal[True] = True
    clinical_output_enabled: Literal[False] = False
    governance_notice: str = Field(min_length=1, max_length=500)
