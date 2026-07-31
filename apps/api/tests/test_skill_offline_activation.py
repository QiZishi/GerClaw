"""Operator-only immutable Skill activation verification tests."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import AsyncClient
from sqlalchemy import func, select

from gerclaw_api.database.models import (
    SkillDefinitionRecord,
    SkillDefinitionRevision,
    SkillEvolutionProposal,
    SkillEvolutionReviewEvent,
)
from gerclaw_api.modules.agent_harness.evolution_governance import (
    governance_manifest_digest,
)
from gerclaw_api.modules.skill.evolution_policy import SkillEvolutionPolicy
from gerclaw_api.modules.skill.loader import parse_skill_markdown
from gerclaw_api.modules.skill.models import SkillDefinition
from gerclaw_api.modules.skill.offline_activation import (
    SkillActivationVerificationKey,
    SkillOfflineActivator,
)
from gerclaw_api.modules.skill.offline_contracts import (
    SkillActivationAuthorization,
    SkillActivationAuthorizationPayload,
    SkillReviewEventAppend,
)
from gerclaw_api.modules.skill.storage_projection import skill_content_hash
from gerclaw_api.repositories.skill import SqlAlchemySkillRepository
from gerclaw_api.repositories.skill_evolution_control import (
    SkillEvolutionControlConflictError,
    SkillEvolutionControlRepository,
)

_NOW = datetime(2026, 7, 30, 12, 10, tzinfo=UTC)
_SIGNING_SEED = b"k" * 32
_ALLOWED_TOOLS = frozenset({"search_knowledge", "web_search", "search_memory"})


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _Repository:
    def __init__(
        self,
        proposal: SkillEvolutionProposal,
        record: SkillDefinitionRecord | None,
    ) -> None:
        self.proposal = proposal
        self.record = record
        self.events: list[SimpleNamespace] = []
        self.committed = False
        self.rolled_back = False

    async def get_proposal_for_update(
        self,
        proposal_id: uuid.UUID,
    ) -> SkillEvolutionProposal | None:
        return self.proposal if proposal_id == self.proposal.id else None

    async def list_events(
        self,
        _proposal_id: uuid.UUID,
    ) -> tuple[SimpleNamespace, ...]:
        return tuple(self.events)

    async def get_skill_for_update(
        self,
        _proposal: SkillEvolutionProposal,
    ) -> SkillDefinitionRecord | None:
        return self.record

    async def append_event(
        self,
        _proposal_id: uuid.UUID,
        command: SkillReviewEventAppend,
    ) -> SimpleNamespace:
        event = SimpleNamespace(
            event_type=command.event_type,
            approval_ticket_digest=command.approval_ticket_digest,
            artifact_sha256=command.artifact_sha256,
        )
        self.events.append(event)
        return event

    async def apply_candidate(
        self,
        record: SkillDefinitionRecord,
        candidate: SkillDefinition,
    ) -> SkillDefinitionRecord:
        record.version = candidate.version
        record.description = candidate.description
        record.source_markdown = candidate.source_markdown
        record.content_hash = skill_content_hash(record.source_markdown)
        record.revision = candidate.revision
        return record

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _definition(*, version: str, revision: int, instruction: str):
    source = f"""---
id: medication-followup
name: 用药复诊准备
description: 为老年患者整理需由医生复核的用药信息
version: {version}
category: followup
parameters:
  topic:
    type: string
    description: 复诊主题
    maxLength: 100
tools: []
---
# 工作流

