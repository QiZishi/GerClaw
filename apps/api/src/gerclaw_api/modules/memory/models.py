"""Strict extraction, persistence, API, and vector DTOs for Memory."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.modules.memory.protocols import (
    MemoryCategory,
    MemoryFactView,
    MemoryStatus,
    MemoryType,
)


class MemoryFactDetails(BaseModel):
    """Finite structured attributes supported by profile extraction."""

    model_config = ConfigDict(extra="forbid")

    value: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=32)
    dose: str | None = Field(default=None, max_length=100)
    frequency: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=64)
    reaction: str | None = Field(default=None, max_length=200)
    severity: Literal["mild", "moderate", "severe", "unknown"] | None = None
    code: str | None = Field(default=None, max_length=32)
    level: str | None = Field(default=None, max_length=100)
    source_status: Literal["active", "stopped", "resolved", "historical", "unknown"] = "unknown"


class ExtractedMemoryFact(BaseModel):
    """One LLM candidate that still requires deterministic evidence validation."""

    model_config = ConfigDict(extra="forbid")

    category: MemoryCategory
    memory_type: MemoryType
    entity: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=1_000)
    evidence_span: str = Field(min_length=1, max_length=300)
    action: Literal["upsert", "deactivate"] = "upsert"
    confidence: float = Field(ge=0, le=1)
    occurred_at: datetime | None = None
    details: MemoryFactDetails = Field(default_factory=MemoryFactDetails)

    @model_validator(mode="after")
    def validate_category_shape(self) -> ExtractedMemoryFact:
        """Reject category-specific candidates missing their identifying value."""

        if self.category == "basic_info" and self.details.value is None:
            raise ValueError("basic information requires a value")
        if self.category == "medication" and self.entity.casefold() in {"药", "药物", "medication"}:
            raise ValueError("medication entity must name the medicine")
        if self.category == "vital_sign" and (
            self.details.value is None or self.details.unit is None
        ):
            raise ValueError("vital sign requires value and unit")
        return self


class MemoryExtraction(BaseModel):
    """Bounded structured result produced by a real configured model."""

    model_config = ConfigDict(extra="forbid")

    facts: list[ExtractedMemoryFact] = Field(default_factory=list, max_length=30)


class MemoryUpdateResult(BaseModel):
    """Safe operational summary; it deliberately contains no fact text."""

    model_config = ConfigDict(extra="forbid")

    profile_version: int = Field(ge=0)
    changed_fact_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    confirmed_count: int = Field(default=0, ge=0)
    pending_count: int = Field(default=0, ge=0)
    inactive_count: int = Field(default=0, ge=0)
    categories: list[MemoryCategory] = Field(default_factory=list, max_length=10)


class MemoryVectorRecord(BaseModel):
    """Embedding input with identifiers separated from encrypted source text."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    category: MemoryCategory
    status: MemoryStatus
    revision: int = Field(ge=1)
    statement: str = Field(min_length=1, max_length=1_000)


class MemoryVectorCandidate(BaseModel):
    """Qdrant result containing references only, never memory text."""

    model_config = ConfigDict(extra="forbid")

    fact_id: uuid.UUID
    revision: int = Field(ge=1)
    category: MemoryCategory
    score: float = Field(ge=0, le=1)


class HealthProfileRead(BaseModel):
    """Authenticated current-user health profile response."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    version: int = Field(ge=0)
    profile: dict[str, object]
    facts: list[MemoryFactView] = Field(default_factory=list, max_length=200)


class MemoryFactDecisionRequest(BaseModel):
    """Optimistic user confirmation or retirement of one extracted fact."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    decision: Literal["confirm", "reject"]


class MemoryFactDecisionRead(BaseModel):
    """Updated fact plus the resulting profile version."""

    model_config = ConfigDict(extra="forbid")

    fact: MemoryFactView
    profile_version: int = Field(ge=1)
