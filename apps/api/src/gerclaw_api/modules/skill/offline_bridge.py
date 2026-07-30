"""Encrypted operator handoff for immutable Skill evolution proposals."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from gerclaw_api.database.models import (
    SkillDefinitionRecord,
    SkillEvolutionProposal,
)
from gerclaw_api.modules.agent_harness.evolution_governance.manifest import (
    COMPONENT_CHARTERS,
    OBJECT_RULES,
)
from gerclaw_api.modules.skill.evolution_policy import SkillEvolutionPolicy
from gerclaw_api.modules.skill.models import SkillDefinition
from gerclaw_api.modules.skill.offline_contracts import (
    SkillProposalBundle,
    SkillProposalExportEnvelope,
    SkillReviewEventAppend,
)
from gerclaw_api.repositories.skill_evolution_control import (
    SkillEvolutionControlConflictError,
    SkillEvolutionControlRepository,
)

_AAD_DOMAIN = b"gerclaw.skill-proposal-export.v1"


@dataclass(frozen=True, slots=True)
class SkillProposalExporterKey:
    key_id: str
    private_key_seed: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.private_key_seed) != 32:
            raise ValueError("exporter signing seed must contain 32 bytes")


@dataclass(frozen=True, slots=True)
class SkillProposalRecipientKey:
    key_id: str
    public_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.public_key) != 32:
            raise ValueError("recipient public key must contain 32 bytes")


class SkillProposalExporter:
    """Validate, encrypt, sign, and ledger one dangerous Skill candidate."""

    def __init__(
        self,
        repository: SkillEvolutionControlRepository,
        *,
        exporter_key: SkillProposalExporterKey,
        owner_binding_secret: bytes,
        allowed_tools: frozenset[str],
    ) -> None:
        if len(owner_binding_secret) < 32:
            raise ValueError("owner binding secret must contain at least 32 bytes")
        self._repository = repository
        self._exporter_key = exporter_key
        self._owner_binding_secret = owner_binding_secret
        self._allowed_tools = allowed_tools

    async def export(
        self,
        proposal_id: uuid.UUID,
        *,
        recipient: SkillProposalRecipientKey,
    ) -> SkillProposalExportEnvelope:
        proposal = await self._repository.get_proposal_for_update(proposal_id)
        if proposal is None:
            raise SkillEvolutionControlConflictError("SKILL_PROPOSAL_NOT_FOUND")
        record = await self._repository.get_skill_for_update(proposal)
        if record is None:
            raise SkillEvolutionControlConflictError("SKILL_PROPOSAL_SKILL_NOT_FOUND")
        base = SkillDefinition.model_validate(proposal.base_snapshot)
        candidate = SkillDefinition.model_validate(proposal.candidate_snapshot)
        self._validate_frozen_candidate(proposal, record, base, candidate)
        bundle = SkillProposalBundle(
            proposal_id=proposal.id,
            opaque_owner_binding=self._owner_binding(proposal),
            object_kind=proposal.object_kind,
            authority=proposal.authority,
            reason_codes=tuple(proposal.reason_codes),
            base_revision=proposal.base_revision,
            candidate_revision=proposal.candidate_revision,
            base_content_sha256=proposal.base_content_hash,
            candidate_content_sha256=proposal.candidate_content_hash,
            base_snapshot=base,
            candidate_snapshot=candidate,
            governance_manifest_sha256=_governance_manifest_digest(),
            exported_at=datetime.now(UTC),
            nonce=os.urandom(16).hex(),
        )
        envelope = self._seal(bundle, recipient=recipient)
        artifact_sha256 = hashlib.sha256(
            _canonical_json(envelope.model_dump(mode="json")).encode()
        ).hexdigest()
        await self._repository.append_event(
            proposal.id,
            SkillReviewEventAppend(
                event_type="exported",
                artifact_sha256=artifact_sha256,
            ),
        )
        return envelope

    def _validate_frozen_candidate(
        self,
        proposal: SkillEvolutionProposal,
        record: SkillDefinitionRecord,
        base: SkillDefinition,
        candidate: SkillDefinition,
    ) -> None:
        if (
            record.id != proposal.skill_record_id
            or record.revision != proposal.base_revision
            or record.content_hash != proposal.base_content_hash
            or record.skill_id != base.skill_id
            or base.skill_id != candidate.skill_id
            or base.revision != proposal.base_revision
            or candidate.revision != proposal.candidate_revision
            or _content_hash(base) != proposal.base_content_hash
            or _content_hash(candidate) != proposal.candidate_content_hash
            or _semver(candidate.version) <= _semver(base.version)
            or not set(candidate.tool_names).issubset(self._allowed_tools)
        ):
            raise SkillEvolutionControlConflictError("SKILL_PROPOSAL_IDENTITY_STALE")
        decision = SkillEvolutionPolicy().decide(
            base,
            candidate,
            expected_revision=proposal.base_revision,
            apply_if_low_risk=False,
        )
        if (
            decision.disposition != "offline_review_required"
            or decision.track != "immutable"
            or decision.object_kind != proposal.object_kind
            or decision.authority != proposal.authority
            or decision.reason_codes != tuple(proposal.reason_codes)
        ):
            raise SkillEvolutionControlConflictError("SKILL_PROPOSAL_POLICY_MISMATCH")

    def _owner_binding(self, proposal: SkillEvolutionProposal) -> str:
        value = (
            f"skill-proposal-owner-v1:{proposal.tenant_id}:{proposal.actor_id}:"
            f"{proposal.skill_record_id}:{proposal.id}"
        )
        return hmac.new(
            self._owner_binding_secret,
            value.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _seal(
        self,
        bundle: SkillProposalBundle,
        *,
        recipient: SkillProposalRecipientKey,
    ) -> SkillProposalExportEnvelope:
        ephemeral = X25519PrivateKey.generate()
        ephemeral_public = ephemeral.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        nonce = os.urandom(12)
        aad = _canonical_json(
            {
                "domain": _AAD_DOMAIN.decode(),
                "exporter_key_id": self._exporter_key.key_id,
                "recipient_key_id": recipient.key_id,
                "ephemeral_public_key": ephemeral_public.hex(),
            }
        ).encode()
        shared_secret = ephemeral.exchange(X25519PublicKey.from_public_bytes(recipient.public_key))
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=nonce,
            info=_AAD_DOMAIN,
        ).derive(shared_secret)
        ciphertext = AESGCM(key).encrypt(
            nonce,
            _canonical_json(bundle.model_dump(mode="json")).encode(),
            aad,
        )
        unsigned = {
            "schema_version": "skill-proposal-export-envelope-v1",
            "exporter_key_id": self._exporter_key.key_id,
            "recipient_key_id": recipient.key_id,
            "ephemeral_public_key": ephemeral_public.hex(),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode(),
            "nonce": nonce.hex(),
            "encrypted_payload_sha256": hashlib.sha256(ciphertext).hexdigest(),
        }
        signature = Ed25519PrivateKey.from_private_bytes(self._exporter_key.private_key_seed).sign(
            _canonical_json(unsigned).encode()
        )
        return SkillProposalExportEnvelope(
            **unsigned,
            exporter_signature=signature.hex(),
        )


def _content_hash(definition: SkillDefinition) -> str:
    return hashlib.sha256(definition.source_markdown.encode()).hexdigest()


def _semver(value: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def _governance_manifest_digest() -> str:
    payload = {
        "rules": [item.model_dump(mode="json") for item in OBJECT_RULES],
        "charters": [item.model_dump(mode="json") for item in COMPONENT_CHARTERS],
    }
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
