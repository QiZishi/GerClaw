"""Human-controlled Ed25519 approval separated from promotion verification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Literal, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gerclaw_evolution.attestation import SealedGateAttestation, SealedGatePayload
from gerclaw_evolution.contracts import CandidateControlError, FrozenCandidate
from gerclaw_evolution.evaluation import PairedEvaluationGate, PairedEvaluationReport

_STRICT = ConfigDict(extra="forbid", frozen=True)
_ID = r"^[a-z][a-z0-9_.-]{2,99}$"
_SHA256 = r"^[a-f0-9]{64}$"
_ED25519_SIGNATURE = r"^[a-f0-9]{128}$"


class HumanApprovalPayload(BaseModel):
    """Commit-bound approval intent; never inferred from automated tests."""

    model_config = _STRICT

    schema_version: Literal["human-approval-payload-v1"] = "human-approval-payload-v1"
    proposal_id: str = Field(pattern=_ID)
    track: Literal["mutable", "immutable"]
    candidate_commit: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    frozen_manifest_sha256: str = Field(pattern=_SHA256)
    paired_report_sha256: str = Field(pattern=_SHA256)
    sealed_attestation_sha256: str = Field(pattern=_SHA256)
    approver_principal_id: str = Field(pattern=_ID)
    approval_ticket_id: str = Field(pattern=_ID)
    approved_at: datetime
    decision: Literal["approved"] = "approved"

    @field_validator("approved_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("approval time must be timezone-aware")
        return value


class HumanApprovalProof(BaseModel):
    """Public-key-verifiable human approval envelope with no private material."""

    model_config = _STRICT

    schema_version: Literal["human-approval-proof-v1"] = "human-approval-proof-v1"
    key_id: str = Field(pattern=_ID)
    payload: HumanApprovalPayload
    signature: str = Field(pattern=_ED25519_SIGNATURE)


@dataclass(frozen=True, slots=True)
class ApprovalVerificationKeyRecord:
    """Promotion-side authority containing only an approver public key."""

    key_id: str
    public_key: bytes = field(repr=False)
    approver_principal_id: str
    allowed_tracks: frozenset[Literal["mutable", "immutable"]]
    promotion_active: bool

    def __post_init__(self) -> None:
        if (
            len(self.public_key) != 32
            or not self.key_id
            or not self.approver_principal_id
            or not self.allowed_tracks
        ):
            raise CandidateControlError("EVOLUTION_APPROVAL_KEY_INVALID")


@dataclass(frozen=True, slots=True)
class ApprovalSigningKeyRecord:
    """Private material loaded only by a separately authenticated approval service."""

    key_id: str
    private_key_seed: bytes = field(repr=False)
    approver_principal_id: str
    allowed_tracks: frozenset[Literal["mutable", "immutable"]]
    promotion_active: bool

    def __post_init__(self) -> None:
        if (
            len(self.private_key_seed) != 32
            or not self.key_id
            or not self.approver_principal_id
            or not self.allowed_tracks
        ):
            raise CandidateControlError("EVOLUTION_APPROVAL_KEY_INVALID")

    def verification_record(self) -> ApprovalVerificationKeyRecord:
        public_key = (
            Ed25519PrivateKey.from_private_bytes(self.private_key_seed)
            .public_key()
            .public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        )
        return ApprovalVerificationKeyRecord(
            key_id=self.key_id,
            public_key=public_key,
            approver_principal_id=self.approver_principal_id,
            allowed_tracks=self.allowed_tracks,
            promotion_active=self.promotion_active,
        )


class SealedAttestationVerifier(Protocol):
    """Trusted automated-gate verifier injected into both approval boundaries."""

    def verify(
        self,
        attestation: SealedGateAttestation,
        *,
        frozen: FrozenCandidate,
        report: PairedEvaluationReport,
    ) -> SealedGatePayload: ...


class ApprovalClock(Protocol):
    """Trusted controller clock; approval time is never caller supplied."""

    def now(self) -> datetime: ...


class SystemApprovalClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class HumanApprovalSigner:
    """Human-service-only signing API; never construct inside promotion workers."""

    def __init__(
        self,
        records: tuple[ApprovalSigningKeyRecord, ...],
        *,
        attestation_verifier: SealedAttestationVerifier,
        clock: ApprovalClock | None = None,
        max_future_skew: timedelta = timedelta(minutes=2),
    ) -> None:
        if not records or len({record.key_id for record in records}) != len(records):
            raise CandidateControlError("EVOLUTION_APPROVAL_KEYRING_INVALID")
        self._records = MappingProxyType({record.key_id: record for record in records})
        self._attestation_verifier = attestation_verifier
        self._clock = clock or SystemApprovalClock()
        self._max_future_skew = max_future_skew

    def approve(
        self,
        key_id: str,
        *,
        frozen: FrozenCandidate,
        report: PairedEvaluationReport,
        sealed_attestation: SealedGateAttestation,
        approval_ticket_id: str,
    ) -> HumanApprovalProof:
        record = self._record(key_id)
        _assert_record_authority(record, frozen)
        sealed_payload = _validate_artifacts(
            self._attestation_verifier,
            frozen,
            report,
            sealed_attestation,
        )
        approved_at = _trusted_now(self._clock)
        _assert_time_order(
            frozen,
            report,
            sealed_payload,
            approved_at=approved_at,
            trusted_now=approved_at,
            max_future_skew=self._max_future_skew,
        )
        payload = HumanApprovalPayload(
            proposal_id=frozen.proposal.proposal_id,
            track=frozen.proposal.declared_track,
            candidate_commit=frozen.proposal.candidate_commit,
            frozen_manifest_sha256=frozen.frozen_manifest_sha256,
            paired_report_sha256=PairedEvaluationGate.digest(report),
            sealed_attestation_sha256=attestation_digest(sealed_attestation),
            approver_principal_id=record.approver_principal_id,
            approval_ticket_id=approval_ticket_id,
            approved_at=approved_at,
        )
        signature = Ed25519PrivateKey.from_private_bytes(record.private_key_seed).sign(
            _canonical(record.key_id, payload)
        )
        return HumanApprovalProof(
            key_id=record.key_id,
            payload=payload,
            signature=signature.hex(),
        )

    def _record(self, key_id: str) -> ApprovalSigningKeyRecord:
        record = self._records.get(key_id)
        if record is None:
            raise CandidateControlError("EVOLUTION_APPROVAL_KEY_UNKNOWN")
        return record


class HumanApprovalVerifier:
    """Promotion-side verification API that cannot create approval proofs."""

    def __init__(
        self,
        records: tuple[ApprovalVerificationKeyRecord, ...],
        *,
        attestation_verifier: SealedAttestationVerifier,
        clock: ApprovalClock | None = None,
        max_future_skew: timedelta = timedelta(minutes=2),
    ) -> None:
        if not records or len({record.key_id for record in records}) != len(records):
            raise CandidateControlError("EVOLUTION_APPROVAL_KEYRING_INVALID")
        self._records = MappingProxyType({record.key_id: record for record in records})
        self._attestation_verifier = attestation_verifier
        self._clock = clock or SystemApprovalClock()
        self._max_future_skew = max_future_skew

    def verify(
        self,
        proof: HumanApprovalProof,
        *,
        frozen: FrozenCandidate,
        report: PairedEvaluationReport,
        sealed_attestation: SealedGateAttestation,
    ) -> HumanApprovalPayload:
        record = self._record(proof.key_id)
        _assert_record_authority(record, frozen)
        try:
            Ed25519PublicKey.from_public_bytes(record.public_key).verify(
                bytes.fromhex(proof.signature),
                _canonical(proof.key_id, proof.payload),
            )
        except (InvalidSignature, ValueError) as error:
            raise CandidateControlError("EVOLUTION_APPROVAL_SIGNATURE_INVALID") from error
        sealed_payload = _validate_artifacts(
            self._attestation_verifier,
            frozen,
            report,
            sealed_attestation,
        )
        payload = proof.payload
        if (
            payload.approver_principal_id != record.approver_principal_id
            or payload.track not in record.allowed_tracks
            or payload.proposal_id != frozen.proposal.proposal_id
            or payload.track != frozen.proposal.declared_track
            or payload.candidate_commit != frozen.proposal.candidate_commit
            or payload.frozen_manifest_sha256 != frozen.frozen_manifest_sha256
            or payload.paired_report_sha256 != PairedEvaluationGate.digest(report)
            or payload.sealed_attestation_sha256 != attestation_digest(sealed_attestation)
        ):
            raise CandidateControlError("EVOLUTION_APPROVAL_IDENTITY_MISMATCH")
        _assert_time_order(
            frozen,
            report,
            sealed_payload,
            approved_at=payload.approved_at,
            trusted_now=_trusted_now(self._clock),
            max_future_skew=self._max_future_skew,
        )
        return payload

    def _record(self, key_id: str) -> ApprovalVerificationKeyRecord:
        record = self._records.get(key_id)
        if record is None:
            raise CandidateControlError("EVOLUTION_APPROVAL_KEY_UNKNOWN")
        return record


def attestation_digest(attestation: SealedGateAttestation) -> str:
    return hashlib.sha256(
        json.dumps(
            attestation.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _validate_artifacts(
    verifier: SealedAttestationVerifier,
    frozen: FrozenCandidate,
    report: PairedEvaluationReport,
    sealed_attestation: SealedGateAttestation,
) -> SealedGatePayload:
    payload = verifier.verify(
        sealed_attestation,
        frozen=frozen,
        report=report,
    )
    if (
        report.proposal_id != frozen.proposal.proposal_id
        or report.base_commit != frozen.proposal.base_commit
        or report.candidate_commit != frozen.proposal.candidate_commit
        or report.frozen_manifest_sha256 != frozen.frozen_manifest_sha256
        or payload.proposal_id != frozen.proposal.proposal_id
        or payload.candidate_commit != frozen.proposal.candidate_commit
        or payload.frozen_manifest_sha256 != frozen.frozen_manifest_sha256
        or payload.paired_report_sha256 != PairedEvaluationGate.digest(report)
    ):
        raise CandidateControlError("EVOLUTION_APPROVAL_ARTIFACT_MISMATCH")
    return payload


def _assert_record_authority(
    record: ApprovalSigningKeyRecord | ApprovalVerificationKeyRecord,
    frozen: FrozenCandidate,
) -> None:
    if not record.promotion_active:
        raise CandidateControlError("EVOLUTION_APPROVAL_KEY_NOT_ACTIVE")
    if frozen.proposal.declared_track not in record.allowed_tracks:
        raise CandidateControlError("EVOLUTION_APPROVAL_TRACK_FORBIDDEN")


def _assert_time_order(
    frozen: FrozenCandidate,
    report: PairedEvaluationReport,
    sealed_payload: SealedGatePayload,
    *,
    approved_at: datetime,
    trusted_now: datetime,
    max_future_skew: timedelta,
) -> None:
    evaluation_times = (
        report.baseline.evaluated_at,
        report.candidate.evaluated_at,
    )
    if (
        max_future_skew < timedelta(0)
        or any(item < frozen.proposal.frozen_at for item in evaluation_times)
        or sealed_payload.evaluated_at < max(evaluation_times)
        or approved_at < sealed_payload.evaluated_at
        or approved_at > trusted_now + max_future_skew
    ):
        raise CandidateControlError("EVOLUTION_APPROVAL_TIME_ORDER_INVALID")


def _trusted_now(clock: ApprovalClock) -> datetime:
    value = clock.now()
    if value.tzinfo is None:
        raise CandidateControlError("EVOLUTION_APPROVAL_CLOCK_INVALID")
    return value


def _canonical(key_id: str, payload: HumanApprovalPayload) -> bytes:
    return json.dumps(
        {
            "domain": "gerclaw.human-approval.v1",
            "envelope_schema_version": "human-approval-proof-v1",
            "key_id": key_id,
            "payload": payload.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
