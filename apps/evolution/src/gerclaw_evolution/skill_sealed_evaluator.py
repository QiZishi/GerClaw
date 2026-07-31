"""Derive sealed Skill gates from secret-runner case observations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal, Protocol

from gerclaw_api.modules.agent_harness.evolution_governance import (
    REQUIRED_CHARTERS_BY_OBJECT_KIND,
)
from gerclaw_api.modules.skill.models import SkillDefinition
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_evolution.attestation import (
    AttestationKeyring,
    SealedEvaluatorProfile,
    SealedGateAttestation,
    SealedGatePayload,
)
from gerclaw_evolution.contracts import CandidateControlError
from gerclaw_evolution.evaluation import (
    CharterObservation,
    EvaluationRole,
    EvaluationSlice,
    PairedEvaluationGate,
    PairedEvaluationReport,
)
from gerclaw_evolution.skill_proposal import FrozenSkillCandidate

_STRICT = ConfigDict(extra="forbid", frozen=True)
_SHA256 = r"^[a-f0-9]{64}$"
_CASE_ID = r"^case_[a-f0-9]{32}$"


class SealedSkillGatePolicy(BaseModel):
    """Exact non-secret thresholds bound to the sealed evaluator profile."""

    model_config = _STRICT

    schema_version: Literal["sealed-skill-gate-policy-v1"] = (
        "sealed-skill-gate-policy-v1"
    )
    max_tokens_per_case: int = Field(ge=1, le=10_000_000)
    max_token_increase_per_case: int = Field(ge=0, le=10_000_000)
    max_latency_ms_per_case: int = Field(ge=1, le=3_600_000)
    max_latency_increase_ms_per_case: int = Field(ge=0, le=3_600_000)

    def digest(self) -> str:
        return _digest(self.model_dump(mode="json"))


class SealedSkillCaseObservation(BaseModel):
    """Content-free result for one secret case; no prompt or answer may enter."""

    model_config = _STRICT

    schema_version: Literal["sealed-skill-case-observation-v1"] = (
        "sealed-skill-case-observation-v1"
    )
    case_id: str = Field(pattern=_CASE_ID)
    slice: EvaluationSlice
    passed: bool
    quality_micros: int = Field(ge=0, le=1_000_000)
    token_count: int = Field(ge=0, le=10_000_000)
    latency_ms: int = Field(ge=0, le=3_600_000)
    runtime_activated: bool
    charters: tuple[CharterObservation, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def require_unique_charters(self) -> SealedSkillCaseObservation:
        ids = [item.evaluator_id for item in self.charters]
        if len(ids) != len(set(ids)):
            raise ValueError("sealed Skill case contains duplicate charters")
        return self


class SealedSkillCaseBatch(BaseModel):
    """One role's exact secret case set projected without case content."""

    model_config = _STRICT

    schema_version: Literal["sealed-skill-case-batch-v1"] = (
        "sealed-skill-case-batch-v1"
    )
    role: EvaluationRole
    candidate_identity: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    case_set_sha256: str = Field(pattern=_SHA256)
    evaluated_at: datetime
    cases: tuple[SealedSkillCaseObservation, ...] = Field(
        min_length=4,
        max_length=10_000,
    )

    @field_validator("evaluated_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("sealed Skill evaluation time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_complete_case_set(self) -> SealedSkillCaseBatch:
        ids = [item.case_id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("sealed Skill case IDs must be unique")
        if {item.slice for item in self.cases} != {
            "normal",
            "complex",
            "high_risk",
            "elderly",
        }:
            raise ValueError("sealed Skill evaluation must cover every required slice")
        return self


class SealedSkillCaseRunner(Protocol):
    """Deployment-owned secret runner; case content never crosses this port."""

    def run(
        self,
        definition: SkillDefinition,
        *,
        role: EvaluationRole,
    ) -> SealedSkillCaseBatch: ...


class SealedSkillEvaluatorClock(Protocol):
    def now(self) -> datetime: ...


class SkillSealedEvaluator:
    """Run both snapshots and derive every signed sealed verdict locally."""

    def __init__(
        self,
        *,
        runner: SealedSkillCaseRunner,
        keyring: AttestationKeyring,
        key_id: str,
        profile: SealedEvaluatorProfile,
        policy: SealedSkillGatePolicy,
        clock: SealedSkillEvaluatorClock,
    ) -> None:
        if policy.digest() != profile.gate_policy_manifest_sha256:
            raise CandidateControlError("EVOLUTION_SKILL_SEALED_POLICY_MISMATCH")
        self._runner = runner
        self._keyring = keyring
        self._key_id = key_id
        self._profile = profile
        self._policy = policy
        self._clock = clock

    def attest(
        self,
        candidate: FrozenSkillCandidate,
        *,
        report: PairedEvaluationReport,
    ) -> SealedGateAttestation:
        frozen = candidate.frozen
        recomputed = PairedEvaluationGate().compare(
            frozen,
            report.baseline,
            report.candidate,
        )
        if recomputed != report or not report.gate.passed:
            raise CandidateControlError("EVOLUTION_SKILL_PUBLIC_GATE_REJECTED")
        baseline = self._runner.run(candidate.base_snapshot, role="baseline")
        evolved = self._runner.run(candidate.candidate_snapshot, role="candidate")
        required_charters = self._required_charters(candidate)
        self._validate_batches(
            candidate,
            baseline=baseline,
            evolved=evolved,
            required_charters=required_charters,
        )
        baseline_cases = {item.case_id: item for item in baseline.cases}
        no_regression = all(
            (
                not baseline_cases[item.case_id].passed
                or item.passed
            )
            and item.quality_micros >= baseline_cases[item.case_id].quality_micros
            for item in evolved.cases
        )
        high_risk_non_degrading = all(
            item.passed
            and item.quality_micros
            >= baseline_cases[item.case_id].quality_micros
            for item in evolved.cases
            if item.slice == "high_risk"
        )
        token_budget_passed = all(
            item.token_count <= self._policy.max_tokens_per_case
            and item.token_count
            <= baseline_cases[item.case_id].token_count
            + self._policy.max_token_increase_per_case
            for item in evolved.cases
        )
        latency_budget_passed = all(
            item.latency_ms <= self._policy.max_latency_ms_per_case
            and item.latency_ms
            <= baseline_cases[item.case_id].latency_ms
            + self._policy.max_latency_increase_ms_per_case
            for item in evolved.cases
        )
        runtime_activation_passed = all(
            item.runtime_activated for item in evolved.cases
        )
        component_charters_passed = all(
            {charter.evaluator_id for charter in item.charters}
            == required_charters
            and all(charter.passed for charter in item.charters)
            for item in evolved.cases
        )
        sealed_cases_passed = all(item.passed for item in evolved.cases)
        values = (
            sealed_cases_passed,
            no_regression,
            high_risk_non_degrading,
            token_budget_passed,
            latency_budget_passed,
            runtime_activation_passed,
            component_charters_passed,
        )
        evaluated_at = self._clock.now()
        if (
            evaluated_at.tzinfo is None
            or evaluated_at < baseline.evaluated_at
            or evaluated_at < evolved.evaluated_at
            or evaluated_at < report.candidate.evaluated_at
        ):
            raise CandidateControlError("EVOLUTION_SKILL_SEALED_CLOCK_INVALID")
        payload = SealedGatePayload(
            proposal_id=frozen.proposal.proposal_id,
            base_commit=frozen.proposal.base_commit,
            candidate_commit=frozen.proposal.candidate_commit,
            frozen_manifest_sha256=frozen.frozen_manifest_sha256,
            paired_report_sha256=PairedEvaluationGate.digest(report),
            sealed_case_set_sha256=evolved.case_set_sha256,
            gate_policy_manifest_sha256=self._policy.digest(),
            evaluator_id=self._profile.evaluator_id,
            evaluator_version=self._profile.evaluator_version,
            evaluated_at=evaluated_at,
            public_report_verified=True,
            sealed_cases_passed=sealed_cases_passed,
            no_sealed_case_regressed=no_regression,
            high_risk_singletons_non_degrading=high_risk_non_degrading,
            token_budget_passed=token_budget_passed,
            latency_budget_passed=latency_budget_passed,
            runtime_activation_passed=runtime_activation_passed,
            component_charters_passed=component_charters_passed,
            passed=all(values),
        )
        return self._keyring.sign(
            self._key_id,
            payload,
            frozen=frozen,
            report=report,
        )

    @staticmethod
    def _required_charters(candidate: FrozenSkillCandidate) -> set[str]:
        required: set[str] = set()
        for change in candidate.frozen.proposal.changes:
            values = REQUIRED_CHARTERS_BY_OBJECT_KIND.get(change.object_kind)
            if values is None:
                raise CandidateControlError(
                    "EVOLUTION_SKILL_SEALED_CHARTER_SCOPE_UNKNOWN"
                )
            required.update(values)
        return required

    def _validate_batches(
        self,
        candidate: FrozenSkillCandidate,
        *,
        baseline: SealedSkillCaseBatch,
        evolved: SealedSkillCaseBatch,
        required_charters: set[str],
    ) -> None:
        if (
            baseline.role != "baseline"
            or evolved.role != "candidate"
            or baseline.candidate_identity
            != candidate.frozen.proposal.base_commit
            or evolved.candidate_identity
            != candidate.frozen.proposal.candidate_commit
            or baseline.case_set_sha256 != evolved.case_set_sha256
            or evolved.case_set_sha256 != self._profile.sealed_case_set_sha256
        ):
            raise CandidateControlError("EVOLUTION_SKILL_SEALED_IDENTITY_MISMATCH")
        baseline_cases = {item.case_id: item for item in baseline.cases}
        evolved_cases = {item.case_id: item for item in evolved.cases}
        if set(baseline_cases) != set(evolved_cases) or any(
            baseline_cases[case_id].slice != item.slice
            for case_id, item in evolved_cases.items()
        ):
            raise CandidateControlError("EVOLUTION_SKILL_SEALED_CASE_SET_MISMATCH")
        if any(
            {charter.evaluator_id for charter in item.charters}
            != required_charters
            for item in (*baseline.cases, *evolved.cases)
        ):
            raise CandidateControlError("EVOLUTION_SKILL_SEALED_CHARTER_SCOPE_MISMATCH")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
