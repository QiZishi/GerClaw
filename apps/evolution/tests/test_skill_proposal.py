"""Encrypted custom Skill handoff and content-addressed freeze tests."""

# ruff: noqa: RUF001 -- Chinese fixtures intentionally use CJK punctuation.

from __future__ import annotations

import asyncio
import hashlib
import uuid
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from gerclaw_api.database.models import (
    SkillDefinitionRecord,
    SkillEvolutionProposal,
)
from gerclaw_api.modules.skill.models import SkillDefinition
from gerclaw_api.modules.skill.offline_bridge import (
    SkillProposalExporter,
    SkillProposalExporterKey,
    SkillProposalRecipientKey,
)

from gerclaw_evolution.contracts import CandidateControlError
from gerclaw_evolution.skill_proposal import (
    SkillExportRecipientPrivateKey,
    SkillExportVerificationKey,
    SkillProposalEnvelopeOpener,
)


class _ControlRepository:
    def __init__(
        self,
        proposal: SkillEvolutionProposal,
        record: SkillDefinitionRecord,
    ) -> None:
        self.proposal = proposal
        self.record = record
        self.events: list[object] = []

    async def get_proposal_for_update(self, proposal_id: uuid.UUID) -> SkillEvolutionProposal:
        assert proposal_id == self.proposal.id
        return self.proposal

    async def get_skill_for_update(
        self,
        proposal: SkillEvolutionProposal,
    ) -> SkillDefinitionRecord:
        assert proposal is self.proposal
        return self.record

    async def append_event(self, _proposal_id: uuid.UUID, command: object) -> object:
        self.events.append(command)
        return SimpleNamespace(sequence=len(self.events))


def _definition(*, version: str, revision: int, instruction: str) -> SkillDefinition:
    markdown = f"""---
id: medication-followup
name: 用药复诊准备
description: 为老年患者整理需由医生复核的用药复诊信息
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
"""
    return SkillDefinition(
        skill_id="medication-followup",
        name="用药复诊准备",
        description="为老年患者整理需由医生复核的用药复诊信息",
        version=version,
        parameter_schema={
            "topic": {
                "type": "string",
                "description": "复诊主题",
                "maxLength": 100,
            }
        },
        tool_names=[],
        category="followup",
        source="custom",
        origin="generated",
        enabled=True,
        revision=revision,
        source_markdown=markdown,
    )


def test_encrypted_skill_proposal_opens_to_content_addressed_frozen_candidate() -> None:
    base = _definition(
        version="1.0.0",
        revision=1,
        instruction="整理用户已提供的用药信息，标记为待医生复核。",
    )
    candidate = _definition(
        version="1.1.0",
        revision=2,
        instruction="整理药物名称、剂量与过敏史，并标记为待医生复核。",
    )
    base_hash = hashlib.sha256(base.source_markdown.encode()).hexdigest()
    candidate_hash = hashlib.sha256(candidate.source_markdown.encode()).hexdigest()
    record_id = uuid.uuid4()
    proposal = SkillEvolutionProposal(
        id=uuid.uuid4(),
        tenant_id="tenant_private",
        actor_id="actor_private",
        trace_id="trace_skill_export",
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
        base_content_hash=base_hash,
        candidate_content_hash=candidate_hash,
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
        tool_names=[],
        source_markdown=base.source_markdown,
        content_hash=base_hash,
        enabled=True,
        revision=1,
    )
    repository = _ControlRepository(proposal, record)
    recipient_private = X25519PrivateKey.generate()
    recipient_private_bytes = recipient_private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    recipient_public_bytes = recipient_private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signing_seed = b"s" * 32
    signing_public = (
        Ed25519PrivateKey.from_private_bytes(signing_seed)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    envelope = asyncio.run(
        SkillProposalExporter(
            repository,  # type: ignore[arg-type]
            exporter_key=SkillProposalExporterKey(
                key_id="api.skill-export",
                private_key_seed=signing_seed,
            ),
            owner_binding_secret=b"owner-binding-secret-for-tests-0001",
            allowed_tools=frozenset(),
        ).export(
            proposal.id,
            recipient=SkillProposalRecipientKey(
                key_id="controller.skill-review",
                public_key=recipient_public_bytes,
            ),
        )
    )

    frozen = SkillProposalEnvelopeOpener(
        exporter_key=SkillExportVerificationKey(
            key_id="api.skill-export",
            public_key=signing_public,
        ),
        recipient_key=SkillExportRecipientPrivateKey(
            key_id="controller.skill-review",
            private_key=recipient_private_bytes,
        ),
    ).open(envelope)

    assert frozen.frozen.proposal.base_commit == base_hash
    assert frozen.frozen.proposal.candidate_commit == candidate_hash
    assert frozen.frozen.proposal.changes[0].object_kind == "skill.clinical"
    assert frozen.candidate_snapshot.source_markdown == candidate.source_markdown
    assert "tenant_private" not in envelope.model_dump_json()
    assert "actor_private" not in envelope.model_dump_json()
    assert len(repository.events) == 1

    tampered = envelope.model_copy(update={"exporter_signature": "0" * 128})
    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_SKILL_EXPORT_SIGNATURE_INVALID",
    ):
        SkillProposalEnvelopeOpener(
            exporter_key=SkillExportVerificationKey(
                key_id="api.skill-export",
                public_key=signing_public,
            ),
            recipient_key=SkillExportRecipientPrivateKey(
                key_id="controller.skill-review",
                private_key=recipient_private_bytes,
            ),
        ).open(tampered)
