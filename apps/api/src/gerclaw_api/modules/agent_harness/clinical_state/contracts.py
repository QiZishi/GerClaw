"""Source-aware clinical facts; model guesses cannot become confirmed facts."""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.security import JsonValue


class FactProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: Literal["user", "trusted_tool"]
    source_id: str = Field(min_length=1, max_length=128)
    observed_at: datetime


class ClinicalFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str = Field(min_length=1, max_length=128)
    category: Literal[
        "demographic",
        "chief_complaint",
        "timeline",
        "symptom",
        "negative_evidence",
        "history",
        "medication",
        "allergy",
        "test",
        "observation",
        "red_flag",
    ]
    value: JsonValue
    status: Literal["reported", "confirmed", "conflicted"]
    provenance: tuple[FactProvenance, ...] = Field(min_length=1, max_length=20)


class ClinicalState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    facts: tuple[ClinicalFact, ...] = Field(default=(), max_length=500)
    unknowns: tuple[str, ...] = Field(default=(), max_length=200)
    conflicts: tuple[str, ...] = Field(default=(), max_length=200)


class ClinicalStateError(RuntimeError):
    """Stable reducer-boundary failure."""


class ClinicalStateReducer(Protocol):
    def reduce(
        self,
        current: ClinicalState,
        observations: tuple[ClinicalFact, ...],
    ) -> ClinicalState:
        """Reduce trusted observations without confirming model hypotheses."""
