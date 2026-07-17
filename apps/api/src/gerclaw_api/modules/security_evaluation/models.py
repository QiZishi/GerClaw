"""Immutable, server-owned security-risk contracts for Runtime assets."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.runtime.models import (
    VERSION,
    DataClass,
    NetworkAccess,
    RiskLevel,
)

STRICT = ConfigDict(extra="forbid", frozen=True)
ASSET_NAME = r"^[a-z][a-z0-9_.-]{1,63}$"


class SecurityAssetKind(StrEnum):
    """Runtime assets that require a reviewed security-risk profile."""

    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"
    WORKFLOW = "workflow"
    MEMORY = "memory"
    RAG_SOURCE = "rag_source"


class SecurityThreat(StrEnum):
    """Bounded threat classes; profiles cannot contain free-text claims."""

    INDIRECT_PROMPT_INJECTION = "indirect_prompt_injection"
    RAG_POISONING = "rag_poisoning"
    MEMORY_POISONING = "memory_poisoning"
    CROSS_PATIENT_ACCESS = "cross_patient_access"
    TOOL_MISUSE = "tool_misuse"
    SENSITIVE_EGRESS = "sensitive_egress"
    HALLUCINATED_EVIDENCE = "hallucinated_evidence"
    MEDICAL_HARM = "medical_harm"
    RESOURCE_EXHAUSTION = "resource_exhaustion"


class SecurityControl(StrEnum):
    """Executable Runtime controls a profile must bind to."""

    INPUT_SCHEMA = "input_schema"
    OUTPUT_BOUNDARY = "output_boundary"
    RUNTIME_PERMISSION = "runtime_permission"
    TIMEOUT = "timeout"
    EXECUTION_BUDGET = "execution_budget"
    UNTRUSTED_DATA_ISOLATION = "untrusted_data_isolation"
    EVIDENCE_PROVENANCE = "evidence_provenance"
    PATIENT_OWNERSHIP = "patient_ownership"
    EXTERNAL_EGRESS_REDACTION = "external_egress_redaction"


class SecurityProfileStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class SecurityRiskProfile(BaseModel):
    """Version-bound profile reviewed before one Runtime asset can be enabled."""

    model_config = STRICT

    schema_version: str = Field(
        default="security-risk-profile-v1",
        pattern=r"^security-risk-profile-v1$",
    )
    profile_id: str = Field(pattern=r"^security\.[a-z][a-z0-9_.-]{2,80}$")
    profile_version: str = Field(pattern=VERSION)
    asset_kind: SecurityAssetKind
    asset_name: str = Field(pattern=ASSET_NAME)
    asset_version: str = Field(pattern=VERSION)
    owner_module: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    status: SecurityProfileStatus = SecurityProfileStatus.ACTIVE
    risk_level: RiskLevel
    network_access: NetworkAccess
    data_classes: frozenset[DataClass] = Field(min_length=1, max_length=6)
    threats: frozenset[SecurityThreat] = Field(min_length=1, max_length=8)
    required_controls: frozenset[SecurityControl] = Field(min_length=1, max_length=12)
    residual_risk: str = Field(min_length=8, max_length=300)


class SecurityEvaluationVerdict(BaseModel):
    """PHI-free result of a deterministic pre-enable profile assessment."""

    model_config = STRICT

    profile_id: str = Field(pattern=r"^security\.[a-z][a-z0-9_.-]{2,80}$")
    profile_version: str = Field(pattern=VERSION)
    asset_kind: SecurityAssetKind
    asset_name: str = Field(pattern=ASSET_NAME)
    asset_version: str = Field(pattern=VERSION)
    allowed: bool = True
