"""Deterministic, fenced state transitions for durable Agent runs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.domain.run_schemas import (
    TERMINAL_RUN_STATUSES,
    AgentRunStatus,
    BoundedIdentifier,
)

_ALLOWED_TRANSITIONS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    AgentRunStatus.RUNNING: frozenset(
        {
            AgentRunStatus.WAITING_FOR_USER,
            AgentRunStatus.COMPLETED,
            AgentRunStatus.COMPLETED_WITH_WARNINGS,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.INTERRUPTED,
        }
    ),
    AgentRunStatus.WAITING_FOR_USER: frozenset(
        {
            AgentRunStatus.RUNNING,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.INTERRUPTED,
        }
    ),
    AgentRunStatus.INTERRUPTED: frozenset(
        {
            AgentRunStatus.RUNNING,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.COMPLETED: frozenset(),
    AgentRunStatus.COMPLETED_WITH_WARNINGS: frozenset(),
    AgentRunStatus.FAILED: frozenset(),
    AgentRunStatus.CANCELLED: frozenset(),
}


class RunTransitionError(RuntimeError):
    """Base error safe to map to a conflict response."""


class RunRevisionConflictError(RunTransitionError):
    """The caller observed an older run revision."""


class RunFenceConflictError(RunTransitionError):
    """A stale worker attempted to write a newer run."""


class RunTerminalConflictError(RunTransitionError):
    """A second or illegal terminal transition was attempted."""


class RunLifecycleState(BaseModel):
    """Content-free state required to decide one transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: uuid.UUID
    status: AgentRunStatus
    revision: int = Field(ge=1)
    fencing_token: int = Field(ge=1)
    warnings: tuple[BoundedIdentifier, ...] = Field(default=(), max_length=50)
    interrupted_at: datetime | None = None
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_terminal_timestamp(self) -> RunLifecycleState:
        if self.status in TERMINAL_RUN_STATUSES and self.completed_at is None:
            raise ValueError("terminal run state requires completed_at")
        if self.status not in TERMINAL_RUN_STATUSES and self.completed_at is not None:
            raise ValueError("non-terminal run state cannot have completed_at")
        if self.status is AgentRunStatus.INTERRUPTED and self.interrupted_at is None:
            raise ValueError("interrupted run state requires interrupted_at")
        return self


class AgentRunStateMachine:
    """Return a new state only when revision, fence, and transition all agree."""

    def transition(
        self,
        current: RunLifecycleState,
        target: AgentRunStatus,
        *,
        expected_revision: int,
        fencing_token: int,
        warnings: tuple[str, ...] = (),
        occurred_at: datetime | None = None,
    ) -> RunLifecycleState:
        if expected_revision != current.revision:
            raise RunRevisionConflictError("agent run revision is stale")
        if fencing_token != current.fencing_token:
            raise RunFenceConflictError("agent run fencing token is stale")
        if target == current.status:
            if target is AgentRunStatus.CANCELLED:
                return current
            raise RunTerminalConflictError("duplicate agent run transition")
        if target not in _ALLOWED_TRANSITIONS[current.status]:
            raise RunTerminalConflictError(
                f"agent run cannot transition from {current.status} to {target}"
            )
        if target is AgentRunStatus.COMPLETED_WITH_WARNINGS and not warnings:
            raise RunTransitionError("completed_with_warnings requires warning codes")
        if target is not AgentRunStatus.COMPLETED_WITH_WARNINGS and warnings:
            raise RunTransitionError("warning codes require completed_with_warnings")
        values = current.model_dump()
        values.update(
            {
                "status": target,
                "revision": current.revision + 1,
                "warnings": warnings,
                "interrupted_at": (
                    occurred_at or datetime.now(UTC)
                    if target is AgentRunStatus.INTERRUPTED
                    else current.interrupted_at
                ),
                "completed_at": (
                    (occurred_at or datetime.now(UTC))
                    if target in TERMINAL_RUN_STATUSES
                    else None
                ),
            }
        )
        return RunLifecycleState.model_validate(values)
