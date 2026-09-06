"""Provider-neutral model backend contracts and a deterministic fake backend.

The router and orchestrator depend on this module, never on a vLLM, NIM, or
remote-provider response shape.  Concrete adapters may translate the typed
request into a provider protocol and must translate the result back here.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator, Protocol

from .errors import ContractValidationError, ValidationIssue
from .ids import idempotency_key
from .ledger import LedgerStore, build_event
from .models import Clearance, Contract, ContractStatus, ModelCallRequest, Taint


_HEX64 = set("0123456789abcdef")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class BackendErrorCode(str, Enum):
    invalid_request = "invalid_request"
    unsupported_capability = "unsupported_capability"
    unavailable = "unavailable"
    not_ready = "not_ready"
    timeout = "timeout"
    cancelled = "cancelled"
    malformed_response = "malformed_response"
    resource_exhausted = "resource_exhausted"
    provider_error = "provider_error"


class BackendHealth(str, Enum):
    healthy = "healthy"
    unhealthy = "unhealthy"


class BackendReadiness(str, Enum):
    ready = "ready"
    not_ready = "not_ready"


@dataclass(frozen=True)
class BackendContent(Contract):
    """A provider-neutral content part.

    Binary content is represented by a governed reference and digest.  The
    adapter never receives an implicit file path or an unbounded byte blob.
    """

    kind: str
    text: str | None = None
    media_ref: str | None = None
    media_type: str | None = None
    content_hash: str | None = None

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        if self.kind not in {"text", "image", "audio", "video", "structured"}:
            issues.append(ValidationIssue("kind", "enum", "unsupported content kind"))
        if self.kind in {"text", "structured"} and not self.text:
            issues.append(ValidationIssue("text", "required", "text content is required"))
        if self.kind in {"image", "audio", "video"}:
            if not self.media_ref or not self.media_type or not self.content_hash:
                issues.append(ValidationIssue("media_ref", "provenance", "media reference, type, and hash are required"))
            elif len(self.content_hash) != 64 or any(char not in _HEX64 for char in self.content_hash.lower()):
                issues.append(ValidationIssue("content_hash", "digest", "media content_hash must be a SHA-256 hex digest"))
        return issues


@dataclass(frozen=True)
class BackendMessage(Contract):
    role: str
    content: tuple[BackendContent, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BackendMessage":
        value = dict(payload)
        value["content"] = tuple(
            item if isinstance(item, BackendContent) else BackendContent.from_dict(item)
            for item in value.get("content", ())
        )
        return super().from_dict(value)  # type: ignore[return-value]

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        if self.role not in {"system", "user", "assistant", "tool"}:
            issues.append(ValidationIssue("role", "enum", "unsupported message role"))
        if not self.content:
            issues.append(ValidationIssue("content", "required", "message content is required"))
        return issues


@dataclass(frozen=True)
class BackendTool(Contract):
    name: str
    description: str
    input_schema: dict[str, Any]

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        if not self.name.strip() or not self.description.strip():
            issues.append(ValidationIssue("name", "required", "tool name and description are required"))
        if not isinstance(self.input_schema, dict):
            issues.append(ValidationIssue("input_schema", "type", "tool input_schema must be an object"))
        return issues


@dataclass(frozen=True)
class BackendOutputSpec(Contract):
    mode: str = "text"
    schema: dict[str, Any] | None = None

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        if self.mode not in {"text", "json_object", "json_schema"}:
            issues.append(ValidationIssue("mode", "enum", "unsupported output mode"))
        if self.mode == "json_schema" and not isinstance(self.schema, dict):
            issues.append(ValidationIssue("schema", "required", "json_schema mode requires a schema"))
        return issues


@dataclass(frozen=True)
class BackendRequest(Contract):
    """Complete provider-neutral input to one model call."""

    model_call: ModelCallRequest
    target_id: str
    artifact_digest: str
    backend_id: str
    backend_version: str
    messages: tuple[BackendMessage, ...]
    output: BackendOutputSpec = field(default_factory=BackendOutputSpec)
    tools: tuple[BackendTool, ...] = ()
    stream: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BackendRequest":
        value = dict(payload)
        model_call = value.get("model_call")
        value["model_call"] = model_call if isinstance(model_call, ModelCallRequest) else ModelCallRequest.from_dict(model_call)
        value["messages"] = tuple(
            item if isinstance(item, BackendMessage) else BackendMessage.from_dict(item)
            for item in value.get("messages", ())
        )
        output = value.get("output", BackendOutputSpec())
        value["output"] = output if isinstance(output, BackendOutputSpec) else BackendOutputSpec.from_dict(output)
        value["tools"] = tuple(
            item if isinstance(item, BackendTool) else BackendTool.from_dict(item)
            for item in value.get("tools", ())
        )
        return super().from_dict(value)  # type: ignore[return-value]

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        if not self.target_id.strip() or not self.backend_id.strip() or not self.backend_version.strip():
            issues.append(ValidationIssue("target_id", "required", "target and backend identity are required"))
        if len(self.artifact_digest) != 64 or any(char not in _HEX64 for char in self.artifact_digest.lower()):
            issues.append(ValidationIssue("artifact_digest", "digest", "artifact_digest must be a SHA-256 hex digest"))
        if not self.messages:
            issues.append(ValidationIssue("messages", "required", "at least one message is required"))
        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            issues.append(ValidationIssue("tools", "unique", "tool names must be unique"))
        return issues


@dataclass(frozen=True)
class BackendCapabilities(Contract):
    structured_output_modes: tuple[str, ...] = ()
    tool_calling: bool = False
    modalities: tuple[str, ...] = ("text",)
    streaming: bool = False
    cancellation: bool = False
    max_context_tokens: int | None = None

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        valid_modes = {"text", "json_object", "json_schema"}
        if any(mode not in valid_modes for mode in self.structured_output_modes):
            issues.append(ValidationIssue("structured_output_modes", "enum", "unsupported structured output mode"))
        if not self.modalities:
            issues.append(ValidationIssue("modalities", "required", "at least one modality is required"))
        if self.max_context_tokens is not None and (type(self.max_context_tokens) is not int or self.max_context_tokens < 1):
            issues.append(ValidationIssue("max_context_tokens", "range", "max_context_tokens must be positive"))
        return issues


@dataclass(frozen=True)
class BackendUsage(Contract):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        values = (self.input_tokens, self.output_tokens, self.total_tokens, self.latency_ms)
        if any(type(value) is not int or value < 0 for value in values):
            issues.append(ValidationIssue("usage", "range", "usage values must be non-negative integers"))
        if self.total_tokens != self.input_tokens + self.output_tokens:
            issues.append(ValidationIssue("total_tokens", "consistency", "total_tokens must equal input plus output"))
        return issues


@dataclass(frozen=True)
class ResponseProvenance(Contract):
    source_ref: str
    confidence: float
    clearance: Clearance
    taint: Taint
    target_id: str
    artifact_digest: str
    backend_id: str
    backend_version: str
    request_hash: str
    response_hash: str

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        if not self.source_ref or not 0 <= self.confidence <= 1:
            issues.append(ValidationIssue("provenance", "range", "source_ref and confidence are required"))
        for field_name in ("artifact_digest", "request_hash", "response_hash"):
            value = getattr(self, field_name)
            if len(value) != 64 or any(char not in _HEX64 for char in value.lower()):
                issues.append(ValidationIssue(field_name, "digest", "must be a SHA-256 hex digest"))
        return issues


@dataclass(frozen=True)
class BackendToolCall(Contract):
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class BackendResponse(Contract):
    request_id: str
    target_id: str
    status: ContractStatus
    output: str | dict[str, Any] | None
    usage: BackendUsage
    provenance: ResponseProvenance
    finish_reason: str
    tool_calls: tuple[BackendToolCall, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BackendResponse":
        value = dict(payload)
        usage = value.get("usage")
        provenance = value.get("provenance")
        value["usage"] = usage if isinstance(usage, BackendUsage) else BackendUsage.from_dict(usage)
        value["provenance"] = provenance if isinstance(provenance, ResponseProvenance) else ResponseProvenance.from_dict(provenance)
        value["tool_calls"] = tuple(
            item if isinstance(item, BackendToolCall) else BackendToolCall.from_dict(item)
            for item in value.get("tool_calls", ())
        )
        return super().from_dict(value)  # type: ignore[return-value]

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        if self.status != ContractStatus.verified:
            issues.append(ValidationIssue("status", "state", "successful backend responses must be verified"))
        if self.output is None and not self.tool_calls:
            issues.append(ValidationIssue("output", "required", "response requires output or tool calls"))
        return issues


@dataclass(frozen=True)
class BackendChunk(Contract):
    request_id: str
    index: int
    text: str
    final: bool = False

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        if self.index < 0:
            issues.append(ValidationIssue("index", "range", "chunk index must be non-negative"))
        return issues


@dataclass(frozen=True)
class BackendFailure:
    code: BackendErrorCode
    message: str
    retryable: bool
    request_id: str
    target_id: str


class BackendCallError(RuntimeError):
    """Safe, typed backend failure without provider payloads or secrets."""

    def __init__(self, failure: BackendFailure):
        self.failure = failure
        super().__init__(f"{failure.code.value}: {failure.message}")


class CancellationToken:
    """Thread-safe cancellation signal shared by adapters and orchestrators."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class BackendAdapter(Protocol):
    adapter_id: str
    adapter_version: str

    def capabilities(self) -> BackendCapabilities: ...
    def health(self) -> BackendHealth: ...
    def readiness(self) -> BackendReadiness: ...
    def complete(self, request: BackendRequest, cancellation: CancellationToken | None = None) -> BackendResponse: ...
    def stream(self, request: BackendRequest, cancellation: CancellationToken | None = None) -> Iterator[BackendChunk]: ...


