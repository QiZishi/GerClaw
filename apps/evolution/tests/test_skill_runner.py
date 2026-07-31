"""Docker-bound public structural runner tests for custom Skill candidates."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from gerclaw_api.modules.agent_harness.evolution_governance import (
    CandidateChange,
    CandidateProposal,
)
from gerclaw_api.modules.skill.models import SkillDefinition
from test_candidate_freeze import _base_repository
from test_runner import _Clock, _test_executor

from gerclaw_evolution import skill_runner as skill_runner_module
from gerclaw_evolution.candidate import CandidateFreezer
from gerclaw_evolution.contracts import (
    CandidateControlError,
    FrozenCandidate,
    FrozenRepositoryChange,
)
from gerclaw_evolution.git_repository import GitRepository
from gerclaw_evolution.runner import CaseIdentityAuthority
from gerclaw_evolution.skill_proposal import FrozenSkillCandidate
from gerclaw_evolution.skill_runner import SubprocessSkillPairedRunner


def _definition(*, version: str, revision: int, description: str) -> SkillDefinition:
    source_markdown = f"""---
id: medication-followup
name: 用药复诊准备
description: {description}
version: {version}
category: followup
parameters:
  topic:
    type: string
    description: 复诊主题
    maxLength: 100
tools:
  - search_knowledge
---
# 工作流

