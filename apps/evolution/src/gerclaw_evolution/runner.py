"""Out-of-process paired runner for the real deterministic routing path."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

from gerclaw_api.modules.agent_harness.evolution_governance import COMPONENT_CHARTERS
from pydantic import BaseModel, ConfigDict, Field

from gerclaw_evolution.candidate import CandidateFreezer
from gerclaw_evolution.contracts import CandidateControlError, FrozenCandidate
from gerclaw_evolution.evaluation import (
    CharterObservation,
    EvaluationCaseObservation,
    EvaluationRole,
    EvaluationRun,
    EvaluationSlice,
)
from gerclaw_evolution.git_repository import GitRepository
from gerclaw_evolution.sandbox import DockerCandidateExecutor

_STRICT = ConfigDict(extra="forbid", frozen=True)
_RUNNER_ID = "runner.routing-charter"
_RUNNER_VERSION = "routing-charter-v1"
_PROCESS_SCRIPT = """
import json
import sys
from gerclaw_api.modules.agent_harness.routing import (
    DeterministicRouter,
    RoutingInput,
    RoutingPolicy,
)
import gerclaw_api.modules.agent_harness.routing.router as router_module

request = json.load(sys.stdin)
router = DeterministicRouter(RoutingPolicy.model_validate(request["policy"]))
results = []
for case in request["cases"]:
    decision = router.decide(RoutingInput.model_validate(case["input"]))
    results.append({
        "name": case["name"],
        "route": decision.route.value,
        "model_allowed": decision.model_allowed,
    })
