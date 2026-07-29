"""Stable inputs and outputs for pre-model route selection."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RouteKind(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"
    EMERGENCY = "emergency"


class RoutingError(RuntimeError):
    """Stable deterministic-routing failure."""


class RoutingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    message: str = Field(min_length=1, max_length=50_000)
    has_images: bool = False
    has_documents: bool = False
    selected_capabilities: tuple[str, ...] = Field(default=(), max_length=50)
    high_risk_detected: bool = False


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    route: RouteKind
    reason_code: str = Field(min_length=1, max_length=64)
    required_capabilities: tuple[str, ...] = Field(default=(), max_length=50)
    model_allowed: bool = True

    @model_validator(mode="after")
    def enforce_emergency_short_circuit(self) -> RouteDecision:
        if self.route is RouteKind.EMERGENCY and self.model_allowed:
            raise ValueError("emergency route must not allow model execution")
        return self


class Router(Protocol):
    def decide(self, routing_input: RoutingInput) -> RouteDecision:
        """Return a deterministic, auditable decision before model execution."""
