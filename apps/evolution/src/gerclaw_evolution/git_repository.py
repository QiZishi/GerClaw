"""Minimal no-shell Git boundary for isolated candidate worktrees."""

from __future__ import annotations

import builtins
import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from gerclaw_evolution.contracts import CandidateControlError

_WORKTREE_NAME = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_OBJECT_ID = re.compile(r"^[a-f0-9]{40}$")
_MAX_EXECUTION_ARCHIVE_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RefUpdate:
    """One compare-and-swap entry in an atomic Git ref transaction."""

    ref_name: str
    new_object_id: str
    expected_old_object_id: str


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

    def export_commit_archive(self, commit: str, destination: Path) -> str:
        """Export only committed Git objects and return the archive SHA-256."""

        if not _OBJECT_ID.fullmatch(commit):
            raise CandidateControlError("EVOLUTION_GIT_OBJECT_INVALID")
        parent = destination.parent
        if (
            destination.exists()
            or destination.is_symlink()
            or not parent.exists()
            or not parent.is_dir()
            or parent.is_symlink()
        ):
            raise CandidateControlError("EVOLUTION_EXECUTION_ARCHIVE_PATH_INVALID")
        try:
            result = subprocess.run(
                (
                    "git",
                    "-C",
                    str(self.root),
                    "archive",
                    "--format=tar",
                    f"--output={destination}",
                    commit,
                ),
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CandidateControlError("EVOLUTION_GIT_UNAVAILABLE") from error
        if result.returncode != 0:
            raise CandidateControlError("EVOLUTION_GIT_COMMAND_FAILED")
        try:
            size = destination.stat().st_size
            if not 0 < size <= _MAX_EXECUTION_ARCHIVE_BYTES or not destination.is_file():
                raise CandidateControlError("EVOLUTION_EXECUTION_ARCHIVE_INVALID")
            digest = hashlib.sha256()
            with destination.open("rb") as archive:
                for block in iter(lambda: archive.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as error:
            raise CandidateControlError("EVOLUTION_EXECUTION_ARCHIVE_INVALID") from error
        return digest.hexdigest()

    def resolve_ref(self, ref_name: str) -> str | None:
        self._validate_ref_name(ref_name)
        try:
            result = subprocess.run(
                (
                    "git",
                    "-C",
                    str(self.root),
                    "rev-parse",
                    "--verify",
                    "--quiet",
                    ref_name,
                ),
                check=False,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CandidateControlError("EVOLUTION_GIT_UNAVAILABLE") from error
        if result.returncode == 1:
            return None
        if result.returncode != 0:
            raise CandidateControlError("EVOLUTION_GIT_COMMAND_FAILED")
        try:
            object_id = result.stdout.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise CandidateControlError("EVOLUTION_GIT_OUTPUT_INVALID") from error
        if not _OBJECT_ID.fullmatch(object_id):
            raise CandidateControlError("EVOLUTION_GIT_REF_INVALID")
        return object_id

    def store_blob(self, content: builtins.bytes) -> str:
        try:
            result = subprocess.run(
                ("git", "-C", str(self.root), "hash-object", "-w", "--stdin"),
                input=content,
                check=False,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CandidateControlError("EVOLUTION_GIT_UNAVAILABLE") from error
        if result.returncode != 0:
            raise CandidateControlError("EVOLUTION_GIT_COMMAND_FAILED")
        try:
            object_id = result.stdout.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise CandidateControlError("EVOLUTION_GIT_OUTPUT_INVALID") from error
        if not _OBJECT_ID.fullmatch(object_id):
            raise CandidateControlError("EVOLUTION_GIT_OBJECT_INVALID")
        return object_id

    def atomic_update_refs(self, updates: tuple[RefUpdate, ...]) -> None:
        if not updates or len({update.ref_name for update in updates}) != len(updates):
            raise CandidateControlError("EVOLUTION_REF_TRANSACTION_INVALID")
        commands = ["start", "option no-deref"]
        for update in updates:
            self._validate_ref_name(update.ref_name)
            self._require_direct_or_missing_ref(update.ref_name)
            if not _OBJECT_ID.fullmatch(update.new_object_id) or not _OBJECT_ID.fullmatch(
                update.expected_old_object_id
            ):
                raise CandidateControlError("EVOLUTION_REF_TRANSACTION_INVALID")
            commands.append(
                f"update {update.ref_name} {update.new_object_id} {update.expected_old_object_id}"
            )
        commands.extend(("prepare", "commit", ""))
        try:
            result = subprocess.run(
                ("git", "-C", str(self.root), "update-ref", "--stdin"),
                input="\n".join(commands).encode("ascii"),
                check=False,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CandidateControlError("EVOLUTION_GIT_UNAVAILABLE") from error
        if result.returncode != 0:
            raise CandidateControlError("EVOLUTION_ATOMIC_REF_UPDATE_FAILED")

    def read_blob(self, object_id: str) -> builtins.bytes:
        if not _OBJECT_ID.fullmatch(object_id):
            raise CandidateControlError("EVOLUTION_GIT_OBJECT_INVALID")
        return self.bytes("cat-file", "blob", object_id)

    def _validate_ref_name(self, ref_name: str) -> None:
        if (
            not ref_name.startswith("refs/gerclaw/")
            or any(character.isspace() for character in ref_name)
            or len(ref_name) > 240
        ):
            raise CandidateControlError("EVOLUTION_REF_NAME_INVALID")
        self.bytes("check-ref-format", ref_name)

    def _require_direct_or_missing_ref(self, ref_name: str) -> None:
        try:
            result = subprocess.run(
                ("git", "-C", str(self.root), "symbolic-ref", "--quiet", ref_name),
                check=False,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CandidateControlError("EVOLUTION_GIT_UNAVAILABLE") from error
        if result.returncode == 0:
            raise CandidateControlError("EVOLUTION_SYMBOLIC_REF_FORBIDDEN")
        if result.returncode != 1:
            raise CandidateControlError("EVOLUTION_GIT_COMMAND_FAILED")


class IsolatedWorktreeFactory:
    """Create detached worktrees only beneath a controller-owned workspace."""

    def __init__(self, repository: GitRepository, workspace_root: Path) -> None:
        if workspace_root.exists() and (not workspace_root.is_dir() or workspace_root.is_symlink()):
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