print(json.dumps({
    "schema_version": "routing-process-output-v1",
    "module_file": router_module.__file__,
    "results": results,
}, sort_keys=True))
"""


class RoutingEvaluationCase(BaseModel):
    """Controller-owned public case; only its HMAC ID enters the report."""

    model_config = _STRICT

    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,99}$")
    slice: EvaluationSlice
    routing_input: dict[str, object]
    expected_route: Literal["quick", "standard", "deep", "emergency"]
    expected_model_allowed: bool


class RoutingRunnerProfile(BaseModel):
    """Exact public runner inputs bound into every paired run."""

    model_config = _STRICT

    schema_version: Literal["routing-runner-profile-v1"] = "routing-runner-profile-v1"
    policy: dict[str, int]
    cases: tuple[RoutingEvaluationCase, ...] = Field(min_length=4, max_length=100)
    affected_object_kinds: tuple[Literal["routing.strategy"], ...] = ("routing.strategy",)


class _ProcessCaseResult(BaseModel):
    model_config = _STRICT

    name: str
    route: Literal["quick", "standard", "deep", "emergency"]
    model_allowed: bool


class _ProcessOutput(BaseModel):
    model_config = _STRICT

    schema_version: Literal["routing-process-output-v1"]
    module_file: str = Field(min_length=1, max_length=1_024)
    results: tuple[_ProcessCaseResult, ...]


class RunnerClock(Protocol):
    def now(self) -> datetime: ...


class SystemRunnerClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CaseIdentityAuthority:
    """Controller-only HMAC authority for non-descriptive public case IDs."""

    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.secret) < 32:
            raise CandidateControlError("EVOLUTION_CASE_IDENTITY_KEY_INVALID")

    def opaque_id(self, case_name: str) -> str:
        digest = hmac.new(
            self.secret,
            f"gerclaw.evolution.case.v1:{case_name}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"case_{digest[:32]}"


DEFAULT_ROUTING_PROFILE = RoutingRunnerProfile(
    policy={
        "quick_max_characters": 80,
        "deep_min_characters": 1_000,
        "deep_attachment_count": 2,
        "deep_capability_count": 2,
    },
    cases=(
        RoutingEvaluationCase(
            name="routing.normal.quick",
            slice="normal",
            routing_input={"message": "1 + 1 = ?"},
            expected_route="quick",
            expected_model_allowed=True,
        ),
        RoutingEvaluationCase(
            name="routing.complex.report",
            slice="complex",
            routing_input={
                "message": "请综合评估并生成报告",
                "medical_content": True,
            },
            expected_route="deep",
            expected_model_allowed=True,
        ),
        RoutingEvaluationCase(
            name="routing.high-risk.short-circuit",
            slice="high_risk",
            routing_input={
                "message": "您好",
                "high_risk_detected": True,
            },
            expected_route="emergency",
            expected_model_allowed=False,
        ),
        RoutingEvaluationCase(
            name="routing.elderly.medical",
            slice="elderly",
            routing_input={
                "message": "老人最近头晕",
                "medical_content": True,
            },
            expected_route="standard",
            expected_model_allowed=True,
        ),
    ),
)


class SubprocessRoutingPairedRunner:
    """Execute baseline and candidate code from their own clean worktrees."""

    def __init__(
        self,
        *,
        case_identity: CaseIdentityAuthority,
        executor: DockerCandidateExecutor,
        profile: RoutingRunnerProfile = DEFAULT_ROUTING_PROFILE,
        clock: RunnerClock | None = None,
        freezer: CandidateFreezer | None = None,
        route_timeout_seconds: int = 30,
    ) -> None:
        if route_timeout_seconds < 1:
            raise CandidateControlError("EVOLUTION_RUNNER_TIMEOUT_INVALID")
        if type(executor) is not DockerCandidateExecutor:
            raise CandidateControlError("EVOLUTION_RUNNER_EXECUTOR_INVALID")
        self._case_identity = case_identity
        self._executor = executor
        self._profile = profile
        self._clock = clock or SystemRunnerClock()
        self._freezer = freezer or CandidateFreezer()
        self._route_timeout = route_timeout_seconds

    def run(
        self,
        repository: GitRepository,
        *,
        frozen: FrozenCandidate,
        role: EvaluationRole,
        expected_commit: str,
    ) -> EvaluationRun:
        self._freezer.assert_manifest(frozen)
        repository.require_clean()
        if repository.head() != expected_commit:
            raise CandidateControlError("EVOLUTION_RUNNER_COMMIT_MISMATCH")
        expected_identity = (
            frozen.proposal.base_commit if role == "baseline" else frozen.proposal.candidate_commit
        )
        if expected_commit != expected_identity or {
            change.object_kind for change in frozen.repository_changes
        } != set(self._profile.affected_object_kinds):
            raise CandidateControlError("EVOLUTION_RUNNER_SCOPE_MISMATCH")
        if role == "candidate":
            self._freezer.assert_unchanged(repository, frozen)
        started = time.monotonic_ns()
        process_output, execution_bundle_sha256 = self._run_route_process(repository)
        elapsed_ms = max(0, (time.monotonic_ns() - started) // 1_000_000)
        repository.require_clean()
        if repository.head() != expected_commit:
            raise CandidateControlError("EVOLUTION_RUNNER_COMMIT_CHANGED")
        if process_output is None and role == "baseline":
            raise CandidateControlError("EVOLUTION_BASELINE_RUNNER_FAILED")
        expected_module = self._executor.runtime_path(
            repository,
            "apps/api/src/gerclaw_api/modules/agent_harness/routing/router.py",
        )
        module_activated = (
            process_output is not None and process_output.module_file == expected_module
        )
        results_by_name = (
            {result.name: result for result in process_output.results}
            if process_output is not None
            else {}
        )
        per_case_latency = elapsed_ms // len(self._profile.cases)
        observations = tuple(
            self._observation(
                case,
                results_by_name.get(case.name),
                runtime_activated=module_activated,
                latency_ms=per_case_latency,
            )
            for case in self._profile.cases
        )
        routing_charter_passed = all(
            item.passed and item.runtime_activated for item in observations
        )
        evaluated_at = self._clock.now()
        if evaluated_at.tzinfo is None:
            raise CandidateControlError("EVOLUTION_RUNNER_CLOCK_INVALID")
        return EvaluationRun(
            role=role,
            commit=expected_commit,
            runner_id=_RUNNER_ID,
            runner_version=_RUNNER_VERSION,
            evaluation_profile_sha256=self.profile_digest(),
            frozen_manifest_sha256=frozen.frozen_manifest_sha256,
            execution_bundle_sha256=execution_bundle_sha256,
            evaluated_at=evaluated_at,
            cases=observations,
            charters=tuple(
                CharterObservation(evaluator_id=evaluator_id, passed=routing_charter_passed)
                for charter in COMPONENT_CHARTERS
                if charter.component == "routing"
                for evaluator_id in charter.sealed_evaluator_ids
            ),
        )

    def profile_digest(self) -> str:
        payload = {
            "runner_id": _RUNNER_ID,
            "runner_version": _RUNNER_VERSION,
            "executor_profile_sha256": self._executor.profile_digest(),
            "profile": self._profile.model_dump(mode="json"),
            "charters": [
                charter.model_dump(mode="json")
                for charter in COMPONENT_CHARTERS
                if charter.component == "routing"
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _run_route_process(
        self,
        repository: GitRepository,
    ) -> tuple[_ProcessOutput | None, str]:
        request = {
            "policy": self._profile.policy,
            "cases": [
                {"name": case.name, "input": case.routing_input} for case in self._profile.cases
            ],
        }
        execution = self._executor.run(
            repository,
            ("-c", _PROCESS_SCRIPT),
            input_data=json.dumps(request, separators=(",", ":")).encode(),
            timeout=self._route_timeout,
        )
        if execution.stdout is None:
            return None, execution.execution_bundle_sha256
        try:
            output = _ProcessOutput.model_validate_json(execution.stdout)
        except ValueError:
            return None, execution.execution_bundle_sha256
        if {item.name for item in output.results} != {case.name for case in self._profile.cases}:
            return None, execution.execution_bundle_sha256
        return output, execution.execution_bundle_sha256

    def _observation(
        self,
        case: RoutingEvaluationCase,
        result: _ProcessCaseResult | None,
        *,
        runtime_activated: bool,
        latency_ms: int,
    ) -> EvaluationCaseObservation:
        passed = (
            result is not None
            and result.route == case.expected_route
            and result.model_allowed == case.expected_model_allowed
        )
        return EvaluationCaseObservation(
            case_id=self._case_identity.opaque_id(case.name),
            slice=case.slice,
            passed=passed,
            quality_micros=1_000_000 if passed else 0,
            token_count=0,
            latency_ms=latency_ms,
            runtime_activated=runtime_activated,
        )
