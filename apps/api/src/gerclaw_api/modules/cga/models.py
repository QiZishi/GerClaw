"""Strict public contracts for the deterministic CGA API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CgaQuestionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    position: int = Field(ge=1, le=30)
    text: str
    sensitive_prefix: str | None = None
    input_kind: Literal["ordinal", "clock_minutes", "duration_minutes"] = "ordinal"
    options: list[tuple[int, str]] = Field(default_factory=list)


class CgaScaleRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["phq9", "sas", "psqi"]
    version: str
    name: str
    description: str
    question_count: int = Field(ge=1, le=30)
    questions: list[CgaQuestionRead]


class CgaScalesRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scales: list[CgaScaleRead]


class CgaStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scale_id: Literal["phq9", "sas", "psqi"]


class CgaAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    question_id: str = Field(
        pattern=r"^(?:phq9_[1-9]|sas_(?:[1-9]|1[0-9]|20)|psqi_(?:[1-9]|10|5[a-j]))$"
    )
    score: int = Field(ge=0, le=1_439)
    supplemental_detail: str | None = Field(default=None, max_length=500)


class CgaCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class CgaRiskRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requires_immediate_safety_assessment: bool
    high_severity_follow_up: bool = False
    messages: list[str] = Field(default_factory=list)


class CgaAssessmentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: uuid.UUID
    scale_id: Literal["phq9", "sas", "psqi"]
    definition_version: str
    status: Literal["active", "completed", "abandoned"]
    revision: int
    answered_count: int = Field(ge=0, le=30)
    next_question: CgaQuestionRead | None
    risk: CgaRiskRead


class CgaReportRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_score: int = Field(ge=0, le=100)
    # Reports persisted before the multi-scale contract only contained PHQ-9
    # fields.  Defaulting to its established maximum keeps those encrypted
    # historical reports readable while newly written reports are explicit.
    score_max: int = Field(default=27, ge=1, le=100)
    raw_score: int | None = Field(default=None, ge=0, le=100)
    standard_score: int | None = Field(default=None, ge=0, le=100)
    severity: Literal[
        "none",
        "minimal",
        "mild",
        "moderate",
        "moderately_severe",
        "severe",
        "good",
        "fair",
        "average",
        "poor",
    ]
    self_harm_signal: bool = False
    requires_immediate_safety_assessment: bool = False
    high_severity_follow_up: bool = False
    safety_messages: list[str] = Field(default_factory=list)
    component_scores: dict[str, int] = Field(default_factory=dict)
    disclaimer: str


class CgaHistoryItemRead(BaseModel):
    """One caller-owned completed screening; raw answers are deliberately absent."""

    model_config = ConfigDict(extra="forbid")

    assessment_id: uuid.UUID
    scale_id: Literal["phq9", "sas", "psqi"]
    definition_version: str
    completed_at: datetime
    report: CgaReportRead


class CgaHistoryRead(BaseModel):
    """A bounded, newest-first view of completed caller-owned screenings."""

    model_config = ConfigDict(extra="forbid")

    items: list[CgaHistoryItemRead] = Field(default_factory=list, max_length=20)


class CgaActiveAssessmentsRead(BaseModel):
    """A bounded list of the caller's resumable screenings only."""

    model_config = ConfigDict(extra="forbid")

    items: list[CgaAssessmentRead] = Field(default_factory=list, max_length=3)
