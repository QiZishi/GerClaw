"""Versioned, content-free contracts for operational Bad Case metrics."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BadCaseSourceValue = Literal["execution_failure", "negative_feedback"]
BadCaseSeverityValue = Literal["low", "medium", "high", "critical"]
BadCaseStatusValue = Literal["open", "triaged", "resolved", "dismissed"]


class BadCaseAggregate(BaseModel):
    """One database-produced count with no case, trace, or user identifiers."""

    model_config = ConfigDict(extra="forbid")

    source: BadCaseSourceValue
    severity: BadCaseSeverityValue
    status: BadCaseStatusValue
    count: int = Field(ge=0)


class BadCaseSummary(BaseModel):
    """PHI-free aggregate used to prioritize operational follow-up."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    open_count: int = Field(ge=0)
    triaged_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    dismissed_count: int = Field(ge=0)
    execution_failure_count: int = Field(ge=0)
    negative_feedback_count: int = Field(ge=0)
    high_priority_count: int = Field(ge=0)


class BadCaseTrendAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date
    source: BadCaseSourceValue
    count: int = Field(ge=0)


class BadCaseTrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date
    total: int = Field(ge=0)
    execution_failure_count: int = Field(ge=0)
    negative_feedback_count: int = Field(ge=0)


class BadCaseTrend(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_days: Literal[7] = 7
    points: list[BadCaseTrendPoint] = Field(min_length=7, max_length=7)
