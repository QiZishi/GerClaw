"""Versioned public and persistence-bound contracts for durable Agent runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.security import JsonValue

BoundedPublicText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=5_000),
]
BoundedIdentifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$"),
]
ArtifactTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


TERMINAL_RUN_STATUSES = frozenset(
    {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.COMPLETED_WITH_WARNINGS,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
        AgentRunStatus.INTERRUPTED,
    }
)


class RunEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    run_id: uuid.UUID
    sequence: int = Field(ge=1)
    event_type: BoundedIdentifier
    status: BoundedIdentifier
    public_summary: BoundedPublicText | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict, max_length=50)
    duration_ms: int | None = Field(default=None, ge=0)
    created_at: datetime


class RunEventPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: uuid.UUID
    events: tuple[RunEventRead, ...] = Field(default=(), max_length=500)
    next_after_sequence: int = Field(ge=0)


class RunEventWrite(BaseModel):
    """Validated public event input before it crosses the persistence boundary."""

    model_config = ConfigDict(extra="forbid")

    event_type: BoundedIdentifier
    status: BoundedIdentifier
    public_summary: BoundedPublicText | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict, max_length=50)
    duration_ms: int | None = Field(default=None, ge=0)


class AgentRunCreate(BaseModel):
    """Validated immutable identity and initial state for one durable run."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    conversation_id: uuid.UUID
    input_message_id: uuid.UUID
    trace_id: BoundedIdentifier
    route: RouteKind
    context_snapshot: dict[str, JsonValue] = Field(default_factory=dict, max_length=100)
    plan: dict[str, JsonValue] = Field(default_factory=dict, max_length=100)
    fencing_token: int = Field(ge=1)


class AgentRunRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    id: uuid.UUID
    conversation_id: uuid.UUID
    input_message_id: uuid.UUID
    trace_id: BoundedIdentifier
    route: RouteKind
    status: AgentRunStatus
    current_answer_version_id: uuid.UUID | None = None
    warnings: tuple[BoundedIdentifier, ...] = Field(default=(), max_length=50)
    last_sequence: int = Field(default=0, ge=0)
    revision: int = Field(ge=1)
    started_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_terminal_timestamp(self) -> AgentRunRead:
        if self.status in TERMINAL_RUN_STATUSES and self.completed_at is None:
            raise ValueError("terminal run requires completed_at")
        if self.status not in TERMINAL_RUN_STATUSES and self.completed_at is not None:
            raise ValueError("non-terminal run cannot have completed_at")
        return self


class AnswerVersionRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.1"] = "1.1"
    id: uuid.UUID
    run_id: uuid.UUID
    producer_run_id: uuid.UUID
    answer_group_id: uuid.UUID
    assistant_message_id: uuid.UUID | None = None
    version: int = Field(ge=1)
    is_current: bool
    supersedes_id: uuid.UUID | None = None
    created_at: datetime


class AnswerVersionRegister(BaseModel):
    """Register an already persisted assistant message as a new answer version."""

    model_config = ConfigDict(extra="forbid")

    assistant_message_id: uuid.UUID
    producer_run_id: uuid.UUID | None = None


class AnswerVersionSelect(BaseModel):
    """Optimistically select a prior version without deleting later versions."""

    model_config = ConfigDict(extra="forbid")

    expected_current_version_id: uuid.UUID


class AnswerVersionListRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: uuid.UUID
    versions: tuple[AnswerVersionRead, ...] = Field(default=(), max_length=100)


class ArtifactKind(StrEnum):
    MARKDOWN = "markdown"
    REPORT = "report"
    PRESCRIPTION = "prescription"
    CGA = "cga"


class ArtifactWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: ArtifactTitle
    markdown: str = Field(max_length=500_000)
    kind: ArtifactKind = ArtifactKind.MARKDOWN
    expected_revision: int | None = Field(default=None, ge=1)


class ArtifactRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    id: uuid.UUID
    run_id: uuid.UUID
    conversation_id: uuid.UUID
    title: ArtifactTitle
    markdown: str = Field(max_length=500_000)
    kind: ArtifactKind
    revision: int = Field(ge=1)
    saved: bool
    created_at: datetime
    updated_at: datetime


class ArtifactListRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: uuid.UUID
    artifacts: tuple[ArtifactRead, ...] = Field(default=(), max_length=100)


class ArtifactDeleted(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: uuid.UUID
    deleted: Literal[True] = True


class FeedbackReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Literal[-1, 0, 1]
    expected_revision: int = Field(ge=0)


class FeedbackStateRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    run_id: uuid.UUID
    value: Literal[-1, 0, 1]
    revision: int = Field(ge=1)
    updated_at: datetime