{instruction}
""".strip()
    return parse_skill_markdown(
        source,
        source="custom",
        origin="generated",
        revision=revision,
        allowed_tools=_ALLOWED_TOOLS,
    )


def _proposal_and_record() -> tuple[SkillEvolutionProposal, SkillDefinitionRecord]:
    base = _definition(
        version="1.0.0",
        revision=1,
        instruction="整理用户已经提供的药物信息,标记为待医生复核。",
    )
    candidate = _definition(
        version="1.1.0",
        revision=2,
        instruction="整理药物名称、剂量和过敏史,标记为待医生复核。",
    )
    record_id = uuid.uuid4()
    proposal = SkillEvolutionProposal(
        id=uuid.uuid4(),
        tenant_id="tenant_private",
        actor_id="actor_private",
        trace_id="trace_private",
        request_fingerprint="f" * 64,
        skill_record_id=record_id,
        skill_id=base.skill_id,
        base_revision=1,
        candidate_revision=2,
        base_version=base.version,
        candidate_version=candidate.version,
        track="immutable",
        object_kind="skill.clinical",
        authority="clinical_guidance",
        review_state="pending_offline_review",
        reason_codes=["SKILL_CLINICAL_CONTENT"],
        change_request="encrypted",
        base_snapshot=base.model_dump(mode="json"),
        candidate_snapshot=candidate.model_dump(mode="json"),
        base_content_hash=skill_content_hash(base.source_markdown),
        candidate_content_hash=skill_content_hash(candidate.source_markdown),
    )
    record = SkillDefinitionRecord(
        id=record_id,
        tenant_id=proposal.tenant_id,
        actor_id=proposal.actor_id,
        skill_id=base.skill_id,
        name=base.name,
        name_fingerprint="a" * 64,
        description=base.description,
        version=base.version,
        category=base.category,
        origin=base.origin,
        tool_names=base.tool_names,
        source_markdown=base.source_markdown,
        content_hash=proposal.base_content_hash,
        enabled=True,
        revision=1,
    )
    return proposal, record


def _authorization(
    proposal: SkillEvolutionProposal,
    *,
    authorized_at: datetime = _NOW,
    expires_at: datetime = _NOW + timedelta(hours=1),
    governance_manifest_sha256: str | None = None,
) -> SkillActivationAuthorization:
    payload = SkillActivationAuthorizationPayload(
        proposal_id=proposal.id,
        object_kind="skill.clinical",
        base_revision=proposal.base_revision,
        candidate_revision=proposal.candidate_revision,
        base_content_sha256=proposal.base_content_hash,
        candidate_content_sha256=proposal.candidate_content_hash,
        governance_manifest_sha256=(
            governance_manifest_sha256 or governance_manifest_digest()
        ),
        frozen_manifest_sha256="1" * 64,
        paired_report_sha256="2" * 64,
        sealed_attestation_sha256="3" * 64,
        approval_proof_sha256="4" * 64,
        approval_ticket_digest="5" * 64,
        authorized_at=authorized_at,
        expires_at=expires_at,
    )
    key_id = "skill-activation-key-v1"
    message = json.dumps(
        {
            "domain": "gerclaw.skill-activation-authorization.v1",
            "key_id": key_id,
            "payload": payload.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = Ed25519PrivateKey.from_private_bytes(_SIGNING_SEED).sign(message)
    return SkillActivationAuthorization(
        key_id=key_id,
        payload=payload,
        signature=signature.hex(),
    )


def _verification_key() -> SkillActivationVerificationKey:
    public_key = (
        Ed25519PrivateKey.from_private_bytes(_SIGNING_SEED)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    return SkillActivationVerificationKey(
        key_id="skill-activation-key-v1",
        public_key=public_key,
        active=True,
    )


@pytest.mark.asyncio
async def test_activation_is_atomic_content_free_and_idempotent() -> None:
    proposal, record = _proposal_and_record()
    repository = _Repository(proposal, record)
    authorization = _authorization(proposal)
    activator = SkillOfflineActivator(
        repository,  # type: ignore[arg-type]
        verification_key=_verification_key(),
        allowed_tools=_ALLOWED_TOOLS,
        clock=_Clock(),
    )

    outcome = await activator.activate(authorization)

    assert outcome.status == "activated"
    assert outcome.revision == 2
    assert repository.committed
    assert [item.event_type for item in repository.events] == [
        "approved",
        "activated",
    ]
    assert "用药复诊准备" not in outcome.model_dump_json()

    replayed = await activator.activate(authorization)
    assert replayed.status == "already_activated"
    assert len(repository.events) == 2

    different_grant = _authorization(
        proposal,
        authorized_at=_NOW + timedelta(seconds=1),
    )
    with pytest.raises(
        SkillEvolutionControlConflictError,
        match="SKILL_PROPOSAL_ALREADY_TERMINAL",
    ):
        await activator.activate(different_grant)


@pytest.mark.asyncio
async def test_stale_record_is_not_overwritten_and_invalid_grant_rolls_back() -> None:
    proposal, record = _proposal_and_record()
    record.revision = 2
    record.content_hash = "9" * 64
    repository = _Repository(proposal, record)
    activator = SkillOfflineActivator(
        repository,  # type: ignore[arg-type]
        verification_key=_verification_key(),
        allowed_tools=_ALLOWED_TOOLS,
        clock=_Clock(),
    )

    stale = await activator.activate(_authorization(proposal))

    assert stale.status == "stale"
    assert stale.revision == 2
    assert record.revision == 2
    assert record.content_hash == "9" * 64
    assert [item.event_type for item in repository.events] == ["stale"]

    other_proposal, other_record = _proposal_and_record()
    invalid_repository = _Repository(other_proposal, other_record)
    invalid = _authorization(other_proposal).model_copy(update={"signature": "0" * 128})
    with pytest.raises(
        SkillEvolutionControlConflictError,
        match="SKILL_ACTIVATION_AUTHORIZATION_SIGNATURE_INVALID",
    ):
        await SkillOfflineActivator(
            invalid_repository,  # type: ignore[arg-type]
            verification_key=_verification_key(),
            allowed_tools=_ALLOWED_TOOLS,
            clock=_Clock(),
        ).activate(invalid)
    assert invalid_repository.rolled_back is False
    assert other_record.revision == 1


@pytest.mark.asyncio
async def test_activation_rejects_authorization_from_previous_governance_manifest() -> None:
    proposal, record = _proposal_and_record()
    repository = _Repository(proposal, record)
    stale_governance = _authorization(
        proposal,
        governance_manifest_sha256="0" * 64,
    )

    with pytest.raises(
        SkillEvolutionControlConflictError,
        match="SKILL_ACTIVATION_GOVERNANCE_MANIFEST_CHANGED",
    ):
        await SkillOfflineActivator(
            repository,  # type: ignore[arg-type]
            verification_key=_verification_key(),
            allowed_tools=_ALLOWED_TOOLS,
            clock=_Clock(),
        ).activate(stale_governance)

    assert record.revision == 1
    assert repository.events == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ten_concurrent_authorizations_apply_exactly_one_skill_revision(
    integration_client: tuple[AsyncClient, object],
) -> None:
    _client, app = integration_client
    suffix = uuid.uuid4().hex[:12]
    tenant_id = f"tenant_skill_{suffix}"
    actor_id = f"actor_skill_{suffix}"
    base = _definition(
        version="1.0.0",
        revision=1,
        instruction="整理用户已经提供的药物信息,标记为待医生复核。",
    )
    candidate = _definition(
        version="1.1.0",
        revision=2,
        instruction="整理药物名称、剂量和过敏史,标记为待医生复核。",
    )
    decision = SkillEvolutionPolicy().decide(
        base,
        candidate,
        expected_revision=1,
        apply_if_low_risk=False,
    )
    async with app.state.database.session() as session:
        skills = SqlAlchemySkillRepository(session)
        await skills.create_custom(
            base,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        proposal = await skills.create_evolution_proposal(
            base.skill_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            expected_revision=1,
            current=base,
            candidate=candidate,
            decision=decision,
            change_request="encrypted",
            trace_id="trace_skill_activation",
            request_fingerprint="a" * 64,
        )
        await skills.commit()
        proposal_id = proposal.id
    authorization = _authorization(proposal)

    async def activate_once() -> str:
        async with app.state.database.session() as session:
            outcome = await SkillOfflineActivator(
                SkillEvolutionControlRepository(session),
                verification_key=_verification_key(),
                allowed_tools=_ALLOWED_TOOLS,
                clock=_Clock(),
            ).activate(authorization)
            return outcome.status

    statuses = await asyncio.gather(*(activate_once() for _ in range(10)))

    assert statuses.count("activated") == 1
    assert statuses.count("already_activated") == 9
    async with app.state.database.session() as session:
        record = await session.scalar(
            select(SkillDefinitionRecord).where(
                SkillDefinitionRecord.tenant_id == tenant_id,
                SkillDefinitionRecord.actor_id == actor_id,
                SkillDefinitionRecord.skill_id == base.skill_id,
            )
        )
        assert record is not None
        assert record.revision == 2
        assert record.source_markdown == candidate.source_markdown
        revision_count = await session.scalar(
            select(func.count(SkillDefinitionRevision.id)).where(
                SkillDefinitionRevision.skill_definition_id == record.id
            )
        )
        events = tuple(
            await session.scalars(
                select(SkillEvolutionReviewEvent)
                .where(SkillEvolutionReviewEvent.proposal_id == proposal_id)
                .order_by(SkillEvolutionReviewEvent.sequence)
            )
        )
    assert revision_count == 1
    assert [event.event_type for event in events] == ["approved", "activated"]
