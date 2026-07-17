"""Validated contracts for deterministic caller-owned risk alerts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.domain.trace_schemas import IDEMPOTENCY_KEY_PATTERN

RISK_ALERT_POLICY_VERSION = "risk-alert-v2"


class RiskAlertDetails(BaseModel):
    """Encrypted policy-owned content; clients can never submit this model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal[
        "cga_immediate_safety",
        "cga_high_follow_up",
        "chat_red_flag",
        "medication_contraindicated",
        "medication_major_risk",
    ]
    severity: Literal["critical", "high"]
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=300)


class RiskAlertRead(BaseModel):
    """Safe, owner-scoped alert projection without its source identity."""

    model_config = ConfigDict(extra="forbid")

    alert_id: uuid.UUID
    kind: Literal[
        "cga_immediate_safety",
        "cga_high_follow_up",
        "chat_red_flag",
        "medication_contraindicated",
        "medication_major_risk",
    ]
    severity: Literal["critical", "high"]
    title: str
    message: str
    action: str
    status: Literal["active", "acknowledged"]
    revision: int = Field(ge=1)
    policy_version: Literal["risk-alert-v1", "risk-alert-v2"]
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None = None


class RiskAlertListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RiskAlertRead] = Field(default_factory=list, max_length=50)


class RiskAlertAcknowledgeRequest(BaseModel):
    """Bounded idempotent acknowledgement with no free-text clinical input."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(pattern=IDEMPOTENCY_KEY_PATTERN)
