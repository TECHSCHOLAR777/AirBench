"""M5.4 — vLLM and NIM adapter tests.

All tests run without a real GPU, model server, or network.  HTTP calls are
intercepted with :mod:`unittest.mock`, so the test suite can run in any
air-gapped environment.

Test plan
---------
A – Protocol conformance (VllmAdapter and NimAdapter implement BackendAdapter)
B – Health / readiness as separate, independent states
C – Tool-call parsers (Hermes, StandardJson, None, Registry)
D – Structured output (json_object, json_schema)
E – Vision / multimodal input encoding
F – Streaming (SSE chunk accumulation, final-chunk flag, ledger events)
G – Cancellation (pre-call, mid-stream)
H – Timeout / unavailable / not-ready typed failures
I – Malformed response / unauthorized tool call
J – No-egress environment enforcement
K – Resource-exhaustion / context overflow
L – Concurrency and resource limits
M – Ledger events (started / completed / failed)
N – Provenance integrity (artifact_digest, target_id, request_hash)
O – NIM-specific paths (health URL, credential rejection)
P – Router integration (VllmAdapter selected when admitted)
"""

from __future__ import annotations

import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

from contracts import (
    BackendCallError,
    BackendCapabilities,
    BackendContent,
    BackendErrorCode,
    BackendHealth,
    BackendMessage,
    BackendOutputSpec,
    BackendReadiness,
    BackendRequest,
    BackendTool,
    BackendToolCall,
    CancellationToken,
    EventLedger,
    AdmissionController,
    AdmissionRequest,
    HardwareMeasurement,
    HardwareProfile,
    HermesToolParser,
    ModelCallRequest,
    ModelRegistry,
    ModelRouter,
    ModelTarget,
    NimAdapter,
    NoneToolParser,
    StandardJsonToolParser,
    ToolCallParserRegistry,
    VllmAdapter,
    build_event,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared test fixtures
# ─────────────────────────────────────────────────────────────────────────────

ARTIFACT = "a" * 64


def _model_call(*, modality: str = "text", timeout_ms: int = 5000) -> ModelCallRequest:
    return ModelCallRequest.from_dict({
        "request_id": "req-m54-1",
        "task_id": "task-m54-1",
        "team_id": "team-m54-1",
        "worker_id": "worker-m54-1",
        "task_kind": "inspection_review",
        "modality": modality,
        "required_capability": "reasoning",
        "evidence_summary": ["ev-1"],
        "clearance": "internal",
        "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 1000},
        "attempt": 1,
        "idempotency_key": "idem-m54-1",
        "timeout_ms": timeout_ms,
        "role": "reasoning",
        "resource_lease_id": "lease-m54-1",
    })


def _backend_request(
    *,
    modality: str = "text",
    output: BackendOutputSpec | None = None,
    tools: tuple[BackendTool, ...] = (),
    image: bool = False,
    backend_id: str = "airbench.vllm",
    backend_version: str = "0.5",
) -> BackendRequest:
    content: list[BackendContent] = [BackendContent(kind="text", text="Summarize the inspection evidence.")]
    if image:
        content.append(BackendContent(
            kind="image",
            media_ref="evidence://scan-001.png",
            media_type="image/png",
            content_hash="b" * 64,
        ))
    return BackendRequest(
        model_call=_model_call(modality=modality),
        target_id="gemma4-26b-a4b-4bit",
        artifact_digest=ARTIFACT,
        backend_id=backend_id,
        backend_version=backend_version,
        messages=(BackendMessage(role="user", content=tuple(content)),),
        output=output or BackendOutputSpec(),
        tools=tools,
    )


def _ledger_with_task() -> EventLedger:
    ledger = EventLedger()
    ledger.append(build_event(
        event_type="task.created", task_id="task-m54-1", actor_id="test",
        actor_type="test", payload_contract="TaskEnvelope", payload_version="1.0",
        payload={}, clearance="internal", idempotency="task-created-m54", sequence=0,
    ))
    return ledger


def _vllm(
    *,
    parser_id: str = "none",
    ledger: EventLedger | None = None,
    require_no_egress_env: bool = False,
    capabilities: BackendCapabilities | None = None,
) -> VllmAdapter:
    return VllmAdapter(
        base_url="http://127.0.0.1:8000",
        model_name="gemma4-26b-a4b-4bit",
        tool_parser=ToolCallParserRegistry.get(parser_id),
        ledger=ledger,
        require_no_egress_env=require_no_egress_env,
        capabilities=capabilities,
    )


def _mock_urlopen_ok(body: dict[str, Any]):
    """Return a mock urlopen context manager that yields a JSON body."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _mock_health_ok():
    resp = MagicMock()
    resp.read.return_value = b"ok"
    resp.status = 200
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _models_list(model_name: str = "gemma4-26b-a4b-4bit") -> dict[str, Any]:
    return {"data": [{"id": model_name}]}


def _completion_response(
    content: str = "The inspection found no anomalies.",
    tool_calls: list[dict] | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10},
    }


# ─────────────────────────────────────────────────────────────────────────────
# A – Protocol conformance
# ─────────────────────────────────────────────────────────────────────────────

class TestProtocolConformance(unittest.TestCase):

    def test_vllm_adapter_has_required_attributes(self) -> None:
        adapter = _vllm()
        self.assertEqual(adapter.adapter_id, "airbench.vllm")
        self.assertEqual(adapter.adapter_version, "0.5")
        self.assertTrue(callable(adapter.capabilities))
        self.assertTrue(callable(adapter.health))
        self.assertTrue(callable(adapter.readiness))
        self.assertTrue(callable(adapter.complete))
        self.assertTrue(callable(adapter.stream))

    def test_nim_adapter_has_required_attributes(self) -> None:
        adapter = NimAdapter("http://127.0.0.1:8001", "qwen3-coder", require_no_egress_env=False)
        self.assertEqual(adapter.adapter_id, "airbench.nim")
        self.assertEqual(adapter.adapter_version, "1.0")
        self.assertTrue(callable(adapter.capabilities))
        self.assertTrue(callable(adapter.health))
        self.assertTrue(callable(adapter.readiness))
        self.assertTrue(callable(adapter.complete))
        self.assertTrue(callable(adapter.stream))

    def test_vllm_capabilities_returns_correct_defaults(self) -> None:
        caps = _vllm().capabilities()
        self.assertIn("json_object", caps.structured_output_modes)
        self.assertIn("json_schema", caps.structured_output_modes)
        self.assertTrue(caps.tool_calling)
        self.assertIn("text", caps.modalities)
        self.assertIn("image", caps.modalities)
        self.assertTrue(caps.streaming)
        self.assertTrue(caps.cancellation)


# ─────────────────────────────────────────────────────────────────────────────
# B – Health / readiness separation
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthReadinessSeparation(unittest.TestCase):

    def test_vllm_health_unhealthy_on_connection_error(self) -> None:
        adapter = _vllm()
        with patch("contracts.adapters.vllm_adapter.urlopen", side_effect=OSError("connection refused")):
            self.assertEqual(adapter.health(), BackendHealth.unhealthy)

    def test_vllm_readiness_not_ready_when_model_absent(self) -> None:
        adapter = _vllm()
        body = {"data": [{"id": "other-model"}]}
        with patch("contracts.adapters.vllm_adapter.urlopen", return_value=_mock_urlopen_ok(body)):
            self.assertEqual(adapter.readiness(), BackendReadiness.not_ready)

    def test_vllm_readiness_ready_when_model_present(self) -> None:
        adapter = _vllm()
        with patch("contracts.adapters.vllm_adapter.urlopen", return_value=_mock_urlopen_ok(_models_list())):
            self.assertEqual(adapter.readiness(), BackendReadiness.ready)

    def test_vllm_health_healthy_on_200(self) -> None:
        adapter = _vllm()
        with patch("contracts.adapters.vllm_adapter.urlopen", return_value=_mock_health_ok()):
            self.assertEqual(adapter.health(), BackendHealth.healthy)

    def test_nim_health_uses_nim_specific_path(self) -> None:
        adapter = NimAdapter("http://127.0.0.1:8001", "qwen3-coder", require_no_egress_env=False)
        captured_urls: list[str] = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
            resp = MagicMock()
            resp.read.return_value = json.dumps({"status": "ready"}).encode()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("contracts.adapters.nim_adapter.urlopen", fake_urlopen):
            result = adapter.health()

        self.assertEqual(result, BackendHealth.healthy)
        self.assertTrue(any("/v1/health/ready" in url for url in captured_urls),
                        f"Expected /v1/health/ready in URLs: {captured_urls}")

    def test_nim_health_unhealthy_on_connection_refused(self) -> None:
        adapter = NimAdapter("http://127.0.0.1:8001", "qwen3-coder", require_no_egress_env=False)
        with patch("contracts.adapters.nim_adapter.urlopen", side_effect=OSError("refused")):
            self.assertEqual(adapter.health(), BackendHealth.unhealthy)


# ─────────────────────────────────────────────────────────────────────────────
# C – Tool-call parsers
# ─────────────────────────────────────────────────────────────────────────────

class TestToolParsers(unittest.TestCase):

    def _tools(self, *names: str) -> tuple[BackendTool, ...]:
        return tuple(BackendTool(n, f"desc of {n}", {"type": "object"}) for n in names)

    def test_hermes_parser_extracts_valid_tool_call(self) -> None:
        parser = HermesToolParser()
        text = '<tool_call>\n{"name": "calculator", "arguments": {"expr": "2+2"}}\n</tool_call>'
        result = parser.parse(text, self._tools("calculator"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "calculator")
        self.assertEqual(result[0].arguments["expr"], "2+2")

    def test_hermes_parser_returns_empty_for_no_blocks(self) -> None:
        parser = HermesToolParser()
        result = parser.parse("No tool call here.", self._tools("calculator"))
        self.assertEqual(result, ())

    def test_hermes_parser_rejects_malformed_json(self) -> None:
        parser = HermesToolParser()
        text = "<tool_call>\n{not valid json}\n</tool_call>"
        with self.assertRaises(BackendCallError) as ctx:
            parser.parse(text, self._tools("calculator"))
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.malformed_response)
        self.assertFalse(ctx.exception.failure.retryable)

    def test_hermes_parser_rejects_undeclared_tool(self) -> None:
        parser = HermesToolParser()
        text = '<tool_call>\n{"name": "secret_tool", "arguments": {}}\n</tool_call>'
        with self.assertRaises(BackendCallError) as ctx:
            parser.parse(text, self._tools("calculator"))
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.malformed_response)
        self.assertIn("secret_tool", str(ctx.exception))

    def test_hermes_parser_handles_parameters_alias(self) -> None:
        parser = HermesToolParser()
        text = '<tool_call>\n{"name": "calc", "parameters": {"x": 1}}\n</tool_call>'
        result = parser.parse(text, self._tools("calc"))
        self.assertEqual(result[0].arguments["x"], 1)

    def test_hermes_parser_multiple_blocks(self) -> None:
        parser = HermesToolParser()
        text = (
            '<tool_call>\n{"name": "a", "arguments": {}}\n</tool_call>\n'
            '<tool_call>\n{"name": "b", "arguments": {}}\n</tool_call>'
        )
        result = parser.parse(text, self._tools("a", "b"))
        self.assertEqual(len(result), 2)
        self.assertEqual({r.name for r in result}, {"a", "b"})

    def test_standard_json_parser_extracts_openai_format(self) -> None:
        parser = StandardJsonToolParser()
        calls = json.dumps([{"type": "function", "function": {"name": "search", "arguments": '{"q": "pressure"}'}}])
        result = parser.parse(calls, self._tools("search"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "search")
        self.assertEqual(result[0].arguments["q"], "pressure")

    def test_standard_json_parser_rejects_undeclared(self) -> None:
        parser = StandardJsonToolParser()
        calls = json.dumps([{"function": {"name": "not_declared", "arguments": "{}"}}])
        with self.assertRaises(BackendCallError) as ctx:
            parser.parse(calls, self._tools("other"))
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.malformed_response)

    def test_standard_json_parser_returns_empty_for_empty_text(self) -> None:
        parser = StandardJsonToolParser()
        self.assertEqual(parser.parse("", self._tools("a")), ())

    def test_none_parser_always_returns_empty(self) -> None:
        parser = NoneToolParser()
        text = '<tool_call>\n{"name": "any", "arguments": {}}\n</tool_call>'
        self.assertEqual(parser.parse(text, self._tools("any")), ())
        self.assertEqual(parser.parse("", ()), ())

    def test_registry_returns_correct_parser_types(self) -> None:
        self.assertIsInstance(ToolCallParserRegistry.get("hermes"), HermesToolParser)
        self.assertIsInstance(ToolCallParserRegistry.get("standard_json"), StandardJsonToolParser)
        self.assertIsInstance(ToolCallParserRegistry.get("none"), NoneToolParser)

    def test_registry_raises_on_unknown_parser_id(self) -> None:
        with self.assertRaises(BackendCallError) as ctx:
            ToolCallParserRegistry.get("does_not_exist")
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.unsupported_capability)
        self.assertFalse(ctx.exception.failure.retryable)

    def test_registry_known_ids_are_sorted(self) -> None:
        ids = ToolCallParserRegistry.known_ids()
        self.assertEqual(ids, tuple(sorted(ids)))
        self.assertIn("hermes", ids)
        self.assertIn("standard_json", ids)
        self.assertIn("none", ids)


# ─────────────────────────────────────────────────────────────────────────────
# D – Structured output
# ─────────────────────────────────────────────────────────────────────────────

class TestStructuredOutput(unittest.TestCase):

    def _complete_with_mock(self, output_spec: BackendOutputSpec, response_content: str) -> Any:
        adapter = _vllm()
        req = _backend_request(output=output_spec)
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        completion_resp = _mock_urlopen_ok(_completion_response(content=response_content))

        call_count = [0]
        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return health_resp
            if call_count[0] == 2:
                return models_resp
            return completion_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            return adapter.complete(req)

    def test_json_object_mode_parses_content_as_dict(self) -> None:
        response = self._complete_with_mock(
            BackendOutputSpec(mode="json_object"),
            '{"finding": "corrosion", "severity": "medium"}',
        )
        self.assertIsInstance(response.output, dict)
        self.assertEqual(response.output["finding"], "corrosion")

    def test_json_schema_mode_parses_content_as_dict(self) -> None:
        response = self._complete_with_mock(
            BackendOutputSpec(mode="json_schema", schema={"type": "object"}),
            '{"status": "ok"}',
        )
        self.assertIsInstance(response.output, dict)

    def test_text_mode_returns_plain_string(self) -> None:
        response = self._complete_with_mock(
            BackendOutputSpec(mode="text"),
            "Plain text answer.",
        )
        self.assertIsInstance(response.output, str)

    def test_unsupported_output_mode_raises_unsupported_capability(self) -> None:
        adapter = _vllm(capabilities=BackendCapabilities(
            modalities=("text",), structured_output_modes=(), streaming=False,
        ))
        req = _backend_request(output=BackendOutputSpec(mode="json_object"))
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())

        call_count = [0]
        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            return health_resp if call_count[0] == 1 else models_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req)
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.unsupported_capability)
        self.assertFalse(ctx.exception.failure.retryable)


# ─────────────────────────────────────────────────────────────────────────────
# E – Vision / multimodal input
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionInput(unittest.TestCase):

    def test_image_content_is_encoded_as_image_url(self) -> None:
        """The HTTP payload must contain an image_url part for image content."""
        adapter = _vllm()
        req = _backend_request(modality="image", image=True)
        captured_bodies: list[dict] = []

        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        completion_resp = _mock_urlopen_ok(_completion_response())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return health_resp
            if call_count[0] == 2:
                return models_resp
            if hasattr(req_obj, "data") and req_obj.data:
                captured_bodies.append(json.loads(req_obj.data))
            return completion_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            adapter.complete(req)

        self.assertTrue(captured_bodies, "No POST body captured")
        messages = captured_bodies[-1].get("messages", [])
        all_parts: list[dict] = []
        for msg in messages:
            c = msg.get("content")
            if isinstance(c, list):
                all_parts.extend(c)
        image_parts = [p for p in all_parts if p.get("type") == "image_url"]
        self.assertTrue(image_parts, f"No image_url part found. Parts: {all_parts}")
        self.assertIn("evidence://scan-001.png", image_parts[0]["image_url"]["url"])

    def test_image_modality_not_supported_raises_explicit_error(self) -> None:
        adapter = _vllm(capabilities=BackendCapabilities(modalities=("text",), streaming=False))
        req = _backend_request(modality="image", image=True)
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            return health_resp if call_count[0] == 1 else models_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req)
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.unsupported_capability)


# ─────────────────────────────────────────────────────────────────────────────
# F – Streaming
# ─────────────────────────────────────────────────────────────────────────────

class TestStreaming(unittest.TestCase):

    def _sse_lines(self, chunks: list[str]) -> bytes:
        lines: list[bytes] = []
        for i, text in enumerate(chunks):
            finish = "stop" if i == len(chunks) - 1 else "null"
            finish_json = f'"{finish}"' if finish != "null" else "null"
            data = json.dumps({
                "choices": [{"delta": {"content": text}, "finish_reason": finish if finish != "null" else None}]
            })
            lines.append(f"data: {data}\n".encode())
        lines.append(b"data: [DONE]\n")
        return b"\n".join(lines)

    def _stream_adapter_with_mock(self, text_chunks: list[str]) -> tuple[VllmAdapter, list[Any]]:
        adapter = _vllm()
        req = _backend_request()
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())

        sse_body = self._sse_lines(text_chunks)

        class FakeStreamResp:
            def read(self): return sse_body
            def __iter__(self):
                for line in sse_body.split(b"\n"):
                    yield line + b"\n"
            def __enter__(self): return self
            def __exit__(self, *_): pass

        call_count = [0]
        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            return FakeStreamResp()

        chunks = []
        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            for chunk in adapter.stream(req):
                chunks.append(chunk)

        return adapter, chunks

    def test_stream_returns_chunks_with_text(self) -> None:
        _, chunks = self._stream_adapter_with_mock(["Hello", " world"])
        texts = "".join(c.text for c in chunks)
        self.assertIn("Hello", texts)
        self.assertIn("world", texts)

    def test_stream_last_chunk_is_final(self) -> None:
        _, chunks = self._stream_adapter_with_mock(["Hello", " world"])
        self.assertTrue(chunks[-1].final, "Last chunk must have final=True")

    def test_stream_chunks_have_sequential_indices(self) -> None:
        _, chunks = self._stream_adapter_with_mock(["a", "b", "c"])
        indices = [c.index for c in chunks]
        self.assertEqual(indices, list(range(len(chunks))))

    def test_stream_emits_started_and_completed_ledger_events(self) -> None:
        ledger = _ledger_with_task()
        adapter = _vllm(ledger=ledger)
        req = _backend_request()
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())

        sse_body = self._sse_lines(["result"])

        class FakeStreamResp:
            def __iter__(self):
                for line in sse_body.split(b"\n"):
                    yield line + b"\n"
            def __enter__(self): return self
            def __exit__(self, *_): pass

        call_count = [0]
        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            return FakeStreamResp()

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            list(adapter.stream(req))

        types = [e.event_type for e in ledger.events]
        self.assertIn("model.call.started", types)
        self.assertIn("model.call.completed", types)


# ─────────────────────────────────────────────────────────────────────────────
# G – Cancellation
# ─────────────────────────────────────────────────────────────────────────────

class TestCancellation(unittest.TestCase):

    def test_pre_cancelled_token_raises_cancelled_before_http_call(self) -> None:
        adapter = _vllm()
        req = _backend_request()
        token = CancellationToken()
        token.cancel()
        calls: list[str] = []

        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            calls.append("completion-called")
            return _mock_urlopen_ok(_completion_response())

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req, token)

        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.cancelled)
        self.assertFalse(ctx.exception.failure.retryable)
        self.assertNotIn("completion-called", calls)

    def test_cancelled_during_stream_raises_cancelled(self) -> None:
        adapter = _vllm()
        req = _backend_request()
        token = CancellationToken()

        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())

        call_count = [0]
        chunk_count = [0]

        class FakeStreamRespWithCancel:
            def __iter__(self):
                for i in range(10):
                    data = json.dumps({
                        "choices": [{"delta": {"content": f"word{i} "}, "finish_reason": None}]
                    })
                    yield f"data: {data}\n".encode()
                    chunk_count[0] += 1
                    if chunk_count[0] >= 2:
                        token.cancel()

            def __enter__(self): return self
            def __exit__(self, *_): pass

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            return FakeStreamRespWithCancel()

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                list(adapter.stream(req, token))

        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.cancelled)

    def test_cancellation_during_stream_emits_failed_ledger_event(self) -> None:
        ledger = _ledger_with_task()
        adapter = _vllm(ledger=ledger)
        req = _backend_request()
        token = CancellationToken()

        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        call_count = [0]

        class FakeInstantCancel:
            def __iter__(self):
                token.cancel()  # cancel before yielding any chunk
                yield b"data: " + json.dumps({"choices": [{"delta": {"content": "x"}, "finish_reason": None}]}).encode() + b"\n"

            def __enter__(self): return self
            def __exit__(self, *_): pass

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            return FakeInstantCancel()

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError):
                list(adapter.stream(req, token))

        event_types = [e.event_type for e in ledger.events]
        self.assertIn("model.call.failed", event_types)
        failed = next(e for e in ledger.events if e.event_type == "model.call.failed")
        self.assertEqual(failed.payload["error_code"], "cancelled")


# ─────────────────────────────────────────────────────────────────────────────
# H – Timeout / unavailable / not-ready
# ─────────────────────────────────────────────────────────────────────────────

class TestTimeoutAndUnavailable(unittest.TestCase):

    def test_connection_refused_raises_unavailable_retryable(self) -> None:
        adapter = _vllm()
        req = _backend_request()
        from urllib.error import URLError

        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            raise URLError("Connection refused")

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req)
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.unavailable)
        self.assertTrue(ctx.exception.failure.retryable)

    def test_timeout_raises_timeout_retryable(self) -> None:
        adapter = _vllm()
        req = _backend_request()
        from urllib.error import URLError

        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            raise URLError("timed out")

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req)
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.timeout)
        self.assertTrue(ctx.exception.failure.retryable)

    def test_unhealthy_backend_raises_unavailable(self) -> None:
        adapter = _vllm()
        req = _backend_request()

        def fake_urlopen(req_obj, timeout=None):
            raise OSError("server down")

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req)
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.unavailable)

    def test_healthy_but_not_ready_raises_not_ready(self) -> None:
        adapter = _vllm()
        req = _backend_request()
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok({"data": []})  # model not in list
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            return models_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req)
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.not_ready)
        self.assertTrue(ctx.exception.failure.retryable)


# ─────────────────────────────────────────────────────────────────────────────
# I – Malformed response / unauthorized tool
# ─────────────────────────────────────────────────────────────────────────────

class TestMalformedResponse(unittest.TestCase):

    def _setup_mock(self, completion_body: dict | None = None, raise_exc=None):
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        if completion_body is not None:
            completion_resp = _mock_urlopen_ok(completion_body)
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            if raise_exc:
                raise raise_exc
            return completion_resp

        return fake_urlopen

    def test_non_json_response_raises_malformed(self) -> None:
        adapter = _vllm()
        req = _backend_request()
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())

        class BadJsonResp:
            def read(self): return b"not json at all"
            def __enter__(self): return self
            def __exit__(self, *_): pass

        call_count = [0]
        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            return BadJsonResp()

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req)
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.malformed_response)

    def test_unauthorized_tool_call_raises_malformed(self) -> None:
        adapter = _vllm(parser_id="standard_json")
        tool = BackendTool("allowed_tool", "An allowed tool", {"type": "object"})
        req = _backend_request(tools=(tool,))

        # Response references an unauthorized tool
        raw_tool_calls = [{"function": {"name": "secret_tool", "arguments": "{}"}}]
        completion = _completion_response(tool_calls=raw_tool_calls)

        fake_urlopen = self._setup_mock(completion_body=completion)
        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req)
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.malformed_response)


# ─────────────────────────────────────────────────────────────────────────────
# J – No-egress environment enforcement
# ─────────────────────────────────────────────────────────────────────────────

class TestNoEgressEnforcement(unittest.TestCase):

    def test_missing_env_vars_raise_unavailable_before_http(self) -> None:
        adapter = VllmAdapter(
            "http://127.0.0.1:8000", "gemma4-26b-a4b-4bit",
            require_no_egress_env=True,
        )
        req = _backend_request()
        calls: list[str] = []

        def fake_urlopen(req_obj, timeout=None):
            calls.append("http-call")
            return _mock_health_ok()

        env_without_offline = {k: v for k, v in os.environ.items()
                               if k not in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
        with patch.dict(os.environ, env_without_offline, clear=True):
            with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
                with self.assertRaises(BackendCallError) as ctx:
                    adapter.complete(req)

        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.unavailable)
        self.assertFalse(ctx.exception.failure.retryable)
        # No HTTP calls must have been made
        self.assertEqual(calls, [], "No-egress check must fire before any HTTP call")

    def test_correct_env_vars_allow_call_to_proceed(self) -> None:
        """With env vars set, the adapter proceeds past the no-egress check."""
        adapter = VllmAdapter(
            "http://127.0.0.1:8000", "gemma4-26b-a4b-4bit",
            require_no_egress_env=True,
        )
        req = _backend_request()
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        completion_resp = _mock_urlopen_ok(_completion_response())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            return completion_resp

        with patch.dict(os.environ, {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}):
            with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
                response = adapter.complete(req)

        self.assertIsNotNone(response)
        self.assertEqual(response.target_id, "gemma4-26b-a4b-4bit")

    def test_nim_refuses_real_api_key_at_construction(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            NimAdapter("http://127.0.0.1:8001", "qwen3", api_key="nvapi-supersecret123")
        self.assertIn("local placeholder", str(ctx.exception).lower())

    def test_nim_accepts_local_placeholder_key(self) -> None:
        # Must not raise
        adapter = NimAdapter("http://127.0.0.1:8001", "qwen3", api_key="local",
                              require_no_egress_env=False)
        self.assertIsNotNone(adapter)


# ─────────────────────────────────────────────────────────────────────────────
# K – Resource exhaustion / context overflow
# ─────────────────────────────────────────────────────────────────────────────

class TestResourceExhaustion(unittest.TestCase):

    def test_context_over_limit_raises_resource_exhausted_retryable(self) -> None:
        adapter = _vllm(capabilities=BackendCapabilities(
            modalities=("text",), max_context_tokens=100, streaming=False,
        ))
        req = _backend_request()  # resource_budget={"context_tokens": 1000} > 100
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            return models_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req)
        self.assertEqual(ctx.exception.failure.code, BackendErrorCode.resource_exhausted)
        self.assertTrue(ctx.exception.failure.retryable)


# ─────────────────────────────────────────────────────────────────────────────
# L – Concurrency and resource limits
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrencyAndResourceLimits(unittest.TestCase):

    def test_concurrent_adapter_calls_and_admission_ceiling(self) -> None:
        """Adapter calls may overlap; team concurrency remains admission-owned."""
        adapter = _vllm()
        first = _backend_request()
        second = replace(
            first,
            model_call=replace(first.model_call, request_id="req-m54-2"),
        )

        post_barrier = threading.Barrier(2)
        state_lock = threading.Lock()
        active_posts = 0
        peak_active_posts = 0

        def fake_urlopen(req_obj, timeout=None):
            nonlocal active_posts, peak_active_posts
            path = req_obj.full_url.rsplit("127.0.0.1:8000", 1)[-1]
            if path == "/health":
                return _mock_health_ok()
            if path == "/v1/models":
                return _mock_urlopen_ok(_models_list())

            with state_lock:
                active_posts += 1
                peak_active_posts = max(peak_active_posts, active_posts)
            try:
                post_barrier.wait(timeout=2)
                return _mock_urlopen_ok(_completion_response())
            finally:
                with state_lock:
                    active_posts -= 1

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(adapter.complete, (first, second)))

        self.assertEqual(len(responses), 2)
        self.assertTrue(all(response.output for response in responses))
        self.assertEqual(peak_active_posts, 2)

        profile = HardwareProfile.from_dict({
            "profile_id": "gpu-m54-concurrency",
            "gpu_model": "test-gpu",
            "gpu_count": 1,
            "vram_bytes": 100_000,
            "driver_version": "test",
            "accelerator_runtime": "test",
            "cpu_model": "test-cpu",
            "cpu_cores": 8,
            "ram_bytes": 100_000,
            "storage_bytes": 100_000,
            "scratch_bytes": 10_000,
            "model_context_tokens": 4096,
            "kv_cache_bytes": 10_000,
            "safe_parallel_slots": 4,
            "egress_policy": "deny-all",
            "measurement_hash": "c" * 64,
            "network_check_id": "check-m54-egress",
        })
        measurement = HardwareMeasurement(
            measurement_id="measurement-m54-concurrency",
            profile_id=profile.profile_id,
            measured_at="2026-09-08T00:00:00Z",
            available_vram_bytes=100_000,
            available_ram_bytes=100_000,
            kv_cache_bytes=10_000,
            model_residency_bytes=(),
            latency_ms=(),
            throughput_tokens_per_second=(),
            sandbox_limits=(),
            max_concurrency=1,
            egress_verified=True,
        )
        admission = AdmissionController(profile, measurement).admit(AdmissionRequest(
            task_id="task-m54-concurrency",
            team_id="team-m54-concurrency",
            worker_capabilities=(("lead", "reasoning"), ("verifier", "verification")),
            reservations=(
                ("lead", (("vram_bytes", 20_000),)),
                ("verifier", (("vram_bytes", 10_000),)),
            ),
            verifier_worker_id="verifier",
        ))
        self.assertEqual(admission.plan.execution_mode, "serial_virtual_team")
        self.assertEqual(admission.plan.concurrency_ceiling, 1)


# ─────────────────────────────────────────────────────────────────────────────
# M – Ledger events
# ─────────────────────────────────────────────────────────────────────────────

class TestLedgerEvents(unittest.TestCase):

    def _complete_with_ledger(self) -> EventLedger:
        ledger = _ledger_with_task()
        adapter = _vllm(ledger=ledger)
        req = _backend_request()
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        completion_resp = _mock_urlopen_ok(_completion_response())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            return completion_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            adapter.complete(req)
        return ledger

    def test_successful_call_emits_started_and_completed(self) -> None:
        ledger = self._complete_with_ledger()
        types = [e.event_type for e in ledger.events]
        self.assertIn("model.call.started", types)
        self.assertIn("model.call.completed", types)
        self.assertNotIn("model.call.failed", types)

    def test_started_event_contains_request_hash(self) -> None:
        ledger = self._complete_with_ledger()
        started = next(e for e in ledger.events if e.event_type == "model.call.started")
        self.assertIn("request_hash", started.payload)

    def test_completed_event_contains_response_hash_and_usage(self) -> None:
        ledger = self._complete_with_ledger()
        completed = next(e for e in ledger.events if e.event_type == "model.call.completed")
        self.assertIn("response_hash", completed.payload)
        self.assertIn("usage", completed.payload)

    def test_failed_call_emits_model_call_failed(self) -> None:
        ledger = _ledger_with_task()
        adapter = _vllm(ledger=ledger)
        req = _backend_request()
        from urllib.error import URLError
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            raise URLError("Connection refused")

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            with self.assertRaises(BackendCallError):
                adapter.complete(req)

        types = [e.event_type for e in ledger.events]
        self.assertIn("model.call.failed", types)

    def test_ledger_events_do_not_contain_prompt_text(self) -> None:
        """Prompt text must never appear in ledger event payloads."""
        ledger = self._complete_with_ledger()
        for event in ledger.events:
            payload_str = json.dumps(event.payload)
            self.assertNotIn("Summarize the inspection", payload_str,
                             f"Prompt text leaked into {event.event_type}")


# ─────────────────────────────────────────────────────────────────────────────
# M – Provenance integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestProvenanceIntegrity(unittest.TestCase):

    def _response(self) -> Any:
        ledger = _ledger_with_task()
        adapter = _vllm(ledger=ledger)
        req = _backend_request()
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        completion_resp = _mock_urlopen_ok(_completion_response())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            return completion_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            return adapter.complete(req)

    def test_provenance_target_id_matches_request(self) -> None:
        response = self._response()
        self.assertEqual(response.provenance.target_id, "gemma4-26b-a4b-4bit")

    def test_provenance_artifact_digest_matches_request(self) -> None:
        response = self._response()
        self.assertEqual(response.provenance.artifact_digest, ARTIFACT)

    def test_provenance_backend_id_matches_adapter(self) -> None:
        response = self._response()
        self.assertEqual(response.provenance.backend_id, "airbench.vllm")

    def test_provenance_taint_is_untrusted(self) -> None:
        response = self._response()
        from contracts.models import Taint
        self.assertEqual(response.provenance.taint, Taint.untrusted)

    def test_provenance_records_bound_endpoint_id(self) -> None:
        ledger = _ledger_with_task()
        adapter = VllmAdapter(
            base_url="http://127.0.0.1:18002",
            model_name="gemma4-26b-a4b-4bit",
            tool_parser=ToolCallParserRegistry.get("none"),
            ledger=ledger,
            endpoint_id="endpoint.gemma-12b",
            require_no_egress_env=False,
        )
        req = _backend_request()
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        completion_resp = _mock_urlopen_ok(_completion_response())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            return completion_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            response = adapter.complete(req)
        self.assertEqual(response.provenance.endpoint_id, "endpoint.gemma-12b")
        self.assertEqual(response.provenance.execution_location, "local")

    def test_response_status_is_verified(self) -> None:
        response = self._response()
        from contracts.models import ContractStatus
        self.assertEqual(response.status, ContractStatus.verified)


# ─────────────────────────────────────────────────────────────────────────────
# N – NIM-specific behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestNimSpecific(unittest.TestCase):

    def test_nim_adapter_id_is_distinct_from_vllm(self) -> None:
        nim = NimAdapter("http://127.0.0.1:8001", "qwen3", require_no_egress_env=False)
        self.assertEqual(nim.adapter_id, "airbench.nim")
        self.assertNotEqual(nim.adapter_id, "airbench.vllm")

    def test_nim_complete_delegates_with_local_key(self) -> None:
        nim = NimAdapter(
            "http://127.0.0.1:8001", "gemma4-26b-a4b-4bit",
            api_key="local",
            require_no_egress_env=False,
        )
        req = _backend_request(backend_id="airbench.nim", backend_version="1.0")
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list())
        completion_resp = _mock_urlopen_ok(_completion_response())
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1: return health_resp
            if call_count[0] == 2: return models_resp
            return completion_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            response = nim.complete(req)
        self.assertIsNotNone(response.output)

    def test_nim_health_returns_healthy_on_ready_status(self) -> None:
        nim = NimAdapter("http://127.0.0.1:8001", "qwen3", require_no_egress_env=False)
        body = json.dumps({"status": "ready"}).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("contracts.adapters.nim_adapter.urlopen", return_value=resp):
            health = nim.health()
        self.assertEqual(health, BackendHealth.healthy)

    def test_nim_health_unhealthy_when_status_not_ready(self) -> None:
        nim = NimAdapter("http://127.0.0.1:8001", "qwen3", require_no_egress_env=False)
        body = json.dumps({"status": "initializing"}).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("contracts.adapters.nim_adapter.urlopen", return_value=resp):
            health = nim.health()
        self.assertEqual(health, BackendHealth.unhealthy)


# ─────────────────────────────────────────────────────────────────────────────
# O – Router integration
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterIntegration(unittest.TestCase):

    def _target(self) -> ModelTarget:
        # vllm and nim backends require a container_digest per registry contract.
        # Use a sha256-prefixed placeholder that satisfies the digest format.
        container_digest = "sha256:" + "a" * 64
        return ModelTarget.from_dict({
            "target_id": "gemma4-26b-a4b-4bit",
            "repository": "local/gemma4-26b",
            "artifact_digest": ARTIFACT,
            "artifact_path": "gemma4-26b.gguf",
            "quantization": "int4",
            "tokenizer_digest": "b" * 64,
            "chat_template_digest": "c" * 64,
            "runtime_version": "vllm-0.5",
            "backend": "vllm",
            "container_digest": container_digest,
            "capabilities": ["reasoning"],
            "roles": ["reasoning"],
            "modalities": ["text"],
            "risk_classes": ["inspection_review"],
            "allowed_clearances": ["internal"],
            "pack_refs": ["pack.refinery.v0"],
            "hardware_profile_refs": ["hw.target-96gb"],
            "context_limit": 8192,
            "image_token_limit": 0,
            "tool_call_parser": "standard_json",
            "structured_output_modes": ["json_object", "json_schema"],
            "license_id": "apache-2.0",
            "local_storage_hash": "d" * 64,
            "qualification_certificate": "cert.gemma4-26b.reasoning",
            "qualification_expires_at": "2030-01-01T00:00:00Z",
            "qualification_signature": "e" * 64,
            "role_qualifications": [["reasoning", "cert.gemma4-26b.reasoning"]],
            "adapter_id": "airbench.vllm",
            "adapter_version": "0.5",
            "streaming": True,
            "cancellation": True,
        })

    def test_vllm_adapter_registered_in_router_and_selected(self) -> None:
        target = self._target()
        registry = ModelRegistry(
            "reg.m54", "1.0", (target,), "f" * 64, "2030-01-01T00:00:00Z"
        )
        vllm_adapter = _vllm()

        # Make the adapter report healthy and ready
        health_resp = _mock_health_ok()
        models_resp = _mock_urlopen_ok(_models_list(model_name="gemma4-26b-a4b-4bit"))
        call_count = [0]

        def fake_urlopen(req_obj, timeout=None):
            call_count[0] += 1
            if call_count[0] % 2 == 1: return health_resp
            return models_resp

        with patch("contracts.adapters.vllm_adapter.urlopen", fake_urlopen):
            router = ModelRouter(
                registry,
                {"airbench.vllm": vllm_adapter},
                policy_version_hash="policy.m54.v1",
                resource_admission=lambda t, r: "admitted",
            )
            from contracts.models import ModelCallRequest
            request = ModelCallRequest.from_dict({
                "request_id": "req-router-m54",
                "task_id": "task-router-m54",
                "team_id": "team-router-m54",
                "worker_id": "worker-router-m54",
                "task_kind": "inspection_review",
                "modality": "text",
                "required_capability": "reasoning",
                "evidence_summary": ["ev-1"],
                "clearance": "internal",
                "action_risk": "inspection_review",
                "resource_budget": {"context_tokens": 512},
                "attempt": 1,
                "idempotency_key": "idem-router-m54",
                "timeout_ms": 5000,
                "role": "reasoning",
                "resource_lease_id": "lease-router-m54",
            })
            result = router.route(
                request,
                pack_ref="pack.refinery.v0",
                hardware_profile_ref="hw.target-96gb",
            )

        from contracts.models import ContractStatus
        self.assertEqual(result.decision.status, ContractStatus.accepted)
        self.assertEqual(result.decision.selected_target, "gemma4-26b-a4b-4bit")
        self.assertIsNotNone(result.adapter)
        self.assertEqual(result.adapter.adapter_id, "airbench.vllm")

    def test_router_queues_when_adapter_not_healthy(self) -> None:
        target = self._target()
        registry = ModelRegistry("reg.m54", "1.0", (target,), "f" * 64, "2030-01-01T00:00:00Z")
        vllm_adapter = _vllm()

        # Force unhealthy by making all requests fail
        with patch("contracts.adapters.vllm_adapter.urlopen", side_effect=OSError("down")):
            router = ModelRouter(
                registry,
                {"airbench.vllm": vllm_adapter},
                policy_version_hash="policy.m54.v1",
                resource_admission=lambda t, r: "admitted",
            )
            from contracts.models import ModelCallRequest
            request = ModelCallRequest.from_dict({
                "request_id": "req-router-m54-queue",
                "task_id": "task-router-m54-queue",
                "team_id": "team-router-m54-queue",
                "worker_id": "worker-router-m54-queue",
                "task_kind": "inspection_review",
                "modality": "text",
                "required_capability": "reasoning",
                "evidence_summary": ["ev-1"],
                "clearance": "internal",
                "action_risk": "inspection_review",
                "resource_budget": {"context_tokens": 512},
                "attempt": 1,
                "idempotency_key": "idem-router-m54-queue",
                "timeout_ms": 5000,
                "role": "reasoning",
                "resource_lease_id": "lease-router-m54-queue",
            })
            result = router.route(request, pack_ref="pack.refinery.v0",
                                  hardware_profile_ref="hw.target-96gb")

        from contracts.models import ContractStatus
        # Unhealthy backend → rejected (not admitted, not queued by resource)
        self.assertIn(result.decision.status,
                      (ContractStatus.rejected, ContractStatus.needs_review, ContractStatus.queued))
        self.assertIsNone(result.adapter)


if __name__ == "__main__":
    unittest.main()
