"""Strict metadata-only signal captured for isolated offline evaluation."""

from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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
    terminal_status: Literal[
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


class EvolutionSignalError(RuntimeError):
    """Stable privacy/export-boundary failure."""


class EvolutionSignalSink(Protocol):
    async def append(self, signal: EvolutionSignal) -> None:
        """Append metadata only; implementations may not mutate production behavior."""
