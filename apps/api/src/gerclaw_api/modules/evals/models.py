"""Strict contracts for synthetic, replay-safe evaluation cases."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

EVAL_CASE_SCHEMA_VERSION: Final = "eval-case-v1"


class EvalCase(BaseModel):
    """A reviewed synthetic case that cannot contain a user or patient identifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["eval-case-v1"] = "eval-case-v1"
    case_id: str = Field(pattern=r"^safety\.[a-z0-9_.-]{3,80}$")
    title: str = Field(min_length=1, max_length=120)
    synthetic_input: str = Field(min_length=1, max_length=500)
    expected_high_risk_codes: tuple[str, ...] = ()
    expected_emergency_short_circuit: bool
    policy_version: Literal["medical_safety_v1"] = "medical_safety_v1"
    provenance: Literal["synthetic_reviewed"] = "synthetic_reviewed"


class EvalCaseResult(BaseModel):
    """Machine-readable result without echoing synthetic or user input text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    expected_high_risk_codes: tuple[str, ...]
    actual_high_risk_codes: tuple[str, ...]
    expected_emergency_short_circuit: bool
    actual_emergency_short_circuit: bool
    policy_version: str
