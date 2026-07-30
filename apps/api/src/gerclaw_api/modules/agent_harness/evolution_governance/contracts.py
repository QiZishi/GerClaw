"""Versioned contracts for online/offline evolution authority."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

GovernanceTrack = Literal["mutable", "immutable"]
EvolutionAuthority = Literal[
    "presentation_only",
    "untrusted_user_context",
    "bounded_retrieval",
    "clinical_guidance",
    "control_plane",
]
EvolutionUpdatePolicy = Literal[
    "online_revisioned",
    "offline_proposal_only",
    "sealed_controller_only",
]
ObjectKind = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]+$",
    ),
]
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


class EvolutionObjectRule(BaseModel):
    """Authority and activation policy for one persistent object class."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["evolution-object-rule-v1"] = "evolution-object-rule-v1"
    object_kind: ObjectKind
    track: GovernanceTrack
    authority: EvolutionAuthority
    owner: Literal[
        "user",
        "skill_owner",
        "trusted_offline_controller",
        "sealed_release_controller",
    ]
    update_policy: EvolutionUpdatePolicy
    allowed_target_prefixes: tuple[str, ...] = Field(default=(), max_length=20)
    candidate_readable: bool = True
    candidate_writable: bool = False

    @model_validator(mode="after")
    def validate_authority_shape(self) -> EvolutionObjectRule:
        if self.track == "mutable" and self.update_policy != "online_revisioned":
            raise ValueError("mutable objects must use revisioned online updates")
        if self.update_policy == "sealed_controller_only" and self.candidate_writable:
            raise ValueError("sealed controller assets cannot be candidate writable")
        if self.update_policy != "sealed_controller_only" and not self.candidate_writable:
            raise ValueError("evolvable objects must be writable only inside their candidate track")
        if self.candidate_writable and not self.allowed_target_prefixes:
            raise ValueError("candidate-writable objects require trusted target prefixes")
        if any(not prefix or not prefix.endswith("/") for prefix in self.allowed_target_prefixes):
            raise ValueError("trusted target prefixes must be non-empty and directory-bounded")
        return self


class ComponentCharter(BaseModel):
    """Candidate-readable but candidate-non-writable component definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["component-charter-v1"] = "component-charter-v1"
    component: ObjectKind
    core_purpose: str = Field(min_length=20, max_length=1_000)
    invariants: tuple[str, ...] = Field(min_length=1, max_length=30)
    mutable_content: tuple[str, ...] = Field(default=(), max_length=20)
    protected_mechanisms: tuple[str, ...] = Field(min_length=1, max_length=30)
    sealed_evaluator_ids: tuple[ObjectKind, ...] = Field(min_length=1, max_length=20)
    candidate_readable: Literal[True] = True
    candidate_writable: Literal[False] = False


class OnlineMutationRequest(BaseModel):
    """Content classification request after owner service authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["online-mutation-v1"] = "online-mutation-v1"
    object_kind: ObjectKind
    requested_authority: EvolutionAuthority
    expected_revision: int = Field(ge=0)


class CandidateChange(BaseModel):
    """One content-addressed change in an isolated candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_kind: ObjectKind
    target: str = Field(min_length=3, max_length=512)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("target")
    @classmethod
    def validate_relative_target(cls, value: str) -> str:
        normalized = value.strip()
        if (
            not normalized
            or normalized.startswith(("/", "\\"))
            or _WINDOWS_ABSOLUTE.match(normalized)
            or "\\" in normalized
            or "\x00" in normalized
            or ".." in normalized.split("/")
        ):
            raise ValueError("candidate target must be a normalized relative target")
        return normalized


class CandidateProposal(BaseModel):
    """Frozen, single-track candidate identity before evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["candidate-proposal-v1"] = "candidate-proposal-v1"
    proposal_id: ObjectKind
    declared_track: GovernanceTrack
    base_commit: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    candidate_commit: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_reason_codes: tuple[ObjectKind, ...] = Field(min_length=1, max_length=20)
    activation_condition_ids: tuple[ObjectKind, ...] = Field(min_length=1, max_length=20)
    frozen_at: datetime
    changes: tuple[CandidateChange, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_frozen_identity(self) -> CandidateProposal:
        if self.base_commit == self.candidate_commit:
            raise ValueError("candidate commit must differ from its base")
        if self.frozen_at.tzinfo is None:
            raise ValueError("candidate freeze timestamp must be timezone-aware")
        return self


class EvolutionGovernanceError(RuntimeError):
    """Stable fail-closed error at the evolution authority boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
