"""Paired non-regression and sealed-attestation tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from gerclaw_api.modules.agent_harness.evolution_governance import (
    COMPONENT_CHARTERS,
    CandidateChange,
    CandidateProposal,
)
from pydantic import ValidationError

from gerclaw_evolution.attestation import (
    AttestationKeyRecord,
    AttestationKeyring,
    SealedEvaluatorProfile,
    SealedGatePayload,
)
from gerclaw_evolution.contracts import (
    CandidateControlError,
    FrozenCandidate,
    FrozenRepositoryChange,
)
from gerclaw_evolution.evaluation import (
    CharterObservation,
    EvaluationCaseObservation,
    EvaluationRun,
    EvaluationSlice,
    PairedEvaluationGate,
)

_BASE = "a" * 40
_CANDIDATE = "b" * 40
_DIGEST = "c" * 64
_NOW = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)
_CASE_NORMAL = "case_" + "1" * 32
_CASE_COMPLEX = "case_" + "2" * 32
_CASE_HIGH_RISK = "case_" + "3" * 32
_CASE_ELDERLY = "case_" + "4" * 32
_PROFILE_DIGEST = "7" * 64
_SEALED_CASE_DIGEST = "f" * 64
_GATE_POLICY_DIGEST = "8" * 64
_CASES: tuple[tuple[str, EvaluationSlice], ...] = (
    (_CASE_NORMAL, "normal"),
    (_CASE_COMPLEX, "complex"),
    (_CASE_HIGH_RISK, "high_risk"),
    (_CASE_ELDERLY, "elderly"),
)


def _frozen() -> FrozenCandidate:
    change = CandidateChange(
        object_kind="routing.strategy",
        target="policy/routing/router.py",
        content_digest=_DIGEST,
    )
    return FrozenCandidate(
        proposal=CandidateProposal(
            proposal_id="candidate.evaluation",
            declared_track="immutable",
            base_commit=_BASE,
            candidate_commit=_CANDIDATE,
            risk_level="high",
            risk_reason_codes=("routing.change",),
            activation_condition_ids=("paired.eval", "sealed.eval"),
            frozen_at=_NOW,
            changes=(change,),
        ),
        repository_changes=(
            FrozenRepositoryChange(
                repository_path=(
                    "apps/api/src/gerclaw_api/modules/agent_harness/routing/router.py"
                ),
                object_kind=change.object_kind,
                target=change.target,
                content_digest=change.content_digest,
            ),
        ),
        governance_manifest_sha256="d" * 64,
        frozen_manifest_sha256="e" * 64,
    )


def _run(
    role: str,
    commit: str,
    *,
    quality_by_case: dict[str, int] | None = None,
    failed_cases: frozenset[str] = frozenset(),
    inactive_cases: frozenset[str] = frozenset(),
    failed_charters: frozenset[str] = frozenset(),
) -> EvaluationRun:
    quality_by_case = quality_by_case or {}
    cases = tuple(
        EvaluationCaseObservation(
            case_id=case_id,
            slice=slice_name,
            passed=case_id not in failed_cases,
            quality_micros=quality_by_case.get(case_id, 900_000),
            token_count=1_000,
            latency_ms=100,
            runtime_activated=case_id not in inactive_cases,
        )
        for case_id, slice_name in _CASES
    )
    charters = tuple(
        CharterObservation(
            evaluator_id=evaluator_id,
            passed=evaluator_id not in failed_charters,
        )
        for evaluator_id in sorted(
            evaluator_id
            for charter in COMPONENT_CHARTERS
            for evaluator_id in charter.sealed_evaluator_ids
        )
    )
    return EvaluationRun.model_validate(
        {
            "role": role,
            "commit": commit,
            "runner_id": "runner.unit",
            "runner_version": "runner-v1",
            "evaluation_profile_sha256": _PROFILE_DIGEST,
            "frozen_manifest_sha256": "e" * 64,
            "execution_bundle_sha256": ("5" if role == "baseline" else "6") * 64,
            "evaluated_at": _NOW,
            "cases": cases,
            "charters": charters,
        }
    )


def _payload(report_digest: str, *, token_budget_passed: bool = True) -> SealedGatePayload:
    return SealedGatePayload(
        proposal_id="candidate.evaluation",
        base_commit=_BASE,
        candidate_commit=_CANDIDATE,
        frozen_manifest_sha256="e" * 64,
        paired_report_sha256=report_digest,
        sealed_case_set_sha256=_SEALED_CASE_DIGEST,
        gate_policy_manifest_sha256=_GATE_POLICY_DIGEST,
        evaluator_id="sealed.medical-v1",
        evaluator_version="sealed-v1",
        evaluated_at=_NOW,
        public_report_verified=True,
        sealed_cases_passed=True,
        no_sealed_case_regressed=True,
        high_risk_singletons_non_degrading=True,
        token_budget_passed=token_budget_passed,
        latency_budget_passed=True,
        runtime_activation_passed=True,
        component_charters_passed=True,
        passed=token_budget_passed,
    )


def _profile() -> SealedEvaluatorProfile:
    return SealedEvaluatorProfile(
        public_runner_id="runner.unit",
        public_runner_version="runner-v1",
        public_evaluation_profile_sha256=_PROFILE_DIGEST,
        evaluator_id="sealed.medical-v1",
        evaluator_version="sealed-v1",
        sealed_case_set_sha256=_SEALED_CASE_DIGEST,
        gate_policy_manifest_sha256=_GATE_POLICY_DIGEST,
    )


def _keyring(
    *,
    secret: bytes = b"a" * 32,
    profile: SealedEvaluatorProfile | None = None,
    promotion_active: bool = True,
    key_id: str = "sealed-key-v1",
) -> AttestationKeyring:
    return AttestationKeyring(
        (
            AttestationKeyRecord(
                key_id=key_id,
                secret=secret,
                profile=profile or _profile(),
                promotion_active=promotion_active,
            ),
        )
    )


def test_paired_report_accepts_only_complete_non_degrading_runtime_results() -> None:
    frozen = _frozen()
    report = PairedEvaluationGate().compare(
        frozen,
        _run("baseline", _BASE),
        _run("candidate", _CANDIDATE),
    )

    assert report.gate.passed
    assert report.gate.all_slices_non_degrading
    assert len(PairedEvaluationGate.digest(report)) == 64


@pytest.mark.parametrize(
    ("candidate", "failed_gate"),
    (
        (
            _run("candidate", _CANDIDATE, failed_cases=frozenset({_CASE_NORMAL})),
            "no_passed_case_regressed",
        ),
        (
            _run(
                "candidate",
                _CANDIDATE,
                quality_by_case={_CASE_HIGH_RISK: 899_999},
            ),
            "high_risk_cases_non_degrading",
        ),
        (
            _run(
                "candidate",
                _CANDIDATE,
                inactive_cases=frozenset({_CASE_COMPLEX}),
            ),
            "all_runtime_paths_activated",
        ),
        (
            _run(
                "candidate",
                _CANDIDATE,
                failed_charters=frozenset({"charter.memory.v1"}),
            ),
            "all_component_charters_passed",
        ),
    ),
)
def test_any_case_high_risk_runtime_or_charter_regression_rejects(
    candidate: EvaluationRun,
    failed_gate: str,
) -> None:
    report = PairedEvaluationGate().compare(
        _frozen(),
        _run("baseline", _BASE),
        candidate,
    )

    assert report.gate.passed is False
    assert getattr(report.gate, failed_gate) is False


def test_a_better_peer_cannot_hide_any_single_case_quality_regression() -> None:
    baseline = _run("baseline", _BASE)
    extra_baseline = baseline.cases[0].model_copy(update={"case_id": "case_" + "5" * 32})
    baseline = baseline.model_copy(update={"cases": (*baseline.cases, extra_baseline)})
    candidate = _run(
        "candidate",
        _CANDIDATE,
        quality_by_case={_CASE_NORMAL: 800_000},
    )
    extra_candidate = candidate.cases[0].model_copy(
        update={"case_id": "case_" + "5" * 32, "quality_micros": 1_000_000}
    )
    candidate = candidate.model_copy(update={"cases": (*candidate.cases, extra_candidate)})

    report = PairedEvaluationGate().compare(_frozen(), baseline, candidate)

    assert report.gate.all_slices_non_degrading
    assert report.gate.all_cases_non_degrading is False
    assert report.gate.passed is False


def test_baseline_and_candidate_must_use_the_same_runner_and_profile() -> None:
    baseline = _run("baseline", _BASE)
    candidate = _run("candidate", _CANDIDATE).model_copy(update={"runner_version": "runner-v2"})

    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_EVALUATOR_PROFILE_MISMATCH",
    ):
        PairedEvaluationGate().compare(_frozen(), baseline, candidate)


def test_case_identifiers_are_opaque_and_cannot_contain_patient_content() -> None:
    valid = _run("baseline", _BASE)
    unsafe = valid.cases[0].model_dump()
    unsafe["case_id"] = "patient.alice-hiv"

    with pytest.raises(ValidationError, match="case_id"):
        EvaluationCaseObservation.model_validate(unsafe)


def test_case_set_or_slice_mismatch_fails_closed() -> None:
    frozen = _frozen()
    candidate = _run("candidate", _CANDIDATE)
    missing = candidate.model_copy(update={"cases": candidate.cases[:-1]})
    with pytest.raises(CandidateControlError, match="EVOLUTION_PAIRED_CASE_SET_MISMATCH"):
        PairedEvaluationGate().compare(frozen, _run("baseline", _BASE), missing)

    changed_case = candidate.cases[0].model_copy(update={"slice": "complex"})
    wrong_slice = candidate.model_copy(update={"cases": (changed_case, *candidate.cases[1:])})
    with pytest.raises(CandidateControlError, match="EVOLUTION_PAIRED_SLICE_MISMATCH"):
        PairedEvaluationGate().compare(frozen, _run("baseline", _BASE), wrong_slice)


def test_evaluation_requires_all_slices_and_known_unique_component_charters() -> None:
    valid = _run("baseline", _BASE)
    missing_slice = (
        *valid.cases[:-1],
        valid.cases[-1].model_copy(update={"slice": "normal"}),
    )
    with pytest.raises(ValidationError, match="all required slices"):
        EvaluationRun.model_validate({**valid.model_dump(), "cases": missing_slice})
    unknown = valid.charters[0].model_copy(update={"evaluator_id": "charter.unknown.v1"})
    with pytest.raises(ValidationError, match="unique known controller charters"):
        EvaluationRun.model_validate(
            {**valid.model_dump(), "charters": (unknown, *valid.charters[1:])}
        )


def test_gate_requires_frozen_manifest_and_applicable_charter_binding() -> None:
    frozen = _frozen()
    baseline = _run("baseline", _BASE)
    candidate = _run("candidate", _CANDIDATE)
    forged_manifest = candidate.model_copy(update={"frozen_manifest_sha256": "0" * 64})
    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_RUN_FROZEN_MANIFEST_MISMATCH",
    ):
        PairedEvaluationGate().compare(frozen, baseline, forged_manifest)

    without_routing = tuple(
        item for item in baseline.charters if item.evaluator_id != "charter.routing.v1"
    )
    with pytest.raises(CandidateControlError, match="EVOLUTION_CHARTER_SCOPE_MISMATCH"):
        PairedEvaluationGate().compare(
            frozen,
            baseline.model_copy(update={"charters": without_routing}),
            candidate.model_copy(update={"charters": without_routing}),
        )


def test_valid_sealed_attestation_binds_freeze_report_and_trusted_key() -> None:
    frozen = _frozen()
    report = PairedEvaluationGate().compare(
        frozen,
        _run("baseline", _BASE),
        _run("candidate", _CANDIDATE),
    )
    keyring = _keyring()
    attestation = keyring.sign(
        "sealed-key-v1",
        _payload(PairedEvaluationGate.digest(report)),
        frozen=frozen,
        report=report,
    )

    verified = keyring.verify(attestation, frozen=frozen, report=report)

    assert verified.passed
    assert not hasattr(attestation, "key")


def test_forged_key_report_or_failed_budget_cannot_pass_attestation() -> None:
    frozen = _frozen()
    report = PairedEvaluationGate().compare(
        frozen,
        _run("baseline", _BASE),
        _run("candidate", _CANDIDATE),
    )
    report_digest = PairedEvaluationGate.digest(report)
    trusted = _keyring()
    forged = _keyring(secret=b"b" * 32).sign(
        "sealed-key-v1",
        _payload(report_digest),
        frozen=frozen,
        report=report,
    )
    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_ATTESTATION_SIGNATURE_INVALID",
    ):
        trusted.verify(forged, frozen=frozen, report=report)

    wrong_report = report.model_copy(update={"candidate_commit": "9" * 40})
    signed = trusted.sign(
        "sealed-key-v1",
        _payload(report_digest),
        frozen=frozen,
        report=report,
    )
    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_PAIRED_REPORT_FORGED",
    ):
        trusted.verify(signed, frozen=frozen, report=wrong_report)

    failed_budget = trusted.sign(
        "sealed-key-v1",
        _payload(report_digest, token_budget_passed=False),
        frozen=frozen,
        report=report,
    )
    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_EVALUATION_GATE_REJECTED",
    ):
        trusted.verify(failed_budget, frozen=frozen, report=report)


def test_attestation_must_match_controller_pinned_case_and_threshold_profile() -> None:
    frozen = _frozen()
    report = PairedEvaluationGate().compare(
        frozen,
        _run("baseline", _BASE),
        _run("candidate", _CANDIDATE),
    )
    trusted = _keyring()
    attestation = trusted.sign(
        "sealed-key-v1",
        _payload(PairedEvaluationGate.digest(report)),
        frozen=frozen,
        report=report,
    )
    wrong_policy = _profile().model_copy(update={"gate_policy_manifest_sha256": "9" * 64})
    wrong_keyring = _keyring(profile=wrong_policy)

    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_ATTESTATION_IDENTITY_MISMATCH",
    ):
        wrong_keyring.verify(attestation, frozen=frozen, report=report)


def test_all_true_gate_cannot_be_forged_over_regressing_observations() -> None:
    frozen = _frozen()
    real_report = PairedEvaluationGate().compare(
        frozen,
        _run("baseline", _BASE),
        _run(
            "candidate",
            _CANDIDATE,
            quality_by_case={_CASE_HIGH_RISK: 1},
        ),
    )
    forged_report = real_report.model_copy(
        update={
            "gate": real_report.gate.model_copy(
                update={
                    "all_cases_non_degrading": True,
                    "all_slices_non_degrading": True,
                    "high_risk_cases_non_degrading": True,
                    "passed": True,
                }
            )
        }
    )

    assert real_report.gate.passed is False
    with pytest.raises(CandidateControlError, match="EVOLUTION_PAIRED_REPORT_FORGED"):
        _keyring().sign(
            "sealed-key-v1",
            _payload(PairedEvaluationGate.digest(forged_report)),
            frozen=frozen,
            report=forged_report,
        )


def test_inactive_or_wrong_profile_key_cannot_claim_current_medical_profile() -> None:
    frozen = _frozen()
    report = PairedEvaluationGate().compare(
        frozen,
        _run("baseline", _BASE),
        _run("candidate", _CANDIDATE),
    )
    old_profile = _profile().model_copy(update={"gate_policy_manifest_sha256": "9" * 64})
    old_payload = _payload(PairedEvaluationGate.digest(report)).model_copy(
        update={"gate_policy_manifest_sha256": "9" * 64}
    )
    old_record = AttestationKeyRecord(
        key_id="old-key-v1",
        secret=b"o" * 32,
        profile=old_profile,
        promotion_active=False,
    )
    current_record = AttestationKeyRecord(
        key_id="sealed-key-v1",
        secret=b"a" * 32,
        profile=_profile(),
        promotion_active=True,
    )
    combined = AttestationKeyring((old_record, current_record))
    old_attestation = combined.sign(
        "old-key-v1",
        old_payload,
        frozen=frozen,
        report=report,
    )

    with pytest.raises(CandidateControlError, match="EVOLUTION_ATTESTATION_KEY_NOT_ACTIVE"):
        combined.verify(old_attestation, frozen=frozen, report=report)
    with pytest.raises(CandidateControlError, match="EVOLUTION_ATTESTATION_IDENTITY_MISMATCH"):
        _keyring(profile=old_profile).sign(
            "sealed-key-v1",
            _payload(PairedEvaluationGate.digest(report)),
            frozen=frozen,
            report=report,
        )


def test_candidate_supplied_public_runner_identity_cannot_replace_controller_profile() -> None:
    frozen = _frozen()
    baseline = _run("baseline", _BASE).model_copy(
        update={
            "runner_id": "candidate.fake",
            "runner_version": "fake-v1",
            "evaluation_profile_sha256": "0" * 64,
        }
    )
    candidate = _run("candidate", _CANDIDATE).model_copy(
        update={
            "runner_id": "candidate.fake",
            "runner_version": "fake-v1",
            "evaluation_profile_sha256": "0" * 64,
        }
    )
    report = PairedEvaluationGate().compare(frozen, baseline, candidate)

    assert report.gate.passed
    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_ATTESTATION_IDENTITY_MISMATCH",
    ):
        _keyring().sign(
            "sealed-key-v1",
            _payload(PairedEvaluationGate.digest(report)),
            frozen=frozen,
            report=report,
        )
