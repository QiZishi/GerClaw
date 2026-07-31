"""Human approval identity, authority, time, and forgery tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from test_paired_evaluation import (
    _BASE,
    _CANDIDATE,
    _CASE_HIGH_RISK,
    _frozen,
    _payload,
    _profile,
    _run,
)

from gerclaw_evolution.approval import (
    ApprovalSigningKeyRecord,
    HumanApprovalProof,
    HumanApprovalSigner,
    HumanApprovalVerifier,
)
from gerclaw_evolution.attestation import (
    AttestationKeyRecord,
    AttestationKeyring,
    SealedGateAttestation,
)
from gerclaw_evolution.contracts import CandidateControlError, FrozenCandidate
from gerclaw_evolution.evaluation import PairedEvaluationGate, PairedEvaluationReport

_NOW = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)
type ApprovalTrack = Literal["mutable", "immutable"]


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


def _artifacts() -> tuple[
    FrozenCandidate,
    PairedEvaluationReport,
    SealedGateAttestation,
    AttestationKeyring,
]:
    frozen = _frozen()
    report = PairedEvaluationGate().compare(
        frozen,
        _run("baseline", _BASE),
        _run("candidate", _CANDIDATE),
    )
    attestation_keyring = AttestationKeyring(
        (
            AttestationKeyRecord(
                key_id="sealed-key-v1",
                secret=b"s" * 32,
                profile=_profile(),
                promotion_active=True,
            ),
        )
    )
    attestation = attestation_keyring.sign(
        "sealed-key-v1",
        _payload(PairedEvaluationGate.digest(report)),
        frozen=frozen,
        report=report,
    )
    return frozen, report, attestation, attestation_keyring


def _authorities(
    attestation_verifier: AttestationKeyring,
    *,
    private_seed: bytes = b"a" * 32,
    approver: str = "approver.clinical-lead",
    tracks: frozenset[ApprovalTrack] = frozenset({"immutable"}),
    active: bool = True,
    now: datetime = _NOW,
) -> tuple[HumanApprovalSigner, HumanApprovalVerifier]:
    signing_record = ApprovalSigningKeyRecord(
        key_id="approval-key-v1",
        private_key_seed=private_seed,
        approver_principal_id=approver,
        allowed_tracks=tracks,
        promotion_active=active,
    )
    signer = HumanApprovalSigner(
        (signing_record,),
        attestation_verifier=attestation_verifier,
        clock=_Clock(now),
    )
    verifier = HumanApprovalVerifier(
        (signing_record.verification_record(),),
        attestation_verifier=attestation_verifier,
        clock=_Clock(now),
    )
    return signer, verifier


def _approve(
    signer: HumanApprovalSigner,
    frozen: FrozenCandidate,
    report: PairedEvaluationReport,
    attestation: SealedGateAttestation,
) -> HumanApprovalProof:
    return signer.approve(
        "approval-key-v1",
        frozen=frozen,
        report=report,
        sealed_attestation=attestation,
        approval_ticket_id="ticket.release-2026-07",
    )


def test_human_approval_binds_actor_track_candidate_and_all_evaluation_artifacts() -> None:
    frozen, report, attestation, attestation_verifier = _artifacts()
    signer, verifier = _authorities(attestation_verifier)

    proof = _approve(signer, frozen, report, attestation)
    verified = verifier.verify(
        proof,
        frozen=frozen,
        report=report,
        sealed_attestation=attestation,
    )

    assert verified.approver_principal_id == "approver.clinical-lead"
    assert verified.track == "immutable"
    assert verified.approved_at == _NOW
    assert verified.decision == "approved"
    assert not hasattr(proof, "approved")


def test_verifier_rejects_stale_approval_before_skill_authorization() -> None:
    frozen, report, attestation, attestation_verifier = _artifacts()
    signer, _ = _authorities(attestation_verifier, now=_NOW)
    proof = _approve(signer, frozen, report, attestation)
    _, stale_verifier = _authorities(
        attestation_verifier,
        now=_NOW + timedelta(days=365),
    )

    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_HUMAN_APPROVAL_EXPIRED",
    ):
        stale_verifier.verify(
            proof,
            frozen=frozen,
            report=report,
            sealed_attestation=attestation,
        )


def test_verifier_requires_positive_approval_freshness_window() -> None:
    _, _, _, attestation_verifier = _artifacts()
    signing_record = ApprovalSigningKeyRecord(
        key_id="approval-key-v1",
        private_key_seed=b"a" * 32,
        approver_principal_id="approver.clinical-lead",
        allowed_tracks=frozenset({"immutable"}),
        promotion_active=True,
    )

    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_APPROVAL_POLICY_INVALID",
    ):
        HumanApprovalVerifier(
            (signing_record.verification_record(),),
            attestation_verifier=attestation_verifier,
            max_approval_age=timedelta(0),
        )


def test_promotion_verifier_has_public_key_only_and_no_approval_api() -> None:
    _, _, _, attestation_verifier = _artifacts()
    signer, verifier = _authorities(attestation_verifier)

    assert hasattr(signer, "approve")
    assert not hasattr(verifier, "approve")
    assert not hasattr(verifier, "sign")
    assert "private" not in repr(verifier)


def test_bare_boolean_caller_identity_and_caller_time_are_not_approval_inputs() -> None:
    frozen, report, attestation, attestation_verifier = _artifacts()
    signer, _ = _authorities(attestation_verifier)

    for forbidden in (
        {"approved": True},
        {"approver_principal_id": "candidate.fake"},
        {"approved_at": _NOW},
    ):
        with pytest.raises(TypeError):
            signer.approve(
                "approval-key-v1",
                frozen=frozen,
                report=report,
                sealed_attestation=attestation,
                approval_ticket_id="ticket.release-2026-07",
                **forbidden,
            )


def test_wrong_key_inactive_key_or_track_cannot_approve() -> None:
    frozen, report, attestation, attestation_verifier = _artifacts()
    signer, _ = _authorities(attestation_verifier)
    proof = _approve(signer, frozen, report, attestation)
    _, wrong_verifier = _authorities(attestation_verifier, private_seed=b"b" * 32)
    with pytest.raises(CandidateControlError, match="EVOLUTION_APPROVAL_SIGNATURE_INVALID"):
        wrong_verifier.verify(
            proof,
            frozen=frozen,
            report=report,
            sealed_attestation=attestation,
        )

    inactive_signer, _ = _authorities(attestation_verifier, active=False)
    with pytest.raises(CandidateControlError, match="EVOLUTION_APPROVAL_KEY_NOT_ACTIVE"):
        _approve(inactive_signer, frozen, report, attestation)

    mutable_signer, _ = _authorities(
        attestation_verifier,
        tracks=frozenset({"mutable"}),
    )
    with pytest.raises(CandidateControlError, match="EVOLUTION_APPROVAL_TRACK_FORBIDDEN"):
        _approve(mutable_signer, frozen, report, attestation)


def test_proof_cannot_be_replayed_for_another_candidate_or_attestation() -> None:
    frozen, report, attestation, attestation_verifier = _artifacts()
    signer, verifier = _authorities(attestation_verifier)
    proof = _approve(signer, frozen, report, attestation)
    other = frozen.model_copy(
        update={"proposal": frozen.proposal.model_copy(update={"candidate_commit": "9" * 40})}
    )
    with pytest.raises(CandidateControlError):
        verifier.verify(
            proof,
            frozen=other,
            report=report,
            sealed_attestation=attestation,
        )

    changed_attestation = attestation.model_copy(update={"signature": "0" * 64})
    with pytest.raises(CandidateControlError):
        verifier.verify(
            proof,
            frozen=frozen,
            report=report,
            sealed_attestation=changed_attestation,
        )


def test_failed_or_forged_evaluation_cannot_receive_human_approval() -> None:
    frozen, _, _, attestation_verifier = _artifacts()
    failed_report = PairedEvaluationGate().compare(
        frozen,
        _run("baseline", _BASE),
        _run(
            "candidate",
            _CANDIDATE,
            failed_cases=frozenset({_CASE_HIGH_RISK}),
        ),
    )
    failed_attestation = attestation_verifier.sign(
        "sealed-key-v1",
        _payload(PairedEvaluationGate.digest(failed_report)),
        frozen=frozen,
        report=failed_report,
    )
    signer, _ = _authorities(attestation_verifier)

    with pytest.raises(CandidateControlError, match="EVOLUTION_EVALUATION_GATE_REJECTED"):
        _approve(signer, frozen, failed_report, failed_attestation)


def test_approval_requires_freeze_evaluation_seal_and_approval_time_order() -> None:
    frozen, report, attestation, attestation_verifier = _artifacts()
    early_signer, _ = _authorities(
        attestation_verifier,
        now=frozen.proposal.frozen_at - timedelta(seconds=1),
    )
    with pytest.raises(CandidateControlError, match="EVOLUTION_APPROVAL_TIME_ORDER_INVALID"):
        _approve(early_signer, frozen, report, attestation)

    early_payload = attestation.payload.model_copy(
        update={"evaluated_at": report.candidate.evaluated_at - timedelta(seconds=1)}
    )
    early_attestation = attestation_verifier.sign(
        "sealed-key-v1",
        early_payload,
        frozen=frozen,
        report=report,
    )
    signer, _ = _authorities(attestation_verifier)
    with pytest.raises(CandidateControlError, match="EVOLUTION_APPROVAL_TIME_ORDER_INVALID"):
        _approve(signer, frozen, report, early_attestation)


def test_verifier_rejects_future_dated_proof_even_when_signature_is_valid() -> None:
    frozen, report, attestation, attestation_verifier = _artifacts()
    future = _NOW + timedelta(hours=1)
    future_signer, _ = _authorities(attestation_verifier, now=future)
    proof = _approve(future_signer, frozen, report, attestation)
    _, current_verifier = _authorities(attestation_verifier, now=_NOW)

    with pytest.raises(CandidateControlError, match="EVOLUTION_APPROVAL_TIME_ORDER_INVALID"):
        current_verifier.verify(
            proof,
            frozen=frozen,
            report=report,
            sealed_attestation=attestation,
        )


def test_naive_trusted_clock_fails_closed() -> None:
    frozen, report, attestation, attestation_verifier = _artifacts()
    signer, _ = _authorities(
        attestation_verifier,
        now=datetime(2026, 7, 30, 10, 0),
    )

    with pytest.raises(CandidateControlError, match="EVOLUTION_APPROVAL_CLOCK_INVALID"):
        _approve(signer, frozen, report, attestation)
