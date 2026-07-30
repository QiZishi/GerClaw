"""Content-addressed Docker sandbox for untrusted candidate execution."""

from __future__ import annotations

import hashlib
import json
import os
import re
import resource
import signal
import subprocess
import tempfile
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from gerclaw_evolution.contracts import CandidateControlError
from gerclaw_evolution.git_repository import GitRepository

_IMAGE_ID = re.compile(r"^sha256:[a-f0-9]{64}$")
_MAX_OUTPUT_BYTES = 1_000_000
_BOOTSTRAP_VERSION = "git-archive-volume-bootstrap-v2"
_BOOTSTRAP_SCRIPT = """
import hashlib
import hmac
import os
import sys
import tarfile

archive_path = "/bundle/candidate.tar"
expected_digest = sys.argv[1]
digest = hashlib.sha256()
with open(archive_path, "rb") as archive:
    for block in iter(lambda: archive.read(1024 * 1024), b""):
        digest.update(block)
if not hmac.compare_digest(digest.hexdigest(), expected_digest):
    raise SystemExit(70)
runtime_root = "/tmp/candidate"
os.mkdir(runtime_root, 0o700)
with tarfile.open(archive_path, mode="r:") as archive:
    archive.extractall(runtime_root, filter="data")
for current_root, directories, files in os.walk(runtime_root, topdown=False):
    for name in files:
        path = os.path.join(current_root, name)
        if not os.path.islink(path):
            os.chmod(path, 0o444)
    for name in directories:
        path = os.path.join(current_root, name)
        if not os.path.islink(path):
            os.chmod(path, 0o555)
os.chmod(runtime_root, 0o555)
os.chdir(runtime_root)
os.execve(
    "/app/.venv/bin/python",
    ("/app/.venv/bin/python", "-S", *sys.argv[2:]),
    os.environ,
)
"""


@dataclass(frozen=True, slots=True)
class CandidateExecutionResult:
    """Bounded candidate stdout and the exact committed execution bundle digest."""

    stdout: bytes | None
    execution_bundle_sha256: str


