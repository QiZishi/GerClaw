"""Versioned, source-traceable medication-review contracts."""
# ruff: noqa: RUF001

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MedicationListEntry(BaseModel):
    """One caller-provided list row, without an inferred drug identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    position: int = Field(ge=1, le=50)
    text: str = Field(min_length=1, max_length=1_500)


class MedicationDuplicateCandidate(BaseModel):
    """Only a normalized-text match; it is not a duplicate-drug conclusion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=1_500)
    positions: tuple[int, ...] = Field(min_length=2, max_length=50)


class MedicationReconciliationRead(BaseModel):
    """Owner-visible input-quality result with no clinical interpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intake_id: uuid.UUID
    version: str = Field(pattern=r"^medication-reconciliation-v[0-9]+$")
    has_medication_list: bool
    entries: tuple[MedicationListEntry, ...] = Field(max_length=50)
    exact_duplicate_candidates: tuple[MedicationDuplicateCandidate, ...] = Field(max_length=50)
    notice: str = Field(min_length=1, max_length=500)


MedicationRiskLevel = Literal["contraindicated", "major", "moderate", "minor"]
MedicationFindingKind = Literal["ddi", "dose", "beers", "duplicate", "polypharmacy"]


class MedicationReviewRequest(BaseModel):
    """Optional age context for one review; it is not written into Trace data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    patient_age: int | None = Field(default=None, ge=0, le=130)


class MedicationRuleSource(BaseModel):
    """A human-verifiable source record for every installed medical rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    title: str = Field(min_length=1, max_length=300)
    publisher: str = Field(min_length=1, max_length=300)
    locator: str = Field(min_length=1, max_length=500)
    local_corpus_path: str = Field(min_length=1, max_length=500)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_status: Literal["source_traceable_pending_clinician_approval"]


class MedicationRuleCoverage(BaseModel):
    """Coverage state prevents a no-finding result from being mistaken for safety."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ddi: Literal["limited_source_traceable"]
    dose: Literal["limited_source_traceable"]
    beers: Literal["limited_source_traceable"]


class ReviewedMedication(BaseModel):
    """An explicit text match only; unmatched text is retained for clinician review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    position: int = Field(ge=1, le=50)
    text: str = Field(min_length=1, max_length=1_500)
    recognized_generic_names: tuple[str, ...] = Field(default_factory=tuple, max_length=4)


class MedicationReviewFinding(BaseModel):
    """One deterministic rule hit, never an instruction to prescribe or stop medication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,95}$")
    kind: MedicationFindingKind
    severity: MedicationRiskLevel
    title: str = Field(min_length=1, max_length=300)
    involved_generic_names: tuple[str, ...] = Field(min_length=1, max_length=4)
    conclusion: str = Field(min_length=1, max_length=1_000)
    clinician_action: str = Field(min_length=1, max_length=1_000)
    elderly_note: str | None = Field(default=None, max_length=1_000)
    source_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=4)
    age_escalated: bool = False


class MedicationReviewDraft(BaseModel):
    """Concrete clinician-review artifact from the installed deterministic rule set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intake_id: uuid.UUID
    ruleset_version: str = Field(pattern=r"^medication-rules-v[0-9]+$")
    patient_age: int | None = Field(default=None, ge=0, le=130)
    reviewed_medications: tuple[ReviewedMedication, ...] = Field(min_length=1, max_length=50)
    findings: tuple[MedicationReviewFinding, ...] = Field(max_length=200)
    sources: tuple[MedicationRuleSource, ...] = Field(min_length=1, max_length=20)
    coverage: MedicationRuleCoverage
    unrecognized_entry_count: int = Field(ge=0, le=50)
    conclusion: str = Field(min_length=1, max_length=1_000)
    disclaimer: Literal[
        "本审查仅基于已安装且来源可追溯的有限规则，不能替代医师或药师的完整用药核对；涉及开始、停用或调整剂量时，应结合完整临床资料和相应证据复核。"
    ] = (
        "本审查仅基于已安装且来源可追溯的有限规则，不能替代医师或药师的完整用药核对；"
        "涉及开始、停用或调整剂量时，应结合完整临床资料和相应证据复核。"
    )


class MedicationReviewDraftRead(BaseModel):
    """One encrypted medication-review revision projected to its owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    draft_id: uuid.UUID
    intake_id: uuid.UUID
    intake_revision: int = Field(ge=1)
    created_at: datetime
    draft: MedicationReviewDraft
    reviews: tuple[MedicationReviewDraftReviewRead, ...] = Field(
        default_factory=tuple, max_length=100
    )


class MedicationReviewDraftReviewRequest(BaseModel):
    """A doctor's non-executable review of one saved medication-review artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Literal["approved", "returned"]
    review_note: str = Field(min_length=1, max_length=5_000)


class MedicationReviewDraftReviewRead(BaseModel):
    """Owner- and reviewer-visible encrypted review projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    review_id: uuid.UUID
    draft_id: uuid.UUID
    doctor_actor_id: str = Field(pattern=r"^usr_account_[a-f0-9]{32}$")
    decision: Literal["approved", "returned"]
    review_note: str = Field(min_length=1, max_length=5_000)
    revision: int = Field(ge=1)
    reviewed_at: datetime


class MedicationReviewDraftHistoryRead(BaseModel):
    """Bounded newest-first history for one owner-scoped intake."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[MedicationReviewDraftRead, ...] = Field(default_factory=tuple, max_length=20)


class DoctorMedicationReviewDraftListRead(BaseModel):
    """A doctor's consent-gated, read-only projection of saved review drafts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[MedicationReviewDraftRead, ...] = Field(default_factory=tuple, max_length=20)
