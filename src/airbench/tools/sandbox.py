"""Bounded local execution for AirBench tool actions.

The Python guard is a defense-in-depth test/runtime layer. It is not claimed
to replace an OS container, job object, namespace, or firewall. A deployment
that requires hard no-egress enforcement must provide a verified isolation
provider and the runner reports that capability explicitly.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol

from contracts import Clearance, Taint, ToolAction, build_event, idempotency_key, stable_id

from .gateway import ToolAuthorization


_RESOURCE_LIMIT_NAMES = frozenset({
    "wall_time", "output_bytes", "code_bytes", "cpu_time", "memory", "disk", "processes",
})


class SandboxError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SandboxCapabilities:
    """Capabilities asserted by the execution provider, not by its caller."""

    provider_id: str
    provider_version: str
    hard_network_isolation: bool
    hard_filesystem_isolation: bool
    non_root_execution: bool
    restricted_syscalls: bool
    resource_limits: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.provider_id or not self.provider_version:
            raise SandboxError("invalid_provider", "sandbox provider identity is required")
        if not all(isinstance(value, bool) for value in (
            self.hard_network_isolation,
            self.hard_filesystem_isolation,
            self.non_root_execution,
            self.restricted_syscalls,
        )):
            raise SandboxError("invalid_provider", "sandbox provider capabilities must be boolean")
        if len(set(self.resource_limits)) != len(self.resource_limits):
            raise SandboxError("invalid_provider", "sandbox provider resource capabilities must be unique")
        if not set(self.resource_limits).issubset(_RESOURCE_LIMIT_NAMES):
            raise SandboxError("invalid_provider", "sandbox provider declares an unknown resource capability")

    def digest(self) -> str:
        self.validate()
        payload = {
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "hard_network_isolation": self.hard_network_isolation,
            "hard_filesystem_isolation": self.hard_filesystem_isolation,
            "non_root_execution": self.non_root_execution,
            "restricted_syscalls": self.restricted_syscalls,
            "resource_limits": sorted(self.resource_limits),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SandboxExecutionRequest:
    """Provider-neutral request for one disposable worker process."""

    command: tuple[str, ...]
    cwd: Path
    environment: Mapping[str, str]
    stdin: str
    timeout_seconds: float
    max_output_bytes: int
    root_dir: Path
    read_paths: tuple[Path, ...]
    write_paths: tuple[Path, ...]
    resource_limits: Mapping[str, float | int | None]


@dataclass(frozen=True, slots=True)
class SandboxExecutionResponse:
    status: Literal["succeeded", "failed", "timed_out"]
    exit_code: int | None
    stdout: str
    stderr: str
    enforced_resource_limits: Mapping[str, float | int | None] = field(default_factory=dict)
    resource_usage: Mapping[str, float | int | None] = field(default_factory=dict)
    isolation_evidence_refs: tuple[str, ...] = ()
    cleanup_status: Literal["completed", "failed"] = "completed"


class SandboxProvider(Protocol):
    @property
    def capabilities(self) -> SandboxCapabilities: ...

    def verify(self) -> None: ...

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResponse: ...


class LocalSubprocessProvider:
    """Development provider using the Python guard as defense in depth only."""

    @property
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities(
            provider_id="python.subprocess-guard",
            provider_version="1",
            hard_network_isolation=False,
            hard_filesystem_isolation=False,
            non_root_execution=False,
            restricted_syscalls=False,
            resource_limits=("code_bytes", "output_bytes", "wall_time"),
        )

    def verify(self) -> None:
        """The local provider has no external runtime to verify."""

        return None

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResponse:
        try:
            process = subprocess.Popen(
                request.command,
                cwd=request.cwd,
                env=dict(request.environment),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError:
            return SandboxExecutionResponse("failed", None, "", "sandbox worker could not be started")
        try:
            raw_stdout, raw_stderr = process.communicate(request.stdin, timeout=request.timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            raw_stdout, raw_stderr = process.communicate()
            return SandboxExecutionResponse(
                "timed_out",
                None,
                _truncate_utf8(raw_stdout or "", request.max_output_bytes * 2 + 4096),
                "sandbox execution timed out",
            )
        except (OSError, TypeError, ValueError):
            if process.poll() is None:
                process.kill()
                process.wait()
            return SandboxExecutionResponse("failed", None, "", "sandbox worker failed or returned invalid output")
        return SandboxExecutionResponse(
            "succeeded" if process.returncode == 0 else "failed",
            process.returncode,
            _truncate_utf8(raw_stdout, request.max_output_bytes * 2 + 4096),
            _truncate_utf8(raw_stderr, request.max_output_bytes * 2 + 4096),
        )


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    root_dir: Path
    max_wall_seconds: float = 10.0
    max_output_bytes: int = 1_000_000
    max_code_bytes: int = 256_000
    require_hard_network_isolation: bool = False
    max_cpu_seconds: float | None = None
    max_memory_bytes: int | None = None
    max_disk_bytes: int | None = None
    max_processes: int | None = None
    allowed_read_paths: tuple[Path, ...] = ()
    allowed_write_paths: tuple[Path, ...] = ()

    def validate(self) -> None:
        try:
            root_dir = self.root_dir.resolve()
        except OSError as exc:
            raise SandboxError("invalid_root", "sandbox root cannot be resolved") from exc
        if not root_dir.is_dir():
            raise SandboxError("invalid_root", "sandbox root must be an existing directory")
        if self.max_wall_seconds <= 0 or self.max_wall_seconds > 300:
            raise SandboxError("invalid_timeout", "sandbox wall time must be between 0 and 300 seconds")
        if self.max_output_bytes <= 0 or self.max_output_bytes > 50_000_000:
            raise SandboxError("invalid_output_limit", "sandbox output limit is invalid")
        if self.max_code_bytes <= 0 or self.max_code_bytes > 5_000_000:
            raise SandboxError("invalid_code_limit", "sandbox code limit is invalid")
        if self.max_cpu_seconds is not None and (self.max_cpu_seconds <= 0 or self.max_cpu_seconds > 300):
            raise SandboxError("invalid_cpu_limit", "sandbox CPU limit is invalid")
        if self.max_memory_bytes is not None and (self.max_memory_bytes <= 0 or self.max_memory_bytes > 64 * 1024**3):
            raise SandboxError("invalid_memory_limit", "sandbox memory limit is invalid")
        if self.max_disk_bytes is not None and (self.max_disk_bytes <= 0 or self.max_disk_bytes > 1024 * 1024**3):
            raise SandboxError("invalid_disk_limit", "sandbox disk limit is invalid")
        if self.max_processes is not None and (self.max_processes <= 0 or self.max_processes > 1024):
            raise SandboxError("invalid_process_limit", "sandbox process limit is invalid")

    def digest(self) -> str:
        payload = {
            "root_dir": str(self.root_dir.resolve()),
            "max_wall_seconds": self.max_wall_seconds,
            "max_output_bytes": self.max_output_bytes,
            "max_code_bytes": self.max_code_bytes,
            "require_hard_network_isolation": self.require_hard_network_isolation,
            "max_cpu_seconds": self.max_cpu_seconds,
            "max_memory_bytes": self.max_memory_bytes,
            "max_disk_bytes": self.max_disk_bytes,
            "max_processes": self.max_processes,
            "allowed_read_paths": sorted(str(path.resolve()) for path in self.allowed_read_paths),
            "allowed_write_paths": sorted(str(path.resolve()) for path in self.allowed_write_paths),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def resource_limits(self) -> dict[str, float | int | None]:
        return {
            "max_wall_seconds": self.max_wall_seconds,
            "max_output_bytes": self.max_output_bytes,
            "max_code_bytes": self.max_code_bytes,
            "max_cpu_seconds": self.max_cpu_seconds,
            "max_memory_bytes": self.max_memory_bytes,
            "max_disk_bytes": self.max_disk_bytes,
            "max_processes": self.max_processes,
        }


@dataclass(frozen=True, slots=True)
class SandboxManifest:
    execution_id: str
    provider_id: str
    provider_version: str
    capability_digest: str
    policy_hash: str
    root_digest: str
    read_scope_digests: tuple[str, ...]
    write_scope_digests: tuple[str, ...]
    resource_limits: Mapping[str, float | int | None]
    enforced_resource_limits: Mapping[str, float | int | None]
    resource_usage: Mapping[str, float | int | None]
    isolation_evidence_refs: tuple[str, ...]
    status: Literal["succeeded", "failed", "timed_out", "rejected"]
    output_hash: str
    observed_wall_ms: int
    cleanup_status: Literal["completed", "failed"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "capability_digest": self.capability_digest,
            "policy_hash": self.policy_hash,
            "root_digest": self.root_digest,
            "read_scope_digests": list(self.read_scope_digests),
            "write_scope_digests": list(self.write_scope_digests),
            "resource_limits": dict(self.resource_limits),
            "enforced_resource_limits": dict(self.enforced_resource_limits),
            "resource_usage": dict(self.resource_usage),
            "isolation_evidence_refs": list(self.isolation_evidence_refs),
            "status": self.status,
            "output_hash": self.output_hash,
            "observed_wall_ms": self.observed_wall_ms,
            "cleanup_status": self.cleanup_status,
        }

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SandboxResult:
    execution_id: str
    status: Literal["succeeded", "failed", "timed_out", "rejected"]
    exit_code: int | None
    stdout: str
    stderr: str
    output_hash: str
    policy_hash: str
    hard_network_isolation: bool
    ledger_event_refs: tuple[str, ...]
    started_at: str
    finished_at: str
    provider_id: str = ""
    provider_version: str = ""
    capability_digest: str = ""
    manifest_hash: str = ""
    cleanup_status: Literal["completed", "failed"] = "completed"
    manifest: SandboxManifest | None = None
    enforced_resource_limits: Mapping[str, float | int | None] = field(default_factory=dict)
    resource_usage: Mapping[str, float | int | None] = field(default_factory=dict)
    isolation_evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "output_hash": self.output_hash,
            "policy_hash": self.policy_hash,
            "hard_network_isolation": self.hard_network_isolation,
            "ledger_event_refs": list(self.ledger_event_refs),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "capability_digest": self.capability_digest,
            "manifest_hash": self.manifest_hash,
            "cleanup_status": self.cleanup_status,
            "manifest": self.manifest.to_dict() if self.manifest is not None else None,
            "enforced_resource_limits": dict(self.enforced_resource_limits),
            "resource_usage": dict(self.resource_usage),
            "isolation_evidence_refs": list(self.isolation_evidence_refs),
        }


class LedgerSink(Protocol):
    @property
    def events(self) -> tuple[Any, ...]: ...

    @property
    def head_hash(self) -> str | None: ...

    def append(self, event: Any) -> Any: ...


_WORKER = textwrap.dedent(
    r'''
    import builtins
    import contextlib
    import io
    import json
    import os
    import pathlib
    import socket
    import subprocess
    import sys
    import urllib.request
    
    payload = json.load(sys.stdin)
    run_dir = pathlib.Path(payload["run_dir"]).resolve()
    read_roots = [pathlib.Path(value).resolve() for value in payload["read_roots"]]
    write_roots = [run_dir, *(pathlib.Path(value).resolve() for value in payload["write_roots"])]
    code = payload["code"]
    max_output_bytes = int(payload["max_output_bytes"])
    
    def inside(path, roots):
        candidate = pathlib.Path(path).resolve()
        return any(candidate == root or root in candidate.parents for root in roots)
    
    def deny_network(*args, **kwargs):
        raise PermissionError("network access is denied by the AirBench sandbox")
    
    def guarded_open(file, mode="r", *args, **kwargs):
        write = any(flag in mode for flag in ("w", "a", "x", "+"))
        if write and not inside(file, write_roots):
            raise PermissionError("write path is outside the AirBench sandbox scope")
        if not write and not inside(file, read_roots + write_roots):
            raise PermissionError("read path is outside the AirBench sandbox scope")
        return _open(file, mode, *args, **kwargs)
    
    _open = builtins.open
    builtins.open = guarded_open
    io.open = guarded_open
    socket.socket = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    urllib.request.urlopen = deny_network
    subprocess.Popen = deny_network
    subprocess.run = deny_network
    subprocess.call = deny_network
    subprocess.check_call = deny_network
    subprocess.check_output = deny_network
    os.system = deny_network
    os.popen = deny_network
    os.execv = deny_network
    os.execve = deny_network
    os.spawnv = deny_network
    os.spawnve = deny_network
    blocked_imports = {"ctypes", "ensurepip", "pip", "setuptools", "socket", "urllib", "http", "subprocess"}
    _import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name.split(".", 1)[0] in blocked_imports:
            raise ImportError("module is denied by the AirBench sandbox")
        return _import(name, *args, **kwargs)
    builtins.__import__ = guarded_import
    
    class CappedBuffer(io.TextIOBase):
        def __init__(self, limit):
            self.limit = limit
            self.value = []
            self.size = 0
            self.truncated = False

        def write(self, value):
            encoded = value.encode("utf-8", errors="replace")
            remaining = max(0, self.limit - self.size)
            if len(encoded) > remaining:
                encoded = encoded[:remaining]
                self.truncated = True
            if encoded:
                self.value.append(encoded.decode("utf-8", errors="ignore"))
                self.size += len(encoded)
            return len(value)

        def getvalue(self):
            return "".join(self.value)

    stdout = CappedBuffer(max_output_bytes)
    stderr = CappedBuffer(max_output_bytes)
    status = "succeeded"
    error_type = None
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exec(compile(code, "<airbench-sandbox>", "exec"), {"__name__": "__main__", "__file__": "<airbench-sandbox>"}, {})
        except BaseException as exc:
            status = "failed"
            error_type = type(exc).__name__
    result = {
        "status": status,
        "error_type": error_type,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "output_limit_exceeded": stdout.truncated or stderr.truncated,
    }
    print(json.dumps(result, ensure_ascii=False), file=sys.__stdout__)
    '''
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _append_tool_event(ledger: LedgerSink, *, event_type: str, action: ToolAction, execution_id: str, payload: dict[str, Any], occurred_at: str) -> str:
    event = build_event(
        event_type=event_type,
        task_id=action.task_id,
        actor_id="sandbox.runner",
        actor_type="service",
        payload_contract="SandboxExecution",
        payload_version="1.0",
        payload={"execution_id": execution_id, "action_id": action.action_id, "tool_name": action.tool_name, **payload},
        clearance=action.clearance,
        idempotency=idempotency_key(f"sandbox.{event_type}", action.task_id, action.action_id, execution_id),
        sequence=len(ledger.events),
        previous_event_hash=ledger.head_hash,
        occurred_at=occurred_at,
    )
    try:
        ledger.append(event)
    except Exception as exc:
        raise SandboxError("ledger_write_failed", "sandbox ledger event could not be committed") from exc
    return event.event_id


def _safe_child_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }


def _truncate_utf8(value: str, limit: int) -> str:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


class SandboxRunner:
    def __init__(self, ledger: LedgerSink, provider: SandboxProvider | None = None) -> None:
        self._ledger = ledger
        self._provider = provider or LocalSubprocessProvider()

    def execute(self, action: ToolAction, policy: SandboxPolicy,
                authorization: ToolAuthorization | None = None) -> SandboxResult:
        policy.validate()
        verifier = getattr(self._provider, "verify", None)
        if callable(verifier):
            verifier()
        capabilities = self._provider.capabilities
        capabilities.validate()
        if policy.require_hard_network_isolation and not (
            capabilities.hard_network_isolation
            and capabilities.hard_filesystem_isolation
            and capabilities.non_root_execution
            and capabilities.restricted_syscalls
        ):
            raise SandboxError("network_isolation_unavailable", "required hard sandbox capabilities are not available")
        required_limits = {
            "wall_time", "output_bytes", "code_bytes",
        } | {
            name for name, value in (
                ("cpu_time", policy.max_cpu_seconds),
                ("memory", policy.max_memory_bytes),
                ("disk", policy.max_disk_bytes),
                ("processes", policy.max_processes),
            ) if value is not None
        }
        if not required_limits.issubset(capabilities.resource_limits):
            missing = ", ".join(sorted(required_limits - set(capabilities.resource_limits)))
            raise SandboxError("resource_isolation_unavailable", f"provider cannot enforce resource limits: {missing}")
        try:
            action = ToolAction.from_dict(action.to_dict())
        except Exception as exc:
            raise SandboxError("invalid_tool_action", "tool action failed contract validation") from exc
        if action.tool_name != "python.execute":
            raise SandboxError("unsupported_tool", "the sandbox accepts only python.execute")
        if authorization is not None:
            if not authorization.allowed:
                raise SandboxError("tool_not_authorized", "the Tool Gateway did not authorize this action")
            if authorization.action != action:
                raise SandboxError("authorization_mismatch", "the authorization does not match the action")
            if not authorization.requested_event_ref or not authorization.authorized_event_ref:
                raise SandboxError("authorization_incomplete", "the authorization has no ledger references")
        code = action.arguments.get("code")
        if not isinstance(code, str) or not code.strip():
            raise SandboxError("invalid_code", "python.execute requires non-empty code")
        if len(code.encode("utf-8")) > policy.max_code_bytes:
            raise SandboxError("code_too_large", "code exceeds the sandbox limit")
        execution_id = stable_id("sandbox", action.task_id, action.action_id, action.idempotency_key)
        policy_hash = policy.digest()
        capability_digest = capabilities.digest()
        started_at = _now()
        if authorization is None:
            requested_ref = _append_tool_event(self._ledger, event_type="tool.requested", action=action, execution_id=execution_id, payload={"input_hash": hashlib.sha256(code.encode()).hexdigest(), "policy_hash": policy_hash}, occurred_at=started_at)
            authorized_ref = _append_tool_event(self._ledger, event_type="tool.authorized", action=action, execution_id=execution_id, payload={"policy_hash": policy_hash, "provider_id": capabilities.provider_id, "provider_version": capabilities.provider_version, "capability_digest": capability_digest, "hard_network_isolation": capabilities.hard_network_isolation}, occurred_at=started_at)
        else:
            requested_ref = authorization.requested_event_ref
            authorized_ref = authorization.authorized_event_ref
        assert requested_ref is not None and authorized_ref is not None
        stdout = ""
        stderr = ""
        exit_code: int | None = None
        status: Literal["succeeded", "failed", "timed_out", "rejected"] = "failed"
        run_dir: Path | None = None
        cleanup_status: Literal["completed", "failed"] = "completed"
        enforced_resource_limits: Mapping[str, float | int | None] = {}
        resource_usage: Mapping[str, float | int | None] = {}
        isolation_evidence_refs: tuple[str, ...] = ()
        provider_cleanup_status: Literal["completed", "failed"] = "completed"
        try:
            run_dir = Path(tempfile.mkdtemp(prefix=f"airbench-{execution_id[:8]}-", dir=policy.root_dir))
            payload = {
                "run_dir": str(run_dir),
                "read_roots": [str(path.resolve()) for path in policy.allowed_read_paths],
                "write_roots": [str(path.resolve()) for path in policy.allowed_write_paths],
                "code": code,
                "max_output_bytes": policy.max_output_bytes,
            }
            response = self._provider.execute(SandboxExecutionRequest(
                command=(sys.executable, "-I", "-c", _WORKER),
                cwd=run_dir,
                environment=_safe_child_env(),
                stdin=json.dumps(payload),
                timeout_seconds=policy.max_wall_seconds,
                max_output_bytes=policy.max_output_bytes,
                root_dir=policy.root_dir,
                read_paths=policy.allowed_read_paths,
                write_paths=policy.allowed_write_paths,
                resource_limits=policy.resource_limits(),
            ))
            exit_code = response.exit_code
            status = response.status
            enforced_resource_limits = dict(response.enforced_resource_limits)
            resource_usage = dict(response.resource_usage)
            isolation_evidence_refs = tuple(response.isolation_evidence_refs)
            provider_cleanup_status = response.cleanup_status
            raw_stdout = response.stdout
            raw_stderr = response.stderr
            try:
                parsed = json.loads(raw_stdout) if raw_stdout else {"status": "failed", "error_type": "empty_worker_result", "stdout": "", "stderr": raw_stderr}
            except json.JSONDecodeError:
                parsed = {"status": "failed", "error_type": "invalid_worker_json", "stdout": "", "stderr": "sandbox worker failed or returned invalid output"}
            stdout = str(parsed.get("stdout", ""))
            stderr = str(parsed.get("stderr", ""))
            if parsed.get("output_limit_exceeded"):
                status = "failed"
                stderr = "sandbox output limit exceeded"
            if status == "succeeded" and (parsed.get("status") != "succeeded" or exit_code != 0):
                status = "failed"
        except (OSError, ValueError):
            stderr = "sandbox worker could not be started"
            status = "failed"
        finally:
            if run_dir is not None:
                try:
                    shutil.rmtree(run_dir)
                except OSError:
                    cleanup_status = "failed"
        if provider_cleanup_status == "failed":
            cleanup_status = "failed"
        finished_at = _now()
        output_hash = hashlib.sha256((stdout + "\n" + stderr).encode("utf-8", errors="replace")).hexdigest()
        observed_wall_ms = self._elapsed_ms(started_at, finished_at)
        manifest = SandboxManifest(
            execution_id=execution_id,
            provider_id=capabilities.provider_id,
            provider_version=capabilities.provider_version,
            capability_digest=capability_digest,
            policy_hash=policy_hash,
            root_digest=_path_digest(policy.root_dir),
            read_scope_digests=tuple(_path_digest(path) for path in policy.allowed_read_paths),
            write_scope_digests=tuple(_path_digest(path) for path in policy.allowed_write_paths),
            resource_limits=policy.resource_limits(),
            enforced_resource_limits=enforced_resource_limits,
            resource_usage=resource_usage,
            isolation_evidence_refs=isolation_evidence_refs,
            status=status,
            output_hash=output_hash,
            observed_wall_ms=observed_wall_ms,
            cleanup_status=cleanup_status,
        )
        manifest_hash = manifest.digest()
        result_ref = _append_tool_event(
            self._ledger,
            event_type="tool.result",
            action=action,
            execution_id=execution_id,
            payload={
                "status": status,
                "exit_code": exit_code,
                "output_hash": output_hash,
                "hard_network_isolation": capabilities.hard_network_isolation,
                "provider_id": capabilities.provider_id,
                "provider_version": capabilities.provider_version,
                "capability_digest": capability_digest,
                "manifest_hash": manifest_hash,
                "enforced_resource_limits": dict(enforced_resource_limits),
                "resource_usage": dict(resource_usage),
                "isolation_evidence_refs": list(isolation_evidence_refs),
                "cleanup_status": cleanup_status,
                "manifest": manifest.to_dict(),
                "provenance": {"source_ref": f"sandbox:{execution_id}", "confidence": 1.0 if status == "succeeded" else 0.0, "clearance": action.clearance.value, "taint": Taint.untrusted.value},
            },
            occurred_at=finished_at,
        )
        return SandboxResult(
            execution_id=execution_id,
            status=status,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            output_hash=output_hash,
            policy_hash=policy_hash,
            hard_network_isolation=capabilities.hard_network_isolation,
            ledger_event_refs=(requested_ref, authorized_ref, result_ref),
            started_at=started_at,
            finished_at=finished_at,
            provider_id=capabilities.provider_id,
            provider_version=capabilities.provider_version,
            capability_digest=capability_digest,
            manifest_hash=manifest_hash,
            cleanup_status=cleanup_status,
            manifest=manifest,
            enforced_resource_limits=enforced_resource_limits,
            resource_usage=resource_usage,
            isolation_evidence_refs=isolation_evidence_refs,
        )

    @staticmethod
    def _elapsed_ms(started_at: str, finished_at: str) -> int:
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            return max(0, int((finished - started).total_seconds() * 1000))
        except ValueError:
            return 0


def _path_digest(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
