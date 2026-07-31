"""Atomic promotion, freshness, ticket, audit, and rollback tests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_candidate_freeze import (
    _base_repository,
    _commit_candidate,
    _git,
    _request,
)
from test_candidate_freeze import (
    _Clock as FreezeTestClock,
)
from test_paired_evaluation import _BASE, _CANDIDATE, _payload, _profile, _run

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
from gerclaw_evolution.candidate import CandidateFreezer
from gerclaw_evolution.contracts import (
    CandidateControlError,
    FrozenCandidate,
)
from gerclaw_evolution.evaluation import PairedEvaluationGate, PairedEvaluationReport
from gerclaw_evolution.git_repository import (
    GitRepository,
    IsolatedWorktreeFactory,
    RefUpdate,
)
from gerclaw_evolution.release import (
    JsonlReleaseAuditLog,
    PromotionController,
    PromotionResult,
    ReleaseAuditWriter,
    ReleaseClock,
    ReleaseSigner,
    ReleaseSigningKeyRecord,
    ReleaseVerifier,
    SignedReleaseRecord,
)

_APPROVAL_TIME = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)
_RELEASE_TIME = datetime(2026, 7, 30, 10, 30, tzinfo=UTC)


class _Clock(ReleaseClock):
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


class _FailingAudit(ReleaseAuditWriter):
    def append(self, _record: SignedReleaseRecord) -> None:
        raise RuntimeError("simulated external audit mirror outage")


def _candidate(
    source: GitRepository,
    root: Path,
    *,
    name: str,
    base_commit: str,
    proposal_id: str,
    content: str,
) -> tuple[GitRepository, FrozenCandidate]:
    candidate = IsolatedWorktreeFactory(source, root).create(
        name=name,
        base_commit=base_commit,
    )
    _commit_candidate(candidate, content=content)
    request = _request(base_commit).model_copy(update={"proposal_id": proposal_id})
    frozen = CandidateFreezer(clock=FreezeTestClock()).freeze(candidate, request)
    return candidate, frozen


def _evaluation(
    frozen: FrozenCandidate,
    *,
    ticket: str,
) -> tuple[
    PairedEvaluationReport,
    SealedGateAttestation,
    AttestationKeyring,
    HumanApprovalProof,
    HumanApprovalVerifier,
]:
    baseline = _run("baseline", _BASE).model_copy(
        update={
            "commit": frozen.proposal.base_commit,
            "frozen_manifest_sha256": frozen.frozen_manifest_sha256,
        }
    )
    candidate = _run("candidate", _CANDIDATE).model_copy(
        update={
            "commit": frozen.proposal.candidate_commit,
            "frozen_manifest_sha256": frozen.frozen_manifest_sha256,
        }
    )
    report = PairedEvaluationGate().compare(frozen, baseline, candidate)
    attestation_authority = AttestationKeyring(
        (
            AttestationKeyRecord(
                key_id="sealed-key-v1",
                secret=b"s" * 32,
                profile=_profile(),
                promotion_active=True,
            ),
        )
    )
    payload = _payload(PairedEvaluationGate.digest(report)).model_copy(
        update={
            "proposal_id": frozen.proposal.proposal_id,
            "base_commit": frozen.proposal.base_commit,
            "candidate_commit": frozen.proposal.candidate_commit,
            "frozen_manifest_sha256": frozen.frozen_manifest_sha256,
        }
    )
    attestation = attestation_authority.sign(
        "sealed-key-v1",
        payload,
        frozen=frozen,
        report=report,
    )
    approval_key = ApprovalSigningKeyRecord(
        key_id="approval-key-v1",
        private_key_seed=b"a" * 32,
        approver_principal_id="approver.clinical-lead",
        allowed_tracks=frozenset({"immutable", "mutable"}),
        promotion_active=True,
    )
    signer = HumanApprovalSigner(
        (approval_key,),
        attestation_verifier=attestation_authority,
        clock=_Clock(_APPROVAL_TIME),
    )
    verifier = HumanApprovalVerifier(
        (approval_key.verification_record(),),
        attestation_verifier=attestation_authority,
        clock=_Clock(_APPROVAL_TIME),
    )
    approval = signer.approve(
        "approval-key-v1",
        frozen=frozen,
        report=report,
        sealed_attestation=attestation,
        approval_ticket_id=ticket,
    )
    return report, attestation, attestation_authority, approval, verifier


def _controller(
    tmp_path: Path,
    *,
    attestation_authority: AttestationKeyring,
    approval_verifier: HumanApprovalVerifier,
    clock: datetime = _RELEASE_TIME,
    audit_writer: ReleaseAuditWriter | None = None,
) -> PromotionController:
    release_key = ReleaseSigningKeyRecord(
        key_id="release-key-v1",
        private_key_seed=b"r" * 32,
        promotion_active=True,
    )
    return PromotionController(
        candidate_revalidator=CandidateFreezer(clock=FreezeTestClock()),
        attestation_verifier=attestation_authority,
        approval_verifier=approval_verifier,
        release_signer=ReleaseSigner(release_key),
        release_verifier=ReleaseVerifier((release_key.verification_record(),)),
        audit_writer=audit_writer or JsonlReleaseAuditLog(tmp_path / "audit" / "release.jsonl"),
        clock=_Clock(clock),
    )


def test_promotion_atomically_binds_release_record_ref_and_consumed_ticket(
    tmp_path: Path,
) -> None:
    source, base_commit = _base_repository(tmp_path)
    candidate, frozen = _candidate(
        source,
        tmp_path / "worktrees",
        name="candidate-one",
        base_commit=base_commit,
        proposal_id="candidate.release-one",
        content="ROUTE = 'deep'\n",
    )
    report, attestation, authority, approval, approval_verifier = _evaluation(
        frozen,
        ticket="ticket.release-one",
    )
    controller = _controller(
        tmp_path,
        attestation_authority=authority,
        approval_verifier=approval_verifier,
    )

    result = controller.promote(
        source_repository=source,
        candidate_repository=candidate,
        channel="production",
        frozen=frozen,
        report=report,
        sealed_attestation=attestation,
        human_approval=approval,
    )

    assert (
        source.resolve_ref("refs/gerclaw/releases/production") == frozen.proposal.candidate_commit
    )
    assert source.resolve_ref(f"refs/gerclaw/release-records/{result.record_sha256}")
    assert (
        source.resolve_ref(f"refs/gerclaw/release-commits/{result.record_sha256}")
        == frozen.proposal.candidate_commit
    )
    assert source.resolve_ref("refs/gerclaw/release-ledger/production")
    assert source.resolve_ref(
        "refs/gerclaw/approval-tickets/" + hashlib.sha256(b"ticket.release-one").hexdigest()
    )
    assert result.audit_mirror_status == "appended"
    assert len((tmp_path / "audit" / "release.jsonl").read_text().splitlines()) == 1

    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_APPROVAL_TICKET_ALREADY_CONSUMED",
    ):
        controller.promote(
            source_repository=source,
            candidate_repository=candidate,
            channel="production",
            frozen=frozen,
            report=report,
            sealed_attestation=attestation,
            human_approval=approval,
        )


def test_atomic_release_ref_transaction_never_dereferences_symbolic_refs(
    tmp_path: Path,
) -> None:
    source, base_commit = _base_repository(tmp_path)
    candidate, _frozen_candidate = _candidate(
        source,
        tmp_path / "worktrees",
        name="candidate-one",
        base_commit=base_commit,
        proposal_id="candidate.release-one",
        content="ROUTE = 'deep'\n",
    )
    branch = _git(source.root, "symbolic-ref", "--short", "HEAD")
    release_ref = "refs/gerclaw/releases/production"
    _git(source.root, "symbolic-ref", release_ref, f"refs/heads/{branch}")

    with pytest.raises(CandidateControlError, match="EVOLUTION_SYMBOLIC_REF_FORBIDDEN"):
        source.atomic_update_refs(
            (
                RefUpdate(
                    release_ref,
                    candidate.head(),
                    base_commit,
                ),
            )
        )

    assert _git(source.root, "rev-parse", f"refs/heads/{branch}") == base_commit
    assert _git(source.root, "symbolic-ref", release_ref) == f"refs/heads/{branch}"


def test_immutable_release_requires_fresh_human_approval_and_unchanged_candidate(
    tmp_path: Path,
) -> None:
    source, base_commit = _base_repository(tmp_path)
    candidate, frozen = _candidate(
        source,
        tmp_path / "worktrees",
        name="candidate-one",
        base_commit=base_commit,
        proposal_id="candidate.release-one",
        content="ROUTE = 'deep'\n",
    )
    report, attestation, authority, approval, approval_verifier = _evaluation(
        frozen,
        ticket="ticket.release-one",
    )
    controller = _controller(
        tmp_path,
        attestation_authority=authority,
        approval_verifier=approval_verifier,
    )
    with pytest.raises(CandidateControlError, match="EVOLUTION_HUMAN_APPROVAL_REQUIRED"):
        controller.promote(
            source_repository=source,
            candidate_repository=candidate,
            channel="production",
            frozen=frozen,
            report=report,
            sealed_attestation=attestation,
            human_approval=None,
        )

    expired = _controller(
        tmp_path,
        attestation_authority=authority,
        approval_verifier=approval_verifier,
        clock=_APPROVAL_TIME + timedelta(days=2),
    )
    with pytest.raises(CandidateControlError, match="EVOLUTION_HUMAN_APPROVAL_EXPIRED"):
        expired.promote(
            source_repository=source,
            candidate_repository=candidate,
            channel="production",
            frozen=frozen,
            report=report,
            sealed_attestation=attestation,
            human_approval=approval,
        )

    changed_file = candidate.root / frozen.repository_changes[0].repository_path
    changed_file.write_text("ROUTE = 'quick'\n", encoding="utf-8")
    with pytest.raises(CandidateControlError, match="EVOLUTION_WORKTREE_DIRTY"):
        controller.promote(
            source_repository=source,
            candidate_repository=candidate,
            channel="production",
            frozen=frozen,
            report=report,
            sealed_attestation=attestation,
            human_approval=approval,
        )


def test_forged_immutable_candidate_cannot_relabel_itself_mutable_to_skip_approval(
    tmp_path: Path,
) -> None:
    source, base_commit = _base_repository(tmp_path)
    candidate, frozen = _candidate(
        source,
        tmp_path / "worktrees",
        name="candidate-one",
        base_commit=base_commit,
        proposal_id="candidate.release-one",
        content="ROUTE = 'deep'\n",
    )
    forged_proposal = frozen.proposal.model_copy(update={"declared_track": "mutable"})
    forged = frozen.model_copy(
        update={
            "proposal": forged_proposal,
            "frozen_manifest_sha256": CandidateFreezer._frozen_digest(
                forged_proposal,
                frozen.repository_changes,
                frozen.governance_manifest_sha256,
            ),
        }
    )
    report, attestation, authority, _approval, approval_verifier = _evaluation(
        forged,
        ticket="ticket.forged-track",
    )
    controller = _controller(
        tmp_path,
        attestation_authority=authority,
        approval_verifier=approval_verifier,
    )

    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_DECLARED_TRACK_MISMATCH",
    ):
        controller.promote(
            source_repository=source,
            candidate_repository=candidate,
            channel="production",
            frozen=forged,
            report=report,
            sealed_attestation=attestation,
            human_approval=None,
        )


def test_audit_mirror_outage_preserves_atomic_release_and_reports_warning(
    tmp_path: Path,
) -> None:
    source, base_commit = _base_repository(tmp_path)
    candidate, frozen = _candidate(
        source,
        tmp_path / "worktrees",
        name="candidate-one",
        base_commit=base_commit,
        proposal_id="candidate.release-one",
        content="ROUTE = 'deep'\n",
    )
    report, attestation, authority, approval, approval_verifier = _evaluation(
        frozen,
        ticket="ticket.release-one",
    )
    controller = _controller(
        tmp_path,
        attestation_authority=authority,
        approval_verifier=approval_verifier,
        audit_writer=_FailingAudit(),
    )

    result = controller.promote(
        source_repository=source,
        candidate_repository=candidate,
        channel="production",
        frozen=frozen,
        report=report,
        sealed_attestation=attestation,
        human_approval=approval,
    )

    assert result.audit_mirror_status == "repair_required"
    assert (
        source.resolve_ref("refs/gerclaw/releases/production") == frozen.proposal.candidate_commit
    )
    assert source.resolve_ref(f"refs/gerclaw/release-records/{result.record_sha256}")


def test_rollback_accepts_only_a_previously_signed_and_atomically_released_record(
    tmp_path: Path,
) -> None:
    source, base_commit = _base_repository(tmp_path)
    first_candidate, first_frozen = _candidate(
        source,
        tmp_path / "first-worktrees",
        name="candidate-one",
        base_commit=base_commit,
        proposal_id="candidate.release-one",
        content="ROUTE = 'deep'\n",
    )
    first_bundle = _evaluation(first_frozen, ticket="ticket.release-one")
    first_controller = _controller(
        tmp_path,
        attestation_authority=first_bundle[2],
        approval_verifier=first_bundle[4],
    )
    first = first_controller.promote(
        source_repository=source,
        candidate_repository=first_candidate,
        channel="production",
        frozen=first_frozen,
        report=first_bundle[0],
        sealed_attestation=first_bundle[1],
        human_approval=first_bundle[3],
    )

    second_candidate, second_frozen = _candidate(
        source,
        tmp_path / "second-worktrees",
        name="candidate-two",
        base_commit=base_commit,
        proposal_id="candidate.release-two",
        content="ROUTE = 'quick'\n",
    )
    second_bundle = _evaluation(second_frozen, ticket="ticket.release-two")
    second_controller = _controller(
        tmp_path,
        attestation_authority=second_bundle[2],
        approval_verifier=second_bundle[4],
    )
    second_controller.promote(
        source_repository=source,
        candidate_repository=second_candidate,
        channel="production",
        frozen=second_frozen,
        report=second_bundle[0],
        sealed_attestation=second_bundle[1],
        human_approval=second_bundle[3],
    )

    release_key = ReleaseSigningKeyRecord(
        key_id="release-key-v1",
        private_key_seed=b"r" * 32,
        promotion_active=True,
    )
    unreleased = ReleaseSigner(release_key).sign(
        first.record.payload.model_copy(update={"release_id": "release.valid-but-unreleased"})
    )
    unreleased_bytes = json.dumps(
        unreleased.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    unreleased_digest = hashlib.sha256(unreleased_bytes).hexdigest()
    unreleased_object = source.store_blob(unreleased_bytes)
    source.atomic_update_refs(
        (
            RefUpdate(
                f"refs/gerclaw/release-records/{unreleased_digest}",
                unreleased_object,
                "0" * 40,
            ),
        )
    )
    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_ROLLBACK_TARGET_NOT_RELEASED",
    ):
        second_controller.rollback(
            source_repository=source,
            channel="production",
            target_record=unreleased,
        )

    rollback = second_controller.rollback(
        source_repository=source,
        channel="production",
        target_record=first.record,
    )
    assert rollback.record.payload.action == "rollback"
    assert rollback.record.payload.rollback_target_record_sha256 == first.record_sha256
    assert (
        source.resolve_ref("refs/gerclaw/releases/production")
        == first_frozen.proposal.candidate_commit
    )

    forged = first.record.model_copy(update={"signature": "0" * 128})
    with pytest.raises(CandidateControlError, match="EVOLUTION_RELEASE_SIGNATURE_INVALID"):
        second_controller.rollback(
            source_repository=source,
            channel="production",
            target_record=forged,
        )


def test_new_promotion_rejects_a_hash_pointer_alias_in_release_history(
    tmp_path: Path,
) -> None:
    source, base_commit = _base_repository(tmp_path)
    released: list[tuple[FrozenCandidate, PromotionResult]] = []
    for index, route in ((1, "deep"), (2, "quick")):
        candidate, frozen = _candidate(
            source,
            tmp_path / f"worktrees-{index}",
            name=f"candidate-{index}",
            base_commit=base_commit,
            proposal_id=f"candidate.release-{index}",
            content=f"ROUTE = '{route}'\n",
        )
        bundle = _evaluation(frozen, ticket=f"ticket.release-{index}")
        controller = _controller(
            tmp_path,
            attestation_authority=bundle[2],
            approval_verifier=bundle[4],
        )
        result = controller.promote(
            source_repository=source,
            candidate_repository=candidate,
            channel="production",
            frozen=frozen,
            report=bundle[0],
            sealed_attestation=bundle[1],
            human_approval=bundle[3],
        )
        released.append((frozen, result))

    first_result = released[0][1]
    first_digest = first_result.record_sha256
    first_record_ref = f"refs/gerclaw/release-records/{first_digest}"
    first_record_object = source.resolve_ref(first_record_ref)
    assert first_record_object is not None
    release_key = ReleaseSigningKeyRecord(
        key_id="release-key-v1",
        private_key_seed=b"r" * 32,
        promotion_active=True,
    )
    alias_record = ReleaseSigner(release_key).sign(
        first_result.record.payload.model_copy(update={"release_id": "release.alias-history"})
    )
    alias_bytes = json.dumps(
        alias_record.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    alias_digest = hashlib.sha256(alias_bytes).hexdigest()
    alias_object = source.store_blob(alias_bytes)
    source.atomic_update_refs(
        (
            RefUpdate(first_record_ref, alias_object, first_record_object),
            RefUpdate(
                f"refs/gerclaw/release-records/{alias_digest}",
                alias_object,
                "0" * 40,
            ),
            RefUpdate(
                f"refs/gerclaw/release-commits/{alias_digest}",
                released[0][0].proposal.candidate_commit,
                "0" * 40,
            ),
        )
    )

    third_candidate, third_frozen = _candidate(
        source,
        tmp_path / "worktrees-3",
        name="candidate-3",
        base_commit=base_commit,
        proposal_id="candidate.release-3",
        content="ROUTE = 'emergency'\n",
    )
    third = _evaluation(third_frozen, ticket="ticket.release-3")
    third_controller = _controller(
        tmp_path,
        attestation_authority=third[2],
        approval_verifier=third[4],
    )
    with pytest.raises(CandidateControlError, match="EVOLUTION_RELEASE_STATE_INCONSISTENT"):
        third_controller.promote(
            source_repository=source,
            candidate_repository=third_candidate,
            channel="production",
            frozen=third_frozen,
            report=third[0],
            sealed_attestation=third[1],
            human_approval=third[3],
        )
