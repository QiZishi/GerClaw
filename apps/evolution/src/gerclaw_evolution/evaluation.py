"""Content-free paired evaluation and non-regression gates."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from gerclaw_api.modules.agent_harness.evolution_governance import (
    COMPONENT_CHARTERS,
    REQUIRED_CHARTERS_BY_OBJECT_KIND,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_evolution.contracts import CandidateControlError, FrozenCandidate

_STRICT = ConfigDict(extra="forbid", frozen=True)
_GIT_SHA = r"^[a-f0-9]{40}$"
_ID = r"^[a-z][a-z0-9_.-]{2,99}$"
_CASE_ID = r"^case_[a-f0-9]{32}$"
EvaluationSlice = Literal["normal", "complex", "high_risk", "elderly"]
EvaluationRole = Literal["baseline", "candidate"]


class EvaluationCaseObservation(BaseModel):
    """One PHI-free result; no prompt, answer, evidence, or Provider payload."""

    model_config = _STRICT

    schema_version: Literal["evaluation-case-observation-v1"] = "evaluation-case-observation-v1"
    case_id: str = Field(pattern=_CASE_ID)
    slice: EvaluationSlice
    passed: bool
    quality_micros: int = Field(ge=0, le=1_000_000)
    token_count: int = Field(ge=0, le=10_000_000)
    latency_ms: int = Field(ge=0, le=3_600_000)
    runtime_activated: bool


class CharterObservation(BaseModel):
    """Public component-charter regression verdict without sealed case data."""

    model_config = _STRICT

    evaluator_id: str = Field(pattern=_ID)
    passed: bool


class EvaluationRun(BaseModel):
    """Commit-bound observations from one evaluator execution."""

    model_config = _STRICT

    schema_version: Literal["evaluation-run-v1"] = "evaluation-run-v1"
    role: EvaluationRole
    commit: str = Field(pattern=_GIT_SHA)
    runner_id: str = Field(pattern=_ID)
    runner_version: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,63}$")
    evaluation_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    frozen_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluated_at: datetime
    cases: tuple[EvaluationCaseObservation, ...] = Field(min_length=4, max_length=10_000)
    charters: tuple[CharterObservation, ...] = Field(min_length=1, max_length=30)

    @field_validator("evaluated_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("evaluation time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_complete_unique_case_set(self) -> EvaluationRun:
        case_ids = [item.case_id for item in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case IDs must be unique")
        if {item.slice for item in self.cases} != {
            "normal",
            "complex",
            "high_risk",
            "elderly",
        }:
            raise ValueError("evaluation must cover all required slices")
        charter_ids = [item.evaluator_id for item in self.charters]
        known = {
            evaluator_id
            for charter in COMPONENT_CHARTERS
            for evaluator_id in charter.sealed_evaluator_ids
        }
        if (
            len(charter_ids) != len(set(charter_ids))
            or not set(charter_ids).issubset(known)
        ):
            raise ValueError("evaluation charters must be unique known controller charters")
        return self


class PairedGateSummary(BaseModel):
    """Hard public gates that an average score cannot offset."""

    model_config = _STRICT

    no_passed_case_regressed: bool
    all_cases_non_degrading: bool
    all_slices_non_degrading: bool
    high_risk_cases_non_degrading: bool
    all_runtime_paths_activated: bool
    all_component_charters_passed: bool
    passed: bool

    @model_validator(mode="after")
    def derive_passed_from_every_gate(self) -> PairedGateSummary:
        expected = all(
            (
                self.no_passed_case_regressed,
                self.all_cases_non_degrading,
                self.all_slices_non_degrading,
                self.high_risk_cases_non_degrading,
                self.all_runtime_paths_activated,
                self.all_component_charters_passed,
            )
        )
        if self.passed != expected:
            raise ValueError("paired gate passed value does not match its mandatory gates")
        return self


class PairedEvaluationReport(BaseModel):
    """Baseline/candidate report bound to one frozen proposal."""

    model_config = _STRICT

    schema_version: Literal["paired-evaluation-report-v1"] = "paired-evaluation-report-v1"
    proposal_id: str = Field(pattern=_ID)
    base_commit: str = Field(pattern=_GIT_SHA)
    candidate_commit: str = Field(pattern=_GIT_SHA)
    frozen_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline: EvaluationRun
    candidate: EvaluationRun
    gate: PairedGateSummary

    @model_validator(mode="after")
    def bind_run_identities(self) -> PairedEvaluationReport:
        if self.baseline.role != "baseline" or self.baseline.commit != self.base_commit:
            raise ValueError("baseline run identity does not match the report")
        if self.candidate.role != "candidate" or self.candidate.commit != self.candidate_commit:
            raise ValueError("candidate run identity does not match the report")
        return self


class PairedEvaluationGate:
    """Construct reports; callers cannot submit their own gate booleans."""

    __slots__ = ()

    def compare(
        self,
        frozen: FrozenCandidate,
        baseline: EvaluationRun,
        candidate: EvaluationRun,
    ) -> PairedEvaluationReport:
        if baseline.role != "baseline" or baseline.commit != frozen.proposal.base_commit:
            raise CandidateControlError("EVOLUTION_BASELINE_IDENTITY_MISMATCH")
        if candidate.role != "candidate" or candidate.commit != frozen.proposal.candidate_commit:
            raise CandidateControlError("EVOLUTION_CANDIDATE_IDENTITY_MISMATCH")
        if (
            baseline.frozen_manifest_sha256 != frozen.frozen_manifest_sha256
            or candidate.frozen_manifest_sha256 != frozen.frozen_manifest_sha256
        ):
            raise CandidateControlError("EVOLUTION_RUN_FROZEN_MANIFEST_MISMATCH")
        if (
            baseline.runner_id != candidate.runner_id
            or baseline.runner_version != candidate.runner_version
            or baseline.evaluation_profile_sha256 != candidate.evaluation_profile_sha256
        ):
            raise CandidateControlError("EVOLUTION_EVALUATOR_PROFILE_MISMATCH")
        baseline_by_id = {item.case_id: item for item in baseline.cases}
        candidate_by_id = {item.case_id: item for item in candidate.cases}
        if set(baseline_by_id) != set(candidate_by_id):
            raise CandidateControlError("EVOLUTION_PAIRED_CASE_SET_MISMATCH")
        if any(
            baseline_by_id[case_id].slice != observation.slice
            for case_id, observation in candidate_by_id.items()
        ):
            raise CandidateControlError("EVOLUTION_PAIRED_SLICE_MISMATCH")
        baseline_charters = {item.evaluator_id for item in baseline.charters}
        candidate_charters = {item.evaluator_id for item in candidate.charters}
        required_charters: set[str] = set()
        for change in frozen.repository_changes:
            expected = REQUIRED_CHARTERS_BY_OBJECT_KIND.get(change.object_kind)
            if expected is None:
                raise CandidateControlError("EVOLUTION_CHARTER_SCOPE_UNKNOWN")
            required_charters.update(expected)
        if (
            baseline_charters != candidate_charters
            or not required_charters.issubset(candidate_charters)
        ):
            raise CandidateControlError("EVOLUTION_CHARTER_SCOPE_MISMATCH")

        no_passed_case_regressed = all(
            not baseline_by_id[case_id].passed or observation.passed
            for case_id, observation in candidate_by_id.items()
        )
        all_cases_non_degrading = all(
            observation.quality_micros >= baseline_by_id[case_id].quality_micros
            for case_id, observation in candidate_by_id.items()
        )
        all_slices_non_degrading = all(
            self._slice_quality(candidate.cases, slice_name)
            >= self._slice_quality(baseline.cases, slice_name)
            for slice_name in ("normal", "complex", "high_risk", "elderly")
        )
        high_risk_non_degrading = all(
            observation.quality_micros >= baseline_by_id[case_id].quality_micros
            and (not baseline_by_id[case_id].passed or observation.passed)
            for case_id, observation in candidate_by_id.items()
            if observation.slice == "high_risk"
        )
        all_runtime_paths_activated = all(item.runtime_activated for item in candidate.cases)
        all_component_charters_passed = all(item.passed for item in candidate.charters)
        values = (
            no_passed_case_regressed,
            all_cases_non_degrading,
            all_slices_non_degrading,
            high_risk_non_degrading,
            all_runtime_paths_activated,
            all_component_charters_passed,
        )
        return PairedEvaluationReport(
            proposal_id=frozen.proposal.proposal_id,
            base_commit=frozen.proposal.base_commit,
            candidate_commit=frozen.proposal.candidate_commit,
            frozen_manifest_sha256=frozen.frozen_manifest_sha256,
            baseline=baseline,
            candidate=candidate,
            gate=PairedGateSummary(
                no_passed_case_regressed=no_passed_case_regressed,
                all_cases_non_degrading=all_cases_non_degrading,
                all_slices_non_degrading=all_slices_non_degrading,
                high_risk_cases_non_degrading=high_risk_non_degrading,
                all_runtime_paths_activated=all_runtime_paths_activated,
                all_component_charters_passed=all_component_charters_passed,
                passed=all(values),
            ),
        )

    @staticmethod
    def digest(report: PairedEvaluationReport) -> str:
        encoded = json.dumps(
            report.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _slice_quality(
        cases: tuple[EvaluationCaseObservation, ...],
        slice_name: str,
    ) -> int:
        values = [item.quality_micros for item in cases if item.slice == slice_name]
        return sum(values) // len(values)
