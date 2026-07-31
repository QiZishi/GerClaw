"""Commit-bound routing runner tests with a test-local process adapter."""

from __future__ import annotations

import os
import site
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import MethodType

import pytest
from test_candidate_freeze import _base_repository

from gerclaw_evolution.candidate import CandidateFreezer
from gerclaw_evolution.contracts import (
    CandidateControlError,
    CandidateFileBinding,
    CandidateFreezeRequest,
    FrozenCandidate,
)
from gerclaw_evolution.git_repository import GitRepository, IsolatedWorktreeFactory
from gerclaw_evolution.runner import (
    CaseIdentityAuthority,
    RoutingRunnerProfile,
    RunnerClock,
    SubprocessRoutingPairedRunner,
)
from gerclaw_evolution.sandbox import (
    CandidateExecutionResult,
    DockerCandidateExecutor,
)

_ROUTING_FILES = ("contracts.py", "router.py", "__init__.py")
_ROUTER = "apps/api/src/gerclaw_api/modules/agent_harness/routing/router.py"


class _Clock(RunnerClock):
    def now(self) -> datetime:
        return datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        capture_output=True,
    )


def _paired_repositories(
    tmp_path: Path,
) -> tuple[GitRepository, GitRepository, FrozenCandidate]:
    baseline, _initial_commit = _base_repository(tmp_path)
    source_root = (
        Path(__file__).resolve().parents[2] / "api/src/gerclaw_api/modules/agent_harness/routing"
    )
    target_root = baseline.root / "apps/api/src/gerclaw_api/modules/agent_harness/routing"
    for name in _ROUTING_FILES:
        target = target_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / name).read_bytes())
    _git(baseline.root, "add", ".")
    _git(baseline.root, "commit", "-m", "routing baseline")
    base_commit = baseline.head()

    candidate = IsolatedWorktreeFactory(
        baseline,
        tmp_path / "worktrees",
    ).create(name="candidate-routing", base_commit=base_commit)
    _git(candidate.root, "config", "user.name", "GerClaw Test")
    _git(candidate.root, "config", "user.email", "test@invalid.local")
    router = candidate.root / _ROUTER
    candidate_source = (
        router.read_text(encoding="utf-8")
        .replace(
            r"(?:生成|形成|撰写|整理).{0,12}(?:报告|文档)|",
            r"(?:生成|形成|撰写|整理).{0,12}(?:文档)|",
        )
        .replace(
            "鉴别诊断|综合评估|五大处方|用药审查|",
            "鉴别诊断|五大处方|用药审查|",
        )
    )
    router.write_text(candidate_source, encoding="utf-8")
    _git(candidate.root, "add", _ROUTER)
    _git(candidate.root, "commit", "-m", "routing regression")
    frozen = CandidateFreezer().freeze(
        candidate,
        CandidateFreezeRequest(
            proposal_id="candidate.runner-test",
            declared_track="immutable",
            base_commit=base_commit,
            risk_level="high",
            risk_reason_codes=("routing.change",),
            activation_condition_ids=("paired.eval",),
            bindings=(
                CandidateFileBinding(
                    repository_path=_ROUTER,
                    object_kind="routing.strategy",
                    target="policy/routing/router.py",
                ),
            ),
        ),
    )
    return baseline, candidate, frozen


def _test_executor(monkeypatch: pytest.MonkeyPatch) -> DockerCandidateExecutor:
    executor = DockerCandidateExecutor(image_id="sha256:" + "a" * 64)

    def runtime_path(
        self: DockerCandidateExecutor,
        repository: GitRepository,
        repository_path: str,
    ) -> str:
        del self
        return str((repository.root / repository_path).resolve())

    def profile_digest(self: DockerCandidateExecutor) -> str:
        del self
        return "9" * 64

    def run(
        self: DockerCandidateExecutor,
        repository: GitRepository,
        args: tuple[str, ...],
        *,
        input_data: bytes | None,
        timeout: int,
    ) -> CandidateExecutionResult:
        del self
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join(
                (str(repository.root / "apps/api/src"), *site.getsitepackages())
            ),
        }
        result = subprocess.run(
            (sys.executable, "-S", *args),
            cwd=repository.root,
            env=environment,
            input=input_data,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
        with tempfile.TemporaryDirectory() as temporary:
            digest = repository.export_commit_archive(
                repository.head(),
                Path(temporary) / "candidate.tar",
            )
        return CandidateExecutionResult(
            stdout=result.stdout if result.returncode == 0 else None,
            execution_bundle_sha256=digest,
        )

    monkeypatch.setattr(executor, "runtime_path", MethodType(runtime_path, executor))
    monkeypatch.setattr(executor, "profile_digest", MethodType(profile_digest, executor))
    monkeypatch.setattr(executor, "run", MethodType(run, executor))
    return executor


def _runner(monkeypatch: pytest.MonkeyPatch) -> SubprocessRoutingPairedRunner:
    from gerclaw_evolution.runner import DEFAULT_ROUTING_PROFILE

    profile = RoutingRunnerProfile(
        policy=DEFAULT_ROUTING_PROFILE.policy,
        cases=DEFAULT_ROUTING_PROFILE.cases,
    )
    return SubprocessRoutingPairedRunner(
        case_identity=CaseIdentityAuthority(b"i" * 32),
        executor=_test_executor(monkeypatch),
        profile=profile,
        clock=_Clock(),
    )


def test_runner_imports_baseline_commit_and_uses_only_applicable_charter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline, _candidate, frozen = _paired_repositories(tmp_path)
    runner = _runner(monkeypatch)

    run = runner.run(
        baseline,
        frozen=frozen,
        role="baseline",
        expected_commit=baseline.head(),
    )

    assert all(case.passed and case.runtime_activated for case in run.cases)
    assert {case.slice for case in run.cases} == {
        "normal",
        "complex",
        "high_risk",
        "elderly",
    }
    assert all(case.case_id.startswith("case_") and len(case.case_id) == 37 for case in run.cases)
    assert [(item.evaluator_id, item.passed) for item in run.charters] == [
        ("charter.routing.v1", True)
    ]
    assert run.frozen_manifest_sha256 == frozen.frozen_manifest_sha256
    assert len(run.execution_bundle_sha256) == 64
    assert run.evaluation_profile_sha256 == runner.profile_digest()


def test_candidate_regression_fails_without_claiming_unexecuted_charters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _baseline, candidate, frozen = _paired_repositories(tmp_path)

    run = _runner(monkeypatch).run(
        candidate,
        frozen=frozen,
        role="candidate",
        expected_commit=candidate.head(),
    )

    complex_case = next(case for case in run.cases if case.slice == "complex")
    assert complex_case.passed is False
    assert complex_case.quality_micros == 0
    assert complex_case.runtime_activated is True
    assert [(item.evaluator_id, item.passed) for item in run.charters] == [
        ("charter.routing.v1", False)
    ]


def test_runner_rejects_forged_freeze_manifest_and_non_docker_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline, _candidate, frozen = _paired_repositories(tmp_path)
    forged = frozen.model_copy(update={"frozen_manifest_sha256": "0" * 64})

    with pytest.raises(CandidateControlError, match="EVOLUTION_FROZEN_MANIFEST_INVALID"):
        _runner(monkeypatch).run(
            baseline,
            frozen=forged,
            role="baseline",
            expected_commit=baseline.head(),
        )
    with pytest.raises(CandidateControlError, match="EVOLUTION_RUNNER_EXECUTOR_INVALID"):
        SubprocessRoutingPairedRunner(
            case_identity=CaseIdentityAuthority(b"i" * 32),
            executor=object(),  # type: ignore[arg-type]
        )
