"""Strict public contracts for the non-clinical chronic-care measurement ledger."""

from __future__ import annotations

import math
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

STRICT = ConfigDict(extra="forbid")


class ChronicConditionCreateRequest(BaseModel):
    """Record a user-described condition without claiming clinical confirmation."""

    model_config = STRICT

    label: str = Field(min_length=1, max_length=80)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("label cannot contain only whitespace")
        return normalized


class ChronicConditionRead(BaseModel):
    """Owner-visible self-reported condition projection."""

    model_config = STRICT

    condition_id: uuid.UUID
    label: str
    confirmation_status: str = "self_reported"
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ChronicConditionListRead(BaseModel):
    model_config = STRICT

    items: list[ChronicConditionRead] = Field(default_factory=list, max_length=100)


class ChronicMeasurementCreateRequest(BaseModel):
    """One immutable user-recorded number and its measurement timestamp."""

    model_config = STRICT

    metric_label: str = Field(min_length=1, max_length=80)
    value: float = Field(ge=0, le=10_000_000)
    unit: str = Field(min_length=1, max_length=32)
    measured_at: datetime

    @field_validator("metric_label", "unit")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("measurement text cannot contain only whitespace")
        return normalized

    @field_validator("value")
    @classmethod
    def require_finite_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        return value


class ChronicMeasurementRead(BaseModel):
    model_config = STRICT

    measurement_id: uuid.UUID
    condition_id: uuid.UUID
    metric_label: str
    value: float = Field(ge=0, le=10_000_000)
    unit: str
    measured_at: datetime
    created_at: datetime


class ChronicMeasurementListRead(BaseModel):
    model_config = STRICT

    items: list[ChronicMeasurementRead] = Field(default_factory=list, max_length=200)


class ChronicTrendRead(BaseModel):
    """Purely arithmetic comparison, deliberately without clinical interpretation."""

    model_config = STRICT

    metric_label: str
    unit: str
    direction: str
    latest_measurement_id: uuid.UUID
    latest_value: float = Field(ge=0, le=10_000_000)
    latest_measured_at: datetime
    previous_measurement_id: uuid.UUID | None = None
    previous_value: float | None = Field(default=None, ge=0, le=10_000_000)
    previous_measured_at: datetime | None = None


class ChronicTrendListRead(BaseModel):
    model_config = STRICT

    items: list[ChronicTrendRead] = Field(default_factory=list, max_length=100)
