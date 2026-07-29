"""C3-inspired, evidence-linked differential direction contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_api.modules.agent_harness.clinical_state.contracts import (
    BoundedClinicalText,
    ClinicalState,
    ClinicalStateError,
)


class DifferentialPriority(StrEnum):
    CONSIDER = "consider"
    LOWER_PRIORITY = "lower_priority"
    MUST_NOT_MISS = "must_not_miss"


class DifferentialCandidate(BaseModel):
    """A non-diagnostic direction with explicit evidence and uncertainty."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=200)
    priority: DifferentialPriority
    supporting_fact_ids: tuple[str, ...] = Field(default=(), max_length=50)
    opposing_fact_ids: tuple[str, ...] = Field(default=(), max_length=50)
    residual_fact_ids: tuple[str, ...] = Field(default=(), max_length=50)
    missing_information: tuple[BoundedClinicalText, ...] = Field(default=(), max_length=50)

    @field_validator("label")
    @classmethod
    def require_non_diagnostic_direction_label(cls, label: str) -> str:
        if not any(marker in label for marker in ("方向", "可能", "待评估", "需排除")):
            raise ValueError("differential label must be explicitly non-diagnostic")
        if any(marker in label for marker in ("确诊", "诊断为", "就是", "一定是", "已经患有")):
            raise ValueError("differential label cannot assert a diagnosis")
        return label

    @model_validator(mode="after")
    def reject_duplicate_or_overlapping_evidence(self) -> DifferentialCandidate:
        groups = (
            self.supporting_fact_ids,
            self.opposing_fact_ids,
            self.residual_fact_ids,
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("differential evidence references must be unique")
        if any(
            set(left) & set(right)
            for index, left in enumerate(groups)
            for right in groups[index + 1 :]
        ):
            raise ValueError("one fact cannot have conflicting roles in one candidate")
        if (
            self.priority is not DifferentialPriority.MUST_NOT_MISS
            and not self.supporting_fact_ids
        ):
            raise ValueError("non-safety differential direction requires supporting evidence")
        if (
            self.priority is DifferentialPriority.MUST_NOT_MISS
            and not self.supporting_fact_ids
            and not self.missing_information
        ):
            raise ValueError("must-not-miss direction requires evidence or missing discriminator")
        return self


class DifferentialAssessment(BaseModel):
    """Bounded differential directions; never a diagnosis record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    candidates: tuple[DifferentialCandidate, ...] = Field(default=(), max_length=20)
    is_diagnosis: Literal[False] = False

    @model_validator(mode="after")
    def require_unique_candidates(self) -> DifferentialAssessment:
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("differential candidate ids must be unique")
        return self


class C3DifferentialValidator:
    """Validate references against ClinicalState without inventing a fixed K."""

    def validate(
        self,
        state: ClinicalState,
        assessment: DifferentialAssessment,
    ) -> DifferentialAssessment:
        facts = {fact.fact_id: fact for fact in state.facts}
        referenced = {
            fact_id
            for candidate in assessment.candidates
            for fact_id in (
                *candidate.supporting_fact_ids,
                *candidate.opposing_fact_ids,
                *candidate.residual_fact_ids,
            )
        }
        if missing := referenced - facts.keys():
            raise ClinicalStateError(
                f"DIFFERENTIAL_FACT_NOT_FOUND:{','.join(sorted(missing))}"
            )
        unsafe_support = {
            fact_id
            for candidate in assessment.candidates
            for fact_id in candidate.supporting_fact_ids
            if facts[fact_id].status == "conflicted"
        }
        if unsafe_support:
            raise ClinicalStateError(
                f"DIFFERENTIAL_CONFLICT_USED_AS_SUPPORT:{','.join(sorted(unsafe_support))}"
            )
        return assessment
