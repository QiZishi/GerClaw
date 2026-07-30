"""Pinned official optimizer sources with fail-closed local inspection."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid", frozen=True)
_SHA256 = r"^[a-f0-9]{64}$"
_GIT_SHA = r"^[a-f0-9]{40}$"

OptimizerName = Literal["a-evolve", "gepa", "adaptive-auto-harness"]
AvailabilityReason = Literal[
    "verified",
    "checkout_not_configured",
    "checkout_missing",
    "checkout_symlink_forbidden",
    "git_metadata_unavailable",
    "remote_mismatch",
    "commit_mismatch",
    "checkout_dirty",
    "license_evidence_mismatch",
]


class OfficialOptimizerPin(BaseModel):
    """Immutable upstream identity reviewed outside candidate control."""

    model_config = _STRICT

    schema_version: Literal["official-optimizer-pin-v1"] = "official-optimizer-pin-v1"
    name: OptimizerName
    repository_url: str = Field(pattern=r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git$")
    reference: str = Field(pattern=r"^refs/heads/[A-Za-z0-9_./-]+$")
    commit: str = Field(pattern=_GIT_SHA)
    license_id: Literal["MIT"]
    license_evidence_path: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    license_evidence_sha256: str = Field(pattern=_SHA256)
    reviewed_on: Literal["2026-07-30"] = "2026-07-30"


class OptimizerAvailability(BaseModel):
    """Bounded inspection result that never exposes subprocess output."""

    model_config = _STRICT

    schema_version: Literal["optimizer-availability-v1"] = "optimizer-availability-v1"
    name: OptimizerName
    status: Literal["available", "unavailable"]
    reason_code: AvailabilityReason
    verified_commit: str | None = Field(default=None, pattern=_GIT_SHA)


OFFICIAL_OPTIMIZER_PINS = (
    OfficialOptimizerPin(
        name="a-evolve",
        repository_url="https://github.com/A-EVO-Lab/a-evolve.git",
        reference="refs/heads/main",
        commit="c9d4789f2be499589d543aa08e74d05d10d93177",
        license_id="MIT",
        # This upstream commit declares MIT in pyproject.toml but does not
        # contain a root LICENSE file. Pin the complete committed declaration.
        license_evidence_path="pyproject.toml",
        license_evidence_sha256="df98b57147f808bf2730e9ed2748580456c3c04e1341a6d13445c9120671c77d",
    ),
    OfficialOptimizerPin(
        name="gepa",
        repository_url="https://github.com/gepa-ai/gepa.git",
        reference="refs/heads/main",
        commit="0310bb7b4952d4695718f9f557e450fd6781301e",
        license_id="MIT",
        license_evidence_path="LICENSE",
        license_evidence_sha256="10c47467a961feb40adf3294fe27dd9cba79d4d1b7cf27173b1c34586d4126c3",
    ),
    OfficialOptimizerPin(
        name="adaptive-auto-harness",
        repository_url="https://github.com/A-EVO-Lab/a-evolve.git",
        reference="refs/heads/release/adaptive-auto-harness",
        commit="17bc9ebb7d4d142af1b109b43ef160031967cc9a",
        license_id="MIT",
        license_evidence_path="LICENSE",
        license_evidence_sha256="ada4e627a4134fc12d0f51289cf674e04822e8e9a978665229707e9bbe93780f",
    ),
)


class OptimizerSourceInspector:
    """Verify a preinstalled checkout without fetching or importing it."""

    __slots__ = ()

    def inspect(
        self,
        pin: OfficialOptimizerPin,
        checkout: Path | None,
    ) -> OptimizerAvailability:
        if checkout is None:
            return self._unavailable(pin, "checkout_not_configured")
        if not checkout.exists() or not checkout.is_dir():
            return self._unavailable(pin, "checkout_missing")
        if checkout.is_symlink():
            return self._unavailable(pin, "checkout_symlink_forbidden")

        root = checkout.resolve(strict=True)
        remote = self._git(root, "remote", "get-url", "origin")
        head = self._git(root, "rev-parse", "--verify", "HEAD")
        status = self._git(root, "status", "--porcelain=v1", "--untracked-files=no")
        if remote is None or head is None or status is None:
            return self._unavailable(pin, "git_metadata_unavailable")
        if remote != pin.repository_url:
            return self._unavailable(pin, "remote_mismatch")
        if head != pin.commit:
            return self._unavailable(pin, "commit_mismatch")
        if status:
            return self._unavailable(pin, "checkout_dirty")
        evidence = self._git_bytes(
            root,
            "show",
            f"{pin.commit}:{pin.license_evidence_path}",
        )
        if evidence is None:
            return self._unavailable(pin, "git_metadata_unavailable")
        if hashlib.sha256(evidence).hexdigest() != pin.license_evidence_sha256:
            return self._unavailable(pin, "license_evidence_mismatch")
        return OptimizerAvailability(
            name=pin.name,
            status="available",
            reason_code="verified",
            verified_commit=head,
        )

    @staticmethod
    def _git(root: Path, *args: str) -> str | None:
        output = OptimizerSourceInspector._git_bytes(root, *args)
        if output is None:
            return None
        return output.decode("utf-8", errors="strict").strip()

    @staticmethod
    def _git_bytes(root: Path, *args: str) -> bytes | None:
        try:
            result = subprocess.run(
                ("git", "-C", str(root), *args),
                check=False,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout if result.returncode == 0 else None

    @staticmethod
    def _unavailable(
        pin: OfficialOptimizerPin,
        reason: AvailabilityReason,
    ) -> OptimizerAvailability:
        return OptimizerAvailability(
            name=pin.name,
            status="unavailable",
            reason_code=reason,
        )
