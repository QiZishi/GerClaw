"""Docker-isolated paired runner for encrypted custom Skill candidates."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Protocol

from gerclaw_api.modules.agent_harness.evolution_governance import COMPONENT_CHARTERS
from pydantic import BaseModel, ConfigDict, Field

from gerclaw_evolution.candidate import CandidateFreezer
from gerclaw_evolution.contracts import CandidateControlError
from gerclaw_evolution.evaluation import (
    CharterObservation,
    EvaluationCaseObservation,
    EvaluationRole,
    EvaluationRun,
    EvaluationSlice,
)
from gerclaw_evolution.git_repository import GitRepository
from gerclaw_evolution.runner import CaseIdentityAuthority, SystemRunnerClock
from gerclaw_evolution.sandbox import DockerCandidateExecutor
from gerclaw_evolution.skill_proposal import FrozenSkillCandidate

_STRICT = ConfigDict(extra="forbid", frozen=True)
_RUNNER_ID = "runner.skill-runtime"
_RUNNER_VERSION = "skill-runtime-v1"
_CASES: tuple[tuple[str, EvaluationSlice], ...] = (
    ("skill.normal.roundtrip", "normal"),
    ("skill.complex.schema", "complex"),
    ("skill.high-risk.runtime-profile", "high_risk"),
    ("skill.elderly.agentscope-activation", "elderly"),
)
_MODULE_PATHS = (
    "apps/api/src/gerclaw_api/modules/skill/loader.py",
    "apps/api/src/gerclaw_api/modules/skill/security.py",
    "apps/api/src/gerclaw_api/modules/skill/agentscope_adapter.py",
)
_PROCESS_SCRIPT = """
import hashlib
import json
import sys

import gerclaw_api.modules.skill.agentscope_adapter as adapter_module
import gerclaw_api.modules.skill.loader as loader_module
import gerclaw_api.modules.skill.security as security_module
from gerclaw_api.modules.skill.agentscope_adapter import to_agentscope_skill
from gerclaw_api.modules.skill.loader import parse_skill_markdown
from gerclaw_api.modules.skill.models import SkillDefinition
from gerclaw_api.modules.skill.security import enforce_skill_runtime_profile

