"""Operator-only contracts for immutable Skill proposal review."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.modules.skill.models import SkillDefinition

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


class SkillProposalBundle(BaseModel):
    """Decrypted content candidate visible only inside the offline controller."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["skill-proposal-bundle-v1"] = "skill-proposal-bundle-v1"
    proposal_id: uuid.UUID
    opaque_owner_binding: str = Field(pattern=r"^[a-f0-9]{64}$")
    object_kind: Literal["skill.clinical", "skill.tooling"]
    authority: Literal["clinical_guidance", "control_plane"]
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=20)
    base_revision: int = Field(ge=1)
    candidate_revision: int = Field(ge=2)
    base_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    base_snapshot: SkillDefinition
    candidate_snapshot: SkillDefinition
    governance_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    exported_at: datetime
    nonce: str = Field(pattern=r"^[a-f0-9]{32}$")

    @model_validator(mode="after")
    def validate_candidate_identity(self) -> SkillProposalBundle:
        if self.exported_at.tzinfo is None:
            raise ValueError("export time must be timezone-aware")
        if self.candidate_revision != self.base_revision + 1:
            raise ValueError("candidate must advance one revision")
        if (
            self.base_snapshot.skill_id != self.candidate_snapshot.skill_id
            or self.base_snapshot.revision != self.base_revision
            or self.candidate_snapshot.revision != self.candidate_revision
        ):
            raise ValueError("bundle snapshots do not match candidate identity")
        return self


class SkillProposalExportEnvelope(BaseModel):
    """Signed encrypted handoff with no owner or Skill content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["skill-proposal-export-envelope-v1"] = (
        "skill-proposal-export-envelope-v1"
    )
    exporter_key_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,99}$")
    recipient_key_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,99}$")
    ephemeral_public_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    ciphertext: str = Field(min_length=32, max_length=100_000)
    nonce: str = Field(pattern=r"^[a-f0-9]{24}$")
    encrypted_payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    exporter_signature: str = Field(pattern=r"^[a-f0-9]{128}$")


class SkillActivationAuthorizationPayload(BaseModel):
    """Content-free immutable candidate identity authorized for one atomic activation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["skill-activation-authorization-payload-v1"] = (
        "skill-activation-authorization-payload-v1"
    )
    proposal_id: uuid.UUID
    object_kind: Literal["skill.clinical", "skill.tooling"]
    base_revision: int = Field(ge=1)
    candidate_revision: int = Field(ge=2)
    base_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    frozen_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    paired_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sealed_attestation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval_proof_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval_ticket_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    authorized_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_activation_identity(self) -> SkillActivationAuthorizationPayload:
        if self.candidate_revision != self.base_revision + 1:
            raise ValueError("activation candidate must advance one revision")
        if (
            self.authorized_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.expires_at <= self.authorized_at
        ):
            raise ValueError("activation authorization requires a bounded aware time window")
        return self


class SkillActivationAuthorization(BaseModel):
    """Ed25519 authorization verifiable by the production operator boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["skill-activation-authorization-v1"] = (
        "skill-activation-authorization-v1"
    )
    key_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,99}$")
    payload: SkillActivationAuthorizationPayload
    signature: str = Field(pattern=r"^[a-f0-9]{128}$")
