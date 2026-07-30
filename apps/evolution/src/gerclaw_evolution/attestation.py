"""Commit-bound HMAC attestations emitted outside candidate processes."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_evolution.contracts import CandidateControlError, FrozenCandidate
from gerclaw_evolution.evaluation import (
    PairedEvaluationGate,
    PairedEvaluationReport,
)

_STRICT = ConfigDict(extra="forbid", frozen=True)
_ID = r"^[a-z][a-z0-9_.-]{2,99}$"
_SHA256 = r"^[a-f0-9]{64}$"


class SealedGatePayload(BaseModel):
    """No sealed cases or thresholds; only their externally computed verdict."""

    model_config = _STRICT

    schema_version: Literal["sealed-gate-payload-v1"] = "sealed-gate-payload-v1"
    proposal_id: str = Field(pattern=_ID)
    base_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    candidate_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    frozen_manifest_sha256: str = Field(pattern=_SHA256)
    paired_report_sha256: str = Field(pattern=_SHA256)
    sealed_case_set_sha256: str = Field(pattern=_SHA256)
    gate_policy_manifest_sha256: str = Field(pattern=_SHA256)
    evaluator_id: str = Field(pattern=_ID)
    evaluator_version: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,63}$")
    evaluated_at: datetime
    public_report_verified: bool
    sealed_cases_passed: bool
    no_sealed_case_regressed: bool
    high_risk_singletons_non_degrading: bool
    token_budget_passed: bool
    latency_budget_passed: bool
    runtime_activation_passed: bool
    component_charters_passed: bool
    passed: bool

    @field_validator("evaluated_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("sealed evaluation time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def derive_passed_from_all_sealed_gates(self) -> SealedGatePayload:
        expected = all(
            (
                self.public_report_verified,
                self.sealed_cases_passed,
                self.no_sealed_case_regressed,
                self.high_risk_singletons_non_degrading,
                self.token_budget_passed,
                self.latency_budget_passed,
                self.runtime_activation_passed,
                self.component_charters_passed,
            )
        )
        if self.passed != expected:
            raise ValueError("sealed passed value does not match mandatory gates")
        return self


class SealedGateAttestation(BaseModel):
    """HMAC record whose key is unavailable to candidate worktrees."""

    model_config = _STRICT

    schema_version: Literal["sealed-gate-attestation-v1"] = "sealed-gate-attestation-v1"
    key_id: str = Field(pattern=_ID)
    payload: SealedGatePayload
    signature: str = Field(pattern=_SHA256)


class SealedEvaluatorProfile(BaseModel):
    """Controller-injected exact evaluator/case/threshold identity."""

    model_config = _STRICT

    schema_version: Literal["sealed-evaluator-profile-v1"] = "sealed-evaluator-profile-v1"
    public_runner_id: str = Field(pattern=_ID)
    public_runner_version: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,63}$")
    public_evaluation_profile_sha256: str = Field(pattern=_SHA256)
    evaluator_id: str = Field(pattern=_ID)
    evaluator_version: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,63}$")
    sealed_case_set_sha256: str = Field(pattern=_SHA256)
    gate_policy_manifest_sha256: str = Field(pattern=_SHA256)


@dataclass(frozen=True, slots=True)
class AttestationKeyRecord:
    """Non-serializable key authority bound to exactly one sealed profile."""

    key_id: str
    secret: bytes = field(repr=False)
    profile: SealedEvaluatorProfile
    promotion_active: bool

    def __post_init__(self) -> None:
        normalized = self.key_id.replace(".", "").replace("-", "")
        if (
            not self.key_id
            or not normalized.isalnum()
            or not self.key_id[0].islower()
            or len(self.secret) < 32
        ):
            raise CandidateControlError("EVOLUTION_ATTESTATION_KEY_INVALID")


class AttestationKeyring:
    """Trusted controller keyring; keys are never serialized in contracts."""

    def __init__(self, records: tuple[AttestationKeyRecord, ...]) -> None:
        if not records or len({record.key_id for record in records}) != len(records):
            raise CandidateControlError("EVOLUTION_ATTESTATION_KEYRING_INVALID")
        self._records = MappingProxyType({record.key_id: record for record in records})

    def sign(
        self,
        key_id: str,
        payload: SealedGatePayload,
        *,
        frozen: FrozenCandidate,
        report: PairedEvaluationReport,
    ) -> SealedGateAttestation:
        record = self._record(key_id)
        self._assert_report_and_identity(
            payload,
            frozen=frozen,
            report=report,
            profile=record.profile,
        )
        signature = hmac.new(
            record.secret,
            self._canonical(key_id, payload),
            hashlib.sha256,
        ).hexdigest()
        return SealedGateAttestation(
            key_id=key_id,
            payload=payload,
            signature=signature,
        )

    def verify(
        self,
        attestation: SealedGateAttestation,
        *,
        frozen: FrozenCandidate,
        report: PairedEvaluationReport,
    ) -> SealedGatePayload:
        record = self._record(attestation.key_id)
        if not record.promotion_active:
            raise CandidateControlError("EVOLUTION_ATTESTATION_KEY_NOT_ACTIVE")
        expected = hmac.new(
            record.secret,
            self._canonical(attestation.key_id, attestation.payload),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, attestation.signature):
            raise CandidateControlError("EVOLUTION_ATTESTATION_SIGNATURE_INVALID")
        payload = attestation.payload
        self._assert_report_and_identity(
            payload,
            frozen=frozen,
            report=report,
            profile=record.profile,
        )
        if not report.gate.passed or not payload.passed:
            raise CandidateControlError("EVOLUTION_EVALUATION_GATE_REJECTED")
        return payload

    @staticmethod
    def _assert_report_and_identity(
        payload: SealedGatePayload,
        *,
        frozen: FrozenCandidate,
        report: PairedEvaluationReport,
        profile: SealedEvaluatorProfile,
    ) -> None:
        recomputed = PairedEvaluationGate().compare(
            frozen,
            report.baseline,
            report.candidate,
        )
        if recomputed != report:
            raise CandidateControlError("EVOLUTION_PAIRED_REPORT_FORGED")
        if (
            report.baseline.runner_id != profile.public_runner_id
            or report.baseline.runner_version != profile.public_runner_version
            or report.baseline.evaluation_profile_sha256 != profile.public_evaluation_profile_sha256
            or report.proposal_id != frozen.proposal.proposal_id
            or report.base_commit != frozen.proposal.base_commit
            or report.candidate_commit != frozen.proposal.candidate_commit
            or report.frozen_manifest_sha256 != frozen.frozen_manifest_sha256
            or payload.proposal_id != frozen.proposal.proposal_id
            or payload.base_commit != frozen.proposal.base_commit
            or payload.candidate_commit != frozen.proposal.candidate_commit
            or payload.frozen_manifest_sha256 != frozen.frozen_manifest_sha256
            or payload.paired_report_sha256 != PairedEvaluationGate.digest(report)
            or payload.evaluator_id != profile.evaluator_id
            or payload.evaluator_version != profile.evaluator_version
            or payload.sealed_case_set_sha256 != profile.sealed_case_set_sha256
            or payload.gate_policy_manifest_sha256 != profile.gate_policy_manifest_sha256
        ):
            raise CandidateControlError("EVOLUTION_ATTESTATION_IDENTITY_MISMATCH")

    def _record(self, key_id: str) -> AttestationKeyRecord:
        record = self._records.get(key_id)
        if record is None:
            raise CandidateControlError("EVOLUTION_ATTESTATION_KEY_UNKNOWN")
        return record

    @staticmethod
    def _canonical(key_id: str, payload: SealedGatePayload) -> bytes:
        return json.dumps(
            {
                "domain": "gerclaw.sealed-gate-attestation.v1",
                "envelope_schema_version": "sealed-gate-attestation-v1",
                "key_id": key_id,
                "payload": payload.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
