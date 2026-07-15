"""Strict public contracts for the deterministic CGA API."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CgaQuestionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    position: int = Field(ge=1, le=9)
    text: str
    sensitive_prefix: str | None = None
    options: list[tuple[int, str]]


class CgaScaleRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["phq9"]
    version: str
    name: str
    description: str
    question_count: int = 9
    questions: list[CgaQuestionRead]


class CgaScalesRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scales: list[CgaScaleRead]


class CgaStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scale_id: Literal["phq9"]


class CgaAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    question_id: str = Field(pattern=r"^phq9_[1-9]$")
    score: int = Field(ge=0, le=3)


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
    scale_id: Literal["phq9"]
    definition_version: str
    status: Literal["active", "completed", "abandoned"]
    revision: int
    answered_count: int = Field(ge=0, le=9)
    next_question: CgaQuestionRead | None
    risk: CgaRiskRead


class CgaReportRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_score: int = Field(ge=0, le=27)
    severity: Literal["minimal", "mild", "moderate", "moderately_severe", "severe"]
    self_harm_signal: bool
    requires_immediate_safety_assessment: bool
    high_severity_follow_up: bool
    safety_messages: list[str]
    disclaimer: str