class FakeBackend:
    """Deterministic backend used for contract and orchestration tests."""

    adapter_id = "airbench.fake-backend"
    adapter_version = "1.0"

    def __init__(self, *, ledger: LedgerStore | None = None, capabilities: BackendCapabilities | None = None,
                 output: str | dict[str, Any] = "fake response", tool_call: BackendToolCall | None = None,
                 delay_ms: int = 0, max_context_tokens: int | None = None) -> None:
        self._ledger = ledger
        self._capabilities = capabilities or BackendCapabilities(
            structured_output_modes=("json_object", "json_schema"), tool_calling=True,
            modalities=("text", "image"), streaming=True, cancellation=True,
            max_context_tokens=max_context_tokens,
        )
        self._output = output
        self._tool_call = tool_call
        self._delay_ms = delay_ms
        self._health = BackendHealth.healthy
        self._readiness = BackendReadiness.ready

    def capabilities(self) -> BackendCapabilities:
        return self._capabilities

    def health(self) -> BackendHealth:
        return self._health

    def readiness(self) -> BackendReadiness:
        return self._readiness

    def set_state(self, *, health: BackendHealth | None = None, readiness: BackendReadiness | None = None) -> None:
        if health is not None:
            self._health = health
        if readiness is not None:
            self._readiness = readiness

    def complete(self, request: BackendRequest, cancellation: CancellationToken | None = None) -> BackendResponse:
        try:
            self._validate_call(request, cancellation)
        except BackendCallError as exc:
            self._append_event("model.call.failed", request, {
                "request_hash": request.digest(), "error_code": exc.failure.code.value,
                "retryable": exc.failure.retryable, "target_id": request.target_id,
            })
            raise
        self._append_event("model.call.started", request, {"request_hash": request.digest()})
        try:
            if self._delay_ms:
                self._sleep_with_cancellation(request, cancellation)
            if cancellation is not None and cancellation.cancelled:
                raise self._failure(request, BackendErrorCode.cancelled, "model call cancelled", retryable=False)
            output = self._normalized_output(request)
            usage = self._usage(request, output)
            response_hash = _sha256(json.dumps(output, sort_keys=True, separators=(",", ":"), default=str))
            provenance = ResponseProvenance(
                source_ref=f"model:{request.target_id}:{request.model_call.request_id}", confidence=1.0,
                clearance=request.model_call.clearance, taint=Taint.untrusted,
                target_id=request.target_id, artifact_digest=request.artifact_digest,
                backend_id=request.backend_id, backend_version=request.backend_version,
                request_hash=request.digest(), response_hash=response_hash,
            )
            tool_calls = (self._tool_call,) if self._tool_call is not None else ()
            response = BackendResponse(
                request_id=request.model_call.request_id, target_id=request.target_id,
                status=ContractStatus.verified, output=None if tool_calls else output, usage=usage,
                provenance=provenance, finish_reason="stop",
                tool_calls=tool_calls,
            )
            BackendResponse.from_dict(response.to_dict())
            self._append_event("model.call.completed", request, {
                "request_hash": request.digest(), "response_hash": response.digest(),
                "usage": usage.to_dict(), "target_id": request.target_id,
            })
            return response
        except BackendCallError as exc:
            self._append_event("model.call.failed", request, {
                "request_hash": request.digest(), "error_code": exc.failure.code.value,
                "retryable": exc.failure.retryable, "target_id": request.target_id,
            })
            raise

    def stream(self, request: BackendRequest, cancellation: CancellationToken | None = None) -> Iterator[BackendChunk]:
        try:
            self._validate_call(request, cancellation)
            if not self._capabilities.streaming:
                raise self._failure(request, BackendErrorCode.unsupported_capability, "streaming is not supported", retryable=False)
        except BackendCallError as exc:
            self._append_event("model.call.failed", request, {
                "request_hash": request.digest(), "error_code": exc.failure.code.value,
                "retryable": exc.failure.retryable, "target_id": request.target_id,
            })
            raise
        self._append_event("model.call.started", request, {"request_hash": request.digest(), "stream": True})
        try:
            text = self._text_output(request)
            words = text.split(" ")
            for index, word in enumerate(words):
                if cancellation is not None and cancellation.cancelled:
                    raise self._failure(request, BackendErrorCode.cancelled, "model stream cancelled", retryable=False)
                yield BackendChunk(request.model_call.request_id, index, word + (" " if index < len(words) - 1 else ""), index == len(words) - 1)
            response_hash = _sha256(text)
            self._append_event("model.call.completed", request, {
                "request_hash": request.digest(), "response_hash": response_hash,
                "usage": self._usage(request, text).to_dict(), "target_id": request.target_id,
                "stream": True,
            })
        except BackendCallError as exc:
            self._append_event("model.call.failed", request, {
                "request_hash": request.digest(), "error_code": exc.failure.code.value,
                "retryable": exc.failure.retryable, "target_id": request.target_id,
                "stream": True,
            })
            raise

    def _validate_call(self, request: BackendRequest, cancellation: CancellationToken | None) -> None:
        try:
            validated = BackendRequest.from_dict(request.to_dict())
        except ContractValidationError as exc:
            raise self._failure(request, BackendErrorCode.invalid_request, "backend request failed contract validation", retryable=False) from exc
        if self.health() != BackendHealth.healthy:
            raise self._failure(validated, BackendErrorCode.unavailable, "backend is unhealthy", retryable=True)
        if self.readiness() != BackendReadiness.ready:
            raise self._failure(validated, BackendErrorCode.not_ready, "backend is not ready", retryable=True)
        required_modalities = {part.kind for message in validated.messages for part in message.content}
        if validated.model_call.modality not in self._capabilities.modalities:
            raise self._failure(validated, BackendErrorCode.unsupported_capability, "requested modality is not supported", retryable=False)
        if any(kind not in {"text", "structured"} and kind not in self._capabilities.modalities for kind in required_modalities):
            raise self._failure(validated, BackendErrorCode.unsupported_capability, "a requested content modality is not supported", retryable=False)
        if validated.output.mode not in {"text", *self._capabilities.structured_output_modes}:
            raise self._failure(validated, BackendErrorCode.unsupported_capability, "requested output mode is not supported", retryable=False)
        if validated.tools and not self._capabilities.tool_calling:
            raise self._failure(validated, BackendErrorCode.unsupported_capability, "tool calling is not supported", retryable=False)
        if self._tool_call is not None and self._tool_call.name not in {tool.name for tool in validated.tools}:
            raise self._failure(validated, BackendErrorCode.malformed_response, "backend emitted an unauthorized tool call", retryable=False)
        requested_context = validated.model_call.resource_budget.get("context_tokens", 0)
        limit = self._capabilities.max_context_tokens
        if limit is not None and requested_context > limit:
            raise self._failure(validated, BackendErrorCode.resource_exhausted, "requested context exceeds backend capacity", retryable=True)
        if cancellation is not None and cancellation.cancelled:
            raise self._failure(validated, BackendErrorCode.cancelled, "model call cancelled", retryable=False)

    def _normalized_output(self, request: BackendRequest) -> str | dict[str, Any]:
        if request.output.mode in {"json_object", "json_schema"}:
            if isinstance(self._output, dict):
                return dict(self._output)
            return {"result": str(self._output)}
        return self._output

    def _text_output(self, request: BackendRequest) -> str:
        output = self._normalized_output(request)
        return output if isinstance(output, str) else json.dumps(output, sort_keys=True, separators=(",", ":"))

    def _usage(self, request: BackendRequest, output: str | dict[str, Any]) -> BackendUsage:
        input_text = " ".join(part.text or part.media_ref or "" for message in request.messages for part in message.content)
        output_text = output if isinstance(output, str) else json.dumps(output, sort_keys=True, separators=(",", ":"))
        input_tokens = len(input_text.split())
        output_tokens = len(output_text.split())
        return BackendUsage(input_tokens, output_tokens, input_tokens + output_tokens, self._delay_ms)

    def _sleep_with_cancellation(self, request: BackendRequest, cancellation: CancellationToken | None) -> None:
        if self._delay_ms > request.model_call.timeout_ms:
            raise self._failure(request, BackendErrorCode.timeout, "backend call exceeded its timeout", retryable=True)
        remaining = self._delay_ms
        while remaining > 0:
            if cancellation is not None and cancellation.cancelled:
                raise self._failure(request, BackendErrorCode.cancelled, "model call cancelled", retryable=False)
            step = min(remaining, 10)
            threading.Event().wait(step / 1000)
            remaining -= step

    def _failure(self, request: BackendRequest, code: BackendErrorCode, message: str, *, retryable: bool) -> BackendCallError:
        return BackendCallError(BackendFailure(code, message, retryable, request.model_call.request_id, request.target_id))

    def _append_event(self, event_type: str, request: BackendRequest, payload: dict[str, Any]) -> None:
        if self._ledger is None:
            return
        events = self._ledger.events
        event = build_event(
            event_type=event_type, task_id=request.model_call.task_id, actor_id=self.adapter_id,
            actor_type="backend", payload_contract="BackendCall", payload_version="1.0",
            payload={**payload, "request_id": request.model_call.request_id, "backend_id": request.backend_id,
                     "backend_version": request.backend_version, "artifact_digest": request.artifact_digest,
                     "clearance": request.model_call.clearance.value, "provenance": {
                         "source_ref": f"model-request:{request.model_call.request_id}",
                         "confidence": 1.0, "clearance": request.model_call.clearance.value,
                         "taint": Taint.untrusted.value,
                     }},
            clearance=request.model_call.clearance, idempotency=idempotency_key(
                f"backend.{event_type}", request.model_call.request_id, event_type,
            ), sequence=len(events), previous_event_hash=self._ledger.head_hash,
        )
        self._ledger.append(event)


__all__ = [
    "BackendAdapter", "BackendCallError", "BackendCapabilities", "BackendChunk", "BackendContent",
    "BackendErrorCode", "BackendFailure", "BackendHealth", "BackendMessage", "BackendOutputSpec",
    "BackendReadiness", "BackendRequest", "BackendResponse", "BackendTool", "BackendToolCall",
    "BackendUsage", "CancellationToken", "FakeBackend", "ResponseProvenance",
]
