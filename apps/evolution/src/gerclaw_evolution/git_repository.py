"""Minimal no-shell Git boundary for isolated candidate worktrees."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from gerclaw_evolution.contracts import CandidateControlError

_WORKTREE_NAME = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


class GitRepository:
    """Run bounded Git operations without exposing stderr to candidates or logs."""

    def __init__(self, root: Path) -> None:
        if not root.exists() or not root.is_dir() or root.is_symlink():
            raise CandidateControlError("EVOLUTION_REPOSITORY_INVALID")
        self.root = root.resolve(strict=True)
        top_level = self.text("rev-parse", "--show-toplevel")
        if Path(top_level).resolve(strict=True) != self.root:
            raise CandidateControlError("EVOLUTION_REPOSITORY_ROOT_MISMATCH")

    def bytes(self, *args: str, timeout: int = 30) -> bytes:
        try:
            result = subprocess.run(
                ("git", "-C", str(self.root), *args),
                check=False,
                capture_output=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CandidateControlError("EVOLUTION_GIT_UNAVAILABLE") from error
        if result.returncode != 0:
            raise CandidateControlError("EVOLUTION_GIT_COMMAND_FAILED")
        return result.stdout

    def text(self, *args: str, timeout: int = 30) -> str:
        try:
            return self.bytes(*args, timeout=timeout).decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError as error:
            raise CandidateControlError("EVOLUTION_GIT_OUTPUT_INVALID") from error

    def head(self) -> str:
        head = self.text("rev-parse", "--verify", "HEAD")
        if not re.fullmatch(r"[a-f0-9]{40}", head):
            raise CandidateControlError("EVOLUTION_GIT_HEAD_INVALID")
        return head

    def require_clean(self) -> None:
        if self.bytes("status", "--porcelain=v1", "-z"):
            raise CandidateControlError("EVOLUTION_WORKTREE_DIRTY")

    def require_ancestor(self, base_commit: str, candidate_commit: str) -> None:
        try:
            self.bytes("merge-base", "--is-ancestor", base_commit, candidate_commit)
        except CandidateControlError as error:
            raise CandidateControlError("EVOLUTION_BASE_NOT_ANCESTOR") from error


class IsolatedWorktreeFactory:
    """Create detached worktrees only beneath a controller-owned workspace."""

    def __init__(self, repository: GitRepository, workspace_root: Path) -> None:
        if workspace_root.exists() and (
            not workspace_root.is_dir() or workspace_root.is_symlink()
        ):
            raise CandidateControlError("EVOLUTION_WORKSPACE_ROOT_INVALID")
        workspace_root.mkdir(parents=True, exist_ok=True)
        self._repository = repository
        self._workspace_root = workspace_root.resolve(strict=True)
        if (
            self._workspace_root == repository.root
            or repository.root in self._workspace_root.parents
        ):
            raise CandidateControlError("EVOLUTION_WORKSPACE_INSIDE_REPOSITORY")

    def create(self, *, name: str, base_commit: str) -> GitRepository:
        if not _WORKTREE_NAME.fullmatch(name):
            raise CandidateControlError("EVOLUTION_WORKTREE_NAME_INVALID")
        destination = self._workspace_root / name
        if destination.exists() or destination.is_symlink():
            raise CandidateControlError("EVOLUTION_WORKTREE_ALREADY_EXISTS")
        self._repository.bytes(
            "worktree",
            "add",
            "--detach",
            str(destination),
            base_commit,
            timeout=60,
        )
        resolved = destination.resolve(strict=True)
        if self._workspace_root not in resolved.parents:
            raise CandidateControlError("EVOLUTION_WORKTREE_ESCAPED_ROOT")
        return GitRepository(resolved)