class DockerCandidateExecutor:
    """Run candidate code without host network, writable mounts, keys, or source repo."""

    def __init__(
        self,
        *,
        image_id: str,
        docker_binary: str = "docker",
        memory_limit: str = "1g",
        cpu_limit: str = "1.0",
        pids_limit: int = 64,
        tmpfs_size: str = "256m",
    ) -> None:
        if (
            not _IMAGE_ID.fullmatch(image_id)
            or docker_binary != "docker"
            or not re.fullmatch(r"[1-9][0-9]*(?:[kmg])?", memory_limit)
            or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", cpu_limit)
            or not 8 <= pids_limit <= 512
            or not re.fullmatch(r"[1-9][0-9]*(?:[kmg])?", tmpfs_size)
        ):
            raise CandidateControlError("EVOLUTION_SANDBOX_CONFIG_INVALID")
        self._image_id = image_id
        self._docker_binary = docker_binary
        self._memory_limit = memory_limit
        self._cpu_limit = cpu_limit
        self._pids_limit = pids_limit
        self._tmpfs_size = tmpfs_size

    @staticmethod
    def runtime_path(repository: GitRepository, repository_path: str) -> str:
        del repository
        if (
            not repository_path
            or repository_path.startswith(("/", "\\"))
            or "\\" in repository_path
            or ".." in repository_path.split("/")
        ):
            raise CandidateControlError("EVOLUTION_SANDBOX_RUNTIME_PATH_INVALID")
        return f"/tmp/candidate/{repository_path}"

    def profile_digest(self) -> str:
        payload = {
            "schema_version": "docker-candidate-executor-profile-v1",
            "image_id": self._image_id,
            "memory_limit": self._memory_limit,
            "cpu_limit": self._cpu_limit,
            "pids_limit": self._pids_limit,
            "tmpfs_size": self._tmpfs_size,
            "bootstrap_version": _BOOTSTRAP_VERSION,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def run(
        self,
        repository: GitRepository,
        args: tuple[str, ...],
        *,
        input_data: bytes | None,
        timeout: int,
    ) -> CandidateExecutionResult:
        if timeout < 1:
            raise CandidateControlError("EVOLUTION_SANDBOX_TIMEOUT_INVALID")
        repository.require_clean()
        expected_head = repository.head()
        name = f"gerclaw-eval-{uuid.uuid4().hex}"
        staging_name = f"{name}-stage"
        volume_name = f"{name}-bundle"
        stdout: bytes | None = None
        with tempfile.TemporaryDirectory(prefix="gerclaw-evolution-bundle-") as temp_root:
            archive_path = Path(temp_root) / "candidate.tar"
            bundle_digest = repository.export_commit_archive(expected_head, archive_path)
            try:
                prepared = self._prepare_bundle(
                    staging_name,
                    volume_name,
                    archive_path,
                )
                created = prepared and self._create_container(
                    name,
                    volume_name,
                    bundle_digest,
                    args,
                )
                if created:
                    stdout = self._start_container(
                        name,
                        input_data=input_data,
                        timeout=timeout,
                    )
            finally:
                container_removed = self._remove_container(name)
                staging_removed = self._remove_container(staging_name)
                volume_removed = self._remove_volume(volume_name)
                if not all((container_removed, staging_removed, volume_removed)):
                    raise CandidateControlError("EVOLUTION_SANDBOX_CLEANUP_FAILED")
        repository.require_clean()
        if repository.head() != expected_head:
            raise CandidateControlError("EVOLUTION_SANDBOX_MUTATED_CANDIDATE")
        return CandidateExecutionResult(
            stdout=stdout,
            execution_bundle_sha256=bundle_digest,
        )

    def _create_container(
        self,
        name: str,
        volume_name: str,
        bundle_digest: str,
        args: tuple[str, ...],
    ) -> bool:
        command = (
            self._docker_binary,
            "create",
            "--interactive",
            "--pull",
            "never",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(self._pids_limit),
            "--memory",
            self._memory_limit,
            "--cpus",
            self._cpu_limit,
            "--ulimit",
            "nofile=128:128",
            "--user",
            "65532:65532",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,nodev,size={self._tmpfs_size}",
            "--mount",
            (
                f"type=volume,src={volume_name},dst=/bundle,"
                "readonly,volume-nocopy"
            ),
            "--workdir",
            "/tmp",
            "--env",
            "HOME=/tmp",
            "--env",
            "TMPDIR=/tmp",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONHASHSEED=0",
            "--env",
            (
                "PYTHONPATH=/tmp/candidate/apps/api/src:"
                "/app/.venv/lib/python3.12/site-packages"
            ),
            self._image_id,
            "/app/.venv/bin/python",
            "-S",
            "-c",
            _BOOTSTRAP_SCRIPT,
            bundle_digest,
            *args,
        )
        return self._controller_command(command, timeout=30)

    def _prepare_bundle(
        self,
        staging_name: str,
        volume_name: str,
        archive_path: Path,
    ) -> bool:
        if not self._controller_command(
            (self._docker_binary, "volume", "create", volume_name),
            timeout=30,
        ):
            return False
        if not self._controller_command(
            (
                self._docker_binary,
                "create",
                "--name",
                staging_name,
                "--network",
                "none",
                "--mount",
                (
                    f"type=volume,src={volume_name},dst=/bundle,"
                    "volume-nocopy"
                ),
                self._image_id,
                "/bin/true",
            ),
            timeout=30,
        ):
            return False
        copied = self._controller_command(
            (
                self._docker_binary,
                "cp",
                str(archive_path),
                f"{staging_name}:/bundle/candidate.tar",
            ),
            timeout=60,
        )
        return copied and self._remove_container(staging_name)

    def _start_container(
        self,
        name: str,
        *,
        input_data: bytes | None,
        timeout: int,
    ) -> bytes | None:
        try:
            with tempfile.TemporaryFile() as output:
                process = subprocess.Popen(
                    (self._docker_binary, "start", "--attach", "--interactive", name),
                    stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    preexec_fn=self._limit_client_output,
                )
                try:
                    process.communicate(input=input_data, timeout=timeout)
                except subprocess.TimeoutExpired:
                    self._terminate_process_group(process)
                    return None
                if process.returncode != 0 or output.tell() > _MAX_OUTPUT_BYTES:
                    return None
                output.seek(0)
                return output.read(_MAX_OUTPUT_BYTES + 1)
        except OSError:
            return None

    @staticmethod
    def _controller_command(command: tuple[str, ...], *, timeout: int) -> bool:
        try:
            result = subprocess.run(
                command,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    @staticmethod
    def _limit_client_output() -> None:
        resource.setrlimit(
            resource.RLIMIT_FSIZE,
            (_MAX_OUTPUT_BYTES, _MAX_OUTPUT_BYTES),
        )

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()

    def _remove_container(self, name: str) -> bool:
        for _attempt in range(3):
            self._controller_command(
                (self._docker_binary, "rm", "--force", name),
                timeout=15,
            )
            absent = self._resource_absent("container", name)
            if absent is True:
                return True
        return False

    def _remove_volume(self, name: str) -> bool:
        for _attempt in range(3):
            self._controller_command(
                (self._docker_binary, "volume", "rm", "--force", name),
                timeout=15,
            )
            absent = self._resource_absent("volume", name)
            if absent is True:
                return True
        return False

    def _resource_absent(
        self,
        resource: str,
        name: str,
    ) -> bool | None:
        command = (
            (
                self._docker_binary,
                "container",
                "ls",
                "--all",
                "--filter",
                f"name=^/{name}$",
                "--format",
                "{{.Names}}",
            )
            if resource == "container"
            else (
                self._docker_binary,
                "volume",
                "ls",
                "--filter",
                f"name=^{name}$",
                "--format",
                "{{.Name}}",
            )
        )
        try:
            result = subprocess.run(
                command,
                check=False,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=15,
            )
            if result.returncode != 0:
                return None
            names = result.stdout.decode("utf-8", errors="strict").splitlines()
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
            return None
        return name not in names
