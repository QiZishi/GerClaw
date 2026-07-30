"""Supply-chain pin and unavailable-semantics tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from gerclaw_evolution.sources import (
    OFFICIAL_OPTIMIZER_PINS,
    OfficialOptimizerPin,
    OptimizerSourceInspector,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(("git", "-C", str(root), *args), check=True, capture_output=True)


type CheckoutFixture = tuple[Path, str, bytes]


def _checkout_for(tmp_path: Path, pin: OfficialOptimizerPin) -> CheckoutFixture:
    root = tmp_path / pin.name
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "GerClaw Test")
    _git(root, "config", "user.email", "test@invalid.local")
    _git(root, "remote", "add", "origin", pin.repository_url)
    evidence = b"reviewed license evidence\n"
    (root / pin.license_evidence_path).write_bytes(evidence)
    _git(root, "add", pin.license_evidence_path)
    _git(root, "commit", "-m", "fixture")
    commit = subprocess.run(
        ("git", "-C", str(root), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return root, commit, evidence


def _fixture_pin(
    source: OfficialOptimizerPin,
    *,
    commit: str,
    evidence: bytes,
) -> OfficialOptimizerPin:
    import hashlib

    return source.model_copy(
        update={
            "commit": commit,
            "license_evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        }
    )


def test_registry_pins_three_distinct_official_sources() -> None:
    assert {pin.name for pin in OFFICIAL_OPTIMIZER_PINS} == {
        "a-evolve",
        "gepa",
        "adaptive-auto-harness",
    }
    assert all(len(pin.commit) == 40 for pin in OFFICIAL_OPTIMIZER_PINS)
    assert all(pin.license_id == "MIT" for pin in OFFICIAL_OPTIMIZER_PINS)
    adaptive = next(pin for pin in OFFICIAL_OPTIMIZER_PINS if pin.name == "adaptive-auto-harness")
    assert adaptive.reference == "refs/heads/release/adaptive-auto-harness"


def test_missing_checkout_is_unavailable_and_never_substituted(tmp_path: Path) -> None:
    pin = OFFICIAL_OPTIMIZER_PINS[0]
    inspector = OptimizerSourceInspector()

    absent = inspector.inspect(pin, None)
    missing = inspector.inspect(pin, tmp_path / "missing")

    assert (absent.status, absent.reason_code) == ("unavailable", "checkout_not_configured")
    assert (missing.status, missing.reason_code) == ("unavailable", "checkout_missing")
    assert absent.verified_commit is None


def test_exact_clean_checkout_is_available(tmp_path: Path) -> None:
    source = OFFICIAL_OPTIMIZER_PINS[0]
    root, commit, evidence = _checkout_for(tmp_path, source)
    pin = _fixture_pin(source, commit=commit, evidence=evidence)

    result = OptimizerSourceInspector().inspect(pin, root)

    assert (result.status, result.reason_code, result.verified_commit) == (
        "available",
        "verified",
        commit,
    )


def test_wrong_remote_commit_dirty_or_license_evidence_fail_closed(tmp_path: Path) -> None:
    source = OFFICIAL_OPTIMIZER_PINS[0]
    root, commit, evidence = _checkout_for(tmp_path, source)
    inspector = OptimizerSourceInspector()
    pin = _fixture_pin(source, commit=commit, evidence=evidence)

    wrong_remote = pin.model_copy(
        update={"repository_url": "https://github.com/example/not-official.git"}
    )
    assert inspector.inspect(wrong_remote, root).reason_code == "remote_mismatch"

    wrong_commit = pin.model_copy(update={"commit": "f" * 40})
    assert inspector.inspect(wrong_commit, root).reason_code == "commit_mismatch"

    (root / pin.license_evidence_path).write_text("modified\n", encoding="utf-8")
    assert inspector.inspect(pin, root).reason_code == "checkout_dirty"
    _git(root, "checkout", "--", pin.license_evidence_path)

    wrong_evidence = pin.model_copy(update={"license_evidence_sha256": "0" * 64})
    assert inspector.inspect(wrong_evidence, root).reason_code == "license_evidence_mismatch"


def test_symlinked_checkout_is_unavailable(tmp_path: Path) -> None:
    source = OFFICIAL_OPTIMIZER_PINS[0]
    root, commit, evidence = _checkout_for(tmp_path, source)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    pin = _fixture_pin(source, commit=commit, evidence=evidence)

    result = OptimizerSourceInspector().inspect(pin, alias)

    assert (result.status, result.reason_code) == (
        "unavailable",
        "checkout_symlink_forbidden",
    )
