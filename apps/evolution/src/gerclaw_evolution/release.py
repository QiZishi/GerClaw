"""Atomic promotion and audited rollback for frozen evolution candidates."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from gerclaw_api.modules.agent_harness.evolution_governance import (
    EvolutionGovernanceError,
    EvolutionGovernancePolicy,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_evolution.approval import (
    HumanApprovalProof,
    HumanApprovalVerifier,
    attestation_digest,
)
from gerclaw_evolution.attestation import SealedGateAttestation, SealedGatePayload
from gerclaw_evolution.contracts import CandidateControlError, FrozenCandidate
from gerclaw_evolution.evaluation import PairedEvaluationGate, PairedEvaluationReport
from gerclaw_evolution.git_repository import GitRepository, RefUpdate

_STRICT = ConfigDict(extra="forbid", frozen=True)
_ID = r"^[a-z][a-z0-9_.-]{2,99}$"
_SHA256 = r"^[a-f0-9]{64}$"
_GIT_SHA = r"^[a-f0-9]{40}$"
_SIGNATURE = r"^[a-f0-9]{128}$"
_ZERO = "0" * 40
_CHANNEL = re.compile(r"^[a-z][a-z0-9-]{2,31}$")


class ReleaseRecordPayload(BaseModel):
    """Immutable release history entry stored as a signed Git blob."""

    model_config = _STRICT

    schema_version: Literal["release-record-payload-v1"] = "release-record-payload-v1"
    action: Literal["promote", "rollback"]
    release_id: str = Field(pattern=_ID)
    release_ref: str = Field(pattern=r"^refs/gerclaw/releases/[a-z][a-z0-9-]{2,31}$")
    proposal_id: str = Field(pattern=_ID)
    track: Literal["mutable", "immutable"]
    commit: str = Field(pattern=_GIT_SHA)
    previous_commit: str | None = Field(default=None, pattern=_GIT_SHA)
    frozen_manifest_sha256: str = Field(pattern=_SHA256)
    paired_report_sha256: str = Field(pattern=_SHA256)
    sealed_attestation_sha256: str = Field(pattern=_SHA256)
    human_approval_sha256: str | None = Field(default=None, pattern=_SHA256)
    approval_ticket_id: str | None = Field(default=None, pattern=_ID)
    previous_release_record_sha256: str | None = Field(default=None, pattern=_SHA256)
    rollback_target_record_sha256: str | None = Field(default=None, pattern=_SHA256)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("release time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_action_specific_fields(self) -> ReleaseRecordPayload:
        if self.action == "rollback" and self.rollback_target_record_sha256 is None:
            raise ValueError("rollback must identify a signed target record")
        if self.action == "promote" and self.rollback_target_record_sha256 is not None:
            raise ValueError("promotion cannot contain a rollback target")
        if (self.human_approval_sha256 is None) != (self.approval_ticket_id is None):
            raise ValueError("approval digest and ticket must be present together")
        return self


class SignedReleaseRecord(BaseModel):
    """Controller-signed public release record."""

    model_config = _STRICT

    schema_version: Literal["signed-release-record-v1"] = "signed-release-record-v1"
    key_id: str = Field(pattern=_ID)
    payload: ReleaseRecordPayload
    signature: str = Field(pattern=_SIGNATURE)


@dataclass(frozen=True, slots=True)
class ReleaseSigningKeyRecord:
    key_id: str
    private_key_seed: bytes = field(repr=False)
    promotion_active: bool

    def __post_init__(self) -> None:
        if len(self.private_key_seed) != 32 or not self.key_id:
            raise CandidateControlError("EVOLUTION_RELEASE_KEY_INVALID")

    def verification_record(self) -> ReleaseVerificationKeyRecord:
        public_key = (
            Ed25519PrivateKey.from_private_bytes(self.private_key_seed)
            .public_key()
            .public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        )
        return ReleaseVerificationKeyRecord(
            key_id=self.key_id,
            public_key=public_key,
            promotion_active=self.promotion_active,
        )


@dataclass(frozen=True, slots=True)
class ReleaseVerificationKeyRecord:
    key_id: str
    public_key: bytes = field(repr=False)
    promotion_active: bool

    def __post_init__(self) -> None:
        if len(self.public_key) != 32 or not self.key_id:
            raise CandidateControlError("EVOLUTION_RELEASE_KEY_INVALID")


class ReleaseSigner:
    """Controller-only release signer; private key never enters candidate roots."""

    def __init__(self, record: ReleaseSigningKeyRecord) -> None:
        self._record = record

    def sign(self, payload: ReleaseRecordPayload) -> SignedReleaseRecord:
        if not self._record.promotion_active:
            raise CandidateControlError("EVOLUTION_RELEASE_KEY_NOT_ACTIVE")
        signature = Ed25519PrivateKey.from_private_bytes(self._record.private_key_seed).sign(
            _canonical(self._record.key_id, payload)
        )
        return SignedReleaseRecord(
            key_id=self._record.key_id,
            payload=payload,
            signature=signature.hex(),
        )


class ReleaseVerifier:
    """Public-key verifier used before accepting a rollback target."""

    def __init__(self, records: tuple[ReleaseVerificationKeyRecord, ...]) -> None:
        if not records or len({record.key_id for record in records}) != len(records):
            raise CandidateControlError("EVOLUTION_RELEASE_KEYRING_INVALID")
        self._records = {record.key_id: record for record in records}

    def verify(self, record: SignedReleaseRecord) -> ReleaseRecordPayload:
        authority = self._records.get(record.key_id)
        if authority is None:
            raise CandidateControlError("EVOLUTION_RELEASE_KEY_UNKNOWN")
        if not authority.promotion_active:
            raise CandidateControlError("EVOLUTION_RELEASE_KEY_NOT_ACTIVE")
        try:
            Ed25519PublicKey.from_public_bytes(authority.public_key).verify(
                bytes.fromhex(record.signature),
                _canonical(record.key_id, record.payload),
            )
        except (InvalidSignature, ValueError) as error:
            raise CandidateControlError("EVOLUTION_RELEASE_SIGNATURE_INVALID") from error
        return record.payload


class CandidateRevalidator(Protocol):
    def assert_unchanged(
        self,
        repository: GitRepository,
        frozen: FrozenCandidate,
    ) -> None: ...


class AttestationVerifier(Protocol):
    def verify(
        self,
        attestation: SealedGateAttestation,
        *,
        frozen: FrozenCandidate,
        report: PairedEvaluationReport,
    ) -> SealedGatePayload: ...


class ReleaseClock(Protocol):
    def now(self) -> datetime: ...


class SystemReleaseClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ReleaseAuditWriter(Protocol):
    def append(self, record: SignedReleaseRecord) -> None: ...


class JsonlReleaseAuditLog:
    """Append-only external mirror; signed Git refs remain the recovery source."""

    def __init__(self, path: Path, *, forbidden_roots: tuple[Path, ...] = ()) -> None:
        if path.exists() and (not path.is_file() or path.is_symlink()):
            raise CandidateControlError("EVOLUTION_AUDIT_LOG_INVALID")
        path.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = path.parent.resolve(strict=True)
        for root in forbidden_roots:
            resolved_root = root.resolve(strict=True)
            if resolved_parent == resolved_root or resolved_root in resolved_parent.parents:
                raise CandidateControlError("EVOLUTION_AUDIT_LOG_INSIDE_UNTRUSTED_ROOT")
        self._path = path

    def append(self, record: SignedReleaseRecord) -> None:
        line = (
            json.dumps(
                record.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        descriptor = os.open(
            self._path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            written = 0
            while written < len(line):
                count = os.write(descriptor, line[written:])
                if count <= 0:
                    raise OSError("audit append made no progress")
                written += count
            os.fsync(descriptor)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


class PromotionResult(BaseModel):
    model_config = _STRICT

    record: SignedReleaseRecord
    record_sha256: str = Field(pattern=_SHA256)
    audit_mirror_status: Literal["appended", "repair_required"]


class PromotionController:
    """Revalidate, authorize, and atomically move protected release refs."""

    def __init__(
        self,
        *,
        candidate_revalidator: CandidateRevalidator,
        attestation_verifier: AttestationVerifier,
        approval_verifier: HumanApprovalVerifier,
        release_signer: ReleaseSigner,
        release_verifier: ReleaseVerifier,
        audit_writer: ReleaseAuditWriter,
        clock: ReleaseClock | None = None,
        max_approval_age: timedelta = timedelta(hours=24),
        deployment_requires_mutable_approval: bool = False,
        governance: EvolutionGovernancePolicy | None = None,
    ) -> None:
        if max_approval_age <= timedelta(0):
            raise CandidateControlError("EVOLUTION_PROMOTION_POLICY_INVALID")
        self._candidate_revalidator = candidate_revalidator
        self._attestation_verifier = attestation_verifier
        self._approval_verifier = approval_verifier
        self._release_signer = release_signer
        self._release_verifier = release_verifier
        self._audit_writer = audit_writer
        self._clock = clock or SystemReleaseClock()
        self._max_approval_age = max_approval_age
        self._mutable_approval_required = deployment_requires_mutable_approval
        self._governance = governance or EvolutionGovernancePolicy()

    def promote(
        self,
        *,
        source_repository: GitRepository,
        candidate_repository: GitRepository,
        channel: str,
        frozen: FrozenCandidate,
        report: PairedEvaluationReport,
        sealed_attestation: SealedGateAttestation,
        human_approval: HumanApprovalProof | None,
    ) -> PromotionResult:
        release_ref, ledger_ref = _release_refs(channel)
        promotion_time = self._now()
        try:
            self._governance.validate_candidate(frozen.proposal)
        except EvolutionGovernanceError as error:
            raise CandidateControlError(error.code) from error
        self._candidate_revalidator.assert_unchanged(candidate_repository, frozen)
        self._attestation_verifier.verify(
            sealed_attestation,
            frozen=frozen,
            report=report,
        )
        approval_digest: str | None = None
        ticket_id: str | None = None
        approval_required = self._governance.approval_required(
            frozen.proposal.declared_track,
            deployment_requires_approval=self._mutable_approval_required,
        )
        if approval_required and human_approval is None:
            raise CandidateControlError("EVOLUTION_HUMAN_APPROVAL_REQUIRED")
        if human_approval is not None:
            approval = self._approval_verifier.verify(
                human_approval,
                frozen=frozen,
                report=report,
                sealed_attestation=sealed_attestation,
            )
            if promotion_time < approval.approved_at:
                raise CandidateControlError("EVOLUTION_PROMOTION_TIME_ORDER_INVALID")
            if promotion_time - approval.approved_at > self._max_approval_age:
                raise CandidateControlError("EVOLUTION_HUMAN_APPROVAL_EXPIRED")
            approval_digest = _digest_model(human_approval)
            ticket_id = approval.approval_ticket_id
            ticket_digest = hashlib.sha256(ticket_id.encode()).hexdigest()
            if source_repository.resolve_ref(f"refs/gerclaw/approval-tickets/{ticket_digest}"):
                raise CandidateControlError("EVOLUTION_APPROVAL_TICKET_ALREADY_CONSUMED")

        previous_commit = source_repository.resolve_ref(release_ref)
        previous_record_object = source_repository.resolve_ref(ledger_ref)
        previous_record_digest = self._verified_current_release(
            source_repository,
            release_ref=release_ref,
            current_commit=previous_commit,
            current_record_object=previous_record_object,
        )
        if previous_commit is not None:
            self._assert_complete_release_chain(
                source_repository,
                release_ref=release_ref,
                current_commit=previous_commit,
                current_record_object=previous_record_object,
            )
        payload = ReleaseRecordPayload(
            action="promote",
            release_id=f"release.{frozen.proposal.proposal_id}.{frozen.proposal.candidate_commit[:12]}",
            release_ref=release_ref,
            proposal_id=frozen.proposal.proposal_id,
            track=frozen.proposal.declared_track,
            commit=frozen.proposal.candidate_commit,
            previous_commit=previous_commit,
            frozen_manifest_sha256=frozen.frozen_manifest_sha256,
            paired_report_sha256=PairedEvaluationGate.digest(report),
            sealed_attestation_sha256=attestation_digest(sealed_attestation),
            human_approval_sha256=approval_digest,
            approval_ticket_id=ticket_id,
            previous_release_record_sha256=previous_record_digest,
            recorded_at=promotion_time,
        )
        return self._commit_record(
            source_repository,
            channel=channel,
            payload=payload,
            expected_commit=previous_commit,
            expected_record_object=previous_record_object,
        )

    def rollback(
        self,
        *,
        source_repository: GitRepository,
        channel: str,
        target_record: SignedReleaseRecord,
    ) -> PromotionResult:
        release_ref, ledger_ref = _release_refs(channel)
        target = self._release_verifier.verify(target_record)
        target_digest = _digest_model(target_record)
        if target.release_ref != release_ref:
            raise CandidateControlError("EVOLUTION_ROLLBACK_TARGET_CHANNEL_MISMATCH")
        previous_commit = source_repository.resolve_ref(release_ref)
        if previous_commit is None:
            raise CandidateControlError("EVOLUTION_RELEASE_REF_MISSING")
        if previous_commit == target.commit:
            raise CandidateControlError("EVOLUTION_ROLLBACK_TARGET_ALREADY_ACTIVE")
        previous_record_object = source_repository.resolve_ref(ledger_ref)
        previous_record_digest = self._verified_current_release(
            source_repository,
            release_ref=release_ref,
            current_commit=previous_commit,
            current_record_object=previous_record_object,
        )
        self._assert_complete_release_chain(
            source_repository,
            release_ref=release_ref,
            current_commit=previous_commit,
            current_record_object=previous_record_object,
            target_digest=target_digest,
            target_record=target_record,
        )
        payload = ReleaseRecordPayload(
            action="rollback",
            release_id=f"rollback.{target.proposal_id}.{target.commit[:12]}",
            release_ref=release_ref,
            proposal_id=target.proposal_id,
            track=target.track,
            commit=target.commit,
            previous_commit=previous_commit,
            frozen_manifest_sha256=target.frozen_manifest_sha256,
            paired_report_sha256=target.paired_report_sha256,
            sealed_attestation_sha256=target.sealed_attestation_sha256,
            previous_release_record_sha256=previous_record_digest,
            rollback_target_record_sha256=target_digest,
            recorded_at=self._now(),
        )
        return self._commit_record(
            source_repository,
            channel=channel,
            payload=payload,
            expected_commit=previous_commit,
            expected_record_object=previous_record_object,
        )

    def _commit_record(
        self,
        repository: GitRepository,
        *,
        channel: str,
        payload: ReleaseRecordPayload,
        expected_commit: str | None,
        expected_record_object: str | None,
    ) -> PromotionResult:
        signed = self._release_signer.sign(payload)
        record_bytes = _record_bytes(signed)
        record_digest = hashlib.sha256(record_bytes).hexdigest()
        record_object = repository.store_blob(record_bytes)
        release_ref, ledger_ref = _release_refs(channel)
        updates = [
            RefUpdate(release_ref, payload.commit, expected_commit or _ZERO),
            RefUpdate(ledger_ref, record_object, expected_record_object or _ZERO),
            RefUpdate(
                f"refs/gerclaw/release-records/{record_digest}",
                record_object,
                _ZERO,
            ),
            RefUpdate(
                f"refs/gerclaw/release-commits/{record_digest}",
                payload.commit,
                _ZERO,
            ),
        ]
        if payload.approval_ticket_id:
            ticket_digest = hashlib.sha256(payload.approval_ticket_id.encode()).hexdigest()
            updates.append(
                RefUpdate(
                    f"refs/gerclaw/approval-tickets/{ticket_digest}",
                    record_object,
                    _ZERO,
                )
            )
        repository.atomic_update_refs(tuple(updates))
        try:
            self._audit_writer.append(signed)
            audit_status: Literal["appended", "repair_required"] = "appended"
        except Exception:
            audit_status = "repair_required"
        return PromotionResult(
            record=signed,
            record_sha256=record_digest,
            audit_mirror_status=audit_status,
        )

    def _now(self) -> datetime:
        value = self._clock.now()
        if value.tzinfo is None:
            raise CandidateControlError("EVOLUTION_RELEASE_CLOCK_INVALID")
        return value

    def _verified_current_release(
        self,
        repository: GitRepository,
        *,
        release_ref: str,
        current_commit: str | None,
        current_record_object: str | None,
    ) -> str | None:
        if current_commit is None and current_record_object is None:
            return None
        if current_commit is None or current_record_object is None:
            raise CandidateControlError("EVOLUTION_RELEASE_STATE_INCONSISTENT")
        raw_record = repository.read_blob(current_record_object)
        try:
            record = SignedReleaseRecord.model_validate_json(raw_record)
        except ValueError as error:
            raise CandidateControlError("EVOLUTION_RELEASE_RECORD_INVALID") from error
        payload = self._release_verifier.verify(record)
        if payload.release_ref != release_ref or payload.commit != current_commit:
            raise CandidateControlError("EVOLUTION_RELEASE_STATE_INCONSISTENT")
        digest = hashlib.sha256(raw_record).hexdigest()
        immutable_record_object = repository.resolve_ref(f"refs/gerclaw/release-records/{digest}")
        immutable_commit = repository.resolve_ref(f"refs/gerclaw/release-commits/{digest}")
        if immutable_record_object != current_record_object or immutable_commit != current_commit:
            raise CandidateControlError("EVOLUTION_RELEASE_STATE_INCONSISTENT")
        return digest

    def _assert_complete_release_chain(
        self,
        repository: GitRepository,
        *,
        release_ref: str,
        current_commit: str,
        current_record_object: str | None,
        target_digest: str | None = None,
        target_record: SignedReleaseRecord | None = None,
    ) -> None:
        if current_record_object is None:
            raise CandidateControlError("EVOLUTION_RELEASE_STATE_INCONSISTENT")
        object_id = current_record_object
        expected_commit = current_commit
        expected_digest: str | None = None
        seen: set[str] = set()
        target_found = False
        for _depth in range(10_000):
            raw_record = repository.read_blob(object_id)
            digest = hashlib.sha256(raw_record).hexdigest()
            if expected_digest is not None and digest != expected_digest:
                raise CandidateControlError("EVOLUTION_RELEASE_STATE_INCONSISTENT")
            if digest in seen:
                raise CandidateControlError("EVOLUTION_RELEASE_LEDGER_CYCLE")
            seen.add(digest)
            try:
                record = SignedReleaseRecord.model_validate_json(raw_record)
            except ValueError as error:
                raise CandidateControlError("EVOLUTION_RELEASE_RECORD_INVALID") from error
            payload = self._release_verifier.verify(record)
            immutable_object = repository.resolve_ref(f"refs/gerclaw/release-records/{digest}")
            immutable_commit = repository.resolve_ref(f"refs/gerclaw/release-commits/{digest}")
            if (
                immutable_object != object_id
                or immutable_commit != payload.commit
                or payload.release_ref != release_ref
                or payload.commit != expected_commit
            ):
                raise CandidateControlError("EVOLUTION_RELEASE_STATE_INCONSISTENT")
            if digest == target_digest:
                if target_record is None or raw_record != _record_bytes(target_record):
                    raise CandidateControlError("EVOLUTION_ROLLBACK_TARGET_NOT_RELEASED")
                target_found = True
            previous_digest = payload.previous_release_record_sha256
            if previous_digest is None:
                if target_digest is not None and not target_found:
                    raise CandidateControlError("EVOLUTION_ROLLBACK_TARGET_NOT_RELEASED")
                return
            if payload.previous_commit is None:
                raise CandidateControlError("EVOLUTION_RELEASE_STATE_INCONSISTENT")
            previous_object = repository.resolve_ref(
                f"refs/gerclaw/release-records/{previous_digest}"
            )
            if previous_object is None:
                raise CandidateControlError("EVOLUTION_RELEASE_STATE_INCONSISTENT")
            object_id = previous_object
            expected_commit = payload.previous_commit
            expected_digest = previous_digest
        raise CandidateControlError("EVOLUTION_RELEASE_LEDGER_TOO_DEEP")


def _release_refs(channel: str) -> tuple[str, str]:
    if not _CHANNEL.fullmatch(channel):
        raise CandidateControlError("EVOLUTION_RELEASE_CHANNEL_INVALID")
    return (
        f"refs/gerclaw/releases/{channel}",
        f"refs/gerclaw/release-ledger/{channel}",
    )


def _record_bytes(record: SignedReleaseRecord) -> bytes:
    return json.dumps(
        record.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _digest_model(model: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(
            model.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _canonical(key_id: str, payload: ReleaseRecordPayload) -> bytes:
    return json.dumps(
        {
            "domain": "gerclaw.release-record.v1",
            "envelope_schema_version": "signed-release-record-v1",
            "key_id": key_id,
            "payload": payload.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
