"""Real Git worktree tests for candidate isolation and freeze."""

from __future__ import annotations

import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from gerclaw_evolution.candidate import CandidateFreezer
from gerclaw_evolution.contracts import (
    CandidateControlError,
    CandidateFileBinding,
    CandidateFreezeRequest,
    FreezeClock,
)
from gerclaw_evolution.git_repository import GitRepository, IsolatedWorktreeFactory

_ROUTER = "apps/api/src/gerclaw_api/modules/agent_harness/routing/router.py"


class _Clock(FreezeClock):
    def now(self) -> datetime:
        return datetime(2026, 7, 30, 8, 0, tzinfo=UTC)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _base_repository(tmp_path: Path) -> tuple[GitRepository, str]:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "GerClaw Test")
    _git(root, "config", "user.email", "test@invalid.local")
    target = root / _ROUTER
    target.parent.mkdir(parents=True)
    target.write_text("ROUTE = 'standard'\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    return GitRepository(root), _git(root, "rev-parse", "HEAD")


def _request(base_commit: str, *bindings: CandidateFileBinding) -> CandidateFreezeRequest:
    return CandidateFreezeRequest(
        proposal_id="candidate.routing-test",
        declared_track="immutable",
        base_commit=base_commit,
        risk_level="high",
        risk_reason_codes=("routing.change",),
        activation_condition_ids=("paired.eval", "sealed.eval"),
        bindings=bindings
        or (
            CandidateFileBinding(
                repository_path=_ROUTER,
                object_kind="routing.strategy",
                target="policy/routing/router.py",
            ),
        ),
    )


def _candidate_worktree(
    tmp_path: Path,
) -> tuple[GitRepository, GitRepository, str]:
    source, base_commit = _base_repository(tmp_path)
    candidate = IsolatedWorktreeFactory(source, tmp_path / "worktrees").create(
        name="candidate-routing",
        base_commit=base_commit,
    )
    _git(candidate.root, "config", "user.name", "GerClaw Test")
    _git(candidate.root, "config", "user.email", "test@invalid.local")
    return source, candidate, base_commit


def _commit_candidate(candidate: GitRepository, *, content: str = "ROUTE = 'deep'\n") -> str:
    (candidate.root / _ROUTER).write_text(content, encoding="utf-8")
    _git(candidate.root, "add", _ROUTER)
    _git(candidate.root, "commit", "-m", "candidate")
    return candidate.head()


def test_freeze_binds_real_diff_commit_and_governance_manifest(tmp_path: Path) -> None:
    _source, candidate, base_commit = _candidate_worktree(tmp_path)
    candidate_commit = _commit_candidate(candidate)

    frozen = CandidateFreezer(clock=_Clock()).freeze(candidate, _request(base_commit))

    assert frozen.proposal.candidate_commit == candidate_commit
    assert frozen.proposal.frozen_at == datetime(2026, 7, 30, 8, 0, tzinfo=UTC)
    assert frozen.repository_changes[0].repository_path == _ROUTER
    assert frozen.repository_changes[0].content_digest == frozen.proposal.changes[0].content_digest
    assert len(frozen.governance_manifest_sha256) == 64
    assert len(frozen.frozen_manifest_sha256) == 64
    CandidateFreezer(clock=_Clock()).assert_unchanged(candidate, frozen)


def test_worktree_name_traversal_and_repository_path_traversal_fail_closed(
    tmp_path: Path,
) -> None:
    source, base_commit = _base_repository(tmp_path)
    factory = IsolatedWorktreeFactory(source, tmp_path / "worktrees")

    with pytest.raises(CandidateControlError, match="EVOLUTION_WORKTREE_NAME_INVALID"):
        factory.create(name="../escaped", base_commit=base_commit)
    with pytest.raises(ValidationError, match="normalized and relative"):
        CandidateFileBinding(
            repository_path="../routing/router.py",
            object_kind="routing.strategy",
            target="policy/routing/router.py",
        )


def test_unlisted_file_and_disguised_repository_authority_are_rejected(
    tmp_path: Path,
) -> None:
    _source, candidate, base_commit = _candidate_worktree(tmp_path)
    extra = candidate.root / "unexpected.txt"
    extra.write_text("unexpected\n", encoding="utf-8")
    _git(candidate.root, "add", ".")
    _git(candidate.root, "commit", "-m", "candidate")

    with pytest.raises(CandidateControlError, match="EVOLUTION_CHANGED_FILE_SET_MISMATCH"):
        CandidateFreezer(clock=_Clock()).freeze(candidate, _request(base_commit))

    second = CandidateFileBinding(
        repository_path="unexpected.txt",
        object_kind="routing.strategy",
        target="policy/routing/unexpected.txt",
    )
    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_REPOSITORY_AUTHORITY_MISMATCH",
    ):
        CandidateFreezer(clock=_Clock()).freeze(candidate, _request(base_commit, second))


