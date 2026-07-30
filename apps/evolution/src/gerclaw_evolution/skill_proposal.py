"""Decrypt and freeze content-addressed custom Skill proposals."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from gerclaw_api.modules.agent_harness.evolution_governance import (
    CandidateChange,
    CandidateProposal,
)
from gerclaw_api.modules.skill.models import SkillDefinition
from gerclaw_api.modules.skill.offline_contracts import (
    SkillProposalBundle,
    SkillProposalExportEnvelope,
)

from gerclaw_evolution.candidate import CandidateFreezer
from gerclaw_evolution.contracts import (
    CandidateControlError,
    FrozenCandidate,
    FrozenRepositoryChange,
)

_AAD_DOMAIN = b"gerclaw.skill-proposal-export.v1"


@dataclass(frozen=True, slots=True)
class SkillExportVerificationKey:
    key_id: str
    public_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.public_key) != 32:
            raise CandidateControlError("EVOLUTION_SKILL_EXPORT_KEY_INVALID")


@dataclass(frozen=True, slots=True)
class SkillExportRecipientPrivateKey:
    key_id: str
    private_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.private_key) != 32:
            raise CandidateControlError("EVOLUTION_SKILL_RECIPIENT_KEY_INVALID")


@dataclass(frozen=True, slots=True)
class FrozenSkillCandidate:
    """Public frozen identity plus protected base/candidate snapshots."""

    frozen: FrozenCandidate
    base_snapshot: SkillDefinition = field(repr=False)
    candidate_snapshot: SkillDefinition = field(repr=False)
    opaque_owner_binding: str = field(repr=False)


class SkillProposalEnvelopeOpener:
    """Verify the API exporter and freeze a decrypted Skill candidate in memory."""

    def __init__(
        self,
        *,
        exporter_key: SkillExportVerificationKey,
        recipient_key: SkillExportRecipientPrivateKey,
        freezer: CandidateFreezer | None = None,
    ) -> None:
        self._exporter_key = exporter_key
        self._recipient_key = recipient_key
        self._freezer = freezer or CandidateFreezer()

    def open(self, envelope: SkillProposalExportEnvelope) -> FrozenSkillCandidate:
        if (
            envelope.exporter_key_id != self._exporter_key.key_id
            or envelope.recipient_key_id != self._recipient_key.key_id
        ):
            raise CandidateControlError("EVOLUTION_SKILL_EXPORT_KEY_MISMATCH")
        unsigned = envelope.model_dump(mode="json", exclude={"exporter_signature"})
        try:
            Ed25519PublicKey.from_public_bytes(self._exporter_key.public_key).verify(
                bytes.fromhex(envelope.exporter_signature),
                _canonical_json(unsigned).encode(),
            )
        except (InvalidSignature, ValueError) as error:
            raise CandidateControlError("EVOLUTION_SKILL_EXPORT_SIGNATURE_INVALID") from error
        try:
            ciphertext = base64.urlsafe_b64decode(envelope.ciphertext.encode())
        except ValueError as error:
            raise CandidateControlError("EVOLUTION_SKILL_EXPORT_CIPHERTEXT_INVALID") from error
        if not hmac.compare_digest(
            hashlib.sha256(ciphertext).hexdigest(),
            envelope.encrypted_payload_sha256,
        ):
            raise CandidateControlError("EVOLUTION_SKILL_EXPORT_DIGEST_MISMATCH")
        aad = _canonical_json(
            {
                "domain": _AAD_DOMAIN.decode(),
                "exporter_key_id": envelope.exporter_key_id,
                "recipient_key_id": envelope.recipient_key_id,
                "ephemeral_public_key": envelope.ephemeral_public_key,
            }
        ).encode()
        try:
            shared_secret = X25519PrivateKey.from_private_bytes(
                self._recipient_key.private_key
            ).exchange(
                X25519PublicKey.from_public_bytes(bytes.fromhex(envelope.ephemeral_public_key))
            )
            key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=bytes.fromhex(envelope.nonce),
                info=_AAD_DOMAIN,
            ).derive(shared_secret)
            plaintext = AESGCM(key).decrypt(
                bytes.fromhex(envelope.nonce),
                ciphertext,
                aad,
            )
            bundle = SkillProposalBundle.model_validate_json(plaintext)
        except (InvalidTag, ValueError) as error:
            raise CandidateControlError("EVOLUTION_SKILL_EXPORT_DECRYPT_FAILED") from error
        if bundle.governance_manifest_sha256 != self._freezer.governance_digest():
            raise CandidateControlError("EVOLUTION_SKILL_GOVERNANCE_MISMATCH")
        frozen = self._freeze(bundle)
        self._freezer.assert_manifest(frozen)
        return FrozenSkillCandidate(
            frozen=frozen,
            base_snapshot=bundle.base_snapshot,
            candidate_snapshot=bundle.candidate_snapshot,
            opaque_owner_binding=bundle.opaque_owner_binding,
        )

    def _freeze(self, bundle: SkillProposalBundle) -> FrozenCandidate:
        target = (
            f"skill://{'clinical' if bundle.object_kind == 'skill.clinical' else 'tooling'}/"
            f"{bundle.opaque_owner_binding[:16]}/{bundle.proposal_id.hex}"
        )
        change = CandidateChange(
            object_kind=bundle.object_kind,
            target=target,
            content_digest=bundle.candidate_content_sha256,
        )
        proposal = CandidateProposal(
            proposal_id=f"skill-proposal-{bundle.proposal_id.hex}",
            declared_track="immutable",
            base_commit=bundle.base_content_sha256,
            candidate_commit=bundle.candidate_content_sha256,
            risk_level="high" if bundle.object_kind == "skill.clinical" else "critical",
            risk_reason_codes=("skill.immutable.review",),
            activation_condition_ids=(
                "paired.skill.v1",
                "sealed.skill.v1",
                "human.skill.v1",
            ),
            frozen_at=bundle.exported_at,
            changes=(change,),
        )
        repository_change = FrozenRepositoryChange(
            repository_path=f"database-skill-proposal/{bundle.proposal_id.hex}.encrypted",
            object_kind=change.object_kind,
            target=change.target,
            content_digest=change.content_digest,
        )
        frozen_digest = CandidateFreezer.frozen_digest(
            proposal,
            (repository_change,),
            bundle.governance_manifest_sha256,
        )
        return FrozenCandidate(
            proposal=proposal,
            repository_changes=(repository_change,),
            governance_manifest_sha256=bundle.governance_manifest_sha256,
            frozen_manifest_sha256=frozen_digest,
        )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
