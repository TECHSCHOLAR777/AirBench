"""vLLM backend adapter for AirBench.

Translates :class:`~contracts.backend.BackendRequest` into HTTP requests
against a locally running vLLM OpenAI-compatible server and normalises the
response back to :class:`~contracts.backend.BackendResponse` or a stream of
:class:`~contracts.backend.BackendChunk` objects.

No provider response shape ever crosses the contract boundary.  The adapter
is deliberately **not** a general-purpose vLLM client; it implements only the
semantics AirBench's contracts require.

Air-gapped safety
-----------------
The adapter enforces that ``HF_HUB_OFFLINE`` and ``TRANSFORMERS_OFFLINE``
environment variables are both set to ``"1"`` before making any HTTP call.
This is a defence-in-depth check: the primary isolation is the network
policy applied at the OS / container level, but this check gives a fast,
typed failure with a clear message when the environment is misconfigured.

Pass ``require_no_egress_env=False`` **only** in unit tests that mock the
HTTP layer; production deployments must always use the default ``True``.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Iterator
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urljoin

from ..model.backend import (
    BackendAdapter,
    BackendCallError,
    BackendCapabilities,
    BackendChunk,
    BackendContent,
    BackendErrorCode,
    BackendFailure,
    BackendHealth,
    BackendMessage,
    BackendOutputSpec,
    BackendReadiness,
    BackendRequest,
    BackendResponse,
    BackendTool,
    BackendToolCall,
    BackendUsage,
    CancellationToken,
    ResponseProvenance,
)
from ..ids import idempotency_key
from ..provenance.ledger import LedgerStore, build_event
from ..models import Clearance, ContractStatus, Taint
from ..security.model_safety import evaluate_model_messages
from .tool_parsers import BaseToolParser, ToolCallParserRegistry


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class VllmAdapter:
    """OpenAI-compatible adapter for a locally running vLLM process.

    Parameters
    ----------
    base_url:
        Root URL of the vLLM server, e.g. ``"http://127.0.0.1:8000"``.
    model_name:
        The ``--model`` value passed to vLLM at startup.  Used in the
        readiness check to confirm the correct model is loaded.
    tool_parser:
        A :class:`~contracts.adapters.tool_parsers.BaseToolParser` instance
        appropriate for the model family.  Pass
        ``ToolCallParserRegistry.get(target.tool_call_parser)`` when
        constructing from a :class:`ModelTarget`.
    ledger:
        Optional :class:`~contracts.ledger.LedgerStore`; when supplied the
        adapter emits ``model.call.started``, ``model.call.completed``, and
        ``model.call.failed`` events.
    capabilities:
        Advertised :class:`~contracts.backend.BackendCapabilities`.  Defaults
        to the superset that covers all AirBench model families.
    require_no_egress_env:
        When ``True`` (production default) the adapter raises
        ``BackendCallError(unavailable)`` if the no-egress environment
        variables are absent.  Set to ``False`` only in unit tests.
    timeout_s:
        HTTP request timeout in seconds.  The adapter converts vLLM's HTTP
        timeout into ``BackendCallError(timeout, retryable=True)``.
    """

    adapter_id = "airbench.vllm"
    adapter_version = "0.5"

    def __init__(
        self,
        base_url: str,
        model_name: str,
        *,
        tool_parser: BaseToolParser | None = None,
        ledger: LedgerStore | None = None,
        capabilities: BackendCapabilities | None = None,
        endpoint_id: str | None = None,
        require_no_egress_env: bool = True,
        timeout_s: float = 120.0,
        enable_thinking: bool | None = None,
        max_images: int | None = None,
        max_videos: int | None = None,
        max_output_tokens: int = 0,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url is required")
        if not model_name.strip():
            raise ValueError("model_name is required")
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._endpoint_id = endpoint_id
        self._tool_parser = tool_parser or ToolCallParserRegistry.get("none")
        self._ledger = ledger
        self._capabilities = capabilities or BackendCapabilities(
            structured_output_modes=("json_object", "json_schema"),
            tool_calling=True,
            modalities=("text", "image"),
            streaming=True,
            cancellation=True,
            max_context_tokens=None,
        )
        self._require_no_egress_env = require_no_egress_env
        self._timeout_s = timeout_s
        self._enable_thinking = enable_thinking
        self._max_images = max_images
        self._max_videos = max_videos
        self._max_output_tokens = max_output_tokens

    @property
    def endpoint_id(self) -> str | None:
        """Deployment identity recorded in response provenance, if bound."""
        return self._endpoint_id

    @property
    def model_name(self) -> str:
        """The exact served model identity this adapter expects."""
        return self._model_name

    # ------------------------------------------------------------------
    # BackendAdapter protocol
    # ------------------------------------------------------------------

    def capabilities(self) -> BackendCapabilities:
        return self._capabilities

    def health(self) -> BackendHealth:
        """GET /health — separate from model readiness."""
        try:
            resp = self._get("/health")
            return BackendHealth.healthy if resp is not None else BackendHealth.unhealthy
        except Exception:
            return BackendHealth.unhealthy

    def readiness(self) -> BackendReadiness:
        """GET /v1/models — ready only when our model is in the list."""
        try:
            data = self._get_json("/v1/models")
            if data is None:
                return BackendReadiness.not_ready
            models = data.get("data", [])
            ids = {m.get("id") for m in models if isinstance(m, dict)}
            return BackendReadiness.ready if self._model_name in ids else BackendReadiness.not_ready
        except Exception:
            return BackendReadiness.not_ready

    def probe(self) -> dict[str, Any]:
        """One-pass health/readiness probe with a typed reason.

        Returns the endpoint states plus the served model IDs so callers can
        report *why* a lane is unavailable without extra HTTP round trips.
        The reason is one of ``unhealthy``, ``not_ready``, ``model_mismatch``,
        or ``ready``; registry-level adapter and qualification checks are
        composed on top by the Node's serving layer.
        """
        if self._get("/health") is None:
            return {"health": BackendHealth.unhealthy.value,
                    "readiness": BackendReadiness.not_ready.value,
                    "reason": "unhealthy", "served_models": []}
        data = self._get_json("/v1/models")
        if data is None:
            return {"health": BackendHealth.healthy.value,
                    "readiness": BackendReadiness.not_ready.value,
                    "reason": "not_ready", "served_models": []}
        served = sorted({
            item.get("id") for item in data.get("data", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        })
        if self._model_name not in served:
            return {"health": BackendHealth.healthy.value,
                    "readiness": BackendReadiness.not_ready.value,
                    "reason": "model_mismatch", "served_models": served}
        return {"health": BackendHealth.healthy.value,
                "readiness": BackendReadiness.ready.value,
                "reason": "ready", "served_models": served}

    def complete(
        self,
        request: BackendRequest,
        cancellation: CancellationToken | None = None,
    ) -> BackendResponse:
        self._check_no_egress(request)
        self._check_model_safety(request)
        self._check_health_and_readiness(request)
        self._check_cancellation(request, cancellation)
        self._check_capabilities(request)
        self._check_resource_budget(request)

        self._append_event("model.call.started", request, {
            "request_hash": request.digest(),
        })

        try:
            payload = self._build_payload(request, stream=False)
            raw = self._post_json("/v1/chat/completions", payload, request, cancellation)
            response = self._parse_completion(raw, request)
            self._append_event("model.call.completed", request, {
                "request_hash": request.digest(),
                "response_hash": response.digest(),
                "usage": response.usage.to_dict(),
                "target_id": request.target_id,
            })
            return response
        except BackendCallError as exc:
            self._append_event("model.call.failed", request, {
                "request_hash": request.digest(),
                "error_code": exc.failure.code.value,
                "retryable": exc.failure.retryable,
                "target_id": request.target_id,
            })
            raise

    def stream(
        self,
        request: BackendRequest,
        cancellation: CancellationToken | None = None,
    ) -> Iterator[BackendChunk]:
        self._check_no_egress(request)
        self._check_model_safety(request)
        self._check_health_and_readiness(request)
        self._check_cancellation(request, cancellation)
        self._check_capabilities(request)
        self._check_resource_budget(request)

        if not self._capabilities.streaming:
            err = self._failure(request, BackendErrorCode.unsupported_capability,
                                "streaming is not supported", retryable=False)
            self._append_event("model.call.failed", request, {
                "request_hash": request.digest(),
                "error_code": err.failure.code.value,
                "retryable": err.failure.retryable,
                "target_id": request.target_id,
            })
            raise err

        self._append_event("model.call.started", request, {
            "request_hash": request.digest(), "stream": True,
        })

        try:
            yield from self._stream_chunks(request, cancellation)
        except BackendCallError as exc:
            self._append_event("model.call.failed", request, {
                "request_hash": request.digest(),
                "error_code": exc.failure.code.value,
                "retryable": exc.failure.retryable,
                "target_id": request.target_id,
                "stream": True,
            })
            raise

    # ------------------------------------------------------------------
    # Internal helpers: validation
    # ------------------------------------------------------------------

    def _check_no_egress(self, request: BackendRequest) -> None:
        if not self._require_no_egress_env:
            return
        missing = [
            var for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
            if os.environ.get(var) != "1"
        ]
        if missing:
            raise self._failure(
                request, BackendErrorCode.unavailable,
                f"no-egress environment not configured: {missing} must be set to '1'",
                retryable=False,
            )

    def _check_health_and_readiness(self, request: BackendRequest) -> None:
        if self.health() != BackendHealth.healthy:
            raise self._failure(request, BackendErrorCode.unavailable,
                                "vllm backend is unhealthy", retryable=True)
        if self.readiness() != BackendReadiness.ready:
            raise self._failure(request, BackendErrorCode.not_ready,
                                "vllm backend is not ready", retryable=True)

    def _check_cancellation(
        self,
        request: BackendRequest,
        cancellation: CancellationToken | None,
    ) -> None:
        if cancellation is not None and cancellation.cancelled:
            raise self._failure(request, BackendErrorCode.cancelled,
                                "model call cancelled before execution", retryable=False)

    def _check_capabilities(self, request: BackendRequest) -> None:
        if request.model_call.modality not in self._capabilities.modalities:
            raise self._failure(request, BackendErrorCode.unsupported_capability,
                                f"modality '{request.model_call.modality}' is not supported",
                                retryable=False)
        if request.output.mode not in {"text", *self._capabilities.structured_output_modes}:
            raise self._failure(request, BackendErrorCode.unsupported_capability,
                                f"output mode '{request.output.mode}' is not supported",
                                retryable=False)
        if request.tools and not self._capabilities.tool_calling:
            raise self._failure(request, BackendErrorCode.unsupported_capability,
                                "tool calling is not supported", retryable=False)
        image_count = sum(
            1 for message in request.messages for part in message.content if part.kind == "image"
        )
        video_count = sum(
            1 for message in request.messages for part in message.content if part.kind == "video"
        )
        if self._max_images is not None and image_count > self._max_images:
            raise self._failure(request, BackendErrorCode.unsupported_capability,
                                "image count exceeds the target deployment limit", retryable=False)
        if self._max_videos is not None and video_count > self._max_videos:
            raise self._failure(request, BackendErrorCode.unsupported_capability,
                                "video content is not supported by the target deployment", retryable=False)

    def _check_resource_budget(self, request: BackendRequest) -> None:
        requested = request.model_call.resource_budget.get("context_tokens", 0)
        limit = self._capabilities.max_context_tokens
        if limit is not None and requested > limit:
            raise self._failure(request, BackendErrorCode.resource_exhausted,
                                f"requested context ({requested}) exceeds limit ({limit})",
                                retryable=True)

    def _check_model_safety(self, request: BackendRequest) -> None:
        """Fail closed before a provider sees an explicit unsafe procedure."""
        decision = evaluate_model_messages(request.messages)
        if decision.allowed:
            return
        error = self._failure(request, BackendErrorCode.authorization_failed,
                              "model request blocked by the local safety policy",
                              retryable=False)
        self._append_event("model.call.failed", request, {
            "request_hash": request.digest(),
            "error_code": BackendErrorCode.authorization_failed.value,
            "retryable": False,
            "target_id": request.target_id,
            "policy_reason": decision.reason,
        })
        raise error

    # ------------------------------------------------------------------
    # Internal helpers: payload construction
    # ------------------------------------------------------------------

    def _build_payload(self, request: BackendRequest, *, stream: bool) -> dict[str, Any]:
        messages = [self._encode_message(msg) for msg in request.messages]

        payload: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "stream": stream,
        }

        # Structured output
        if request.output.mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        elif request.output.mode == "json_schema" and request.output.schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": request.output.schema, "strict": True},
            }

        # Tool definitions
        if request.tools:
            payload["tools"] = [self._encode_tool(t) for t in request.tools]
            payload["tool_choice"] = "auto"

        # Qwen3's vLLM chat template accepts this provider-specific option.
        # It is bound to the signed target, never chosen by model output or by
        # an endpoint label.  Reasoning content is intentionally not returned
        # across the provider-neutral response boundary.
        if self._enable_thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": self._enable_thinking}
            if self._enable_thinking is False:
                payload["temperature"] = 0

        # Token budget
        ctx = request.model_call.resource_budget.get("context_tokens")
        if ctx:
            payload["max_tokens"] = min(ctx, self._max_output_tokens) if self._max_output_tokens else ctx

        return payload

    @staticmethod
    def _encode_message(msg: BackendMessage) -> dict[str, Any]:
        """Encode a :class:`BackendMessage` into the OpenAI messages format.

        Multi-part content (text + image) is encoded as a list.  Pure-text
        messages use the string shorthand for compatibility with all vLLM
        versions.
        """
        parts: list[dict[str, Any]] = []
        for part in msg.content:
            parts.append(VllmAdapter._encode_content(part))

        # If all parts are plain text, flatten to a single string.
        if len(parts) == 1 and parts[0].get("type") == "text":
            return {"role": msg.role, "content": parts[0]["text"]}
        return {"role": msg.role, "content": parts}

    @staticmethod
    def _encode_content(part: BackendContent) -> dict[str, Any]:
        if part.kind == "text" or part.kind == "structured":
            return {"type": "text", "text": part.text or ""}
        if part.kind == "image":
            # AirBench governed media URI + digest.  vLLM's vision endpoint
            # accepts image_url with a base64 data URL or a local file URL.
            # Here we forward the governed URI; the deployment's network
            # policy must ensure the URI resolves locally.
            return {
                "type": "image_url",
                "image_url": {
                    "url": part.media_ref or "",
                    "detail": "auto",
                },
            }
        # audio / video: not yet supported; let the capability check above
        # reject these before we reach encoding.
        return {"type": "text", "text": f"[unsupported media kind: {part.kind}]"}

    @staticmethod
    def _encode_tool(tool: BackendTool) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers: HTTP
    # ------------------------------------------------------------------

    def _get(self, path: str) -> bytes | None:
        """GET *path*, return body bytes or None on non-200."""
        url = self._base_url + path
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=self._timeout_s) as resp:
                return resp.read()
        except HTTPError as exc:
            if exc.code and exc.code < 500:
                return None  # definitive "not found / not ready"
            return None
        except (URLError, OSError):
            return None

    def _get_json(self, path: str) -> dict[str, Any] | None:
        body = self._get(path)
        if body is None:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        request: BackendRequest,
        cancellation: CancellationToken | None,
    ) -> dict[str, Any]:
        url = self._base_url + path
        body = _json_bytes(payload)
        try:
            req = Request(
                url, data=body, method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlopen(req, timeout=self._timeout_s) as resp:
                if cancellation and cancellation.cancelled:
                    raise self._failure(request, BackendErrorCode.cancelled,
                                        "model call cancelled", retryable=False)
                return json.loads(resp.read())
        except (URLError, OSError) as exc:
            msg = str(exc)
            if "timed out" in msg.lower() or "timeout" in msg.lower():
                raise self._failure(request, BackendErrorCode.timeout,
                                    "vllm request timed out", retryable=True) from exc
            raise self._failure(request, BackendErrorCode.unavailable,
                                f"vllm connection failed: {exc}", retryable=True) from exc
        except HTTPError as exc:
            if exc.code == 400:
                raise self._failure(request, BackendErrorCode.invalid_request,
                                    f"vllm rejected request: HTTP {exc.code}", retryable=False) from exc
            if exc.code == 413:
                raise self._failure(request, BackendErrorCode.resource_exhausted,
                                    "context window exceeded (HTTP 413)", retryable=True) from exc
            raise self._failure(request, BackendErrorCode.provider_error,
                                f"vllm returned HTTP {exc.code}", retryable=exc.code >= 500) from exc
        except json.JSONDecodeError as exc:
            raise self._failure(request, BackendErrorCode.malformed_response,
                                "vllm returned non-JSON body", retryable=False) from exc

    def _stream_chunks(
        self,
        request: BackendRequest,
        cancellation: CancellationToken | None,
    ) -> Iterator[BackendChunk]:
        payload = self._build_payload(request, stream=True)
        url = self._base_url + "/v1/chat/completions"
        body = _json_bytes(payload)

        try:
            req = Request(
                url, data=body, method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlopen(req, timeout=self._timeout_s) as resp:
                accumulated = []
                index = 0
                for raw_line in resp:
                    if cancellation and cancellation.cancelled:
                        raise self._failure(request, BackendErrorCode.cancelled,
                                            "model stream cancelled", retryable=False)
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_part = line[len("data:"):].strip()
                    if data_part == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_part)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk_data.get("choices") or [{}])[0].get("delta", {})
                    text = delta.get("content") or ""
                    finish = (chunk_data.get("choices") or [{}])[0].get("finish_reason")
                    is_final = finish is not None
                    if text or is_final:
                        chunk = BackendChunk(
                            request_id=request.model_call.request_id,
                            index=index,
                            text=text,
                            final=is_final,
                        )
                        accumulated.append(text)
                        yield chunk
                        index += 1
                        if is_final:
                            break

                full_text = "".join(accumulated)
                response_hash = _sha256(full_text)
                self._append_event("model.call.completed", request, {
                    "request_hash": request.digest(),
                    "response_hash": response_hash,
                    "target_id": request.target_id,
                    "stream": True,
                })
        except BackendCallError:
            raise
        except (URLError, OSError) as exc:
            msg = str(exc)
            if "timed out" in msg.lower() or "timeout" in msg.lower():
                raise self._failure(request, BackendErrorCode.timeout,
                                    "vllm stream timed out", retryable=True) from exc
            raise self._failure(request, BackendErrorCode.unavailable,
                                f"vllm stream connection failed: {exc}", retryable=True) from exc

    # ------------------------------------------------------------------
    # Internal helpers: response parsing
    # ------------------------------------------------------------------

    def _parse_completion(
        self, raw: dict[str, Any], request: BackendRequest,
    ) -> BackendResponse:
        try:
            choice = (raw.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            finish_reason = choice.get("finish_reason") or "stop"

            content_text: str | None = message.get("content")
            reasoning_content = message.get("reasoning_content")
            if reasoning_content is not None and not isinstance(reasoning_content, str):
                raise self._failure(
                    request, BackendErrorCode.malformed_response,
                    "vllm reasoning field was malformed", retryable=False,
                )
            raw_tool_calls = message.get("tool_calls")

            # Tool calls: prefer native tool_calls structure; fall back to
            # parser on the content text for Hermes-style models.
            tool_calls: tuple[BackendToolCall, ...] = ()
            if raw_tool_calls is not None:
                tool_calls = self._tool_parser.parse(
                    json.dumps(raw_tool_calls, separators=(",", ":")),
                    request.tools,
                )
            elif content_text and request.tools:
                tool_calls = self._tool_parser.parse(content_text, request.tools)

            if content_text is None and not tool_calls and reasoning_content:
                raise self._failure(
                    request, BackendErrorCode.malformed_response,
                    "vllm returned reasoning without an answer", retryable=False,
                )

            # Validate: if tool_calls were produced, confirm they are declared.
            declared_names = {t.name for t in request.tools}
            for tc in tool_calls:
                if tc.name not in declared_names:
                    raise self._failure(
                        request, BackendErrorCode.malformed_response,
                        f"model emitted unauthorized tool call '{tc.name}'",
                        retryable=False,
                    )

            # Output value
            output: str | dict[str, Any] | None
            if tool_calls:
                output = None
            elif request.output.mode in {"json_object", "json_schema"} and isinstance(content_text, str):
                try:
                    output = json.loads(content_text)
                except json.JSONDecodeError:
                    output = {"result": content_text}
            else:
                output = content_text

            # Usage
            usage_raw = raw.get("usage") or {}
            input_tokens = int(usage_raw.get("prompt_tokens", 0))
            output_tokens = int(usage_raw.get("completion_tokens", 0))

            # Approximate latency — vLLM doesn't expose it directly in the
            # completion response; record 0 so the usage contract is satisfied.
            usage = BackendUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                latency_ms=0,
            )

            # Provenance
            out_text = (
                json.dumps(output, sort_keys=True, separators=(",", ":"), default=str)
                if isinstance(output, dict)
                else (output or "")
            )
            response_hash = _sha256(out_text)
            provenance = ResponseProvenance(
                source_ref=f"model:{request.target_id}:{request.model_call.request_id}",
                confidence=1.0,
                clearance=request.model_call.clearance,
                taint=Taint.untrusted,
                target_id=request.target_id,
                artifact_digest=request.artifact_digest,
                backend_id=request.backend_id,
                backend_version=request.backend_version,
                request_hash=request.digest(),
                response_hash=response_hash,
                endpoint_id=self._endpoint_id,
            )

            return BackendResponse(
                request_id=request.model_call.request_id,
                target_id=request.target_id,
                status=ContractStatus.verified,
                output=output,
                usage=usage,
                provenance=provenance,
                finish_reason=finish_reason,
                tool_calls=tool_calls,
            )

        except BackendCallError:
            raise
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise self._failure(
                request, BackendErrorCode.malformed_response,
                f"could not parse vllm completion response: {exc}",
                retryable=False,
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers: ledger and failures
    # ------------------------------------------------------------------

    def _failure(
        self,
        request: BackendRequest,
        code: BackendErrorCode,
        message: str,
        *,
        retryable: bool,
    ) -> BackendCallError:
        # Validation and no-egress gates can fail before a fully materialized
        # ModelCallRequest reaches the adapter (for example during startup or
        # a provider-compatibility probe).  Failure reporting must remain
        # typed and redacted without assuming every test/adapter seam exposes
        # request_id on its lightweight request object.
        request_id = str(getattr(request.model_call, "request_id", ""))
        return BackendCallError(BackendFailure(
            code=code,
            message=message,
            retryable=retryable,
            request_id=request_id,
            target_id=request.target_id,
        ))

    def _append_event(
        self,
        event_type: str,
        request: BackendRequest,
        payload: dict[str, Any],
    ) -> None:
        if self._ledger is None:
            return
        events = self._ledger.events
        event = build_event(
            event_type=event_type,
            task_id=request.model_call.task_id,
            actor_id=self.adapter_id,
            actor_type="backend",
            payload_contract="BackendCall",
            payload_version="1.0",
            payload={
                **payload,
                "request_id": request.model_call.request_id,
                "backend_id": request.backend_id,
                "backend_version": request.backend_version,
                "artifact_digest": request.artifact_digest,
                "clearance": request.model_call.clearance.value,
                "provenance": {
                    "source_ref": f"model-request:{request.model_call.request_id}",
                    "confidence": 1.0,
                    "clearance": request.model_call.clearance.value,
                    "taint": Taint.untrusted.value,
                },
            },
            clearance=request.model_call.clearance,
            idempotency=idempotency_key(
                f"vllm.{event_type}", request.model_call.request_id, event_type,
            ),
            sequence=len(events),
            previous_event_hash=self._ledger.head_hash,
        )
        self._ledger.append(event)


__all__ = ["VllmAdapter"]
