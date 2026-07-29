"""STEP-style treatment context and deterministic prerequisite gate."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.modules.agent_harness.clinical_state.contracts import (
    BoundedClinicalText,
    ClinicalState,
)


class TreatmentIntent(StrEnum):
    GENERAL = "general"
    MEDICATION = "medication"
    EXERCISE = "exercise"
    NUTRITION = "nutrition"
    PSYCHOLOGICAL = "psychological"
    REHABILITATION = "rehabilitation"
    FIVE_PRESCRIPTION = "five_prescription"


class TreatmentContext(BaseModel):
    """Only structured, source-aware context may enter treatment generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    intent: TreatmentIntent
    clinical_direction_ids: tuple[str, ...] = Field(default=(), max_length=20)
    clinical_state: ClinicalState
    age_fact_id: str | None = Field(default=None, max_length=128)
    allergy_fact_ids: tuple[str, ...] = Field(default=(), max_length=20)
    medication_fact_ids: tuple[str, ...] = Field(default=(), max_length=50)
    comorbidity_fact_ids: tuple[str, ...] = Field(default=(), max_length=50)
    test_fact_ids: tuple[str, ...] = Field(default=(), max_length=50)
    uncertainties: tuple[BoundedClinicalText, ...] = Field(default=(), max_length=100)
    monitoring_conditions: tuple[BoundedClinicalText, ...] = Field(
        default=(), max_length=50
    )
    follow_up_conditions: tuple[BoundedClinicalText, ...] = Field(
        default=(), max_length=50
    )
    clinician_review_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_fact_references(self) -> TreatmentContext:
        facts = {fact.fact_id: fact for fact in self.clinical_state.facts}
        references = {
            fact_id
            for fact_id in (
                *((self.age_fact_id,) if self.age_fact_id is not None else ()),
                *self.allergy_fact_ids,
                *self.medication_fact_ids,
                *self.comorbidity_fact_ids,
                *self.test_fact_ids,
            )
        }
        if unknown := references - facts.keys():
            raise ValueError(f"treatment context references unknown facts: {sorted(unknown)}")
        expected_categories = (
            ((self.age_fact_id,), {"demographic"})
            if self.age_fact_id is not None
            else ((), {"demographic"})
        )
        checks = (
            expected_categories,
            (self.allergy_fact_ids, {"allergy", "negative_evidence"}),
            (self.medication_fact_ids, {"medication", "negative_evidence"}),
            (self.comorbidity_fact_ids, {"history", "negative_evidence"}),
            (self.test_fact_ids, {"test", "observation"}),
        )
        if any(
            facts[fact_id].category not in categories
            for fact_ids, categories in checks
            for fact_id in fact_ids
        ):
            raise ValueError("treatment context fact category is invalid")
        return self


class TreatmentGateMode(StrEnum):
    EMERGENCY_BLOCK = "emergency_block"
    PREREQUISITES_REQUIRED = "prerequisites_required"
    REVIEW_DRAFT = "review_draft"


class TreatmentGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actionable_treatment_allowed: bool
    mode: TreatmentGateMode
    missing_prerequisites: tuple[str, ...] = Field(default=(), max_length=20)
    warning_codes: tuple[str, ...] = Field(default=(), max_length=20)


class STEPTreatmentGate:
    """Keep emergency, conflict, and treatment prerequisites outside the model."""

    def evaluate(self, context: TreatmentContext) -> TreatmentGateDecision:
        state = context.clinical_state
        if any(fact.category == "red_flag" for fact in state.facts):
            return TreatmentGateDecision(
                actionable_treatment_allowed=False,
                mode=TreatmentGateMode.EMERGENCY_BLOCK,
                warning_codes=("emergency_escalation_required",),
            )

        missing: list[str] = []
        if context.age_fact_id is None:
            missing.append("age")
        if not context.allergy_fact_ids:
            missing.append("allergies")
        if not context.medication_fact_ids:
            missing.append("current_medications")
        if not context.comorbidity_fact_ids:
            missing.append("comorbidities")
        if not context.monitoring_conditions:
            missing.append("monitoring")
        if not context.follow_up_conditions:
            missing.append("follow_up")
        if state.conflicts:
            missing.append("resolve_conflicts")
        if context.uncertainties:
            missing.append("resolve_uncertainties")

        blocking = tuple(dict.fromkeys(missing))
        if blocking:
            return TreatmentGateDecision(
                actionable_treatment_allowed=False,
                mode=TreatmentGateMode.PREREQUISITES_REQUIRED,
                missing_prerequisites=blocking,
                warning_codes=("review_only_until_prerequisites_complete",),
            )
        return TreatmentGateDecision(
            actionable_treatment_allowed=True,
            mode=TreatmentGateMode.REVIEW_DRAFT,
        )
