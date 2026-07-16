"""Shared typed facts for non-clinical intake boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ClinicalIntakeKind = Literal["prescription", "medication_review"]
CLINICAL_INTAKE_VERSION = "clinical-intake-v1"


@dataclass(frozen=True)
class ClinicalIntakeField:
    """Server-owned collection field whose value is encrypted at rest."""

    id: str
    label: str
    required: bool
    max_length: int
    placeholder: str


@dataclass(frozen=True)
class ClinicalIntakeDefinition:
    """Versioned non-clinical collection contract without clinical advice."""

    kind: ClinicalIntakeKind
    version: str
    title: str
    description: str
    fields: tuple[ClinicalIntakeField, ...]
