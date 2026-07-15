"""Strict, versioned contracts for governed Agent and workflow execution."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.security import JsonValue

STRICT = ConfigDict(extra="forbid", frozen=True)
SAFE_ID = r"^[a-z][a-z0-9]{1,31}_[A-Za-z0-9][A-Za-z0-9_.:-]{7,95}$"
TOOL_NAME = r"^[a-z][a-z0-9_.-]{1,63}$"
VERSION = r"^[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}$"
IDEMPOTENCY_KEY = r"^idem_[A-Za-z0-9][A-Za-z0-9_.:-]{15,111}$"
INVOCATION_ID = r"^invoke_[A-Za-z0-9][A-Za-z0-9_.:-]{15,87}$"


class PermissionBehavior(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionCode(StrEnum):
    ALLOWED = "RUNTIME_ALLOWED"
    TOOL_UNKNOWN = "RUNTIME_TOOL_UNKNOWN"
    VERSION_MISMATCH = "RUNTIME_VERSION_MISMATCH"
    SCOPE_REQUIRED = "RUNTIME_SCOPE_REQUIRED"
    ROLE_FORBIDDEN = "RUNTIME_ROLE_FORBIDDEN"
    PATIENT_ACCESS_REQUIRED = "RUNTIME_PATIENT_ACCESS_REQUIRED"
    NETWORK_FORBIDDEN = "RUNTIME_NETWORK_FORBIDDEN"
    PHI_EGRESS_FORBIDDEN = "RUNTIME_PHI_EGRESS_FORBIDDEN"
    CRITICAL_ACTION_DENIED = "RUNTIME_CRITICAL_ACTION_DENIED"
    APPROVAL_REQUIRED = "RUNTIME_APPROVAL_REQUIRED"
    AGENTSCOPE_DENIED = "RUNTIME_AGENTSCOPE_DENIED"
    AGENTSCOPE_APPROVAL_REQUIRED = "RUNTIME_AGENTSCOPE_APPROVAL_REQUIRED"


class ActorRole(StrEnum):
    GUEST = "guest"
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"
    AUDITOR = "auditor"
    SERVICE = "service"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SideEffect(StrEnum):
    NONE = "none"
    INTERNAL_WRITE = "internal_write"
    EXTERNAL_WRITE = "external_write"
    CLINICAL_ACTION = "clinical_action"


class NetworkAccess(StrEnum):
    NONE = "none"
    INTERNAL = "internal"
    EXTERNAL = "external"


class DataClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    IDENTIFIER = "identifier"
    PHI = "phi"
    CREDENTIAL = "credential"
    HIGH_SENSITIVITY_CLINICAL = "high_sensitivity_clinical"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RuntimePrincipal(BaseModel):
    """Server-verified identity and patient boundary for one decision."""

    model_config = STRICT

    tenant_id: str = Field(pattern=SAFE_ID)
    actor_id: str = Field(pattern=SAFE_ID)
    role: ActorRole
    scopes: frozenset[str] = Field(max_length=64)
    user_id: uuid.UUID | None = None
    patient_id: uuid.UUID | None = None
    patient_access_verified: bool = False
    interactive: bool = True

    @model_validator(mode="after")
    def prevent_unbound_patient_proof(self) -> RuntimePrincipal:
        if self.patient_access_verified and self.patient_id is None:
            raise ValueError("patient access proof requires a patient id")
        return self


class ToolCapability(BaseModel):
    """Immutable server-owned capability descriptor."""

    model_config = STRICT

    name: str = Field(pattern=TOOL_NAME)
    version: str = Field(pattern=VERSION)
    description: str = Field(min_length=8, max_length=500)
    required_scopes: frozenset[str] = Field(min_length=1, max_length=16)
    allowed_roles: frozenset[ActorRole] = Field(min_length=1, max_length=6)
    risk_level: RiskLevel
    side_effect: SideEffect
    network_access: NetworkAccess
    data_classes: frozenset[DataClass] = Field(min_length=1, max_length=6)
    patient_scoped: bool = False
    timeout_seconds: float = Field(default=10, gt=0, le=60)
    max_input_bytes: int = Field(default=16_384, ge=256, le=262_144)
    max_output_bytes: int = Field(default=262_144, ge=256, le=2_097_152)
    idempotency_required: bool = False
    approval_roles: frozenset[ActorRole] = Field(default_factory=frozenset, max_length=4)

    @model_validator(mode="after")
    def validate_risk_contract(self) -> ToolCapability:
        if self.side_effect is not SideEffect.NONE and not self.idempotency_required:
            raise ValueError("side-effecting tools require an idempotency key")
        if self.risk_level is RiskLevel.CRITICAL and self.approval_roles:
            raise ValueError("critical tools are denied, not approvable")
        if (
            (self.risk_level is RiskLevel.HIGH or self.side_effect is not SideEffect.NONE)
            and self.risk_level is not RiskLevel.CRITICAL
            and not self.approval_roles
        ):
            raise ValueError("high-risk or side-effecting tools require approval roles")
        if (
            DataClass.CREDENTIAL in self.data_classes
            and self.network_access is NetworkAccess.EXTERNAL
        ):
            raise ValueError("credential data can never be assigned to an external tool")
        return self


class ToolInvocationRequest(BaseModel):
    """Validated proposal from an Agent; identity is supplied separately."""

    model_config = STRICT

    invocation_id: str = Field(pattern=INVOCATION_ID)
    tool_name: str = Field(pattern=TOOL_NAME)
    tool_version: str = Field(pattern=VERSION)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, pattern=IDEMPOTENCY_KEY)
    outbound_data_redacted: bool = False


class PermissionVerdict(BaseModel):
    """PHI-free deterministic decision suitable for SSE and Trace."""

    model_config = STRICT

    behavior: PermissionBehavior
    code: PermissionCode
    message: str = Field(min_length=1, max_length=300)
    policy_version: str = Field(pattern=VERSION)
    capability_version: str | None = Field(default=None, pattern=VERSION)
    approval_roles: tuple[ActorRole, ...] = Field(default_factory=tuple, max_length=4)
    bypass_immune: bool = True


class ApprovalCreate(BaseModel):
    """Internal ASK persistence command derived from a verified verdict."""

    model_config = STRICT

    user_id: uuid.UUID
    patient_id: uuid.UUID | None = None
    session_id: uuid.UUID
    trace_id: str = Field(pattern=r"^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$")
    invocation: ToolInvocationRequest
    required_roles: tuple[ActorRole, ...] = Field(min_length=1, max_length=4)
    policy_version: str = Field(pattern=VERSION)
    expires_at: datetime


class ApprovalRead(BaseModel):
    """Public approval metadata; encrypted tool arguments are never returned."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    requester_actor_id: str
    patient_id: uuid.UUID | None
    session_id: uuid.UUID
    trace_id: str
    invocation_id: str
    tool_name: str
    tool_version: str
    required_roles: list[ActorRole]
    policy_version: str
    status: ApprovalStatus
    revision: int
    decided_by_actor_id: str | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ApprovalDecisionRequest(BaseModel):
    model_config = STRICT

    expected_revision: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=2, max_length=1_000)