request = json.load(sys.stdin)
snapshot = SkillDefinition.model_validate(request["snapshot"])
allowed_tools = frozenset(request["allowed_tools"])
expected_hash = request["expected_content_sha256"]
source_hash = hashlib.sha256(snapshot.source_markdown.encode()).hexdigest()
parsed = parse_skill_markdown(
    snapshot.source_markdown,
    source=snapshot.source,
    origin=snapshot.origin,
    enabled=snapshot.enabled,
    revision=snapshot.revision,
    allowed_tools=allowed_tools,
)
identity_fields = (
    "skill_id",
    "name",
    "description",
    "version",
    "parameter_schema",
    "tool_names",
    "category",
    "source",
    "origin",
    "enabled",
    "revision",
    "source_markdown",
)
roundtrip = all(getattr(parsed, field) == getattr(snapshot, field) for field in identity_fields)
schema = parsed.parameter_schema
schema_bounded = (
    schema.get("type") == "object"
    and schema.get("additionalProperties") is False
    and isinstance(schema.get("properties"), dict)
    and isinstance(schema.get("required"), list)
)
enforce_skill_runtime_profile(parsed)
runtime_profile = set(parsed.tool_names).issubset(allowed_tools)
activated = to_agentscope_skill(parsed)
agentscope_activation = (
    activated.name == parsed.name
    and activated.description == parsed.description
    and activated.dir == f"skill://{parsed.skill_id}@{parsed.version}"
    and bool(activated.markdown.strip())
)
results = {
    "skill.normal.roundtrip": source_hash == expected_hash and roundtrip,
    "skill.complex.schema": schema_bounded,
    "skill.high-risk.runtime-profile": runtime_profile,
    "skill.elderly.agentscope-activation": agentscope_activation,
}
print(json.dumps({
    "schema_version": "skill-process-output-v1",
    "content_sha256": source_hash,
    "module_files": [
        loader_module.__file__,
        security_module.__file__,
        adapter_module.__file__,
    ],
    "results": [
        {"name": name, "passed": passed}
        for name, passed in results.items()
    ],
}, sort_keys=True))
"""


class _ProcessCaseResult(BaseModel):
    model_config = _STRICT

    name: str
    passed: bool


class _ProcessOutput(BaseModel):
    model_config = _STRICT

    schema_version: str = Field(pattern=r"^skill-process-output-v1$")
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    module_files: tuple[str, str, str]
    results: tuple[_ProcessCaseResult, ...]


class SkillRunnerClock(Protocol):
    def now(self) -> datetime: ...


class SubprocessSkillPairedRunner:
    """Re-validate one protected Skill snapshot inside the exact Docker executor."""

    def __init__(
        self,
        *,
        case_identity: CaseIdentityAuthority,
        executor: DockerCandidateExecutor,
        evaluator_commit: str,
        allowed_tools: frozenset[str],
        clock: SkillRunnerClock | None = None,
        freezer: CandidateFreezer | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        if (
            type(executor) is not DockerCandidateExecutor
            or not len(evaluator_commit) == 40
            or any(character not in "0123456789abcdef" for character in evaluator_commit)
            or not allowed_tools
            or timeout_seconds < 1
        ):
            raise CandidateControlError("EVOLUTION_SKILL_RUNNER_CONFIG_INVALID")
        self._case_identity = case_identity
        self._executor = executor
        self._evaluator_commit = evaluator_commit
        self._allowed_tools = allowed_tools
        self._clock = clock or SystemRunnerClock()
        self._freezer = freezer or CandidateFreezer()
        self._timeout = timeout_seconds

    def run(
        self,
        repository: GitRepository,
        *,
        candidate: FrozenSkillCandidate,
        role: EvaluationRole,
    ) -> EvaluationRun:
        frozen = candidate.frozen
        self._freezer.assert_manifest(frozen)
        repository.require_clean()
        if repository.head() != self._evaluator_commit:
            raise CandidateControlError("EVOLUTION_SKILL_EVALUATOR_COMMIT_MISMATCH")
        if len(frozen.repository_changes) != 1 or frozen.repository_changes[0].object_kind not in {
            "skill.clinical",
            "skill.tooling",
        }:
            raise CandidateControlError("EVOLUTION_SKILL_RUNNER_SCOPE_MISMATCH")
        snapshot = candidate.base_snapshot if role == "baseline" else candidate.candidate_snapshot
        expected_identity = (
            frozen.proposal.base_commit if role == "baseline" else frozen.proposal.candidate_commit
        )
        if self._content_hash(snapshot.source_markdown) != expected_identity:
            raise CandidateControlError("EVOLUTION_SKILL_SNAPSHOT_IDENTITY_MISMATCH")

        started = time.monotonic_ns()
        output, execution_bundle_sha256 = self._run_process(
            repository,
            snapshot=snapshot.model_dump(mode="json"),
            expected_identity=expected_identity,
        )
        elapsed_ms = max(0, (time.monotonic_ns() - started) // 1_000_000)
        repository.require_clean()
        if repository.head() != self._evaluator_commit:
            raise CandidateControlError("EVOLUTION_SKILL_EVALUATOR_CHANGED")
        if output is None and role == "baseline":
            raise CandidateControlError("EVOLUTION_SKILL_BASELINE_RUNNER_FAILED")

        expected_modules = tuple(
            self._executor.runtime_path(repository, path) for path in _MODULE_PATHS
        )
        runtime_activated = (
            output is not None
            and output.content_sha256 == expected_identity
            and output.module_files == expected_modules
        )
        results = {item.name: item.passed for item in output.results} if output is not None else {}
        per_case_latency = elapsed_ms // len(_CASES)
        observations = tuple(
            EvaluationCaseObservation(
                case_id=self._case_identity.opaque_id(name),
                slice=slice_name,
                passed=bool(results.get(name)),
                quality_micros=1_000_000 if results.get(name) else 0,
                token_count=0,
                latency_ms=per_case_latency,
                runtime_activated=runtime_activated,
            )
            for name, slice_name in _CASES
        )
        charter_passed = all(item.passed and item.runtime_activated for item in observations)
        evaluated_at = self._clock.now()
        if evaluated_at.tzinfo is None:
            raise CandidateControlError("EVOLUTION_SKILL_RUNNER_CLOCK_INVALID")
        return EvaluationRun(
            role=role,
            commit=expected_identity,
            runner_id=_RUNNER_ID,
            runner_version=_RUNNER_VERSION,
            evaluation_profile_sha256=self.profile_digest(),
            frozen_manifest_sha256=frozen.frozen_manifest_sha256,
            execution_bundle_sha256=execution_bundle_sha256,
            evaluated_at=evaluated_at,
            cases=observations,
            charters=tuple(
                CharterObservation(
                    evaluator_id=evaluator_id,
                    passed=charter_passed,
                )
                for charter in COMPONENT_CHARTERS
                if charter.component in {"plugin_runtime", "skill"}
                for evaluator_id in charter.sealed_evaluator_ids
            ),
        )

    def profile_digest(self) -> str:
        payload = {
            "runner_id": _RUNNER_ID,
            "runner_version": _RUNNER_VERSION,
            "executor_profile_sha256": self._executor.profile_digest(),
            "evaluator_commit": self._evaluator_commit,
            "allowed_tools": sorted(self._allowed_tools),
            "cases": _CASES,
            "module_paths": _MODULE_PATHS,
            "process_script_sha256": hashlib.sha256(
                _PROCESS_SCRIPT.encode()
            ).hexdigest(),
            "charters": [
                charter.model_dump(mode="json")
                for charter in COMPONENT_CHARTERS
                if charter.component in {"plugin_runtime", "skill"}
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _run_process(
        self,
        repository: GitRepository,
        *,
        snapshot: dict[str, object],
        expected_identity: str,
    ) -> tuple[_ProcessOutput | None, str]:
        execution = self._executor.run(
            repository,
            ("-c", _PROCESS_SCRIPT),
            input_data=json.dumps(
                {
                    "snapshot": snapshot,
                    "expected_content_sha256": expected_identity,
                    "allowed_tools": sorted(self._allowed_tools),
                },
                separators=(",", ":"),
            ).encode(),
            timeout=self._timeout,
        )
        if execution.stdout is None:
            return None, execution.execution_bundle_sha256
        try:
            output = _ProcessOutput.model_validate_json(execution.stdout)
        except ValueError:
            return None, execution.execution_bundle_sha256
        if {item.name for item in output.results} != {name for name, _ in _CASES}:
            return None, execution.execution_bundle_sha256
        return output, execution.execution_bundle_sha256

    @staticmethod
    def _content_hash(source_markdown: str) -> str:
        return hashlib.sha256(source_markdown.encode()).hexdigest()