def test_rename_symlink_and_delete_are_rejected(tmp_path: Path) -> None:
    for operation, expected in (
        ("rename", "EVOLUTION_RENAME_OR_COPY_FORBIDDEN"),
        ("symlink", "EVOLUTION_NON_REGULAR_FILE_FORBIDDEN"),
        ("delete", "EVOLUTION_CHANGE_TYPE_FORBIDDEN"),
    ):
        case_root = tmp_path / operation
        case_root.mkdir()
        _source, candidate, base_commit = _candidate_worktree(case_root)
        if operation == "rename":
            renamed = _ROUTER.replace("router.py", "strategy.py")
            (candidate.root / _ROUTER).rename(candidate.root / renamed)
            _git(candidate.root, "add", "-A")
        elif operation == "symlink":
            (candidate.root / _ROUTER).unlink()
            (candidate.root / _ROUTER).symlink_to("/tmp/not-trusted")
            _git(candidate.root, "add", "-A")
        else:
            (candidate.root / _ROUTER).unlink()
            _git(candidate.root, "add", "-A")
        _git(candidate.root, "commit", "-m", operation)

        binding_path = (
            _ROUTER.replace("router.py", "strategy.py") if operation == "rename" else _ROUTER
        )
        request = _request(
            base_commit,
            CandidateFileBinding(
                repository_path=binding_path,
                object_kind="routing.strategy",
                target="policy/routing/router.py",
            ),
        )
        with pytest.raises(CandidateControlError, match=expected):
            CandidateFreezer(clock=_Clock()).freeze(candidate, request)


def test_dirty_or_new_head_after_freeze_cannot_pass_revalidation(tmp_path: Path) -> None:
    _source, candidate, base_commit = _candidate_worktree(tmp_path)
    _commit_candidate(candidate)
    freezer = CandidateFreezer(clock=_Clock())
    frozen = freezer.freeze(candidate, _request(base_commit))

    (candidate.root / _ROUTER).write_text("ROUTE = 'quick'\n", encoding="utf-8")
    with pytest.raises(CandidateControlError, match="EVOLUTION_WORKTREE_DIRTY"):
        freezer.assert_unchanged(candidate, frozen)

    _git(candidate.root, "add", _ROUTER)
    _git(candidate.root, "commit", "-m", "post-freeze mutation")
    with pytest.raises(CandidateControlError, match="EVOLUTION_HEAD_CHANGED_AFTER_FREEZE"):
        freezer.assert_unchanged(candidate, frozen)


def test_forged_frozen_manifest_digest_is_rejected(tmp_path: Path) -> None:
    _source, candidate, base_commit = _candidate_worktree(tmp_path)
    _commit_candidate(candidate)
    freezer = CandidateFreezer(clock=_Clock())
    frozen = freezer.freeze(candidate, _request(base_commit))
    forged = frozen.model_copy(update={"frozen_manifest_sha256": "0" * 64})

    with pytest.raises(CandidateControlError, match="EVOLUTION_FROZEN_MANIFEST_INVALID"):
        freezer.assert_unchanged(candidate, forged)


def test_execution_archive_contains_only_named_commit_objects(tmp_path: Path) -> None:
    repository, _commit = _base_repository(tmp_path)
    (repository.root / ".gitignore").write_text(".env.runtime\n", encoding="utf-8")
    _git(repository.root, "add", ".gitignore")
    _git(repository.root, "commit", "-m", "ignore runtime probe")
    (repository.root / ".env.runtime").write_text(
        "COMMIT_EXTERNAL_BYTES=true\n",
        encoding="utf-8",
    )
    repository.require_clean()
    archive_path = tmp_path / "candidate.tar"

    digest = repository.export_commit_archive(repository.head(), archive_path)

    with tarfile.open(archive_path, mode="r:") as archive:
        names = set(archive.getnames())
    assert len(digest) == 64
    assert ".env.runtime" not in names
    assert ".git" not in names
    assert _ROUTER in names
