"""Audited code execution and calculation evidence manifests."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, Protocol

from contracts import Clearance, LedgerEventEnvelope, Taint, ToolAction, build_event, idempotency_key, stable_id

from .sandbox import SandboxPolicy, SandboxResult, SandboxRunner
from .tool_gateway import ToolAuthorization


class CodeExecutionError(RuntimeError):
    """The execution request or manifest could not be accepted."""


class ExecutionLedger(Protocol):
    @property
    def events(self) -> tuple[LedgerEventEnvelope, ...]: ...

    @property
    def head_hash(self) -> str | None: ...

    def append(self, event: LedgerEventEnvelope) -> Any: ...


@dataclass(frozen=True, slots=True)
class CodeExecutionRequest:
    action: ToolAction
    policy: SandboxPolicy
    declared_tests: tuple[ToolAction, ...] = ()
    output_paths: tuple[str, ...] = ()
    calculation_names: tuple[str, ...] = ()
    authorization: ToolAuthorization | None = None
    test_authorizations: tuple[ToolAuthorization | None, ...] = ()


@dataclass(frozen=True, slots=True)
class TestResult:
    test_id: str
    status: Literal["passed", "failed", "timed_out", "rejected"]
    output_hash: str
    ledger_event_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "status": self.status,
            "output_hash": self.output_hash,
            "ledger_event_refs": list(self.ledger_event_refs),
        }


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    path: str
    content_hash: str
    byte_size: int
    media_type: str
    source_ref: str
    confidence: float
    clearance: Clearance
    taint: Taint

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content_hash": self.content_hash,
            "byte_size": self.byte_size,
            "media_type": self.media_type,
            "source_ref": self.source_ref,
            "confidence": self.confidence,
            "clearance": self.clearance.value,
            "taint": self.taint.value,
        }


@dataclass(frozen=True, slots=True)
class CalculationEvidence:
    name: str
    value_text: str
    source_ref: str
    confidence: float
    clearance: Clearance
    taint: Taint

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value_text": self.value_text,
            "source_ref": self.source_ref,
            "confidence": self.confidence,
            "clearance": self.clearance.value,
            "taint": self.taint.value,
        }


@dataclass(frozen=True, slots=True)
class ExecutionManifest:
    execution_id: str
    task_id: str
    status: Literal["succeeded", "failed", "needs_review", "timed_out", "rejected"]
    main_status: str
    test_results: tuple[TestResult, ...]
    artifacts: tuple[ArtifactRecord, ...]
    calculations: tuple[CalculationEvidence, ...]
    stdout_hash: str
    stderr_hash: str
    wall_time_ms: int
    failure_code: str | None
    ledger_event_refs: tuple[str, ...]
    started_at: str
    finished_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "status": self.status,
            "main_status": self.main_status,
            "test_results": [result.to_dict() for result in self.test_results],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "calculations": [calculation.to_dict() for calculation in self.calculations],
            "stdout_hash": self.stdout_hash,
            "stderr_hash": self.stderr_hash,
            "wall_time_ms": self.wall_time_ms,
            "failure_code": self.failure_code,
            "ledger_event_refs": list(self.ledger_event_refs),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class CodeExecutionRunner:
    """Run code and declared tests in the sandbox and seal one manifest."""

    CALCULATION_MARKER = "AIRBENCH_CALCULATION:"

    def __init__(self, sandbox: SandboxRunner, ledger: ExecutionLedger) -> None:
        self._sandbox = sandbox
        self._ledger = ledger

    def run(self, request: CodeExecutionRequest) -> ExecutionManifest:
        self._validate_request(request)
        main = self._sandbox.execute(request.action, request.policy, authorization=request.authorization)
        test_results: list[TestResult] = []
        if main.status == "succeeded":
            for index, test_action in enumerate(request.declared_tests):
                authorization = request.test_authorizations[index] if request.test_authorizations else None
                test = self._sandbox.execute(test_action, request.policy, authorization=authorization)
                test_status = "passed" if test.status == "succeeded" else test.status
                test_results.append(TestResult(
                    test_id=test_action.action_id,
                    status=test_status,
                    output_hash=test.output_hash,
                    ledger_event_refs=test.ledger_event_refs,
                ))

        artifacts, missing_artifact = self._capture_artifacts(request, main)
        calculations, calculation_error = self._capture_calculations(request, main)
        test_failed = any(test.status != "passed" for test in test_results)
        if main.status == "timed_out":
            status: Literal["succeeded", "failed", "needs_review", "timed_out", "rejected"] = "timed_out"
            failure_code = "main_timeout"
        elif main.status != "succeeded":
            status = "failed"
            failure_code = "main_execution_failed"
        elif test_failed or missing_artifact:
            status = "failed"
            failure_code = "declared_test_failed" if test_failed else "declared_artifact_missing"
        elif calculation_error:
            status = "needs_review"
            failure_code = calculation_error
        else:
            status = "succeeded"
            failure_code = None

        finished_at = _now()
        manifest = ExecutionManifest(
            execution_id=stable_id("code-execution", request.action.task_id, request.action.action_id, request.action.idempotency_key),
            task_id=request.action.task_id,
            status=status,
            main_status=main.status,
            test_results=tuple(test_results),
            artifacts=tuple(artifacts),
            calculations=tuple(calculations),
            stdout_hash=_hash_bytes(main.stdout.encode("utf-8", errors="replace")),
            stderr_hash=_hash_bytes(main.stderr.encode("utf-8", errors="replace")),
            wall_time_ms=self._elapsed_ms(main.started_at, finished_at),
            failure_code=failure_code,
            ledger_event_refs=main.ledger_event_refs + tuple(ref for test in test_results for ref in test.ledger_event_refs),
            started_at=main.started_at,
            finished_at=finished_at,
        )
        manifest_ref = self._append_manifest(request.action, manifest)
        return replace(manifest, ledger_event_refs=manifest.ledger_event_refs + (manifest_ref,))

    def _validate_request(self, request: CodeExecutionRequest) -> None:
        if not isinstance(request, CodeExecutionRequest):
            raise CodeExecutionError("request must be CodeExecutionRequest")
        if request.action.tool_name != "python.execute":
            raise CodeExecutionError("code execution accepts only python.execute")
        if len(request.declared_tests) > 100:
            raise CodeExecutionError("declared test count exceeds 100")
        if len(set(request.calculation_names)) != len(request.calculation_names):
            raise CodeExecutionError("calculation names must be unique")
        if any(not name or not name.replace("_", "").isalnum() for name in request.calculation_names):
            raise CodeExecutionError("calculation names must be stable identifiers")
        if request.test_authorizations and len(request.test_authorizations) != len(request.declared_tests):
            raise CodeExecutionError("test authorizations must match declared tests")
        for test in request.declared_tests:
            if test.task_id != request.action.task_id or test.worker_id != request.action.worker_id:
                raise CodeExecutionError("declared tests must remain within the main action identity")
            if test.tool_name != "python.execute":
                raise CodeExecutionError("declared tests must use python.execute")
        for path in request.output_paths:
            if not isinstance(path, str) or not path or "\x00" in path:
                raise CodeExecutionError("artifact path is invalid")
            if not self._inside(path, request.policy.allowed_write_paths):
                raise CodeExecutionError("artifact path is outside the allowed write scope")

    def _capture_artifacts(self, request: CodeExecutionRequest, main: SandboxResult) -> tuple[list[ArtifactRecord], bool]:
        if main.status != "succeeded":
            return [], False
        artifacts: list[ArtifactRecord] = []
        missing = False
        for raw_path in request.output_paths:
            path = Path(raw_path).resolve(strict=False)
            if not path.is_file():
                missing = True
                continue
            try:
                content = path.read_bytes()
            except OSError:
                missing = True
                continue
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            artifacts.append(ArtifactRecord(
                path=str(path), content_hash=_hash_bytes(content), byte_size=len(content),
                media_type=media_type, source_ref=f"sandbox:{main.execution_id}:{path.name}",
                confidence=1.0, clearance=Clearance(request.action.clearance), taint=Taint.untrusted,
            ))
        return artifacts, missing

    def _capture_calculations(self, request: CodeExecutionRequest, main: SandboxResult) -> tuple[list[CalculationEvidence], str | None]:
        if not request.calculation_names:
            return [], None
        payloads: dict[str, Any] = {}
        for line in main.stdout.splitlines():
            if not line.startswith(self.CALCULATION_MARKER):
                continue
            try:
                value = json.loads(line[len(self.CALCULATION_MARKER):])
            except json.JSONDecodeError:
                return [], "calculation_marker_invalid"
            if not isinstance(value, dict):
                return [], "calculation_marker_not_object"
            payloads.update(value)
        evidence: list[CalculationEvidence] = []
        for name in request.calculation_names:
            if name not in payloads:
                return evidence, "calculation_evidence_missing"
            try:
                value = Decimal(str(payloads[name]))
            except (InvalidOperation, ValueError):
                return evidence, "calculation_value_not_numeric"
            if not value.is_finite():
                return evidence, "calculation_value_not_finite"
            evidence.append(CalculationEvidence(
                name=name, value_text=format(value, "f"),
                source_ref=f"sandbox:{main.execution_id}:calculation:{name}",
                confidence=1.0, clearance=Clearance(request.action.clearance), taint=Taint.untrusted,
            ))
        return evidence, None

    def _append_manifest(self, action: ToolAction, manifest: ExecutionManifest) -> str:
        payload = {
            "execution_id": manifest.execution_id,
            "manifest": manifest.to_dict(),
            "provenance": {
                "source_ref": f"sandbox:{manifest.execution_id}",
                "confidence": 1.0 if manifest.status == "succeeded" else 0.0,
                "clearance": action.clearance.value,
                "taint": Taint.untrusted.value,
            },
        }
        key = idempotency_key("code-execution.manifest", action.task_id, action.action_id, action.idempotency_key)
        existing = next((event for event in self._ledger.events if event.idempotency_key == key), None)
        if existing is not None:
            return existing.event_id
        event = build_event(
            event_type="artifact.checked",
            task_id=action.task_id,
            actor_id="code-execution.local",
            actor_type="service",
            payload_contract="ExecutionManifest",
            payload_version="1.0",
            payload=payload,
            clearance=action.clearance,
            idempotency=key,
            sequence=len(self._ledger.events),
            previous_event_hash=self._ledger.head_hash,
        )
        try:
            self._ledger.append(event)
        except Exception as exc:
            raise CodeExecutionError("execution manifest ledger append failed") from exc
        return event.event_id

    @staticmethod
    def _inside(candidate: str, roots: tuple[Path, ...]) -> bool:
        try:
            path = Path(candidate).resolve(strict=False)
            return any(path == root.resolve() or root.resolve() in path.parents for root in roots)
        except (OSError, RuntimeError, ValueError):
            return False

    @staticmethod
    def _elapsed_ms(started_at: str, finished_at: str) -> int:
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            return max(0, int((finished - started).total_seconds() * 1000))
        except ValueError:
            return 0


__all__ = [
    "CodeExecutionError",
    "CodeExecutionRequest",
    "TestResult",
    "ArtifactRecord",
    "CalculationEvidence",
    "ExecutionManifest",
    "CodeExecutionRunner",
]
