"""Issue production-verifiable activation authorization after every offline gate."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from gerclaw_api.modules.skill.offline_contracts import (
    SkillActivationAuthorization,
    SkillActivationAuthorizationPayload,
)

from gerclaw_evolution.approval import (
    HumanApprovalProof,
    HumanApprovalVerifier,
    attestation_digest,
)
from gerclaw_evolution.attestation import SealedGateAttestation
from gerclaw_evolution.contracts import CandidateControlError
from gerclaw_evolution.evaluation import PairedEvaluationGate, PairedEvaluationReport
from gerclaw_evolution.skill_proposal import FrozenSkillCandidate

_DOMAIN = "gerclaw.skill-activation-authorization.v1"


class SkillAuthorizationClock(Protocol):
    def now(self) -> datetime: ...


class SystemSkillAuthorizationClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class SkillActivationSigningKey:
    """Offline-only signer; production receives only its public key."""

    key_id: str
    private_key_seed: bytes = field(repr=False)
    active: bool

    def __post_init__(self) -> None:
        if len(self.private_key_seed) != 32 or not self.key_id or not self.key_id[0].islower():
            raise CandidateControlError("EVOLUTION_SKILL_AUTHORIZATION_KEY_INVALID")


class SkillActivationAuthorizer:
    """Verify paired, sealed, and human gates before signing one short-lived grant."""

    def __init__(
        self,
        *,
        key: SkillActivationSigningKey,
        approval_verifier: HumanApprovalVerifier,
        clock: SkillAuthorizationClock | None = None,
        lifetime: timedelta = timedelta(hours=1),
    ) -> None:
        if lifetime <= timedelta(0) or lifetime > timedelta(days=1):
            raise CandidateControlError("EVOLUTION_SKILL_AUTHORIZATION_LIFETIME_INVALID")
        self._key = key
        self._approval_verifier = approval_verifier
        self._clock = clock or SystemSkillAuthorizationClock()
        self._lifetime = lifetime

    def authorize(
        self,
        candidate: FrozenSkillCandidate,
        *,
        report: PairedEvaluationReport,
        sealed_attestation: SealedGateAttestation,
        human_approval: HumanApprovalProof,
    ) -> SkillActivationAuthorization:
        if not self._key.active:
            raise CandidateControlError("EVOLUTION_SKILL_AUTHORIZATION_KEY_NOT_ACTIVE")
        frozen = candidate.frozen
        approval = self._approval_verifier.verify(
            human_approval,
            frozen=frozen,
            report=report,
            sealed_attestation=sealed_attestation,
        )
        proposal_id = _proposal_uuid(frozen.proposal.proposal_id)
        change_kinds = {change.object_kind for change in frozen.proposal.changes}
        object_kind: Literal["skill.clinical", "skill.tooling"]
        if change_kinds == {"skill.clinical"}:
            object_kind = "skill.clinical"
        elif change_kinds == {"skill.tooling"}:
            object_kind = "skill.tooling"
        else:
            raise CandidateControlError("EVOLUTION_SKILL_AUTHORIZATION_SCOPE_INVALID")
        authorized_at = self._clock.now()
        if authorized_at.tzinfo is None:
            raise CandidateControlError("EVOLUTION_SKILL_AUTHORIZATION_CLOCK_INVALID")
        payload = SkillActivationAuthorizationPayload(
            proposal_id=proposal_id,
            object_kind=object_kind,
            base_revision=candidate.base_snapshot.revision,
            candidate_revision=candidate.candidate_snapshot.revision,
            base_content_sha256=frozen.proposal.base_commit,
            candidate_content_sha256=frozen.proposal.candidate_commit,
            governance_manifest_sha256=frozen.governance_manifest_sha256,
            frozen_manifest_sha256=frozen.frozen_manifest_sha256,
            paired_report_sha256=PairedEvaluationGate.digest(report),
            sealed_attestation_sha256=attestation_digest(sealed_attestation),
            approval_proof_sha256=_digest(human_approval.model_dump(mode="json")),
            approval_ticket_digest=hashlib.sha256(approval.approval_ticket_id.encode()).hexdigest(),
            authorized_at=authorized_at,
            expires_at=authorized_at + self._lifetime,
        )
        signature = Ed25519PrivateKey.from_private_bytes(self._key.private_key_seed).sign(
            _canonical(self._key.key_id, payload)
        )
        return SkillActivationAuthorization(
            key_id=self._key.key_id,
            payload=payload,
            signature=signature.hex(),
        )


def _proposal_uuid(proposal_id: str) -> uuid.UUID:
    prefix = "skill-proposal-"
    if not proposal_id.startswith(prefix):
        raise CandidateControlError("EVOLUTION_SKILL_PROPOSAL_ID_INVALID")
    try:
        return uuid.UUID(hex=proposal_id.removeprefix(prefix))
    except ValueError as error:
        raise CandidateControlError("EVOLUTION_SKILL_PROPOSAL_ID_INVALID") from error


def _canonical(
    key_id: str,
    payload: SkillActivationAuthorizationPayload,
) -> bytes:
    return json.dumps(
        {
            "domain": _DOMAIN,
            "key_id": key_id,
            "payload": payload.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
