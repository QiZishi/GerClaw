"""Stable inputs and outputs for pre-model route selection."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.modules.contracts import MAX_PUBLIC_TEXT_CHARACTERS


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
    message: str = Field(min_length=1, max_length=MAX_PUBLIC_TEXT_CHARACTERS)
    has_images: bool = False
    has_documents: bool = False
    image_count: int = Field(default=0, ge=0, le=10)
    document_count: int = Field(default=0, ge=0, le=10)
    selected_capabilities: tuple[str, ...] = Field(default=(), max_length=50)
    medical_content: bool = False
    high_risk_detected: bool = False


class RoutingPolicy(BaseModel):
    """Injected deterministic thresholds; this module never reads environment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    quick_max_characters: int = Field(ge=1, le=1_000)
    deep_min_characters: int = Field(ge=100, le=4_000)
    deep_attachment_count: int = Field(ge=1, le=20)
    deep_capability_count: int = Field(ge=1, le=20)


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