class ApprovalCancelRequest(BaseModel):
    """Optimistic requester cancellation; a terminal approval cannot be cancelled."""

    model_config = STRICT

    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=1_000)


class ApprovalGrant(BaseModel):
    """One-time grant returned only to the authorized approver."""

    model_config = STRICT

    approval: ApprovalRead
    execution_token: str | None = Field(default=None, min_length=32, max_length=256)


class ApprovalReviewRead(BaseModel):
    """Decrypted action detail projected only to a role-authorized approver."""

    model_config = STRICT

    approval: ApprovalRead
    arguments: dict[str, JsonValue]


class ExecutionBudget(BaseModel):
    """Hard limits enforced for every Runtime execution."""

    model_config = STRICT

    wall_clock_seconds: int = Field(default=120, ge=1, le=900)
    max_steps: int = Field(default=20, ge=1, le=100)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_model_calls: int = Field(default=12, ge=0, le=50)
    max_tool_calls: int = Field(default=12, ge=0, le=50)
    max_input_tokens: int = Field(default=80_000, ge=256, le=1_000_000)
    max_output_tokens: int = Field(default=8_192, ge=256, le=100_000)
    max_output_bytes: int = Field(default=100_000, ge=1_000, le=2_097_152)


class RuntimeCheckpoint(BaseModel):
    """Version-bound recovery state; sensitive payload is encrypted at rest."""

    model_config = STRICT

    checkpoint_id: uuid.UUID
    trace_id: str = Field(pattern=r"^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$")
    sequence: int = Field(ge=1)
    schema_version: str = Field(pattern=VERSION)
    policy_version: str = Field(pattern=VERSION)
    workflow_version: str = Field(pattern=VERSION)
    capability_versions: dict[str, str] = Field(default_factory=dict, max_length=100)
    completed_steps: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    consumed_effect_tokens: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    state: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime
