"""Opt-in Gemini API adapter for integration testing only.

This adapter is deliberately separate from the local model roster.  It uses
the provider-neutral BackendAdapter contract so tests can exercise routing,
orchestration, provenance, ledger events, structured output, tools, and
streaming without changing AirBench's production model path.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from contracts.ids import idempotency_key
from contracts.model.backend import (
    BackendCallError, BackendCapabilities, BackendChunk, BackendContent,
    BackendErrorCode, BackendFailure, BackendHealth, BackendMessage,
    BackendOutputSpec, BackendReadiness, BackendRequest, BackendResponse,
    BackendTool, BackendToolCall, BackendUsage, CancellationToken,
    ResponseProvenance,
)
from contracts.models import ContractStatus, Taint
from contracts.provenance.ledger import build_event


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class GeminiApiAdapter:
    """Google Gemini REST adapter with no production-roster side effects.

    The API key is read at call time from ``GEMINI_API_KEY`` and is only sent
    in the HTTPS request query string. It is never included in errors, ledger
    payloads, or response provenance.
    """

    adapter_id = "airbench.gemini-test"
    adapter_version = "0.1"

    def __init__(self, model_name: str, *, api_key_env: str = "GEMINI_API_KEY",
                 ledger=None, timeout_s: float = 120.0) -> None:
        if not model_name.strip():
            raise ValueError("model_name is required")
        self.model_name = model_name
        self.api_key_env = api_key_env
        self._ledger = ledger
        self._timeout_s = timeout_s
        self._capabilities = BackendCapabilities(
            structured_output_modes=("json_object", "json_schema"),
            tool_calling=True, modalities=("text", "image", "document"),
            streaming=True, cancellation=True,
        )

    def capabilities(self) -> BackendCapabilities:
        return self._capabilities

    def health(self) -> BackendHealth:
        return BackendHealth.healthy if os.environ.get(self.api_key_env) else BackendHealth.unhealthy

    def readiness(self) -> BackendReadiness:
        # Do not make an unaudited probe call during router selection. The
        # explicit live runner performs the real call and reports readiness.
        return BackendReadiness.ready if os.environ.get(self.api_key_env) else BackendReadiness.not_ready

    def available_models(self) -> tuple[str, ...]:
        """Return API models that advertise ``generateContent`` support."""
        if not os.environ.get(self.api_key_env):
            return ()
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={quote(os.environ[self.api_key_env], safe='')}"
        try:
            with urlopen(Request(url, method="GET"), timeout=self._timeout_s) as response:
                payload = json.loads(response.read())
            return tuple(
                item["name"].removeprefix("models/")
                for item in payload.get("models", ())
                if isinstance(item, dict) and "generateContent" in item.get("supportedGenerationMethods", ())
            )
        except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError, KeyError, TypeError):
            return ()

    def complete(self, request: BackendRequest, cancellation: CancellationToken | None = None) -> BackendResponse:
        self._preflight(request, cancellation)
        self._append_event("model.call.started", request, {"request_hash": request.digest()})
        try:
            raw = self._post(request, self._payload(request, stream=False), stream=False, cancellation=cancellation)
            response = self._parse(raw, request)
            self._append_event("model.call.completed", request, {
                "request_hash": request.digest(), "response_hash": response.digest(),
                "usage": response.usage.to_dict(), "target_id": request.target_id,
            })
            return response
        except BackendCallError as exc:
            self._failed(request, exc)
            raise

    def stream(self, request: BackendRequest, cancellation: CancellationToken | None = None) -> Iterator[BackendChunk]:
        self._preflight(request, cancellation)
        self._append_event("model.call.started", request, {"request_hash": request.digest(), "stream": True})
        try:
            raw = self._post(request, self._payload(request, stream=True), stream=True, cancellation=cancellation)
            text = self._text(raw)
            for index, word in enumerate(text.split(" ")):
                if cancellation and cancellation.cancelled:
                    raise self._failure(request, BackendErrorCode.cancelled, "model stream cancelled", False)
                yield BackendChunk(request.model_call.request_id, index, word + (" " if index + 1 < len(text.split(" ")) else ""), index == len(text.split(" ")) - 1)
            self._append_event("model.call.completed", request, {"request_hash": request.digest(), "response_hash": _sha256(text), "target_id": request.target_id, "stream": True})
        except BackendCallError as exc:
            self._failed(request, exc)
            raise

    def _preflight(self, request: BackendRequest, cancellation: CancellationToken | None) -> None:
        if not os.environ.get(self.api_key_env):
            raise self._failure(request, BackendErrorCode.authentication_failed, "Gemini API credential is unavailable", False)
        if cancellation and cancellation.cancelled:
            raise self._failure(request, BackendErrorCode.cancelled, "model call cancelled", False)
        if request.model_call.modality not in self._capabilities.modalities or request.output.mode not in {"text", *self._capabilities.structured_output_modes}:
            raise self._failure(request, BackendErrorCode.unsupported_capability, "Gemini test adapter does not support this request", False)

    def _payload(self, request: BackendRequest, *, stream: bool) -> dict[str, Any]:
        system: list[dict[str, str]] = []
        contents: list[dict[str, Any]] = []
        for message in request.messages:
            parts = [self._part(part) for part in message.content]
            if message.role == "system":
                system.extend(parts)
            else:
                contents.append({"role": "model" if message.role == "assistant" else "user", "parts": parts})
        payload: dict[str, Any] = {"contents": contents, "generationConfig": {}}
        if system:
            payload["systemInstruction"] = {"parts": system}
        if request.output.mode == "json_object":
            payload["generationConfig"]["responseMimeType"] = "application/json"
        elif request.output.mode == "json_schema" and request.output.schema:
            payload["generationConfig"].update({"responseMimeType": "application/json", "responseSchema": request.output.schema})
        if request.tools:
            payload["tools"] = [{"functionDeclarations": [self._tool(tool) for tool in request.tools]}]
        return payload

    @staticmethod
    def _part(part: BackendContent) -> dict[str, Any]:
        if part.kind in {"text", "structured"}:
            return {"text": part.text or ""}
        if part.media_ref and part.media_ref.startswith("data:") and ";base64," in part.media_ref:
            header, encoded = part.media_ref.split(",", 1)
            mime_type = header[5:].split(";", 1)[0] or part.media_type or "application/octet-stream"
            return {"inlineData": {"mimeType": mime_type, "data": encoded}}
        return {"fileData": {"fileUri": part.media_ref or "", "mimeType": part.media_type or "application/octet-stream"}}

    @staticmethod
    def _tool(tool: BackendTool) -> dict[str, Any]:
        return {"name": tool.name, "description": tool.description, "parameters": tool.input_schema}

    def _post(self, request: BackendRequest, payload: dict[str, Any], *, stream: bool, cancellation: CancellationToken | None) -> dict[str, Any]:
        action = "streamGenerateContent" if stream else "generateContent"
        suffix = "&alt=sse" if stream else ""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(self.model_name, safe='')}:{action}?key={quote(os.environ[self.api_key_env], safe='')}{suffix}"
        try:
            with urlopen(Request(url, data=json.dumps(payload, separators=(",", ":")).encode(), method="POST", headers={"Content-Type": "application/json"}), timeout=self._timeout_s) as response:
                if cancellation and cancellation.cancelled:
                    raise self._failure(request, BackendErrorCode.cancelled, "model call cancelled", False)
                body = response.read()
                if stream:
                    merged: dict[str, Any] = {"candidates": [{"content": {"parts": []}}]}
                    for line in body.decode("utf-8").splitlines():
                        if line.startswith("data:"):
                            item = json.loads(line[5:].strip())
                            candidate = (item.get("candidates") or [{}])[0]
                            merged["candidates"][0]["content"]["parts"].extend((candidate.get("content") or {}).get("parts", []))
                            if candidate.get("finishReason"):
                                merged["candidates"][0]["finishReason"] = candidate["finishReason"]
                            if item.get("usageMetadata"):
                                merged["usageMetadata"] = item["usageMetadata"]
                    return merged
                return json.loads(body)
        except BackendCallError:
            raise
        except HTTPError as exc:
            code = BackendErrorCode.invalid_request if exc.code == 400 else BackendErrorCode.provider_error
            detail = f"Gemini API returned HTTP {exc.code} for model '{self.model_name}'"
            if exc.code == 404:
                detail += "; model is unavailable for this API key/API version"
            raise self._failure(request, code, detail, exc.code >= 500) from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise self._failure(request, BackendErrorCode.timeout if "timed out" in str(exc).lower() else BackendErrorCode.unavailable, "Gemini API request failed", True) from exc
        except json.JSONDecodeError as exc:
            raise self._failure(request, BackendErrorCode.malformed_response, "Gemini API returned non-JSON output", False) from exc

    def _parse(self, raw: dict[str, Any], request: BackendRequest) -> BackendResponse:
        try:
            candidate = (raw.get("candidates") or [{}])[0]
            parts = ((candidate.get("content") or {}).get("parts") or [])
            tool_calls = tuple(BackendToolCall(p["functionCall"]["name"], p["functionCall"].get("args", {})) for p in parts if "functionCall" in p)
            declared = {tool.name for tool in request.tools}
            if any(call.name not in declared for call in tool_calls):
                raise self._failure(request, BackendErrorCode.malformed_response, "Gemini emitted an undeclared tool call", False)
            text = "".join(p.get("text", "") for p in parts if "text" in p) or None
            output: str | dict[str, Any] | None = None if tool_calls else text
            if request.output.mode in {"json_object", "json_schema"} and isinstance(text, str):
                try: output = json.loads(text)
                except json.JSONDecodeError: raise self._failure(request, BackendErrorCode.malformed_response, "Gemini returned invalid structured output", False)
            usage_raw = raw.get("usageMetadata") or {}
            input_tokens, output_tokens = int(usage_raw.get("promptTokenCount", 0)), int(usage_raw.get("candidatesTokenCount", 0))
            response_hash = _sha256(json.dumps(output, sort_keys=True, separators=(",", ":"), default=str))
            usage = BackendUsage(input_tokens, output_tokens, input_tokens + output_tokens, 0)
            provenance = ResponseProvenance(f"model:{request.target_id}:{request.model_call.request_id}", 1.0, request.model_call.clearance, Taint.untrusted, request.target_id, request.artifact_digest, request.backend_id, request.backend_version, request.digest(), response_hash)
            return BackendResponse(request.model_call.request_id, request.target_id, ContractStatus.verified, output, usage, provenance, candidate.get("finishReason", "STOP"), tool_calls)
        except BackendCallError:
            raise
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise self._failure(request, BackendErrorCode.malformed_response, "could not parse Gemini response", False) from exc

    @staticmethod
    def _text(raw: dict[str, Any]) -> str:
        return "".join(p.get("text", "") for p in (((raw.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []) if "text" in p)

    def _failure(self, request: BackendRequest, code: BackendErrorCode, message: str, retryable: bool) -> BackendCallError:
        return BackendCallError(BackendFailure(code, message, retryable, request.model_call.request_id, request.target_id))

    def _failed(self, request: BackendRequest, exc: BackendCallError) -> None:
        self._append_event("model.call.failed", request, {"request_hash": request.digest(), "error_code": exc.failure.code.value, "retryable": exc.failure.retryable, "target_id": request.target_id})

    def _append_event(self, event_type: str, request: BackendRequest, payload: dict[str, Any]) -> None:
        if self._ledger is None:
            return
        self._ledger.append(build_event(event_type=event_type, task_id=request.model_call.task_id, actor_id=self.adapter_id, actor_type="backend", payload_contract="BackendCall", payload_version="1.0", payload={**payload, "request_id": request.model_call.request_id, "backend_id": request.backend_id, "backend_version": request.backend_version, "artifact_digest": request.artifact_digest, "clearance": request.model_call.clearance.value, "provenance": {"source_ref": f"model-request:{request.model_call.request_id}", "confidence": 1.0, "clearance": request.model_call.clearance.value, "taint": Taint.untrusted.value}}, clearance=request.model_call.clearance, idempotency=idempotency_key(f"gemini.{event_type}", request.model_call.request_id, event_type), sequence=len(self._ledger), previous_event_hash=self._ledger.head_hash))


__all__ = ["GeminiApiAdapter"]
