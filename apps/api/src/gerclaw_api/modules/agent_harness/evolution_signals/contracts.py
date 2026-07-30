"""Strict metadata-only signal captured for isolated offline evaluation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SignalIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_.-]+$",
    ),
]
ErrorCode = Annotated[
    str,
    StringConstraints(min_length=2, max_length=128, pattern=r"^[A-Z][A-Z0-9_]+$"),
]


class EvolutionSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    run_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    route: Literal["quick", "standard", "deep", "emergency"]
    run_status: Literal[
        "waiting_for_user",
        "completed",
        "completed_with_warnings",
        "failed",
        "cancelled",
        "interrupted",
    ]
    error_code: ErrorCode | None = None
    risk_level: Literal["low", "medium", "high", "critical"]
    capability_ids: tuple[SignalIdentifier, ...] = Field(default=(), max_length=50)
    skill_ids: tuple[SignalIdentifier, ...] = Field(default=(), max_length=50)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    feedback_value: Literal[-1, 0, 1] = 0
    feedback_revision: int = Field(default=0, ge=0)
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_error_semantics(self) -> EvolutionSignal:
        failed = self.run_status in {"failed", "cancelled"}
        if failed != (self.error_code is not None):
            raise ValueError("failed or cancelled signals require exactly one stable error code")
        return self


class EvolutionSignalSource(BaseModel):
    """Narrow ephemeral Run projection; raw Skill ids are HMACed before storage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: uuid.UUID
    route: Literal["quick", "standard", "deep", "emergency"]
    run_status: Literal[
        "waiting_for_user",
        "completed",
        "completed_with_warnings",
        "failed",
        "cancelled",
        "interrupted",
    ]
    error_code: ErrorCode | None = None
    capability_ids: tuple[SignalIdentifier, ...] = Field(default=(), max_length=50)
    skill_ids: tuple[SignalIdentifier, ...] = Field(default=(), max_length=50)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    feedback_value: Literal[-1, 0, 1] = 0
    feedback_revision: int = Field(default=0, ge=0)
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_error_semantics(self) -> EvolutionSignalSource:
        failed = self.run_status in {"failed", "cancelled"}
        if failed != (self.error_code is not None):
            raise ValueError("failed or cancelled sources require exactly one stable error code")
        return self


class EvolutionSignalError(RuntimeError):
    """Stable privacy/export-boundary failure."""


class EvolutionSignalSink(Protocol):
    async def reconcile(self, signal: EvolutionSignal) -> None:
        """Upsert current metadata only; never mutate production behavior."""


class EvolutionSignalSourceReader(Protocol):
    async def read_source(self, run_id: uuid.UUID) -> EvolutionSignalSource | None:
        """Return one decontented source projection or no signal."""


class EvolutionSignalCollector(Protocol):
    def schedule(self, run_id: uuid.UUID) -> None:
        """Schedule bounded post-commit collection without awaiting user traffic."""


class EvolutionSignalReader(Protocol):
    async def list_signals(
        self,
        *,
        after_occurred_at: datetime | None,
        after_fingerprint: str | None,
        limit: int,
    ) -> tuple[EvolutionSignal, ...]:
        """Return a bounded, deterministic export page."""
