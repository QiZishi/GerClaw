"""Strict tenant-safe contracts for trace, event, feedback, and bad-case ingestion."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_api.domain.enums import (
    FeedbackRating,
    TraceEventStatus,
    TraceEventType,
    TraceStatus,
)
from gerclaw_api.security import JsonValue, validate_audit_payload

TRACE_ID_PATTERN = r"^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$"
SAFE_IDENTIFIER_PATTERN = r"^[a-z][a-z0-9]{1,31}_[A-Za-z0-9][A-Za-z0-9_.:-]{7,95}$"
EVENT_ID_PATTERN = r"^event_[A-Za-z0-9][A-Za-z0-9_.:-]{7,89}$"
FINISH_KEY_PATTERN = r"^finish_[A-Za-z0-9][A-Za-z0-9_.:-]{7,88}$"
IDEMPOTENCY_KEY_PATTERN = r"^idem_[A-Za-z0-9][A-Za-z0-9_.:-]{7,90}$"
EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9_.-]{1,63}$"
FEEDBACK_CATEGORY_PATTERN = r"^[a-z][a-z0-9_.-]{1,63}$"
FeedbackCategory = Annotated[
    str, Field(min_length=2, max_length=64, pattern=FEEDBACK_CATEGORY_PATTERN)
]

STRICT_MODEL_CONFIG = ConfigDict(extra="forbid")

EVENT_AUDIT_KEYS: dict[TraceEventType, frozenset[str]] = {
    TraceEventType.AGENT_START: frozenset(
        {"channel", "feature", "model", "module", "operation", "provider", "protocol"}
    ),
    TraceEventType.AGENT_FINISH: frozenset(
        {
            "citation_count",
            "duration_ms",
            "input_tokens",
            "model",
            "outcome",
            "output_tokens",
            "safety_flags",
            "success",
            "token_usage",
            "total_tokens",
        }
    ),
    TraceEventType.MODEL_CALL: frozenset(
        {
            "duration_ms",
            "error_code",
            "input_tokens",
            "latency_ms",
            "model",
            "outcome",
            "output_tokens",
            "provider",
            "protocol",
            "retry_count",
            "success",
            "token_usage",
            "total_tokens",
        }
    ),
    TraceEventType.RAG_RETRIEVE: frozenset(
        {
            "chunk_ids",
            "citation_ids",
            "document_count",
            "document_ids",
            "duration_ms",
            "latency_ms",
            "model",
            "operation",
            "provider",
            "score",
            "scores",
            "success",
        }
    ),
    TraceEventType.SEARCH_QUERY: frozenset(
        {
            "duration_ms",
            "module",
            "operation",
            "outcome",
            "provider",
            "result_count",
            "retry_index",
            "success",
        }
    ),
    TraceEventType.TOOL_CALL: frozenset(
        {"duration_ms", "error_code", "operation", "outcome", "success", "tool", "tool_name"}
    ),
    TraceEventType.SKILL_EXECUTE: frozenset(
        {
            "duration_ms",
            "error_code",
            "operation",
            "outcome",
            "skill",
            "success",
            "version",
        }
    ),
    TraceEventType.MEMORY_UPDATE: frozenset(
        {
            "categories",
            "confirmed_count",
            "document_count",
            "duration_ms",
            "event_count",
            "inactive_count",
            "memory_ids",
            "operation",
            "outcome",
            "pending_count",
            "success",
            "version",
        }
    ),
    TraceEventType.SAFETY_CHECK: frozenset({"duration_ms", "outcome", "safety_flags", "success"}),
    TraceEventType.VOICE_CALL: frozenset(
        {"duration_ms", "error_code", "model", "operation", "provider", "success"}
    ),
    TraceEventType.SYSTEM_ERROR: frozenset({"error_code", "module", "operation", "result_code"}),
}


class TraceStartRequest(BaseModel):
    """Start a system execution; identity and Trace ID come from verified context."""

    model_config = STRICT_MODEL_CONFIG

    session_id: uuid.UUID | None = None
    execution_type: str = Field(min_length=2, max_length=64, pattern=EVENT_TYPE_PATTERN)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("attributes", mode="before")
    @classmethod
    def validate_attributes(cls, value: Any) -> dict[str, JsonValue]:
        return validate_audit_payload(value)


class TraceEventCreate(BaseModel):
    """Append one idempotent, typed audit event without model chain-of-thought."""

    model_config = STRICT_MODEL_CONFIG

    event_id: str = Field(pattern=EVENT_ID_PATTERN)
    event_type: TraceEventType
    status: TraceEventStatus
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload(cls, value: Any) -> dict[str, JsonValue]:
        return validate_audit_payload(value)

    @model_validator(mode="after")
    def validate_event_specific_payload(self) -> TraceEventCreate:
        unexpected = set(self.payload) - EVENT_AUDIT_KEYS[self.event_type]
        if unexpected:
            raise ValueError(
                f"payload keys are not valid for {self.event_type.value}: {sorted(unexpected)}"
            )
        return self


class TraceFinishRequest(BaseModel):
    """Complete, fail, or cancel a running trace idempotently."""

    model_config = STRICT_MODEL_CONFIG

    idempotency_key: str = Field(pattern=FINISH_KEY_PATTERN)
    status: TraceStatus
    error_code: str | None = Field(default=None, max_length=64, pattern=FEEDBACK_CATEGORY_PATTERN)
    error_summary: str | None = Field(default=None, max_length=2_000)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("attributes", mode="before")
    @classmethod
    def validate_attributes(cls, value: Any) -> dict[str, JsonValue]:
        return validate_audit_payload(value)


class TraceRead(BaseModel):
    """Public redacted representation of an execution trace."""

    model_config = ConfigDict(from_attributes=True)

    trace_id: str
    request_id: str
    tenant_id: str
    actor_id: str
    session_id: uuid.UUID | None
    execution_type: str
    status: TraceStatus
    attributes: dict[str, JsonValue]
    error_code: str | None
    error_summary: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None


class TraceEventRead(BaseModel):
    """Public representation of one allowlisted audit event."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    trace_id: str
    sequence: int
    event_type: TraceEventType
    status: TraceEventStatus
    payload: dict[str, JsonValue]
    duration_ms: int | None
    created_at: datetime


class FeedbackCreate(BaseModel):
    """Submit idempotent feedback for the authenticated actor."""

    model_config = STRICT_MODEL_CONFIG

    idempotency_key: str = Field(pattern=IDEMPOTENCY_KEY_PATTERN)
    trace_id: str = Field(pattern=TRACE_ID_PATTERN)
    rating: FeedbackRating
    categories: list[FeedbackCategory] = Field(default_factory=list, max_length=20)
    comment: str | None = Field(default=None, max_length=2_000)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_metadata(cls, value: Any) -> dict[str, JsonValue]:
        return validate_audit_payload(value)


class FeedbackRead(BaseModel):
    """Stored feedback visible within the authenticated tenant."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    idempotency_key: str
    trace_id: str
    actor_id: str
    rating: FeedbackRating
    categories: list[str]
    comment: str | None
    feedback_metadata: dict[str, JsonValue]
    created_at: datetime


class TraceDetail(TraceRead):
    """Trace response with one bounded page of ordered events."""

    events: list[TraceEventRead]
    next_event_cursor: int | None = None
