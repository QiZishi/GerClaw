"""Docker candidate sandbox contract and optional real isolation test."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from test_candidate_freeze import _base_repository

from gerclaw_evolution.contracts import CandidateControlError
from gerclaw_evolution.sandbox import DockerCandidateExecutor


def test_sandbox_requires_a_content_addressed_image_and_bounded_resources() -> None:
    with pytest.raises(CandidateControlError, match="EVOLUTION_SANDBOX_CONFIG_INVALID"):
        DockerCandidateExecutor(image_id="gerclaw-api:latest")
    with pytest.raises(CandidateControlError, match="EVOLUTION_SANDBOX_CONFIG_INVALID"):
        DockerCandidateExecutor(
            image_id="sha256:" + "a" * 64,
            docker_binary="/tmp/fake-docker",
        )


def test_unconfirmed_resource_cleanup_is_a_bounded_controller_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _commit = _base_repository(tmp_path)
    executor = DockerCandidateExecutor(image_id="sha256:" + "a" * 64)
    monkeypatch.setattr(executor, "_prepare_bundle", lambda *_args: False)
    monkeypatch.setattr(executor, "_remove_container", lambda _name: False)
    monkeypatch.setattr(executor, "_remove_volume", lambda _name: True)

    with pytest.raises(
        CandidateControlError,
        match="EVOLUTION_SANDBOX_CLEANUP_FAILED",
    ):
        executor.run(
            repository,
            ("-c", "print('unreachable')"),
            input_data=None,
            timeout=1,
        )


@pytest.mark.skipif(
    not os.environ.get("GERCLAW_EVOLUTION_TEST_IMAGE_ID"),
    reason="content-addressed sandbox test image is not configured",
)
def test_real_docker_sandbox_hides_host_assets_and_destroys_process_domain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_id = os.environ["GERCLAW_EVOLUTION_TEST_IMAGE_ID"]
    repository, _commit = _base_repository(tmp_path)
    (repository.root / ".gitignore").write_text("ignored-probe.py\n", encoding="utf-8")
    subprocess.run(
        ("git", "-C", str(repository.root), "add", ".gitignore"),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ("git", "-C", str(repository.root), "commit", "-m", "ignore probe"),
        check=True,
        capture_output=True,
    )
    (repository.root / "ignored-probe.py").write_text(
        "COMMIT_EXTERNAL_BYTES = True\n",
        encoding="utf-8",
    )
    repository.require_clean()
    host_secret = tmp_path / "controller-secret.txt"
    host_secret.write_text("APPROVAL_PRIVATE_KEY", encoding="utf-8")
    monkeypatch.setenv("GERCLAW_LLM_API_KEY", "host-provider-secret")
    before = _sandbox_containers()
    before_volumes = _sandbox_volumes()
    script = f"""
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

request = json.load(sys.stdin)
result = {{}}
result["controller_input_received"] = request == {{"probe": "bounded-input"}}
try:
    result["host_secret_read"] = (
        Path({str(host_secret)!r}).read_text() == "APPROVAL_PRIVATE_KEY"
    )
except Exception:
    result["host_secret_read"] = False
try:
    Path("/tmp/candidate/escape.txt").write_text("bad")
    result["candidate_mount_writable"] = True
except Exception:
    result["candidate_mount_writable"] = False
result["git_metadata_visible"] = Path("/tmp/candidate/.git").exists()
result["ignored_file_visible"] = Path("/tmp/candidate/ignored-probe.py").exists()
result["docker_socket_visible"] = Path("/var/run/docker.sock").exists()
result["host_provider_secret_visible"] = os.environ.get("GERCLAW_LLM_API_KEY") is not None
connection = socket.socket()
connection.settimeout(1)
try:
    connection.connect(("1.1.1.1", 53))
    result["network_available"] = True
except Exception:
    result["network_available"] = False
subprocess.Popen(
    (sys.executable, "-c", "import time; time.sleep(60)"),
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)
print(json.dumps(result, sort_keys=True))
"""
    execution = DockerCandidateExecutor(image_id=image_id).run(
        repository,
        ("-c", script),
        input_data=b'{"probe":"bounded-input"}',
        timeout=30,
    )

    assert execution.stdout is not None
    assert len(execution.execution_bundle_sha256) == 64
    assert json.loads(execution.stdout) == {
        "candidate_mount_writable": False,
        "controller_input_received": True,
        "docker_socket_visible": False,
        "git_metadata_visible": False,
        "host_provider_secret_visible": False,
        "host_secret_read": False,
        "ignored_file_visible": False,
        "network_available": False,
    }
    assert not (repository.root / "escape.txt").exists()
    assert _sandbox_containers() == before
    assert _sandbox_volumes() == before_volumes
    repository.require_clean()

    timed_out = DockerCandidateExecutor(image_id=image_id).run(
        repository,
        ("-c", "import time; time.sleep(60)"),
        input_data=None,
        timeout=1,
    )

    assert timed_out.stdout is None
    assert timed_out.execution_bundle_sha256 == execution.execution_bundle_sha256
    assert _sandbox_containers() == before
    assert _sandbox_volumes() == before_volumes
    repository.require_clean()


def _sandbox_containers() -> frozenset[str]:
    result = subprocess.run(
        (
            "docker",
            "ps",
            "--all",
            "--filter",
            "name=gerclaw-eval-",
            "--format",
            "{{.Names}}",
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    return frozenset(line for line in result.stdout.splitlines() if line)


def _sandbox_volumes() -> frozenset[str]:
    result = subprocess.run(
        (
            "docker",
            "volume",
            "ls",
            "--filter",
            "name=gerclaw-eval-",
            "--format",
            "{{.Name}}",
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    return frozenset(line for line in result.stdout.splitlines() if line)
