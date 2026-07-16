"""Strict HTTP contracts for non-clinical prescription and medication intake."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    kind: Literal["prescription", "medication_review"]


class ClinicalIntakeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    answers: dict[str, str] = Field(min_length=1, max_length=3)


class ClinicalIntakeRead(BaseModel):
    """Caller-owned intake state. It deliberately contains no clinical output."""

    model_config = ConfigDict(extra="forbid")

    intake_id: uuid.UUID
    session_id: uuid.UUID
    kind: Literal["prescription", "medication_review"]
    definition_version: str = Field(min_length=1, max_length=32)
    status: Literal["collecting", "information_complete_pending_governance"]
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=300)
    fields: list[ClinicalIntakeFieldRead] = Field(min_length=1, max_length=5)
    answers: dict[str, str] = Field(default_factory=dict, max_length=3)
    missing_required_fields: list[str] = Field(default_factory=list, max_length=3)
    governance_notice: str = Field(min_length=1, max_length=500)
    updated_at: datetime
