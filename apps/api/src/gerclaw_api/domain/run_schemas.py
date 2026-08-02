"""Versioned public and persistence-bound contracts for durable Agent runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.modules.contracts import MAX_PUBLIC_TEXT_CHARACTERS, Citation
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
BoundedDirectiveText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
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
    }
)
RUN_EVENT_CLOSED_STATUSES = frozenset(
    {
        *TERMINAL_RUN_STATUSES,
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


class RunDirectiveMode(StrEnum):
    """How a user instruction joins an already active Agent execution."""

    INTERRUPT_AND_STEER = "interrupt_and_steer"
    QUEUE_FOR_NEXT_BOUNDARY = "queue_for_next_boundary"


class RunDirectiveStatus(StrEnum):
    """Durable lifecycle for one user instruction."""

    PENDING = "pending"
    PENDING_NEXT_RUN = "pending_next_run"
    CLAIMED = "claimed"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class RunDirectiveCreate(BaseModel):
    """Create one idempotent instruction without exposing worker internals."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    mode: RunDirectiveMode
    instruction: BoundedDirectiveText
    idempotency_key: BoundedIdentifier


class RunQueuedDirectiveCreate(BaseModel):
    """Public request for a requirement applied at the next safe boundary."""

    model_config = ConfigDict(extra="forbid")

    instruction: BoundedDirectiveText
    idempotency_key: BoundedIdentifier


class RunSteerDirectiveCreate(BaseModel):
    """Public instruction that replaces an active execution with a successor."""

    model_config = ConfigDict(extra="forbid")

    instruction: BoundedDirectiveText
    idempotency_key: BoundedIdentifier


class RunDirectiveClaim(BaseModel):
    """Internal claim identity for exactly-once boundary consumption."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fencing_token: int = Field(ge=1)
    boundary_id: BoundedIdentifier


class RunDirectiveRead(BaseModel):
    """Owner-visible directive state; private execution attempts stay excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    id: uuid.UUID
    conversation_id: uuid.UUID
    target_run_id: uuid.UUID
    successor_run_id: uuid.UUID | None = None
    sequence: int = Field(ge=1)
    mode: RunDirectiveMode
    status: RunDirectiveStatus
    instruction: BoundedDirectiveText
    idempotency_key: BoundedIdentifier
    claimed_by_fencing_token: int | None = Field(default=None, ge=1)
    claim_boundary_id: BoundedIdentifier | None = None
    revision: int = Field(ge=1)
    created_at: datetime
    claimed_at: datetime | None = None
    applied_at: datetime | None = None
    cancelled_at: datetime | None = None

    @model_validator(mode="after")
    def validate_lifecycle_timestamps(self) -> RunDirectiveRead:
        if self.status in {
            RunDirectiveStatus.CLAIMED,
            RunDirectiveStatus.APPLIED,
        } and (
            self.claimed_at is None
            or self.claimed_by_fencing_token is None
            or self.claim_boundary_id is None
        ):
            raise ValueError("claimed directive requires its worker claim identity")
        if self.status is RunDirectiveStatus.APPLIED and self.applied_at is None:
            raise ValueError("applied directive requires applied_at")
        if self.status is RunDirectiveStatus.CANCELLED and self.cancelled_at is None:
            raise ValueError("cancelled directive requires cancelled_at")
        return self


class RunDirectivePublicRead(BaseModel):
    """Owner-visible state without worker fencing or boundary identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    id: uuid.UUID
    conversation_id: uuid.UUID
    target_run_id: uuid.UUID
    successor_run_id: uuid.UUID | None = None
    sequence: int = Field(ge=1)
    mode: RunDirectiveMode
    status: RunDirectiveStatus
    instruction: BoundedDirectiveText
    revision: int = Field(ge=1)
    created_at: datetime
    claimed_at: datetime | None = None
    applied_at: datetime | None = None
    cancelled_at: datetime | None = None

    @classmethod
    def from_internal(cls, directive: RunDirectiveRead) -> RunDirectivePublicRead:
        return cls.model_validate(
            directive.model_dump(
                exclude={
                    "idempotency_key",
                    "claimed_by_fencing_token",
                    "claim_boundary_id",
                }
            )
        )


class RunDirectiveListRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: uuid.UUID
    directives: tuple[RunDirectivePublicRead, ...] = Field(default=(), max_length=200)


class RunAttemptStatus(StrEnum):
    STAGING = "staging"
    VALIDATED = "validated"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"


class ValidationFeedback(BaseModel):
    """Content-free repair instruction retained only in the private audit plane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    step_id: BoundedIdentifier
    attempt: int = Field(ge=1)
    error_code: BoundedIdentifier
    field_paths: tuple[BoundedIdentifier, ...] = Field(default=(), max_length=20)
    contract_version: BoundedIdentifier
    repair_action: BoundedIdentifier
    checkpoint_id: BoundedIdentifier


