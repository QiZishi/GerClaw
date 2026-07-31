"""Offline candidate contracts bound to the online governance fact source."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from gerclaw_api.modules.agent_harness.evolution_governance import CandidateProposal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_STRICT = ConfigDict(extra="forbid", frozen=True)
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_SHA256 = r"^[a-f0-9]{64}$"


def validate_repository_path(value: str) -> str:
    """Accept one normalized repository-relative POSIX path."""

    normalized = value.strip()
    if (
        not normalized
        or normalized.startswith(("/", "\\"))
        or _WINDOWS_ABSOLUTE.match(normalized)
        or "\\" in normalized
        or "\x00" in normalized
        or ".." in normalized.split("/")
        or normalized.endswith("/")
    ):
        raise ValueError("repository path must be normalized and relative")
    return normalized


class CandidateFileBinding(BaseModel):
    """Controller-declared binding between a repository file and logical authority."""

    model_config = _STRICT

    repository_path: str = Field(min_length=3, max_length=512)
    object_kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,99}$")
    target: str = Field(min_length=3, max_length=512)

    @field_validator("repository_path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_repository_path(value)


class FrozenRepositoryChange(CandidateFileBinding):
    """One committed regular-file change read from the candidate Git object."""

    content_digest: str = Field(pattern=_SHA256)


class FrozenCandidate(BaseModel):
    """Commit-bound candidate manifest copied outside the worktree."""

    model_config = _STRICT

    schema_version: Literal["frozen-candidate-v1"] = "frozen-candidate-v1"
    proposal: CandidateProposal
    repository_changes: tuple[FrozenRepositoryChange, ...] = Field(
        min_length=1,
        max_length=100,
    )
    governance_manifest_sha256: str = Field(pattern=_SHA256)
    frozen_manifest_sha256: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def bind_repository_and_logical_changes(self) -> FrozenCandidate:
        logical = tuple(
            (item.object_kind, item.target, item.content_digest) for item in self.proposal.changes
        )
        repository = tuple(
            (item.object_kind, item.target, item.content_digest) for item in self.repository_changes
        )
        if logical != repository:
            raise ValueError("repository changes do not match the proposal")
        return self


class CandidateFreezeRequest(BaseModel):
    """Trusted metadata supplied before inspecting an isolated candidate HEAD."""

    model_config = _STRICT

    schema_version: Literal["candidate-freeze-request-v1"] = "candidate-freeze-request-v1"
    proposal_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,99}$")
    declared_track: Literal["mutable", "immutable"]
    base_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_reason_codes: tuple[str, ...] = Field(min_length=1, max_length=20)
    activation_condition_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    bindings: tuple[CandidateFileBinding, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_duplicate_bindings(self) -> CandidateFreezeRequest:
        repository_paths = [item.repository_path for item in self.bindings]
        targets = [item.target for item in self.bindings]
        if len(repository_paths) != len(set(repository_paths)):
            raise ValueError("candidate bindings contain duplicate repository paths")
        if len(targets) != len(set(targets)):
            raise ValueError("candidate bindings contain duplicate logical targets")
        return self


class CandidateControlError(RuntimeError):
    """Stable fail-closed candidate-control error without raw Git output."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FreezeClock:
    """Small clock port that keeps freeze tests deterministic."""

    def now(self) -> datetime:
        raise NotImplementedError
