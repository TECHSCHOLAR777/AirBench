"""Secure adapter for an approved remote OpenAI-compatible endpoint."""

from __future__ import annotations

import json
import os
import ssl
from datetime import datetime, timezone
import hashlib
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..backend import (
    BackendCallError, BackendChunk, BackendErrorCode,
    BackendHealth, BackendReadiness, BackendRequest, BackendResponse,
    CancellationToken, FakeBackend, ResponseProvenance,
)
from ..model_registry import ModelTarget
from ..remote_endpoint import RemoteEndpointProfile
from .vllm_adapter import VllmAdapter


class RemoteEndpointAdapter(VllmAdapter):
    """Provider-neutral transport for a signed, allowlisted remote endpoint.

    The endpoint is never trusted because it answers health checks.  Every
    call first verifies the endpoint profile and its matching qualified model
    target.  Credentials are read from one named environment variable and are
    never included in exceptions, ledger payloads, or provenance.
    """

    adapter_id = "airbench.remote-endpoint"
    adapter_version = "0.1"

    def __init__(
        self,
        profile: RemoteEndpointProfile,
        target: ModelTarget,
        *,
        endpoint_signing_key: bytes,
        target_signing_key: bytes | None = None,
        ledger=None,
        capabilities=None,
        timeout_s: float | None = None,
    ) -> None:
        super().__init__(
            profile.endpoint_url,
            profile.model_target_id,
            ledger=ledger,
            capabilities=capabilities,
            require_no_egress_env=False,
            timeout_s=(timeout_s or profile.timeout_ms / 1000),
        )
        self.profile = profile
        self.target = target
        self._endpoint_signing_key = endpoint_signing_key
        self._target_signing_key = target_signing_key
        self._ssl_context = ssl.create_default_context()
        self._configuration_error = self._configuration_problem()

    def _configuration_problem(self) -> str:
        if self.profile.disabled:
            return "endpoint profile is disabled"
        if not self.profile.verify_signature(self._endpoint_signing_key):
            return "endpoint profile signature is invalid"
        if self._target_signing_key is None or not self.target.verify_qualification_signature(self._target_signing_key):
            return "model target signature is invalid"
        if self.target.artifact_digest == "0" * 64:
            return "model target artifact digest is a placeholder"
        try:
            expiry = datetime.fromisoformat(self.target.qualification_expires_at.replace("Z", "+00:00"))
            if expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                return "model target qualification is stale"
        except (TypeError, ValueError):
            return "model target qualification expiry is invalid"
        profile_issues = self.profile._validate({})
        if profile_issues:
            return "; ".join(issue.message for issue in profile_issues)
        return ""

    def validate_target(self, target: ModelTarget, request) -> None:
        """Router hook: reject endpoint/model mismatches before health checks."""
        if target.target_id != self.target.target_id:
            raise ValueError("adapter target identity mismatch")
        if self._configuration_error:
            raise ValueError(self._configuration_error)
        self.profile.validate_target(target, request)

    def _preflight(self, request: BackendRequest) -> None:
        if self._configuration_error:
            code = BackendErrorCode.stale_target if "stale" in self._configuration_error else BackendErrorCode.unsigned_target
            if "artifact" in self._configuration_error:
                code = BackendErrorCode.artifact_mismatch
            raise self._failure(request, code, self._configuration_error, retryable=False)
        try:
            self.profile.validate_target(self.target, request.model_call)
        except ValueError as exc:
            message = str(exc)
            if "stale" in message:
                code = BackendErrorCode.stale_target
            elif "artifact" in message:
                code = BackendErrorCode.artifact_mismatch
            elif "modality" in message or "capability" in message:
                code = BackendErrorCode.unsupported_capability
            else:
                code = BackendErrorCode.authorization_failed
            raise self._failure(request, code, "remote target preflight was rejected", retryable=False) from exc
        self._check_no_egress(request)

    def health(self) -> BackendHealth:
        if self._configuration_error or not self.profile.credential():
            return BackendHealth.unhealthy
        return super().health()

    def readiness(self) -> BackendReadiness:
        if self._configuration_error or not self.profile.credential():
            return BackendReadiness.not_ready
        return super().readiness()

    def _check_no_egress(self, request: BackendRequest) -> None:
        if self._configuration_error:
            code = BackendErrorCode.stale_target if "stale" in self._configuration_error else BackendErrorCode.unsigned_target
            if "artifact" in self._configuration_error:
                code = BackendErrorCode.artifact_mismatch
            raise self._failure(request, code, self._configuration_error, retryable=False)
        if self.profile.data_egress_policy != "approved_remote_endpoint":
            self._append_endpoint_event("endpoint.egress.denied", request, {})
            raise self._failure(request, BackendErrorCode.egress_denied, "remote data egress policy denied", retryable=False)
        if self.profile.remote_execution_policy != "approved_remote_endpoint":
            raise self._failure(request, BackendErrorCode.remote_execution_denied, "remote execution policy denied", retryable=False)
        if not self.profile.credential():
            raise self._failure(request, BackendErrorCode.authentication_failed, "approved endpoint credential is unavailable", retryable=False)

    def _check_health_and_readiness(self, request: BackendRequest) -> None:
        if self.health() != BackendHealth.healthy:
            raise self._failure(request, BackendErrorCode.unavailable, "remote endpoint is unavailable", retryable=True)
        if self.readiness() != BackendReadiness.ready:
            raise self._failure(request, BackendErrorCode.not_ready, "remote endpoint is not ready", retryable=True)

    def complete(self, request: BackendRequest, cancellation: CancellationToken | None = None) -> BackendResponse:
        if cancellation and cancellation.cancelled:
            raise self._failure(request, BackendErrorCode.cancelled, "remote model call cancelled", retryable=False)
        try:
            self._preflight(request)
        except BackendCallError as exc:
            self._append_endpoint_event("endpoint.rejected", request, {"error_code": exc.failure.code.value})
            raise
        attempts = self.profile.max_retries + 1
        if self.profile.retry_only_idempotent and not request.model_call.idempotency_key.strip():
            attempts = 1
        last_error: BackendCallError | None = None
        for attempt in range(attempts):
            try:
                self._append_endpoint_event("endpoint.selected", request, {"attempt": attempt + 1})
                self._append_endpoint_event("endpoint.request.started", request, {"attempt": attempt + 1})
                response = super().complete(request, cancellation)
                response = self._with_provenance(response)
                self._append_endpoint_event("endpoint.request.completed", request, {
                    "attempt": attempt + 1, "response_hash": response.digest(),
                })
                return response
            except BackendCallError as exc:
                last_error = exc
                if exc.failure.code in {
                    BackendErrorCode.unsigned_target, BackendErrorCode.stale_target,
                    BackendErrorCode.artifact_mismatch, BackendErrorCode.allowlist_denied,
                    BackendErrorCode.egress_denied, BackendErrorCode.authorization_failed,
                    BackendErrorCode.authentication_failed, BackendErrorCode.unsupported_capability,
                    BackendErrorCode.remote_execution_denied,
                }:
                    self._append_endpoint_event("endpoint.rejected", request, {
                        "error_code": exc.failure.code.value,
                    })
                self._append_endpoint_event("endpoint.request.failed", request, {
                    "attempt": attempt + 1,
                    "error_code": exc.failure.code.value,
                    "retryable": exc.failure.retryable,
                })
                if not exc.failure.retryable or attempt + 1 >= attempts:
                    raise
        assert last_error is not None
        raise last_error

    def _with_provenance(self, response: BackendResponse) -> BackendResponse:
        provenance = response.provenance
        return BackendResponse(
            request_id=response.request_id,
            target_id=response.target_id,
            status=response.status,
            output=response.output,
            usage=response.usage,
            provenance=ResponseProvenance(
                source_ref=provenance.source_ref,
                confidence=provenance.confidence,
                clearance=provenance.clearance,
                taint=provenance.taint,
                target_id=provenance.target_id,
                artifact_digest=provenance.artifact_digest,
                backend_id=provenance.backend_id,
                backend_version=provenance.backend_version,
                request_hash=provenance.request_hash,
                response_hash=provenance.response_hash,
                endpoint_id=self.profile.endpoint_id,
                execution_location=self.profile.execution_location,
                qualification_reference=self.profile.qualification_reference,
            ),
            finish_reason=response.finish_reason,
            tool_calls=response.tool_calls,
        )

    def stream(self, request: BackendRequest, cancellation: CancellationToken | None = None) -> Iterator[BackendChunk]:
        if cancellation and cancellation.cancelled:
            raise self._failure(request, BackendErrorCode.cancelled, "remote stream cancelled", retryable=False)
        try:
            self._preflight(request)
        except BackendCallError as exc:
            self._append_endpoint_event("endpoint.rejected", request, {"error_code": exc.failure.code.value})
            raise
        if not self.profile.streaming:
            raise self._failure(request, BackendErrorCode.unsupported_capability, "remote streaming is not declared", retryable=False)
        self._append_endpoint_event("endpoint.selected", request, {"stream": True})
        self._append_endpoint_event("endpoint.request.started", request, {"stream": True})
        try:
            yield from super().stream(request, cancellation)
            self._append_endpoint_event("endpoint.request.completed", request, {"stream": True})
        except BackendCallError as exc:
            self._append_endpoint_event("endpoint.request.failed", request, {
                "stream": True, "error_code": exc.failure.code.value, "retryable": exc.failure.retryable,
            })
            raise

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.profile.credential()}",
        }

    def _check_capabilities(self, request: BackendRequest) -> None:
        super()._check_capabilities(request)
        declared = set(self.profile.capabilities)
        required = {request.model_call.modality}
        if request.output.mode != "text":
            required.add(request.output.mode)
        if request.tools:
            required.add("tool_calling")
        if any(part.kind != "text" for message in request.messages for part in message.content):
            required.update(part.kind for message in request.messages for part in message.content)
        missing = sorted(required - declared)
        if missing:
            raise self._failure(
                request, BackendErrorCode.unsupported_capability,
                f"remote endpoint lacks declared capabilities: {', '.join(missing)}", retryable=False,
            )

    def _check_certificate(self, response: Any) -> None:
        expected = self.profile.certificate_fingerprint.replace(":", "").lower()
        if not expected:
            return
        try:
            certificate = response.fp.raw._sock.getpeercert(binary_form=True)
        except AttributeError as exc:
            raise ssl.SSLError("peer certificate was unavailable") from exc
        actual = hashlib.sha256(certificate).hexdigest()
        if actual != expected:
            raise ssl.SSLError("peer certificate fingerprint mismatch")

    def _get(self, path: str) -> bytes | None:
        try:
            request = Request(self._base_url + path, method="GET", headers=self._headers())
            with urlopen(request, timeout=self._timeout_s, context=self._ssl_context) as response:
                self._check_certificate(response)
                return response.read()
        except (HTTPError, URLError, OSError, ssl.SSLError):
            return None

    def _post_json(self, path: str, payload: dict[str, Any], request: BackendRequest, cancellation: CancellationToken | None) -> dict[str, Any]:
        if cancellation and cancellation.cancelled:
            raise self._failure(request, BackendErrorCode.cancelled, "remote model call cancelled", retryable=False)
        try:
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            req = Request(self._base_url + path, data=body, method="POST", headers=self._headers())
            with urlopen(req, timeout=self._timeout_s, context=self._ssl_context) as response:
                self._check_certificate(response)
                if cancellation and cancellation.cancelled:
                    raise self._failure(request, BackendErrorCode.cancelled, "remote model call cancelled", retryable=False)
                return json.loads(response.read())
        except ssl.SSLError as exc:
            raise self._failure(request, BackendErrorCode.tls_failure, "remote TLS validation failed", retryable=False) from exc
        except HTTPError as exc:
            if exc.code in {401}:
                raise self._failure(request, BackendErrorCode.authentication_failed, "remote endpoint authentication failed", retryable=False) from exc
            if exc.code in {403}:
                raise self._failure(request, BackendErrorCode.authorization_failed, "remote endpoint authorization failed", retryable=False) from exc
            if exc.code == 408:
                raise self._failure(request, BackendErrorCode.timeout, "remote endpoint timed out", retryable=True) from exc
            if exc.code == 429:
                raise self._failure(request, BackendErrorCode.resource_exhausted, "remote endpoint resource limit reached", retryable=True) from exc
            raise self._failure(request, BackendErrorCode.provider_error, f"remote endpoint returned HTTP {exc.code}", retryable=exc.code >= 500) from exc
        except (TimeoutError, URLError, OSError) as exc:
            message = str(exc).lower()
            if "timeout" in message or "timed out" in message:
                raise self._failure(request, BackendErrorCode.timeout, "remote endpoint timed out", retryable=True) from exc
            raise self._failure(request, BackendErrorCode.unavailable, "remote endpoint connection failed", retryable=True) from exc
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise self._failure(request, BackendErrorCode.malformed_response, "remote endpoint returned malformed JSON", retryable=False) from exc

    def _stream_chunks(self, request: BackendRequest, cancellation: CancellationToken | None) -> Iterator[BackendChunk]:
        payload = self._build_payload(request, stream=True)
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        try:
            req = Request(
                self._base_url + "/v1/chat/completions", data=body, method="POST", headers=self._headers(),
            )
            with urlopen(req, timeout=self._timeout_s, context=self._ssl_context) as response:
                self._check_certificate(response)
                for index, raw_line in enumerate(response):
                    if cancellation and cancellation.cancelled:
                        raise self._failure(request, BackendErrorCode.cancelled, "remote stream cancelled", retryable=False)
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        raise self._failure(request, BackendErrorCode.malformed_response, "remote stream returned malformed JSON", retryable=False)
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content") or ""
                    finish = choice.get("finish_reason")
                    if text or finish is not None:
                        yield BackendChunk(request.model_call.request_id, index, text, finish is not None)
        except BackendCallError:
            raise
        except ssl.SSLError as exc:
            raise self._failure(request, BackendErrorCode.tls_failure, "remote TLS validation failed", retryable=False) from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise self._failure(request, BackendErrorCode.timeout if "timeout" in str(exc).lower() else BackendErrorCode.unavailable, "remote stream failed", retryable=True) from exc

    def _append_endpoint_event(self, event_type: str, request: BackendRequest, payload: dict[str, Any]) -> None:
        self._append_event(event_type, request, {
            **payload,
            "endpoint_id": self.profile.endpoint_id,
            "model_target_id": self.profile.model_target_id,
            "execution_location": self.profile.execution_location,
            "qualification_reference": self.profile.qualification_reference,
        })


class FakeRemoteEndpoint(FakeBackend):
    """Deterministic endpoint for tests; it never opens a network connection."""

    adapter_id = "airbench.fake-remote-endpoint"
    adapter_version = "0.1"

    def __init__(self, profile: RemoteEndpointProfile, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.profile = profile


__all__ = ["FakeRemoteEndpoint", "RemoteEndpointAdapter"]
