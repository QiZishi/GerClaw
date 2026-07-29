"""Source-aware clinical facts; model guesses cannot become confirmed facts."""

from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from gerclaw_api.security import JsonValue

BoundedClinicalText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=5_000),
]


def _validate_bounded_json(value: JsonValue, *, depth: int = 0) -> JsonValue:
    if depth > 5:
        raise ValueError("clinical fact value nesting exceeds limit")
    if isinstance(value, str):
        if not value.strip() or len(value) > 5_000:
            raise ValueError("clinical fact text must be non-empty and bounded")
        return value
    if isinstance(value, list):
        if len(value) > 50:
            raise ValueError("clinical fact list exceeds limit")
        for item in value:
            _validate_bounded_json(item, depth=depth + 1)
    elif isinstance(value, dict):
        if len(value) > 50:
            raise ValueError("clinical fact object exceeds limit")
        for key, item in value.items():
            if not key or len(key) > 128:
                raise ValueError("clinical fact object key is invalid")
            _validate_bounded_json(item, depth=depth + 1)
    return value


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

    @field_validator("value")
    @classmethod
    def bound_nested_value(cls, value: JsonValue) -> JsonValue:
        return _validate_bounded_json(value)

    @model_validator(mode="after")
    def require_trusted_confirmation(self) -> "ClinicalFact":
        if self.status == "confirmed" and not any(
            item.source_type == "trusted_tool" for item in self.provenance
        ):
            raise ValueError("confirmed fact requires trusted-tool provenance")
        return self


class ClinicalState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    facts: tuple[ClinicalFact, ...] = Field(default=(), max_length=500)
    unknowns: tuple[BoundedClinicalText, ...] = Field(default=(), max_length=200)
    conflicts: tuple[BoundedClinicalText, ...] = Field(default=(), max_length=200)


class ClinicalStateError(RuntimeError):
    """Stable reducer-boundary failure."""


class ClinicalStateReducer(Protocol):
    def reduce(
        self,
        current: ClinicalState,
        observations: tuple[ClinicalFact, ...],
        *,
        unknowns: tuple[BoundedClinicalText, ...] = (),
        resolved_unknowns: tuple[BoundedClinicalText, ...] = (),
    ) -> ClinicalState:
        """Reduce trusted observations without confirming model hypotheses."""