整理用户已提供的药物、剂量和过敏史,所有内容标记为待医生复核。
""".strip()
    return SkillDefinition(
        skill_id="medication-followup",
        name="用药复诊准备",
        description=description,
        version=version,
        parameter_schema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "复诊主题",
                    "minLength": 0,
                    "maxLength": 100,
                }
            },
            "required": ["topic"],
            "additionalProperties": False,
        },
        tool_names=["search_knowledge"],
        category="followup",
        source="custom",
        origin="generated",
        enabled=True,
        revision=revision,
        source_markdown=source_markdown,
    )


def _evaluator_repository(tmp_path: Path) -> GitRepository:
    repository, _ = _base_repository(tmp_path)
    source = Path(__file__).resolve().parents[2] / "api/src/gerclaw_api"
    target = repository.root / "apps/api/src/gerclaw_api"
    shutil.copytree(source, target, dirs_exist_ok=True)
    subprocess.run(
        ("git", "-C", str(repository.root), "add", "."),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ("git", "-C", str(repository.root), "commit", "-m", "trusted evaluator"),
        check=True,
        capture_output=True,
    )
    return repository


def _candidate(*, tamper_candidate: bool = False) -> FrozenSkillCandidate:
    base = _definition(
        version="1.0.0",
        revision=1,
        description="为老年患者整理需由医生复核的用药复诊信息",
    )
    candidate = _definition(
        version="1.1.0",
        revision=2,
        description="为老年患者整理药物、剂量和过敏史供医生复核",
    )
    base_hash = hashlib.sha256(base.source_markdown.encode()).hexdigest()
    candidate_hash = hashlib.sha256(candidate.source_markdown.encode()).hexdigest()
    change = CandidateChange(
        object_kind="skill.clinical",
        target="skill://clinical/opaque/candidate",
        content_digest=candidate_hash,
    )
    proposal = CandidateProposal(
        proposal_id="skill-proposal-0123456789abcdef0123456789abcdef",
        declared_track="immutable",
        base_commit=base_hash,
        candidate_commit=candidate_hash,
        risk_level="high",
        risk_reason_codes=("skill.immutable.review",),
        activation_condition_ids=(
            "paired.skill.v1",
            "sealed.skill.v1",
            "human.skill.v1",
        ),
        frozen_at=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
        changes=(change,),
    )
    repository_change = FrozenRepositoryChange(
        repository_path="database-skill-proposal/candidate.encrypted",
        object_kind=change.object_kind,
        target=change.target,
        content_digest=change.content_digest,
    )
    governance_digest = CandidateFreezer().governance_digest()
    frozen = FrozenCandidate(
        proposal=proposal,
        repository_changes=(repository_change,),
        governance_manifest_sha256=governance_digest,
        frozen_manifest_sha256=CandidateFreezer.frozen_digest(
            proposal,
            (repository_change,),
            governance_digest,
        ),
    )
    if tamper_candidate:
        candidate = candidate.model_copy(
            update={"description": "未写入 source_markdown 的篡改描述"}
        )
    return FrozenSkillCandidate(
        frozen=frozen,
        base_snapshot=base,
        candidate_snapshot=candidate,
        opaque_owner_binding="0" * 64,
    )


def _runner(
    repository: GitRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> SubprocessSkillPairedRunner:
    return SubprocessSkillPairedRunner(
        case_identity=CaseIdentityAuthority(b"c" * 32),
        executor=_test_executor(monkeypatch),
        evaluator_commit=repository.head(),
        allowed_tools=frozenset({"search_knowledge", "web_search", "search_memory"}),
        clock=_Clock(),
    )


def test_skill_runner_executes_four_slices_and_only_applicable_charters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _evaluator_repository(tmp_path)
    candidate = _candidate()
    runner = _runner(repository, monkeypatch)

    baseline = runner.run(repository, candidate=candidate, role="baseline")
    evolved = runner.run(repository, candidate=candidate, role="candidate")

    assert all(item.passed and item.runtime_activated for item in baseline.cases), [
        item.model_dump() for item in baseline.cases
    ]
    assert all(item.passed and item.runtime_activated for item in evolved.cases)
    assert {item.slice for item in evolved.cases} == {
        "normal",
        "complex",
        "high_risk",
        "elderly",
    }
    assert [item.evaluator_id for item in evolved.charters] == [
        "charter.plugin_runtime.v1",
        "charter.skill.v1",
    ]
    assert evolved.commit == candidate.frozen.proposal.candidate_commit
    assert evolved.execution_bundle_sha256 == baseline.execution_bundle_sha256
    assert evolved.evaluation_profile_sha256 == runner.profile_digest()


def test_skill_runner_hides_candidate_failure_and_rejects_wrong_evaluator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _evaluator_repository(tmp_path)
    candidate = _candidate(tamper_candidate=True)
    runner = _runner(repository, monkeypatch)

    evolved = runner.run(repository, candidate=candidate, role="candidate")

    normal = next(item for item in evolved.cases if item.slice == "normal")
    assert normal.passed is False
    assert all(item.runtime_activated for item in evolved.cases)
    charter_results = {item.evaluator_id: item.passed for item in evolved.charters}
    assert charter_results == {
        "charter.plugin_runtime.v1": True,
        "charter.skill.v1": False,
    }

    other_root = tmp_path / "other"
    other_root.mkdir()
    other, _ = _base_repository(other_root)
    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_SKILL_EVALUATOR_COMMIT_MISMATCH",
    ):
        runner.run(other, candidate=_candidate(), role="baseline")


def test_skill_runner_profile_binds_actual_process_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _evaluator_repository(tmp_path)
    runner = _runner(repository, monkeypatch)
    before = runner.profile_digest()

    monkeypatch.setattr(
        skill_runner_module,
        "_PROCESS_SCRIPT",
        skill_runner_module._PROCESS_SCRIPT + "\n# evaluator behavior changed\n",
    )

    assert runner.profile_digest() != before


@pytest.mark.skipif(
    not os.environ.get("GERCLAW_EVOLUTION_TEST_IMAGE_ID"),
    reason="content-addressed sandbox test image is not configured",
)
def test_skill_runner_uses_real_content_addressed_docker_sandbox(
    tmp_path: Path,
) -> None:
    from gerclaw_evolution.sandbox import DockerCandidateExecutor

    repository = _evaluator_repository(tmp_path)
    candidate = _candidate()
    runner = SubprocessSkillPairedRunner(
        case_identity=CaseIdentityAuthority(b"d" * 32),
        executor=DockerCandidateExecutor(image_id=os.environ["GERCLAW_EVOLUTION_TEST_IMAGE_ID"]),
        evaluator_commit=repository.head(),
        allowed_tools=frozenset({"search_knowledge", "web_search", "search_memory"}),
        clock=_Clock(),
    )

    baseline = runner.run(repository, candidate=candidate, role="baseline")
    evolved = runner.run(repository, candidate=candidate, role="candidate")

    assert all(item.passed and item.runtime_activated for item in baseline.cases)
    assert all(item.passed and item.runtime_activated for item in evolved.cases)
    assert baseline.execution_bundle_sha256 == evolved.execution_bundle_sha256
