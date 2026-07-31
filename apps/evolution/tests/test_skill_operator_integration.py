"""Real PostgreSQL + Docker audit loop for clinical and tooling Skill proposals."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from gerclaw_api.database.models import (
    SkillDefinitionRecord,
    SkillEvolutionProposal,
    SkillEvolutionReviewEvent,
)
from gerclaw_api.encryption import configure_field_encryption
from gerclaw_api.modules.skill.evolution_policy import SkillEvolutionPolicy
from gerclaw_api.modules.skill.loader import parse_skill_markdown
from gerclaw_api.modules.skill.models import SkillDefinition
from gerclaw_api.repositories.skill import SqlAlchemySkillRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_human_approval import _Clock
from test_skill_runner import _evaluator_repository

from gerclaw_evolution.approval import (
    ApprovalSigningKeyRecord,
    HumanApprovalSigner,
)
from gerclaw_evolution.attestation import (
    AttestationKeyRecord,
    AttestationKeyring,
    SealedEvaluatorProfile,
)
from gerclaw_evolution.cli import main
from gerclaw_evolution.evaluation import CharterObservation
from gerclaw_evolution.skill_operator import PreparedSkillReviewPackage
from gerclaw_evolution.skill_proposal import (
    SkillExportRecipientPrivateKey,
    SkillExportVerificationKey,
    SkillProposalEnvelopeOpener,
)
from gerclaw_evolution.skill_sealed_evaluator import (
    SealedSkillCaseBatch,
    SealedSkillGatePolicy,
    SkillSealedEvaluator,
)

_RUN_REAL = os.getenv("GERCLAW_RUN_SKILL_OPERATOR_INTEGRATION") == "1"
_DATABASE_URL = os.getenv(
    "GERCLAW_EVOLUTION_TEST_DATABASE_URL",
    "postgresql+asyncpg://gerclaw:local-postgres-only@127.0.0.1:5432/gerclaw_test",
)
_IMAGE_ID = "sha256:7d3da6a92589797a796a389c79cbbaa4622581ce397f0ee10d5c4741f21207f7"
_ALLOWED_TOOLS = frozenset({"search_knowledge", "web_search", "search_memory"})
_CASE_SET_DIGEST = "6" * 64


class _SecretRunner:
    def __init__(self, *, candidate_passes: bool, evaluated_at: datetime) -> None:
        self._candidate_passes = candidate_passes
        self._evaluated_at = evaluated_at

    def run(
        self,
        definition: SkillDefinition,
        *,
        role: str,
    ) -> SealedSkillCaseBatch:
        passed = role == "baseline" or self._candidate_passes
        charters = (
            CharterObservation(
                evaluator_id="charter.plugin_runtime.v1",
                passed=passed,
            ),
            CharterObservation(
                evaluator_id="charter.skill.v1",
                passed=passed,
            ),
        )
        return SealedSkillCaseBatch.model_validate(
            {
                "role": role,
                "candidate_identity": hashlib.sha256(
                    definition.source_markdown.encode()
                ).hexdigest(),
                "case_set_sha256": _CASE_SET_DIGEST,
                "evaluated_at": self._evaluated_at,
                "cases": [
                    {
                        "case_id": f"case_{index:032x}",
                        "slice": slice_name,
                        "passed": passed,
                        "quality_micros": 900_000 if passed else 0,
                        "token_count": 100,
                        "latency_ms": 10,
                        "runtime_activated": True,
                        "charters": [item.model_dump(mode="json") for item in charters],
                    }
                    for index, slice_name in enumerate(
                        ("normal", "complex", "high_risk", "elderly"),
                        start=1,
                    )
                ],
            }
        )


def _definition(
    skill_id: str,
    *,
    version: str,
    revision: int,
    tools: tuple[str, ...],
    instruction: str,
) -> SkillDefinition:
    rendered_tools = (
        "tools:\n" + "\n".join(f"  - {tool}" for tool in tools) if tools else "tools: []"
    )
    markdown = f"""---
id: {skill_id}
name: 老年复诊资料准备
description: 为老年患者整理需要由医生复核的临床用药资料
version: {version}
category: followup
parameters:
  topic:
    type: string
    description: 复诊主题
    maxLength: 100
{rendered_tools}
---
# 工作流

