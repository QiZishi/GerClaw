"""Operator composition and secret-file CLI boundary tests."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from gerclaw_api.modules.skill.offline_activation import SkillActivationOutcome
from gerclaw_api.modules.skill.offline_contracts import SkillProposalExportEnvelope
from test_skill_runner import _candidate, _evaluator_repository, _runner

from gerclaw_evolution.cli import _secret_file
from gerclaw_evolution.contracts import CandidateControlError
from gerclaw_evolution.skill_operator import SkillReviewOperator


def _envelope() -> SkillProposalExportEnvelope:
    ciphertext = b"encrypted-candidate-placeholder"
    return SkillProposalExportEnvelope(
        exporter_key_id="api.skill-export",
        recipient_key_id="controller.skill-review",
        ephemeral_public_key="1" * 64,
        ciphertext="e" * 32,
        nonce="2" * 24,
        encrypted_payload_sha256=hashlib.sha256(ciphertext).hexdigest(),
        exporter_signature="3" * 128,
    )


class _Opener:
    def __init__(self) -> None:
        self.calls = 0

    def open(self, _envelope: object) -> object:
        self.calls += 1
        return _candidate()


class _Authorizer:
    def __init__(self) -> None:
        self.calls = 0

    def authorize(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        return object()


class _Activator:
    def __init__(self) -> None:
        self.calls = 0

    async def activate(self, _authorization: object) -> SkillActivationOutcome:
        self.calls += 1
        return SkillActivationOutcome(
            status="activated",
            proposal_id="01234567-89ab-cdef-0123-456789abcdef",
            revision=2,
            artifact_sha256="a" * 64,
        )


def test_operator_reproduces_pair_before_atomic_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _evaluator_repository(tmp_path)
    opener = _Opener()
    authorizer = _Authorizer()
    activator = _Activator()
    operator = SkillReviewOperator(
        opener=opener,  # type: ignore[arg-type]
        paired_runner=_runner(repository, monkeypatch),
        activation_authorizer=authorizer,  # type: ignore[arg-type]
        offline_activator=activator,  # type: ignore[arg-type]
    )
    package = operator.pair(repository, _envelope())

    outcome = asyncio.run(
        operator.activate(
            repository,
            package,
            sealed_attestation=SimpleNamespace(),  # type: ignore[arg-type]
            human_approval=SimpleNamespace(),  # type: ignore[arg-type]
        )
    )

    assert package.paired_report.gate.passed is True
    assert outcome.status == "activated"
    assert opener.calls == 3
    assert authorizer.calls == 1
    assert activator.calls == 1


def test_cli_reads_secrets_only_from_owner_only_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "secret"
    path.write_bytes(b"s" * 32)
    monkeypatch.setenv("GERCLAW_EVOLUTION_TEST_SECRET_FILE", str(path))
    path.chmod(0o600)

    assert _secret_file("GERCLAW_EVOLUTION_TEST_SECRET_FILE", exact=32) == b"s" * 32

    path.chmod(0o644)
    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_OPERATOR_SECRET_FILE_PERMISSIONS",
    ):
        _secret_file("GERCLAW_EVOLUTION_TEST_SECRET_FILE", exact=32)


def test_cli_rejects_secret_file_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "secret"
    target.write_bytes(b"s" * 32)
    target.chmod(0o600)
    link = tmp_path / "secret-link"
    link.symlink_to(target)
    monkeypatch.setenv("GERCLAW_EVOLUTION_TEST_SECRET_FILE", str(link))

    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_OPERATOR_SECRET_FILE_UNAVAILABLE",
    ):
        _secret_file("GERCLAW_EVOLUTION_TEST_SECRET_FILE", exact=32)
