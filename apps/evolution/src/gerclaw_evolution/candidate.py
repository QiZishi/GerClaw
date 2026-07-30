"""Candidate freeze and post-evaluation immutability enforcement."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from types import MappingProxyType

from gerclaw_api.modules.agent_harness.evolution_governance import (
    COMPONENT_CHARTERS,
    OBJECT_RULES,
    REQUIRED_CHARTERS_BY_OBJECT_KIND,
    CandidateChange,
    CandidateProposal,
    EvolutionGovernanceError,
    EvolutionGovernancePolicy,
)

from gerclaw_evolution.contracts import (
    CandidateControlError,
    CandidateFileBinding,
    CandidateFreezeRequest,
    FreezeClock,
    FrozenCandidate,
    FrozenRepositoryChange,
)
from gerclaw_evolution.git_repository import GitRepository

_REPOSITORY_PATHS = MappingProxyType(
    {
        "routing.strategy": frozenset(
            {"apps/api/src/gerclaw_api/modules/agent_harness/routing/router.py"}
        ),
        "planning.strategy": frozenset(
            {
                "apps/api/src/gerclaw_api/modules/agent_harness/planning/action_selection.py",
                "apps/api/src/gerclaw_api/modules/agent_harness/planning/clarification.py",
                "apps/api/src/gerclaw_api/modules/agent_harness/planning/planner.py",
            }
        ),
        "prompt.policy": frozenset(
            {"apps/api/src/gerclaw_api/modules/agent_harness/planning/agent_factory.py"}
        ),
    }
)
_BUILTIN_SKILL_PREFIX = "apps/api/src/gerclaw_api/modules/skill/builtin/"


class SystemFreezeClock(FreezeClock):
    def now(self) -> datetime:
        return datetime.now(UTC)


class RepositoryAuthorityPolicy:
    """Trusted mapping from logical object kinds to actual candidate files."""

    __slots__ = ()

    def assert_allowed(self, binding: CandidateFileBinding) -> None:
        exact_paths = _REPOSITORY_PATHS.get(binding.object_kind, frozenset())
        if binding.repository_path in exact_paths:
            return
        if (
            binding.object_kind == "skill.clinical"
            and binding.repository_path.startswith(_BUILTIN_SKILL_PREFIX)
            and binding.repository_path.endswith("/SKILL.md")
        ):
            return
        raise CandidateControlError("EVOLUTION_REPOSITORY_AUTHORITY_MISMATCH")


class CandidateFreezer:
    """Freeze a clean committed candidate after verifying every changed file."""

    def __init__(
        self,
        *,
        governance: EvolutionGovernancePolicy | None = None,
        repository_policy: RepositoryAuthorityPolicy | None = None,
        clock: FreezeClock | None = None,
    ) -> None:
        self._governance = governance or EvolutionGovernancePolicy()
        self._repository_policy = repository_policy or RepositoryAuthorityPolicy()
        self._clock = clock or SystemFreezeClock()

    def freeze(
        self,
        repository: GitRepository,
        request: CandidateFreezeRequest,
    ) -> FrozenCandidate:
        repository.require_clean()
        candidate_commit = repository.head()
        if candidate_commit == request.base_commit:
            raise CandidateControlError("EVOLUTION_CANDIDATE_EQUALS_BASE")
        repository.require_ancestor(request.base_commit, candidate_commit)
        frozen_changes = self._inspect_changes(
            repository,
            base_commit=request.base_commit,
            candidate_commit=candidate_commit,
            bindings=request.bindings,
        )
        proposal = CandidateProposal(
            proposal_id=request.proposal_id,
            declared_track=request.declared_track,
            base_commit=request.base_commit,
            candidate_commit=candidate_commit,
            risk_level=request.risk_level,
            risk_reason_codes=request.risk_reason_codes,
            activation_condition_ids=request.activation_condition_ids,
            frozen_at=self._clock.now(),
            changes=tuple(
                CandidateChange(
                    object_kind=change.object_kind,
                    target=change.target,
                    content_digest=change.content_digest,
                )
                for change in frozen_changes
            ),
        )
        try:
            self._governance.validate_candidate(proposal)
        except EvolutionGovernanceError as error:
            raise CandidateControlError(error.code) from error

        governance_digest = self.governance_digest()
        frozen_digest = self._frozen_digest(
            proposal,
            frozen_changes,
            governance_digest,
        )
        return FrozenCandidate(
            proposal=proposal,
            repository_changes=frozen_changes,
            governance_manifest_sha256=governance_digest,
            frozen_manifest_sha256=frozen_digest,
        )

    def assert_unchanged(
        self,
        repository: GitRepository,
        frozen: FrozenCandidate,
    ) -> None:
        repository.require_clean()
        self.assert_manifest(frozen)
        if repository.head() != frozen.proposal.candidate_commit:
            raise CandidateControlError("EVOLUTION_HEAD_CHANGED_AFTER_FREEZE")
        current = self._inspect_changes(
            repository,
            base_commit=frozen.proposal.base_commit,
            candidate_commit=frozen.proposal.candidate_commit,
            bindings=tuple(
                CandidateFileBinding(
                    repository_path=item.repository_path,
                    object_kind=item.object_kind,
                    target=item.target,
                )
                for item in frozen.repository_changes
            ),
        )
        if current != frozen.repository_changes:
            raise CandidateControlError("EVOLUTION_CONTENT_CHANGED_AFTER_FREEZE")

    def assert_manifest(self, frozen: FrozenCandidate) -> None:
        """Validate controller governance and the content-addressed freeze record."""

        try:
            self._governance.validate_candidate(frozen.proposal)
        except EvolutionGovernanceError as error:
            raise CandidateControlError(error.code) from error
        if self.governance_digest() != frozen.governance_manifest_sha256:
            raise CandidateControlError("EVOLUTION_GOVERNANCE_CHANGED_AFTER_FREEZE")
        expected_manifest_digest = self._frozen_digest(
            frozen.proposal,
            frozen.repository_changes,
            frozen.governance_manifest_sha256,
        )
        if expected_manifest_digest != frozen.frozen_manifest_sha256:
            raise CandidateControlError("EVOLUTION_FROZEN_MANIFEST_INVALID")

    def governance_digest(self) -> str:
        payload = {
            "object_rules": [
                rule.model_dump(mode="json")
                for rule in sorted(OBJECT_RULES, key=lambda item: item.object_kind)
            ],
            "component_charters": [
                charter.model_dump(mode="json")
                for charter in sorted(COMPONENT_CHARTERS, key=lambda item: item.component)
            ],
            "required_charters_by_object_kind": {
                object_kind: list(required)
                for object_kind, required in sorted(
                    REQUIRED_CHARTERS_BY_OBJECT_KIND.items()
                )
            },
        }
        return self._digest(payload)

    def _inspect_changes(
        self,
        repository: GitRepository,
        *,
        base_commit: str,
        candidate_commit: str,
        bindings: tuple[CandidateFileBinding, ...],
    ) -> tuple[FrozenRepositoryChange, ...]:
        changed = self._changed_paths(repository, base_commit, candidate_commit)
        binding_by_path = {item.repository_path: item for item in bindings}
        if set(changed) != set(binding_by_path):
            raise CandidateControlError("EVOLUTION_CHANGED_FILE_SET_MISMATCH")

        frozen: list[FrozenRepositoryChange] = []
        for path in changed:
            binding = binding_by_path[path]
            self._repository_policy.assert_allowed(binding)
            tree_entry = repository.bytes(
                "ls-tree",
                "-z",
                candidate_commit,
                "--",
                path,
            )
            mode, object_type = self._tree_mode_and_type(tree_entry)
            if mode not in {"100644", "100755"} or object_type != "blob":
                raise CandidateControlError("EVOLUTION_NON_REGULAR_FILE_FORBIDDEN")
            content = repository.bytes("show", f"{candidate_commit}:{path}")
            frozen.append(
                FrozenRepositoryChange(
                    repository_path=path,
                    object_kind=binding.object_kind,
                    target=binding.target,
                    content_digest=hashlib.sha256(content).hexdigest(),
                )
            )
        return tuple(frozen)

    @staticmethod
    def _changed_paths(
        repository: GitRepository,
        base_commit: str,
        candidate_commit: str,
    ) -> tuple[str, ...]:
        output = repository.bytes(
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            "--find-copies",
            base_commit,
            candidate_commit,
        )
        fields = output.decode("utf-8", errors="strict").split("\x00")
        if fields and fields[-1] == "":
            fields.pop()
        paths: list[str] = []
        index = 0
        while index < len(fields):
            status = fields[index]
            index += 1
            if status.startswith(("R", "C")):
                raise CandidateControlError("EVOLUTION_RENAME_OR_COPY_FORBIDDEN")
            # Type changes continue to the committed tree-mode check so a
            # regular-file-to-symlink/submodule mutation receives the precise
            # fail-closed error instead of being treated as a generic edit.
            if status not in {"A", "M", "T"} or index >= len(fields):
                raise CandidateControlError("EVOLUTION_CHANGE_TYPE_FORBIDDEN")
            paths.append(fields[index])
            index += 1
        if not paths or len(paths) != len(set(paths)):
            raise CandidateControlError("EVOLUTION_CHANGED_FILE_SET_INVALID")
        return tuple(sorted(paths))

    @staticmethod
    def _tree_mode_and_type(entry: bytes) -> tuple[str, str]:
        try:
            header, _path = entry.rstrip(b"\x00").split(b"\t", maxsplit=1)
            mode, object_type, _object_id = header.decode("ascii").split(" ", maxsplit=2)
        except (UnicodeDecodeError, ValueError) as error:
            raise CandidateControlError("EVOLUTION_TREE_ENTRY_INVALID") from error
        return mode, object_type

    @staticmethod
    def _digest(payload: object) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _frozen_digest(
        cls,
        proposal: CandidateProposal,
        changes: tuple[FrozenRepositoryChange, ...],
        governance_digest: str,
    ) -> str:
        return cls._digest(
            {
                "proposal": proposal.model_dump(mode="json"),
                "repository_changes": [
                    item.model_dump(mode="json") for item in changes
                ],
                "governance_manifest_sha256": governance_digest,
            }
        )
