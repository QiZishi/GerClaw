"""Operator-only verification and atomic activation for reviewed immutable Skills."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.database.models import (
    SkillDefinitionRecord,
    SkillEvolutionProposal,
)
from gerclaw_api.modules.agent_harness.evolution_governance import (
    governance_manifest_digest,
)
from gerclaw_api.modules.skill.evolution_policy import SkillEvolutionPolicy
from gerclaw_api.modules.skill.loader import parse_skill_markdown
from gerclaw_api.modules.skill.models import SkillDefinition
from gerclaw_api.modules.skill.offline_contracts import (
    TERMINAL_SKILL_REVIEW_EVENTS,
    SkillActivationAuthorization,
    SkillActivationAuthorizationPayload,
    SkillReviewEventAppend,
)
from gerclaw_api.modules.skill.storage_projection import skill_content_hash
from gerclaw_api.repositories.skill_evolution_control import (
    SkillEvolutionControlConflictError,
    SkillEvolutionControlRepository,
)

_DOMAIN = "gerclaw.skill-activation-authorization.v1"


@dataclass(frozen=True, slots=True)
class SkillActivationVerificationKey:
    key_id: str
    public_key: bytes = field(repr=False)
    active: bool

    def __post_init__(self) -> None:
        if len(self.public_key) != 32 or not self.key_id:
            raise ValueError("activation verification key is invalid")


class SkillActivationClock(Protocol):
    def now(self) -> datetime: ...


class SystemSkillActivationClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SkillActivationOutcome(BaseModel):
    """Content-free operator result; Skill content never enters logs or public APIs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["activated", "already_activated", "stale"]
    proposal_id: str
    revision: int = Field(ge=1)
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SkillOfflineActivator:
    """Verify a short-lived grant and mutate the exact locked owner record."""

    def __init__(
        self,
        repository: SkillEvolutionControlRepository,
        *,
        verification_key: SkillActivationVerificationKey,
        allowed_tools: frozenset[str],
        clock: SkillActivationClock | None = None,
        max_future_skew: timedelta = timedelta(minutes=2),
    ) -> None:
        self._repository = repository
        self._verification_key = verification_key
        self._allowed_tools = allowed_tools
        self._clock = clock or SystemSkillActivationClock()
        self._max_future_skew = max_future_skew

    async def activate(
        self,
        authorization: SkillActivationAuthorization,
    ) -> SkillActivationOutcome:
        payload = self._verify_authorization(authorization)
        artifact_sha256 = _digest(authorization.model_dump(mode="json"))
        try:
            proposal = await self._repository.get_proposal_for_update(payload.proposal_id)
            if proposal is None:
                raise SkillEvolutionControlConflictError("SKILL_PROPOSAL_NOT_FOUND")
            events = await self._repository.list_events(proposal.id)
            terminal = next(
                (event for event in events if event.event_type in TERMINAL_SKILL_REVIEW_EVENTS),
                None,
            )
            if terminal is not None:
                if (
                    terminal.event_type == "activated"
                    and terminal.approval_ticket_digest == payload.approval_ticket_digest
                    and terminal.artifact_sha256 is not None
                    and hmac.compare_digest(
                        terminal.artifact_sha256,
                        artifact_sha256,
                    )
                ):
                    return SkillActivationOutcome(
                        status="already_activated",
                        proposal_id=str(proposal.id),
                        revision=proposal.candidate_revision,
                        artifact_sha256=artifact_sha256,
                    )
                raise SkillEvolutionControlConflictError("SKILL_PROPOSAL_ALREADY_TERMINAL")
            self._validate_proposal_identity(proposal, payload)
            record = await self._repository.get_skill_for_update(proposal)
            if record is None or self._record_is_stale(record, proposal):
                await self._repository.append_event(
                    proposal.id,
                    SkillReviewEventAppend(
                        event_type="stale",
                        artifact_sha256=artifact_sha256,
                        reason_codes=("SKILL_BASE_REVISION_STALE",),
                    ),
                )
                await self._repository.commit()
                return SkillActivationOutcome(
                    status="stale",
                    proposal_id=str(proposal.id),
                    revision=(
                        record.revision
                        if record is not None
                        else proposal.base_revision
                    ),
                    artifact_sha256=artifact_sha256,
                )
            candidate = self._validated_candidate(proposal)
            await self._repository.append_event(
                proposal.id,
                SkillReviewEventAppend(
                    event_type="approved",
                    artifact_sha256=payload.approval_proof_sha256,
                ),
            )
            updated = await self._repository.apply_candidate(record, candidate)
            await self._repository.append_event(
                proposal.id,
                SkillReviewEventAppend(
                    event_type="activated",
                    artifact_sha256=artifact_sha256,
                    approval_ticket_digest=payload.approval_ticket_digest,
                ),
            )
            await self._repository.commit()
            return SkillActivationOutcome(
                status="activated",
                proposal_id=str(proposal.id),
                revision=updated.revision,
                artifact_sha256=artifact_sha256,
            )
        except Exception:
            await self._repository.rollback()
            raise

    def _verify_authorization(
        self,
        authorization: SkillActivationAuthorization,
    ) -> SkillActivationAuthorizationPayload:
        if (
            not self._verification_key.active
            or authorization.key_id != self._verification_key.key_id
        ):
            raise SkillEvolutionControlConflictError("SKILL_ACTIVATION_AUTHORIZATION_KEY_INVALID")
        try:
            Ed25519PublicKey.from_public_bytes(self._verification_key.public_key).verify(
                bytes.fromhex(authorization.signature),
                _canonical(authorization.key_id, authorization.payload),
            )
        except (InvalidSignature, ValueError) as error:
            raise SkillEvolutionControlConflictError(
                "SKILL_ACTIVATION_AUTHORIZATION_SIGNATURE_INVALID"
            ) from error
        if not hmac.compare_digest(
            authorization.payload.governance_manifest_sha256,
            governance_manifest_digest(),
        ):
            raise SkillEvolutionControlConflictError(
                "SKILL_ACTIVATION_GOVERNANCE_MANIFEST_CHANGED"
            )
        now = self._clock.now()
        if now.tzinfo is None:
            raise SkillEvolutionControlConflictError("SKILL_ACTIVATION_CLOCK_INVALID")
        if (
            authorization.payload.authorized_at > now + self._max_future_skew
            or now >= authorization.payload.expires_at
            or authorization.payload.expires_at - authorization.payload.authorized_at
            > timedelta(days=1)
        ):
            raise SkillEvolutionControlConflictError("SKILL_ACTIVATION_AUTHORIZATION_EXPIRED")
        return authorization.payload

    @staticmethod
    def _validate_proposal_identity(
        proposal: SkillEvolutionProposal,
        payload: SkillActivationAuthorizationPayload,
    ) -> None:
        if (
            proposal.id != payload.proposal_id
            or proposal.object_kind != payload.object_kind
            or proposal.base_revision != payload.base_revision
            or proposal.candidate_revision != payload.candidate_revision
            or proposal.base_content_hash != payload.base_content_sha256
            or proposal.candidate_content_hash != payload.candidate_content_sha256
            or proposal.track != "immutable"
            or proposal.review_state != "pending_offline_review"
        ):
            raise SkillEvolutionControlConflictError("SKILL_ACTIVATION_PROPOSAL_IDENTITY_MISMATCH")

    @staticmethod
    def _record_is_stale(
        record: SkillDefinitionRecord,
        proposal: SkillEvolutionProposal,
    ) -> bool:
        return (
            record.id != proposal.skill_record_id
            or record.revision != proposal.base_revision
            or not hmac.compare_digest(
                record.content_hash,
                proposal.base_content_hash,
            )
        )

    def _validated_candidate(
        self,
        proposal: SkillEvolutionProposal,
    ) -> SkillDefinition:
        base = SkillDefinition.model_validate(proposal.base_snapshot)
        candidate = SkillDefinition.model_validate(proposal.candidate_snapshot)
        parsed = parse_skill_markdown(
            candidate.source_markdown,
            source=candidate.source,
            origin=candidate.origin,
            enabled=candidate.enabled,
            revision=candidate.revision,
            allowed_tools=self._allowed_tools,
        )
        excluded = {"created_at", "updated_at"}
        decision = SkillEvolutionPolicy().decide(
            base,
            candidate,
            expected_revision=proposal.base_revision,
            apply_if_low_risk=False,
        )
        if (
            parsed.model_dump(mode="json", exclude=excluded)
            != candidate.model_dump(mode="json", exclude=excluded)
            or skill_content_hash(base.source_markdown) != proposal.base_content_hash
            or skill_content_hash(candidate.source_markdown) != proposal.candidate_content_hash
            or candidate.revision != proposal.candidate_revision
            or decision.disposition != "offline_review_required"
            or decision.track != "immutable"
            or decision.object_kind != proposal.object_kind
            or decision.authority != proposal.authority
            or decision.reason_codes != tuple(proposal.reason_codes)
        ):
            raise SkillEvolutionControlConflictError("SKILL_ACTIVATION_CANDIDATE_INVALID")
        return candidate


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
