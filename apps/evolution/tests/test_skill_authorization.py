"""Offline Skill authorization binds every automated and human gate."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_human_approval import _Clock as ApprovalClock
from test_skill_runner import _candidate, _evaluator_repository, _runner

from gerclaw_evolution.approval import (
    ApprovalSigningKeyRecord,
    HumanApprovalSigner,
    HumanApprovalVerifier,
)
from gerclaw_evolution.attestation import (
    AttestationKeyRecord,
    AttestationKeyring,
    SealedEvaluatorProfile,
    SealedGatePayload,
)
from gerclaw_evolution.contracts import CandidateControlError
from gerclaw_evolution.evaluation import PairedEvaluationGate
from gerclaw_evolution.skill_authorization import (
    SkillActivationAuthorizer,
    SkillActivationSigningKey,
)

_NOW = datetime(2026, 7, 30, 12, 5, tzinfo=UTC)


def test_skill_authorization_requires_paired_sealed_and_human_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _evaluator_repository(tmp_path)
    candidate = _candidate()
    runner = _runner(repository, monkeypatch)
    baseline = runner.run(repository, candidate=candidate, role="baseline")
    evolved = runner.run(repository, candidate=candidate, role="candidate")
    report = PairedEvaluationGate().compare(candidate.frozen, baseline, evolved)
    sealed_profile = SealedEvaluatorProfile(
        public_runner_id=baseline.runner_id,
        public_runner_version=baseline.runner_version,
        public_evaluation_profile_sha256=baseline.evaluation_profile_sha256,
        evaluator_id="sealed.skill-medical-v1",
        evaluator_version="sealed-skill-v1",
        sealed_case_set_sha256="1" * 64,
        gate_policy_manifest_sha256="2" * 64,
    )
    sealed_keys = AttestationKeyring(
        (
            AttestationKeyRecord(
                key_id="sealed-skill-key-v1",
                secret=b"s" * 32,
                profile=sealed_profile,
                promotion_active=True,
            ),
        )
    )
    sealed_payload = SealedGatePayload(
        proposal_id=candidate.frozen.proposal.proposal_id,
        base_commit=candidate.frozen.proposal.base_commit,
        candidate_commit=candidate.frozen.proposal.candidate_commit,
        frozen_manifest_sha256=candidate.frozen.frozen_manifest_sha256,
        paired_report_sha256=PairedEvaluationGate.digest(report),
        sealed_case_set_sha256=sealed_profile.sealed_case_set_sha256,
        gate_policy_manifest_sha256=sealed_profile.gate_policy_manifest_sha256,
        evaluator_id=sealed_profile.evaluator_id,
        evaluator_version=sealed_profile.evaluator_version,
        evaluated_at=_NOW,
        public_report_verified=True,
        sealed_cases_passed=True,
        no_sealed_case_regressed=True,
        high_risk_singletons_non_degrading=True,
        token_budget_passed=True,
        latency_budget_passed=True,
        runtime_activation_passed=True,
        component_charters_passed=True,
        passed=True,
    )
    attestation = sealed_keys.sign(
        "sealed-skill-key-v1",
        sealed_payload,
        frozen=candidate.frozen,
        report=report,
    )
    approval_key = ApprovalSigningKeyRecord(
        key_id="skill-approval-key-v1",
        private_key_seed=b"a" * 32,
        approver_principal_id="approver.clinical-lead",
        allowed_tracks=frozenset({"immutable"}),
        promotion_active=True,
    )
    signer = HumanApprovalSigner(
        (approval_key,),
        attestation_verifier=sealed_keys,
        clock=ApprovalClock(_NOW),
    )
    verifier = HumanApprovalVerifier(
        (approval_key.verification_record(),),
        attestation_verifier=sealed_keys,
        clock=ApprovalClock(_NOW),
    )
    approval = signer.approve(
        approval_key.key_id,
        frozen=candidate.frozen,
        report=report,
        sealed_attestation=attestation,
        approval_ticket_id="ticket.skill-release-2026-07",
    )
    authorization_seed = b"z" * 32
    authorization = SkillActivationAuthorizer(
        key=SkillActivationSigningKey(
            key_id="skill-activation-key-v1",
            private_key_seed=authorization_seed,
            active=True,
        ),
        approval_verifier=verifier,
        clock=ApprovalClock(_NOW),
    ).authorize(
        candidate,
        report=report,
        sealed_attestation=attestation,
        human_approval=approval,
    )

    assert authorization.payload.proposal_id.hex in candidate.frozen.proposal.proposal_id
    assert authorization.payload.candidate_content_sha256 == evolved.commit
    assert authorization.payload.paired_report_sha256 == PairedEvaluationGate.digest(report)
    assert authorization.payload.expires_at > authorization.payload.authorized_at
    public_key = (
        Ed25519PrivateKey.from_private_bytes(authorization_seed)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    assert len(public_key) == 32
    assert "用药复诊准备" not in authorization.model_dump_json()

    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_SKILL_AUTHORIZATION_KEY_NOT_ACTIVE",
    ):
        SkillActivationAuthorizer(
            key=SkillActivationSigningKey(
                key_id="skill-activation-key-v1",
                private_key_seed=authorization_seed,
                active=False,
            ),
            approval_verifier=verifier,
            clock=ApprovalClock(_NOW),
        ).authorize(
            candidate,
            report=report,
            sealed_attestation=attestation,
            human_approval=approval,
        )
