"""Pinned rootless Podman provider for the AirBench sandbox.

The provider is intentionally Linux/POSIX-only in the first scope.  The
Windows Podman client controls a Linux VM, but Windows paths embedded in an
AirBench code action are not valid paths inside that VM.  Refusing that
combination is safer than silently changing the meaning of a path scope.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .sandbox import (
    SandboxCapabilities,
    SandboxError,
    SandboxExecutionRequest,
    SandboxExecutionResponse,
)


_IMAGE_DIGEST = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
_USER = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*$")
_SAFE_ENVIRONMENT = frozenset({
    "PYTHONNOUSERSITE",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
})
_DEFAULT_CPU_SECONDS = 10.0
_DEFAULT_MEMORY_BYTES = 512 * 1024 * 1024
_DEFAULT_DISK_BYTES = 64 * 1024 * 1024
_DEFAULT_PROCESS_COUNT = 64


@dataclass(slots=True)
class PodmanProvider:
    """Execute the existing AirBench worker inside a pinned Podman image."""

    image_ref: str
    executable: str = "podman"
    python_executable: str = "/usr/local/bin/python"
    user: str = "65532:65532"
    expected_runtime_version: str | None = None
    default_cpu_seconds: float = _DEFAULT_CPU_SECONDS
    default_memory_bytes: int = _DEFAULT_MEMORY_BYTES
    default_disk_bytes: int = _DEFAULT_DISK_BYTES
    default_processes: int = _DEFAULT_PROCESS_COUNT
    control_timeout_seconds: float = 10.0
    _verified_runtime_version: str | None = None
    _verification_digest: str | None = None

    def __post_init__(self) -> None:
        if not _IMAGE_DIGEST.fullmatch(self.image_ref):
            raise SandboxError(
                "unverified_image",
                "Podman sandbox images must use a sha256 digest, not a tag",
            )
        if not self.python_executable.startswith("/"):
            raise SandboxError("invalid_provider", "container Python executable must be an absolute POSIX path")
        if not _USER.fullmatch(self.user):
            raise SandboxError("invalid_provider", "container user must be an explicit non-root uid:gid")
        if self.default_cpu_seconds <= 0:
            raise SandboxError("invalid_provider", "default CPU limit must be positive")
        if self.default_memory_bytes <= 0 or self.default_disk_bytes <= 0 or self.default_processes <= 0:
            raise SandboxError("invalid_provider", "default resource limits must be positive")
        if self.control_timeout_seconds <= 0:
            raise SandboxError("invalid_provider", "provider control timeout must be positive")

    @property
    def capabilities(self) -> SandboxCapabilities:
        verified = self._verification_digest is not None
        return SandboxCapabilities(
            provider_id="podman.rootless",
            provider_version=self._verified_runtime_version or self.expected_runtime_version or "unverified",
            hard_network_isolation=verified,
            hard_filesystem_isolation=verified,
            non_root_execution=verified,
            restricted_syscalls=verified,
            resource_limits=(
                "code_bytes", "output_bytes", "wall_time", "cpu_time", "memory", "disk", "processes",
            ) if verified else ("code_bytes", "output_bytes", "wall_time"),
        )

    def verify(self) -> None:
        """Verify the local runtime, rootless mode, seccomp, and image digest."""

        if os.name == "nt":
            raise SandboxError(
                "provider_host_unsupported",
                "PodmanProvider requires AirBench to run on a POSIX host; Windows Podman path mapping is not supported",
            )
        executable = self._resolve_executable()
        version = self._control(executable, ("version", "--format", "json"))
        version_payload = self._json_object(version.stdout, "Podman version output")
        runtime_version = self._runtime_version(version_payload)
        if not runtime_version:
            raise SandboxError("provider_unverified", "Podman runtime version was not present in its identity response")
        if self.expected_runtime_version is not None and runtime_version != self.expected_runtime_version:
            raise SandboxError("provider_version_mismatch", "Podman runtime version does not match the pinned configuration")

        info = self._control(executable, ("info", "--format", "json"))
        info_payload = self._json_object(info.stdout, "Podman info output")
        host = info_payload.get("host")
        security = host.get("security") if isinstance(host, dict) else None
        if not isinstance(security, dict) or security.get("rootless") is not True:
            raise SandboxError("provider_not_rootless", "Podman provider is not running in rootless mode")
        if security.get("seccompEnabled") is not True:
            raise SandboxError("provider_seccomp_unavailable", "Podman provider does not report seccomp enforcement")

        image = self._control(
            executable,
            ("image", "inspect", "--format", "{{json .RepoDigests}}", self.image_ref),
        )
        repo_digests = self._json_array(image.stdout, "Podman image identity output")
        if self.image_ref not in repo_digests:
            raise SandboxError("image_unverified", "the pinned Podman image digest is not present in the local image store")

        self._verified_runtime_version = runtime_version
        self._verification_digest = _digest({
            "version": version_payload,
            "info": info_payload,
            "image": repo_digests,
        })

    def build_command(
        self,
        request: SandboxExecutionRequest,
    ) -> tuple[tuple[str, ...], Mapping[str, float | int | None], str]:
        """Build a fully explicit, no-pull Podman command for one request."""

        self._validate_request(request)
        effective_limits = self._effective_limits(request.resource_limits)
        container_name = self._container_name(request)
        command: list[str] = [
            self.executable,
            "run",
            "--name",
            container_name,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user",
            self.user,
            "--workdir",
            str(request.cwd.resolve()),
            "--ulimit",
            f"cpu={max(1, math.ceil(float(effective_limits['max_cpu_seconds'])))}",
            "--memory",
            str(int(effective_limits["max_memory_bytes"])),
            "--storage-opt",
            f"size={int(effective_limits['max_disk_bytes'])}",
            "--pids-limit",
            str(int(effective_limits["max_processes"])),
        ]

        mounts: dict[str, str] = {str(request.cwd.resolve()): "rw"}
        for path in request.read_paths:
            mounts[str(path.resolve())] = "ro"
        for path in request.write_paths:
            mounts[str(path.resolve())] = "rw"
        for path, mode in sorted(mounts.items()):
            command.extend(("--mount", f"type=bind,src={path},dst={path},{mode}"))

        command.extend(("--env", "PATH=/usr/local/bin:/usr/bin:/bin"))
        for key in sorted(_SAFE_ENVIRONMENT):
            if key in request.environment:
                command.extend(("--env", f"{key}={request.environment[key]}"))
        command.extend((self.image_ref, self.python_executable, *request.command[1:]))
        return tuple(command), effective_limits, container_name

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResponse:
        self.verify()
        command, enforced_limits, container_name = self.build_command(request)
        executable = self._resolve_executable()
        self._remove_container(executable, container_name)
        try:
            process = subprocess.Popen(
                command,
                cwd=str(request.cwd.resolve()),
                env=self._control_environment(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError:
            self._remove_container(executable, container_name)
            return SandboxExecutionResponse(
                "failed",
                None,
                "",
                "Podman sandbox could not be started",
                enforced_resource_limits=enforced_limits,
                isolation_evidence_refs=self._evidence_refs(command),
            )

        try:
            stdout, stderr = process.communicate(request.stdin, timeout=request.timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            cleanup_status = self._remove_container(executable, container_name)
            return SandboxExecutionResponse(
                "timed_out",
                None,
                _truncate(stdout or "", request.max_output_bytes * 2 + 4096),
                "Podman sandbox execution timed out",
                enforced_resource_limits=enforced_limits,
                resource_usage={"exit_code": -1, "timed_out": 1},
                isolation_evidence_refs=self._evidence_refs(command),
                cleanup_status=cleanup_status,
            )

        state, state_digest = self._inspect_container(executable, container_name)
        usage = self._resource_usage(executable, container_name, state)
        cleanup_status = self._remove_container(executable, container_name)
        status = "succeeded" if process.returncode == 0 else "failed"
        evidence = self._evidence_refs(command, state_digest)
        if cleanup_status == "failed":
            status = "failed"
            stderr = (stderr or "") + "\nPodman sandbox cleanup failed"
        return SandboxExecutionResponse(
            status,
            process.returncode,
            _truncate(stdout or "", request.max_output_bytes * 2 + 4096),
            _truncate(stderr or "", request.max_output_bytes * 2 + 4096),
            enforced_resource_limits=enforced_limits,
            resource_usage=usage,
            isolation_evidence_refs=evidence,
            cleanup_status=cleanup_status,
        )

    def _validate_request(self, request: SandboxExecutionRequest) -> None:
        if os.name == "nt":
            raise SandboxError(
                "provider_host_unsupported",
                "PodmanProvider requires POSIX paths so the container sees the same approved path scopes",
            )
        if len(request.command) < 3 or request.command[1:3] != ("-I", "-c"):
            raise SandboxError("invalid_worker_command", "PodmanProvider accepts only the AirBench isolated Python worker command")
        paths = (request.root_dir, request.cwd, *request.read_paths, *request.write_paths)
        for raw_path in paths:
            if not raw_path.is_absolute():
                raise SandboxError("invalid_scope", "Podman sandbox paths must be absolute")
            if "," in str(raw_path) or "\x00" in str(raw_path):
                raise SandboxError("invalid_scope", "Podman mount paths cannot contain mount delimiters")
        try:
            root = request.root_dir.resolve()
            cwd = request.cwd.resolve()
        except OSError as exc:
            raise SandboxError("invalid_scope", "Podman sandbox paths could not be resolved") from exc
        if not _inside(cwd, (root,)):
            raise SandboxError("invalid_scope", "Podman worker cwd is outside the sandbox root")
        if not cwd.is_dir() or not root.is_dir():
            raise SandboxError("invalid_scope", "Podman worker cwd and root must exist")
        for path in (*request.read_paths, *request.write_paths):
            if not path.exists():
                raise SandboxError("invalid_scope", "Podman mount scope must exist before execution")
        for read_path in request.read_paths:
            for write_path in request.write_paths:
                if _overlaps(read_path.resolve(), write_path.resolve()):
                    raise SandboxError("conflicting_scope", "Podman read and write mounts overlap")
        unknown_environment = set(request.environment) - _SAFE_ENVIRONMENT - {"PATH"}
        if unknown_environment:
            raise SandboxError("invalid_environment", "Podman sandbox received an environment variable outside its allowlist")

    def _effective_limits(self, limits: Mapping[str, float | int | None]) -> dict[str, float | int | None]:
        return {
            "max_wall_seconds": float(limits.get("max_wall_seconds") or 10.0),
            "max_output_bytes": int(limits.get("max_output_bytes") or 1_000_000),
            "max_code_bytes": int(limits.get("max_code_bytes") or 256_000),
            "max_cpu_seconds": float(limits.get("max_cpu_seconds") or self.default_cpu_seconds),
            "max_memory_bytes": int(limits.get("max_memory_bytes") or self.default_memory_bytes),
            "max_disk_bytes": int(limits.get("max_disk_bytes") or self.default_disk_bytes),
            "max_processes": int(limits.get("max_processes") or self.default_processes),
        }

    def _resolve_executable(self) -> str:
        candidate = str(self.executable)
        resolved = candidate if os.path.isabs(candidate) and Path(candidate).is_file() else shutil.which(candidate)
        if not resolved:
            raise SandboxError("provider_unavailable", "configured Podman executable is not available")
        return resolved

    def _control(self, executable: str, args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                (executable, *args),
                env=self._control_environment(),
                capture_output=True,
                text=True,
                timeout=self.control_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SandboxError("provider_unavailable", "Podman control command could not be completed") from exc
        if result.returncode != 0:
            raise SandboxError("provider_unverified", "Podman control command failed")
        return result

    def _control_environment(self) -> dict[str, str]:
        allowed = {"PATH", "HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "CONTAINERS_CONF"}
        return {key: value for key, value in os.environ.items() if key in allowed}

    def _remove_container(self, executable: str, name: str) -> str:
        try:
            result = subprocess.run(
                (executable, "container", "rm", "--force", "--ignore", name),
                env=self._control_environment(),
                capture_output=True,
                text=True,
                timeout=self.control_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "failed"
        return "completed" if result.returncode == 0 else "failed"

    def _inspect_container(self, executable: str, name: str) -> tuple[dict[str, Any], str]:
        try:
            result = self._control(executable, ("container", "inspect", "--size", name))
            payload = json.loads(result.stdout)
            container = payload[0] if isinstance(payload, list) and payload else {}
            if not isinstance(container, dict):
                container = {}
        except (SandboxError, json.JSONDecodeError, IndexError, TypeError):
            return {}, _digest({"inspect": "unavailable"})
        return container, _digest(container)

    def _resource_usage(self, executable: str, name: str, state: Mapping[str, Any]) -> dict[str, float | int | None]:
        usage: dict[str, float | int | None] = {
            "exit_code": _number(state.get("State", {}).get("ExitCode")) if isinstance(state.get("State"), dict) else None,
            "oom_killed": int(bool(state.get("State", {}).get("OOMKilled"))) if isinstance(state.get("State"), dict) else None,
            "disk_bytes": _number(state.get("SizeRw")),
        }
        try:
            stats = self._control(executable, ("stats", "--no-stream", "--format", "json", name))
            payload = json.loads(stats.stdout)
            record = payload[0] if isinstance(payload, list) and payload else payload
            if isinstance(record, dict):
                usage["cpu_percent"] = _percent(record.get("CPU %"))
                usage["memory_bytes"] = _memory_bytes(record.get("MemUsage"))
                usage["pids_current"] = _number(record.get("PIDS"))
        except (SandboxError, json.JSONDecodeError, TypeError, ValueError):
            usage["stats_available"] = 0
        else:
            usage["stats_available"] = 1
        return usage

    def _container_name(self, request: SandboxExecutionRequest) -> str:
        digest = hashlib.sha256((str(request.cwd.resolve()) + request.stdin).encode("utf-8")).hexdigest()[:20]
        return f"airbench-sbx-{digest}"

    def _evidence_refs(self, command: tuple[str, ...], state_digest: str | None = None) -> tuple[str, ...]:
        verification = self._verification_digest or _digest({"status": "unverified"})
        command_digest = _digest({"command": command})
        refs = [f"podman:verification:{verification}", f"podman:command:{command_digest}"]
        if state_digest is not None:
            refs.append(f"podman:state:{state_digest}")
        return tuple(refs)

    @staticmethod
    def _json_object(raw: str, label: str) -> dict[str, Any]:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SandboxError("provider_unverified", f"{label} was not valid JSON") from exc
        if not isinstance(value, dict):
            raise SandboxError("provider_unverified", f"{label} was not a JSON object")
        return value

    @staticmethod
    def _json_array(raw: str, label: str) -> list[str]:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SandboxError("provider_unverified", f"{label} was not valid JSON") from exc
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise SandboxError("provider_unverified", f"{label} was not a string array")
        return value

    @staticmethod
    def _runtime_version(payload: Mapping[str, Any]) -> str | None:
        for section in (payload.get("Server"), payload.get("server"), payload.get("Version"), payload.get("version")):
            if isinstance(section, dict):
                value = section.get("Version") or section.get("version")
                if isinstance(value, str):
                    return value
        return None


def _inside(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _truncate(value: str, limit: int) -> str:
    encoded = value.encode("utf-8", errors="replace")
    return value if len(encoded) <= limit else encoded[:limit].decode("utf-8", errors="ignore")


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        match = re.search(r"-?[0-9]+(?:\.[0-9]+)?", value)
        if match:
            number = float(match.group(0))
            return int(number) if number.is_integer() else number
    return None


def _percent(value: Any) -> float | None:
    number = _number(value)
    return float(number) if number is not None else None


def _memory_bytes(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(B|KB|KiB|MB|MiB|GB|GiB)", value, re.IGNORECASE)
    if not match:
        return None
    factors = {"b": 1, "kb": 1000, "kib": 1024, "mb": 1000**2, "mib": 1024**2, "gb": 1000**3, "gib": 1024**3}
    return int(float(match.group(1)) * factors[match.group(2).lower()])


__all__ = ["PodmanProvider"]
