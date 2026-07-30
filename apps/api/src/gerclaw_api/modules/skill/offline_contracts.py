"""Operator-only contracts for immutable Skill proposal review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SkillReviewEventType = Literal[
    "exported",
    "paired_rejected",
    "sealed_rejected",
    "approved",
    "activated",
    "stale",
]
TERMINAL_SKILL_REVIEW_EVENTS = frozenset(
    {"paired_rejected", "sealed_rejected", "activated", "stale"}
)


class SkillReviewEventAppend(BaseModel):
    """Content-free append request from the offline control plane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: SkillReviewEventType
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason_codes: tuple[str, ...] = Field(default=(), max_length=20)
    approval_ticket_digest: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )

    @model_validator(mode="after")
    def validate_event_shape(self) -> SkillReviewEventAppend:
        if any(
            not code
            or len(code) > 64
            or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in code)
            for code in self.reason_codes
        ):
            raise ValueError("review reason codes must be bounded stable identifiers")
        if self.event_type == "activated" and self.approval_ticket_digest is None:
            raise ValueError("activation must consume an approval ticket")
        if self.event_type != "activated" and self.approval_ticket_digest is not None:
            raise ValueError("only activation consumes an approval ticket")
        return self