{instruction}
""".strip()
    return parse_skill_markdown(
        markdown,
        source="custom",
        origin="generated",
        revision=revision,
        allowed_tools=_ALLOWED_TOOLS,
    )


async def _create_proposal(
    *,
    skill_id: str,
    tooling: bool,
) -> uuid.UUID:
    base = _definition(
        skill_id,
        version="1.0.0",
        revision=1,
        tools=(),
        instruction="整理用户提供的药物、剂量和过敏史,全部标记为待医生复核。",
    )
    candidate = _definition(
        skill_id,
        version="1.1.0",
        revision=2,
        tools=("search_knowledge",) if tooling else (),
        instruction=(
            "先调用本地知识检索工具,再整理用户提供的药物资料并标记为待医生复核。"
            if tooling
            else "补充整理症状时间线、药物剂量和过敏史,全部标记为待医生复核。"
        ),
    )
    decision = SkillEvolutionPolicy().decide(
        base,
        candidate,
        expected_revision=1,
        apply_if_low_risk=False,
    )
    expected_kind = "skill.tooling" if tooling else "skill.clinical"
    assert decision.object_kind == expected_kind
    suffix = uuid.uuid4().hex[:12]
    engine = create_async_engine(_DATABASE_URL, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            repository = SqlAlchemySkillRepository(session)
            await repository.create_custom(
                base,
                tenant_id=f"tenant_operator_{suffix}",
                actor_id=f"actor_operator_{suffix}",
            )
            proposal = await repository.create_evolution_proposal(
                skill_id,
                tenant_id=f"tenant_operator_{suffix}",
                actor_id=f"actor_operator_{suffix}",
                expected_revision=1,
                current=base,
                candidate=candidate,
                decision=decision,
                change_request="operator integration candidate",
                trace_id=f"trace_operator_{suffix}",
                request_fingerprint=hashlib.sha256(suffix.encode()).hexdigest(),
            )
            await repository.commit()
            return proposal.id
    finally:
        await engine.dispose()


def _write_secret(root: Path, name: str, value: bytes) -> Path:
    path = root / name
    path.write_bytes(value)
    path.chmod(0o600)
    return path


def _operator_environment(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, bytes]:
    root.mkdir(parents=True, exist_ok=True)
    exporter_seed = b"e" * 32
    exporter_public = (
        Ed25519PrivateKey.from_private_bytes(exporter_seed)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    recipient_seed = b"r" * 32
    activation_seed = b"z" * 32
    activation_public = (
        Ed25519PrivateKey.from_private_bytes(activation_seed)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    approval_seed = b"a" * 32
    approval_key = ApprovalSigningKeyRecord(
        key_id="skill-approval-key-v1",
        private_key_seed=approval_seed,
        approver_principal_id="approver.clinical-lead",
        allowed_tracks=frozenset({"immutable"}),
        promotion_active=True,
    )
    secret_values = {
        "exporter_private": exporter_seed,
        "exporter_public": exporter_public,
        "recipient_private": recipient_seed,
        "owner_binding": b"o" * 32,
        "case_identity": b"c" * 32,
        "attestation": b"s" * 32,
        "approval_public": approval_key.verification_record().public_key,
        "activation_private": activation_seed,
        "activation_public": activation_public,
    }
    paths = {name: _write_secret(root, name, value) for name, value in secret_values.items()}
    values = {
        "GERCLAW_EVOLUTION_DATABASE_URL": _DATABASE_URL,
        "GERCLAW_EVOLUTION_EXPORTER_KEY_ID": "api.skill-export",
        "GERCLAW_EVOLUTION_RECIPIENT_KEY_ID": "controller.skill-review",
        "GERCLAW_EVOLUTION_ACTIVATION_KEY_ID": "skill-activation-key-v1",
        "GERCLAW_EVOLUTION_DOCKER_IMAGE_ID": _IMAGE_ID,
        "GERCLAW_EVOLUTION_ALLOWED_TOOLS": ",".join(sorted(_ALLOWED_TOOLS)),
        "GERCLAW_EVOLUTION_EXPORTER_PRIVATE_KEY_FILE": str(paths["exporter_private"]),
        "GERCLAW_EVOLUTION_EXPORTER_PUBLIC_KEY_FILE": str(paths["exporter_public"]),
        "GERCLAW_EVOLUTION_RECIPIENT_PRIVATE_KEY_FILE": str(paths["recipient_private"]),
        "GERCLAW_EVOLUTION_OWNER_BINDING_SECRET_FILE": str(paths["owner_binding"]),
        "GERCLAW_EVOLUTION_CASE_IDENTITY_SECRET_FILE": str(paths["case_identity"]),
        "GERCLAW_EVOLUTION_ATTESTATION_KEY_ID": "sealed-skill-key-v1",
        "GERCLAW_EVOLUTION_ATTESTATION_SECRET_FILE": str(paths["attestation"]),
        "GERCLAW_EVOLUTION_APPROVAL_KEY_ID": approval_key.key_id,
        "GERCLAW_EVOLUTION_APPROVAL_PUBLIC_KEY_FILE": str(paths["approval_public"]),
        "GERCLAW_EVOLUTION_APPROVER_PRINCIPAL_ID": (approval_key.approver_principal_id),
        "GERCLAW_EVOLUTION_ACTIVATION_PRIVATE_KEY_FILE": str(paths["activation_private"]),
        "GERCLAW_EVOLUTION_ACTIVATION_PUBLIC_KEY_FILE": str(paths["activation_public"]),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return {
        **secret_values,
        "approval_seed": approval_seed,
        "recipient_seed": recipient_seed,
        "exporter_public": exporter_public,
    }


def _sealed_artifacts(
    root: Path,
    package: PreparedSkillReviewPackage,
    *,
    secrets: dict[str, bytes],
    candidate_passes: bool,
) -> tuple[Path, Path, Path]:
    candidate = SkillProposalEnvelopeOpener(
        exporter_key=SkillExportVerificationKey(
            key_id="api.skill-export",
            public_key=secrets["exporter_public"],
        ),
        recipient_key=SkillExportRecipientPrivateKey(
            key_id="controller.skill-review",
            private_key=secrets["recipient_seed"],
        ),
    ).open(package.envelope)
    now = datetime.now(UTC)
    policy = SealedSkillGatePolicy(
        max_tokens_per_case=1_000,
        max_token_increase_per_case=100,
        max_latency_ms_per_case=1_000,
        max_latency_increase_ms_per_case=100,
    )
    profile = SealedEvaluatorProfile(
        public_runner_id=package.paired_report.baseline.runner_id,
        public_runner_version=package.paired_report.baseline.runner_version,
        public_evaluation_profile_sha256=(package.paired_report.baseline.evaluation_profile_sha256),
        evaluator_id="sealed.skill-medical-v1",
        evaluator_version="sealed-skill-v1",
        sealed_case_set_sha256=_CASE_SET_DIGEST,
        gate_policy_manifest_sha256=policy.digest(),
    )
    keyring = AttestationKeyring(
        (
            AttestationKeyRecord(
                key_id="sealed-skill-key-v1",
                secret=secrets["attestation"],
                profile=profile,
                promotion_active=True,
            ),
        )
    )
    evaluator = SkillSealedEvaluator(
        runner=_SecretRunner(
            candidate_passes=candidate_passes,
            evaluated_at=now,
        ),  # type: ignore[arg-type]
        keyring=keyring,
        key_id="sealed-skill-key-v1",
        profile=profile,
        policy=policy,
        clock=_Clock(now),
    )
    attestation = evaluator.attest(
        candidate,
        report=package.paired_report,
    )
    passing_attestation = (
        attestation
        if candidate_passes
        else SkillSealedEvaluator(
            runner=_SecretRunner(
                candidate_passes=True,
                evaluated_at=now,
            ),  # type: ignore[arg-type]
            keyring=keyring,
            key_id="sealed-skill-key-v1",
            profile=profile,
            policy=policy,
            clock=_Clock(now),
        ).attest(candidate, report=package.paired_report)
    )
    approval_key = ApprovalSigningKeyRecord(
        key_id="skill-approval-key-v1",
        private_key_seed=secrets["approval_seed"],
        approver_principal_id="approver.clinical-lead",
        allowed_tracks=frozenset({"immutable"}),
        promotion_active=True,
    )
    approval = HumanApprovalSigner(
        (approval_key,),
        attestation_verifier=keyring,
        clock=_Clock(now),
    ).approve(
        approval_key.key_id,
        frozen=candidate.frozen,
        report=package.paired_report,
        sealed_attestation=passing_attestation,
        approval_ticket_id=f"ticket.{candidate.frozen.proposal.proposal_id[-12:]}",
    )
    profile_path = root / f"{candidate.frozen.proposal.proposal_id}.profile.json"
    attestation_path = root / (f"{candidate.frozen.proposal.proposal_id}.attestation.json")
    approval_path = root / f"{candidate.frozen.proposal.proposal_id}.approval.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")
    attestation_path.write_text(attestation.model_dump_json(), encoding="utf-8")
    approval_path.write_text(approval.model_dump_json(), encoding="utf-8")
    return profile_path, attestation_path, approval_path


async def _stored_state(proposal_id: uuid.UUID) -> tuple[int, tuple[str, ...]]:
    engine = create_async_engine(_DATABASE_URL, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            event_rows = tuple(
                await session.scalars(
                    select(SkillEvolutionReviewEvent)
                    .where(SkillEvolutionReviewEvent.proposal_id == proposal_id)
                    .order_by(SkillEvolutionReviewEvent.sequence)
                )
            )
            proposal = await session.get(SkillEvolutionProposal, proposal_id)
            assert proposal is not None
            record = await session.get(
                SkillDefinitionRecord,
                proposal.skill_record_id,
            )
            assert record is not None
            return record.revision, tuple(item.event_type for item in event_rows)
    finally:
        await engine.dispose()


@pytest.mark.skipif(
    not _RUN_REAL,
    reason="set GERCLAW_RUN_SKILL_OPERATOR_INTEGRATION=1 for PostgreSQL + Docker",
)
def test_operator_cli_promotes_clinical_and_rejects_tooling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_field_encryption(
        key_id="operator-integration-v1",
        key_base64=base64.b64encode(b"d" * 32).decode(),
    )
    evaluator_root = tmp_path / "evaluator"
    evaluator_root.mkdir()
    evaluator_repository = _evaluator_repository(evaluator_root)
    evaluator_commit = evaluator_repository.head()
    secrets = _operator_environment(tmp_path / "secrets", monkeypatch)

    for tooling, candidate_passes in ((False, True), (True, False)):
        proposal_id = asyncio.run(
            _create_proposal(
                skill_id=f"operator-{uuid.uuid4().hex[:16]}",
                tooling=tooling,
            )
        )
        assert (
            main(
                (
                    "skill-pair",
                    "--proposal-id",
                    str(proposal_id),
                    "--evaluator-repository",
                    str(evaluator_repository.root),
                    "--evaluator-commit",
                    evaluator_commit,
                )
            )
            == 0
        )
        package = PreparedSkillReviewPackage.model_validate_json(capsys.readouterr().out)
        package_path = tmp_path / f"{proposal_id}.package.json"
        package_path.write_text(package.model_dump_json(), encoding="utf-8")
        profile_path, attestation_path, approval_path = _sealed_artifacts(
            tmp_path,
            package,
            secrets=secrets,
            candidate_passes=candidate_passes,
        )
        result = main(
            (
                "skill-activate",
                "--package",
                str(package_path),
                "--sealed-attestation",
                str(attestation_path),
                "--human-approval",
                str(approval_path),
                "--sealed-profile",
                str(profile_path),
                "--evaluator-repository",
                str(evaluator_repository.root),
                "--evaluator-commit",
                evaluator_commit,
            )
        )
        output = capsys.readouterr()
        if candidate_passes:
            assert result == 0
            assert json.loads(output.out)["status"] == "activated"
            assert asyncio.run(_stored_state(proposal_id)) == (
                2,
                ("exported", "approved", "activated"),
            )
        else:
            assert result == 2
            assert json.loads(output.err)["reason_code"] == "EVOLUTION_EVALUATION_GATE_REJECTED"
            assert asyncio.run(_stored_state(proposal_id)) == (
                1,
                ("exported", "sealed_rejected"),
            )
