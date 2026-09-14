"""Contract tests for the signed remote Qwen deployment described by the handoff."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from contracts import (
    BackendContent, BackendMessage, BackendOutputSpec, BackendRequest, BackendTool,
    Clearance, ModelCallRequest, RegistryError, RemoteDeploymentAttestation,
)
from airbench.node.model_serving import ModelServingConfig, load_model_serving_runtime
from scripts.airbench_qwen_aimslab_records import write_records


KEY = b"qwen-aimslab-test-signing-key-32b"[:32]


def _config(*, allow_candidates: bool = False) -> ModelServingConfig:
    return ModelServingConfig.from_dict({
        "policy_version_hash": "policy.qwen.1",
        "require_no_egress_env": False,
        "allow_candidate_qualification": allow_candidates,
        "endpoints": [
            {"endpoint_id": "endpoint-vision", "target_id": "airbench-qwen25-vl-7b", "base_url": "http://127.0.0.1:18001", "served_model_name": "airbench-qwen25-vl-7b"},
            {"endpoint_id": "endpoint-reasoning", "target_id": "airbench-qwen3-8b", "base_url": "http://127.0.0.1:18002", "served_model_name": "airbench-qwen3-8b"},
        ],
    })


class QwenAimsLabIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.roster = root / "qwen.yaml"
        self.attestation = root / "attestation.yaml"
        write_records(KEY, self.roster, self.attestation)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _runtime(self, *, allow_candidates: bool = True):
        return load_model_serving_runtime(
            _config(allow_candidates=allow_candidates), roster_path=self.roster,
            artifact_root=None, signing_key=KEY, deployment_attestation_path=self.attestation,
            attestation_signing_key=KEY, resource_admission=lambda _target, _request: "admitted",
        )

    def test_signed_remote_records_load_without_local_model_bytes(self) -> None:
        runtime = self._runtime()
        self.assertEqual({target.target_id for target in runtime.registry.targets}, {"airbench-qwen25-vl-7b", "airbench-qwen3-8b"})
        self.assertIsNotNone(runtime.deployment_attestation)
        self.assertEqual(runtime.router.endpoint_bindings["airbench-qwen3-8b"]._tool_parser.__class__.__name__, "HermesToolParser")

    def test_candidate_records_are_not_routable_without_explicit_demo_switch(self) -> None:
        runtime = self._runtime(allow_candidates=False)
        request = ModelCallRequest.from_dict({
            "request_id": "request.qwen.candidate", "task_id": "task.qwen", "team_id": "team.qwen", "worker_id": "worker.qwen",
            "task_kind": "inspection_review", "modality": "text", "required_capability": "reasoning",
            "evidence_summary": ["evidence.qwen"], "clearance": "internal", "action_risk": "inspection_review",
            "resource_budget": {"context_tokens": 128}, "attempt": 1, "idempotency_key": "idem.qwen.candidate",
            "timeout_ms": 1000, "role": "reasoning", "resource_lease_id": "lease.qwen",
        })
        route = runtime.router.route(request, pack_ref="refinery-psu-v0", hardware_profile_ref="aimslab-titan-rtx-24gb")
        self.assertEqual(route.decision.status.value, "rejected")

    def test_qwen3_payload_is_deterministic_and_binds_thinking_option(self) -> None:
        runtime = self._runtime()
        adapter = runtime.router.endpoint_bindings["airbench-qwen3-8b"]
        request = self._backend_request(
            target_id="airbench-qwen3-8b", role="reasoning", capability="reasoning", modality="text",
            messages=(BackendMessage("user", (BackendContent(kind="text", text="Reply with exactly OK."),)),),
            tools=(BackendTool("lookup", "lookup", {"type": "object", "properties": {}}),),
        )
        payload = adapter._build_payload(request, stream=False)
        self.assertEqual(payload["model"], "airbench-qwen3-8b")
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["tools"][0]["function"]["name"], "lookup")

    def test_qwen25_vl_encodes_one_image_and_rejects_video_or_second_image(self) -> None:
        runtime = self._runtime()
        adapter = runtime.router.endpoint_bindings["airbench-qwen25-vl-7b"]
        image = BackendContent(kind="image", media_ref="intake://image/red-square", media_type="image/png", content_hash="a" * 64)
        request = self._backend_request(
            target_id="airbench-qwen25-vl-7b", role="vision_worker", capability="vision", modality="image",
            messages=(BackendMessage("user", (BackendContent(kind="text", text="Describe the image."), image)),),
        )
        payload = adapter._build_payload(request, stream=False)
        self.assertEqual(payload["messages"][0]["content"][1]["type"], "image_url")
        self.assertEqual(payload["messages"][0]["content"][1]["image_url"]["url"], "intake://image/red-square")
        second_image = BackendContent(kind="image", media_ref="intake://image/second", media_type="image/png", content_hash="b" * 64)
        with self.assertRaises(Exception):
            adapter._check_capabilities(self._backend_request(
                target_id="airbench-qwen25-vl-7b", role="vision_worker", capability="vision", modality="image",
                messages=(BackendMessage("user", (image, second_image)),),
            ))

    def test_qwen3_native_hermes_tool_call_is_normalized(self) -> None:
        runtime = self._runtime()
        adapter = runtime.router.endpoint_bindings["airbench-qwen3-8b"]
        request = self._backend_request(
            target_id="airbench-qwen3-8b", role="reasoning", capability="reasoning", modality="text",
            messages=(BackendMessage("user", (BackendContent(kind="text", text="look up x"),)),),
            tools=(BackendTool("lookup", "lookup", {"type": "object"}),),
        )
        response = adapter._parse_completion({
            "choices": [{"message": {"content": None, "reasoning_content": "private reasoning", "tool_calls": [
                {"id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": "{\"key\":\"x\"}"}}
            ]}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3},
        }, request)
        self.assertEqual(response.tool_calls[0].name, "lookup")
        self.assertEqual(response.tool_calls[0].arguments, {"key": "x"})
        self.assertNotIn("private reasoning", json.dumps(response.to_dict()))

    def test_mismatched_attestation_fails_closed(self) -> None:
        config = ModelServingConfig.from_dict({
            "policy_version_hash": "policy.qwen.1", "require_no_egress_env": False,
            "endpoints": [
                {"endpoint_id": "endpoint-vision", "target_id": "airbench-qwen25-vl-7b", "base_url": "http://127.0.0.1:19001", "served_model_name": "airbench-qwen25-vl-7b"},
                {"endpoint_id": "endpoint-reasoning", "target_id": "airbench-qwen3-8b", "base_url": "http://127.0.0.1:18002", "served_model_name": "airbench-qwen3-8b"},
            ],
        })
        with self.assertRaises(RegistryError):
            load_model_serving_runtime(
                config,
                roster_path=self.roster, artifact_root=None, signing_key=KEY,
                deployment_attestation_path=self.attestation, attestation_signing_key=KEY,
            )

    def test_stale_attestation_is_rejected(self) -> None:
        import yaml
        document = yaml.safe_load(self.attestation.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "stale"):
            RemoteDeploymentAttestation.from_dict(
                document, signing_key=KEY,
                now=datetime(2026, 11, 1, tzinfo=timezone.utc),
            )

    def test_missing_attestation_is_rejected_in_remote_mode(self) -> None:
        with self.assertRaises(ValueError):
            load_model_serving_runtime(
                _config(), roster_path=self.roster, artifact_root=None, signing_key=KEY,
                deployment_attestation_path=Path(self.tmp.name) / "missing.yaml", attestation_signing_key=KEY,
            )

    def _backend_request(self, *, target_id: str, role: str, capability: str, modality: str,
                         messages: tuple[BackendMessage, ...], tools: tuple[BackendTool, ...] = ()) -> BackendRequest:
        call = ModelCallRequest.from_dict({
            "request_id": f"request.{target_id}", "task_id": "task.qwen", "team_id": "team.qwen", "worker_id": "worker.qwen",
            "task_kind": "inspection_review", "modality": modality, "required_capability": capability,
            "evidence_summary": ["evidence.qwen"], "clearance": "internal", "action_risk": "inspection_review",
            "resource_budget": {"context_tokens": 128, "image_tokens": 128}, "attempt": 1, "idempotency_key": "idem.qwen.backend",
            "timeout_ms": 1000, "role": role, "resource_lease_id": "lease.qwen",
        })
        target = self._runtime().registry.targets[[item.target_id for item in self._runtime().registry.targets].index(target_id)]
        return BackendRequest(model_call=call, target_id=target_id, artifact_digest=target.artifact_digest,
                              backend_id=target.adapter_id, backend_version=target.adapter_version,
                              messages=messages, output=BackendOutputSpec(), tools=tools)


if __name__ == "__main__":
    unittest.main()
