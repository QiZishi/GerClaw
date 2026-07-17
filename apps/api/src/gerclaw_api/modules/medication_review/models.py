"""Public, non-clinical medication-reconciliation contracts."""

from __future__ import annotations

import uuid

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
