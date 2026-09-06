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
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from contracts import Clearance, Taint, ToolAction, build_event, idempotency_key, stable_id


class SandboxError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    root_dir: Path
    max_wall_seconds: float = 10.0
    max_output_bytes: int = 1_000_000
    max_code_bytes: int = 256_000
    require_hard_network_isolation: bool = False
    hard_network_isolation_available: bool = False
    allowed_read_paths: tuple[Path, ...] = ()
    allowed_write_paths: tuple[Path, ...] = ()

    def validate(self) -> None:
        if self.max_wall_seconds <= 0 or self.max_wall_seconds > 300:
            raise SandboxError("invalid_timeout", "sandbox wall time must be between 0 and 300 seconds")
        if self.max_output_bytes <= 0 or self.max_output_bytes > 50_000_000:
            raise SandboxError("invalid_output_limit", "sandbox output limit is invalid")
        if self.max_code_bytes <= 0 or self.max_code_bytes > 5_000_000:
            raise SandboxError("invalid_code_limit", "sandbox code limit is invalid")
        if self.require_hard_network_isolation and not self.hard_network_isolation_available:
            raise SandboxError("network_isolation_unavailable", "hard OS network isolation is not available")

    def digest(self) -> str:
        payload = {
            "root_dir": str(self.root_dir.resolve()),
            "max_wall_seconds": self.max_wall_seconds,
            "max_output_bytes": self.max_output_bytes,
            "max_code_bytes": self.max_code_bytes,
            "require_hard_network_isolation": self.require_hard_network_isolation,
            "hard_network_isolation_available": self.hard_network_isolation_available,
            "allowed_read_paths": sorted(str(path.resolve()) for path in self.allowed_read_paths),
            "allowed_write_paths": sorted(str(path.resolve()) for path in self.allowed_write_paths),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


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
    
    stdout = io.StringIO()
    stderr = io.StringIO()
    status = "succeeded"
    error_type = None
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exec(compile(code, "<airbench-sandbox>", "exec"), {"__name__": "__main__", "__file__": "<airbench-sandbox>"}, {})
        except BaseException as exc:
            status = "failed"
            error_type = type(exc).__name__
    result = {"status": status, "error_type": error_type, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}
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


class SandboxRunner:
    def __init__(self, ledger: LedgerSink) -> None:
        self._ledger = ledger

    def execute(self, action: ToolAction, policy: SandboxPolicy) -> SandboxResult:
        policy.validate()
        try:
            action = ToolAction.from_dict(action.to_dict())
        except Exception as exc:
            raise SandboxError("invalid_tool_action", "tool action failed contract validation") from exc
        if action.tool_name != "python.execute":
            raise SandboxError("unsupported_tool", "the sandbox accepts only python.execute")
        code = action.arguments.get("code")
        if not isinstance(code, str) or not code.strip():
            raise SandboxError("invalid_code", "python.execute requires non-empty code")
        if len(code.encode("utf-8")) > policy.max_code_bytes:
            raise SandboxError("code_too_large", "code exceeds the sandbox limit")
        execution_id = stable_id("sandbox", action.task_id, action.action_id, action.idempotency_key)
        policy_hash = policy.digest()
        started_at = _now()
        requested_ref = _append_tool_event(self._ledger, event_type="tool.requested", action=action, execution_id=execution_id, payload={"input_hash": hashlib.sha256(code.encode()).hexdigest(), "policy_hash": policy_hash}, occurred_at=started_at)
        authorized_ref = _append_tool_event(self._ledger, event_type="tool.authorized", action=action, execution_id=execution_id, payload={"policy_hash": policy_hash, "hard_network_isolation": policy.hard_network_isolation_available}, occurred_at=started_at)
        run_dir = Path(tempfile.mkdtemp(prefix=f"airbench-{execution_id[:8]}-", dir=policy.root_dir))
        try:
            payload = {
                "run_dir": str(run_dir),
                "read_roots": [str(path.resolve()) for path in policy.allowed_read_paths],
                "write_roots": [str(path.resolve()) for path in policy.allowed_write_paths],
                "code": code,
            }
            process = subprocess.Popen([sys.executable, "-I", "-c", _WORKER], cwd=run_dir, env=_safe_child_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                raw_stdout, raw_stderr = process.communicate(json.dumps(payload), timeout=policy.max_wall_seconds)
                exit_code = process.returncode
                parsed = json.loads(raw_stdout) if raw_stdout else {"status": "failed", "error_type": "empty_worker_result", "stdout": "", "stderr": raw_stderr}
                stdout = str(parsed.get("stdout", ""))
                stderr = str(parsed.get("stderr", ""))
                status: Literal["succeeded", "failed", "timed_out", "rejected"] = "succeeded" if parsed.get("status") == "succeeded" and exit_code == 0 else "failed"
                if len(stdout.encode()) > policy.max_output_bytes or len(stderr.encode()) > policy.max_output_bytes:
                    status = "failed"
                    stderr = "sandbox output limit exceeded"
                    stdout = stdout[:policy.max_output_bytes]
            except subprocess.TimeoutExpired:
                process.kill()
                raw_stdout, raw_stderr = process.communicate()
                exit_code = None
                stdout = raw_stdout[:policy.max_output_bytes]
                stderr = "sandbox execution timed out"
                status = "timed_out"
        finally:
            pass
        finished_at = _now()
        output_hash = hashlib.sha256((stdout + "\n" + stderr).encode("utf-8", errors="replace")).hexdigest()
        result_ref = _append_tool_event(
            self._ledger,
            event_type="tool.result",
            action=action,
            execution_id=execution_id,
            payload={
                "status": status,
                "exit_code": exit_code,
                "output_hash": output_hash,
                "provenance": {"source_ref": f"sandbox:{execution_id}", "confidence": 1.0 if status == "succeeded" else 0.0, "clearance": action.clearance.value, "taint": Taint.untrusted.value},
            },
            occurred_at=finished_at,
        )
        return SandboxResult(execution_id, status, exit_code, stdout, stderr, output_hash, policy_hash, policy.hard_network_isolation_available, (requested_ref, authorized_ref, result_ref), started_at, finished_at)