class RunAttemptCreate(BaseModel):
    """Start one private attempt for a stable user-facing operation."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    public_operation_id: uuid.UUID
    step_id: BoundedIdentifier
    checkpoint_id: BoundedIdentifier
    expected_current_attempt_id: uuid.UUID | None = None


class RunAttemptRead(BaseModel):
    """Private audit metadata; never serialize this contract on public Run routes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    id: uuid.UUID
    run_id: uuid.UUID
    public_operation_id: uuid.UUID
    attempt: int = Field(ge=1)
    step_id: BoundedIdentifier
    checkpoint_id: BoundedIdentifier
    fencing_token: int = Field(ge=1)
    status: RunAttemptStatus
    expected_current_attempt_id: uuid.UUID | None = None
    error_code: BoundedIdentifier | None = None
    feedback: ValidationFeedback | None = None
    created_at: datetime
    completed_at: datetime | None = None


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

    schema_version: Literal["1.1"] = "1.1"
    id: uuid.UUID
    conversation_id: uuid.UUID
    input_message_id: uuid.UUID
    trace_id: BoundedIdentifier
    route: RouteKind
    status: AgentRunStatus
    current_answer_version_id: uuid.UUID | None = None
    current_valid_attempt_id: uuid.UUID | None = Field(default=None, exclude=True)
    warnings: tuple[BoundedIdentifier, ...] = Field(default=(), max_length=50)
    last_sequence: int = Field(default=0, ge=0)
    revision: int = Field(ge=1)
    started_at: datetime
    interrupted_at: datetime | None = None
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_terminal_timestamp(self) -> AgentRunRead:
        if self.status in TERMINAL_RUN_STATUSES and self.completed_at is None:
            raise ValueError("terminal run requires completed_at")
        if self.status not in TERMINAL_RUN_STATUSES and self.completed_at is not None:
            raise ValueError("non-terminal run cannot have completed_at")
        if self.status is AgentRunStatus.INTERRUPTED and self.interrupted_at is None:
            raise ValueError("interrupted run requires interrupted_at")
        return self


class RecoverableRunRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: uuid.UUID
    run: AgentRunRead | None = None


class AnswerVersionRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.2"] = "1.2"
    id: uuid.UUID
    run_id: uuid.UUID
    producer_run_id: uuid.UUID
    answer_group_id: uuid.UUID
    assistant_message_id: uuid.UUID | None = None
    version: int = Field(ge=1)
    is_current: bool
    supersedes_id: uuid.UUID | None = None
    answer_markdown: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_PUBLIC_TEXT_CHARACTERS,
    )
    citations: tuple[Citation, ...] = Field(default=(), max_length=50)
    created_at: datetime


class AnswerVersionRegister(BaseModel):
    """Register an already persisted assistant message as a new answer version."""

    model_config = ConfigDict(extra="forbid")

    assistant_message_id: uuid.UUID
    producer_run_id: uuid.UUID | None = None
    expected_current_version_id: uuid.UUID | None = None


class AnswerVersionSelect(BaseModel):
    """Optimistically select a prior version without deleting later versions."""

    model_config = ConfigDict(extra="forbid")

    expected_current_version_id: uuid.UUID


class AnswerVersionListRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: uuid.UUID
    versions: tuple[AnswerVersionRead, ...] = Field(default=(), max_length=100)


class RunRegenerationContext(BaseModel):
    """Server-validated immutable source for a replacement generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_run_id: uuid.UUID
    source_trace_id: BoundedIdentifier
    input_message_id: uuid.UUID
    current_answer_version_id: uuid.UUID


class RunAnswerContext(BaseModel):
    """Current answer metadata returned for initial completion or Trace replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: uuid.UUID
    answer_group_run_id: uuid.UUID
    answer_version_id: uuid.UUID
    answer_version: int = Field(ge=1)


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
