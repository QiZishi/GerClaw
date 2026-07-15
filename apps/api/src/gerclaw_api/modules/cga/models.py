"""Strict public contracts for the deterministic CGA API."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CgaQuestionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    position: int = Field(ge=1, le=30)
    text: str
    sensitive_prefix: str | None = None
    options: list[tuple[int, str]]


class CgaScaleRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["phq9", "sas"]
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

    scale_id: Literal["phq9", "sas"]


class CgaAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    question_id: str = Field(pattern=r"^(?:phq9_[1-9]|sas_(?:[1-9]|1[0-9]|20))$")
    score: int = Field(ge=0, le=4)


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
    scale_id: Literal["phq9", "sas"]
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
        "none", "minimal", "mild", "moderate", "moderately_severe", "severe"
    ]
    self_harm_signal: bool = False
    requires_immediate_safety_assessment: bool = False
    high_severity_follow_up: bool = False
    safety_messages: list[str] = Field(default_factory=list)
    disclaimer: str
