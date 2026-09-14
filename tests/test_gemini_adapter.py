from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from contracts import BackendContent, BackendMessage, BackendRequest, ModelCallRequest
from devtools.gemini_adapter import GeminiApiAdapter


class _Response:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode()

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.payload


def _request(output: str = "text") -> BackendRequest:
    call = ModelCallRequest.from_dict({
        "request_id": "request.gemini.test", "task_id": "task.gemini.test",
        "team_id": "team.gemini.test", "worker_id": "worker.gemini.test",
        "task_kind": "inspection_review", "modality": "text",
        "required_capability": "reasoning", "evidence_summary": ["evidence.test"],
        "clearance": "internal", "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 512}, "attempt": 1,
        "idempotency_key": "idem.gemini.test", "timeout_ms": 5000,
        "role": "reasoning", "resource_lease_id": "lease.gemini.test",
    })
    from contracts import BackendOutputSpec
    return BackendRequest(call, "gemini-2.5-flash", "a" * 64, "airbench.gemini-test", "0.1",
                          (BackendMessage("user", (BackendContent("text", text="hello"),)),),
                          BackendOutputSpec(mode=output))


class GeminiAdapterTests(unittest.TestCase):
    def test_normalizes_text_response_and_uses_model_in_endpoint(self):
        adapter = GeminiApiAdapter("gemini-2.5-flash")
        response = _Response({"candidates": [{"content": {"parts": [{"text": "hello back"}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}})
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch("devtools.gemini_adapter.urlopen", return_value=response) as opened:
            result = adapter.complete(_request())
        self.assertEqual(result.output, "hello back")
        self.assertEqual(result.usage.total_tokens, 5)
        self.assertIn("gemini-2.5-flash:generateContent", opened.call_args.args[0].full_url)
        self.assertNotIn("test-key", result.provenance.to_dict().__repr__())

    def test_normalizes_structured_output(self):
        adapter = GeminiApiAdapter("gemini-2.5-pro")
        response = _Response({"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch("devtools.gemini_adapter.urlopen", return_value=response):
            result = adapter.complete(_request("json_object"))
        self.assertEqual(result.output, {"ok": True})

    def test_missing_key_fails_closed(self):
        adapter = GeminiApiAdapter("gemini-2.5-flash")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(Exception, "authentication_failed"):
                adapter.complete(_request())

    def test_inline_multimodal_part_is_normalized(self):
        adapter = GeminiApiAdapter("gemini-2.5-flash")
        from contracts import BackendContent
        part = BackendContent("image", media_ref="data:image/png;base64,AQI=", media_type="image/png", content_hash="a" * 64)
        payload = adapter._payload(_request(), stream=False)
        self.assertIn("contents", payload)
        self.assertEqual(adapter._part(part), {"inlineData": {"mimeType": "image/png", "data": "AQI="}})


if __name__ == "__main__":
    unittest.main()
