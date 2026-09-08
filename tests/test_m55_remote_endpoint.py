"""M5 remote endpoint profile, security, and adapter tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from contracts import (
    BackendContent, BackendErrorCode, BackendMessage, BackendOutputSpec, BackendTool,
    BackendRequest, CancellationToken, Clearance, ContractValidationError,
    EventLedger, ModelCallRequest, ModelTarget, RemoteEndpointAdapter, build_event,
    RemoteEndpointProfile, ModelRegistry, ModelRouter, ContractStatus,
)


KEY = b"remote-endpoint-test-key"


def make_target() -> ModelTarget:
    return ModelTarget.from_dict({
        "target_id": "target.remote",
        "repository": "approved/remote",
        "artifact_digest": "a" * 64,
        "artifact_path": "remote.manifest",
        "quantization": "int4",
        "tokenizer_digest": "b" * 64,
        "chat_template_digest": "c" * 64,
        "runtime_version": "runtime-1",
        "backend": "custom",
        "capabilities": ["reasoning"],
        "roles": ["reasoning"],
        "modalities": ["text"],
        "risk_classes": ["inspection_review"],
        "allowed_clearances": ["internal"],
        "pack_refs": ["pack.remote"],
        "hardware_profile_refs": ["hw.remote"],
        "context_limit": 4096,
        "image_token_limit": 0,
        "tool_call_parser": "none",
        "structured_output_modes": ["json_object"],
        "license_id": "license.remote",
        "local_storage_hash": "d" * 64,
        "qualification_certificate": "cert.remote",
        "qualification_expires_at": "2099-01-01T00:00:00Z",
        "qualification_signature": "0" * 64,
        "role_qualifications": [["reasoning", "cert.remote"]],
        "adapter_id": "airbench.remote-endpoint",
        "adapter_version": "0.1",
        "streaming": True,
        "cancellation": True,
    })


def sign_target(target: ModelTarget) -> ModelTarget:
    unsigned = target.qualification_payload()
    signature = hmac.new(KEY, json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
    return replace(target, qualification_signature=signature)


def make_profile(target: ModelTarget, *, disabled: bool = False, max_retries: int = 1) -> RemoteEndpointProfile:
    return RemoteEndpointProfile.from_dict({
        "endpoint_id": "endpoint.remote.test",
        "endpoint_url": "https://gpu.example.test",
        "provider_type": "trusted-provider",
        "backend_type": "openai_compatible",
        "model_target_id": target.target_id,
        "artifact_digest": target.artifact_digest,
        "tokenizer_digest": target.tokenizer_digest,
        "chat_template_digest": target.chat_template_digest,
        "runtime_version": target.runtime_version,
        "adapter_id": "airbench.remote-endpoint",
        "adapter_version": "0.1",
        "capabilities": ["reasoning", "text", "json_object", "json_schema", "tool_calling", "streaming", "cancellation"],
        "roles": ["reasoning"],
        "modalities": ["text"],
        "risk_classes": ["inspection_review"],
        "allowed_clearances": ["internal"],
        "license_id": target.license_id,
        "qualification_reference": "qualification.remote.test",
        "qualification_expires_at": "2099-01-01T00:00:00Z",
        "qualification_signature": "0" * 64,
        "execution_location": "remote",
        "remote_execution_policy": "approved_remote_endpoint",
        "data_egress_policy": "approved_remote_endpoint",
        "allowed_hosts": ["gpu.example.test"],
        "credential_env": "AIRBENCH_REMOTE_TOKEN",
        "timeout_ms": 1000,
        "max_retries": max_retries,
        "streaming": True,
        "cancellation": True,
        "retry_only_idempotent": True,
        "disabled": disabled,
    })


def sign_profile(profile: RemoteEndpointProfile) -> RemoteEndpointProfile:
    signature = hmac.new(KEY, json.dumps(profile.qualification_payload(), sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
    return replace(profile, qualification_signature=signature)


def make_call(*, idempotency_key: str = "idempotent.remote.test") -> ModelCallRequest:
    return ModelCallRequest.from_dict({
        "request_id": "request.remote.test",
        "task_id": "task.remote.test",
        "team_id": "team.remote.test",
        "worker_id": "worker.remote.test",
        "task_kind": "inspection_review",
        "modality": "text",
        "required_capability": "reasoning",
        "evidence_summary": ["evidence.remote.test"],
        "clearance": "internal",
        "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 100},
        "attempt": 1,
        "idempotency_key": idempotency_key,
        "timeout_ms": 1000,
        "role": "reasoning",
        "resource_lease_id": "lease.remote.test",
    })


def make_request(call: ModelCallRequest | None = None, *, tools=()) -> BackendRequest:
    return BackendRequest(
        model_call=call or make_call(), target_id="target.remote", artifact_digest="a" * 64,
        backend_id="remote-provider", backend_version="runtime-1",
        messages=(BackendMessage("user", (BackendContent(kind="text", text="hello"),)),),
        output=BackendOutputSpec(), tools=tuple(tools),
    )


class Response:
    def __init__(self, body: bytes):
        self.body = body
        self.fp = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return self.body


def healthy_responses():
    return [
        Response(b"{}"),
        Response(b'{"data":[{"id":"target.remote"}]}'),
        Response(b'{"choices":[{"message":{"content":"remote answer"},"finish_reason":"stop"}],"usage":{"prompt_tokens":2,"completion_tokens":2}}'),
    ]


class RemoteEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = sign_target(make_target())
        self.profile = sign_profile(make_profile(self.target))
        self.call = make_call()
        self.request = make_request(self.call)

    def adapter(self, *, profile=None, ledger=None):
        return RemoteEndpointAdapter(
            profile or self.profile, self.target, endpoint_signing_key=KEY,
            target_signing_key=KEY, ledger=ledger,
        )

    def ledger(self) -> EventLedger:
        ledger = EventLedger()
        ledger.append(build_event(
            event_type="task.created", task_id=self.call.task_id, actor_id="test",
            actor_type="test", payload_contract="TaskEnvelope", payload_version="1.0",
            payload={}, clearance=Clearance.internal, idempotency="remote-task-created",
            sequence=0, previous_event_hash=None,
        ))
        return ledger

    def test_valid_profile_is_signed_fresh_and_target_bound(self) -> None:
        self.profile.validate_target(self.target, self.call)
        self.assertTrue(self.profile.verify_signature(KEY))
        self.assertTrue(self.profile.is_fresh())

    def test_http_profile_is_rejected_before_adapter_creation(self) -> None:
        with self.assertRaises(ContractValidationError):
            make_profile(self.target).from_dict({**make_profile(self.target).to_dict(), "endpoint_url": "http://gpu.example.test"})

    def test_disabled_placeholder_profile_can_be_loaded_but_adapter_rejects_it(self) -> None:
        profile = make_profile(self.target, disabled=True)
        adapter = self.adapter(profile=profile)
        with patch.dict(os.environ, {"AIRBENCH_REMOTE_TOKEN": "secret"}):
            with self.assertRaises(Exception) as raised:
                adapter.complete(self.request)
        self.assertIn("unsigned_target", str(raised.exception))

    def test_missing_credential_is_rejected_without_network(self) -> None:
        adapter = self.adapter()
        with patch.dict(os.environ, {}, clear=True), patch("contracts.adapters.remote_adapter.urlopen") as call:
            with self.assertRaises(Exception) as raised:
                adapter.complete(self.request)
        self.assertEqual(raised.exception.failure.code, BackendErrorCode.authentication_failed)
        call.assert_not_called()

    def test_remote_call_normalizes_response_and_preserves_provenance(self) -> None:
        adapter = self.adapter()
        with patch.dict(os.environ, {"AIRBENCH_REMOTE_TOKEN": "secret"}), patch(
            "contracts.adapters.remote_adapter.urlopen", side_effect=healthy_responses()
        ) as call:
            response = adapter.complete(self.request)
        self.assertEqual(response.output, "remote answer")
        self.assertEqual(response.provenance.endpoint_id, "endpoint.remote.test")
        self.assertEqual(response.provenance.execution_location, "remote")
        self.assertEqual(response.provenance.qualification_reference, "qualification.remote.test")
        sent_headers = call.call_args_list[-1].args[0].headers
        self.assertEqual(sent_headers["Authorization"], "Bearer secret")

    def test_endpoint_events_do_not_contain_credentials(self) -> None:
        ledger = self.ledger()
        adapter = self.adapter(ledger=ledger)
        with patch.dict(os.environ, {"AIRBENCH_REMOTE_TOKEN": "do-not-log"}), patch(
            "contracts.adapters.remote_adapter.urlopen", side_effect=healthy_responses()
        ):
            adapter.complete(self.request)
        serialized = json.dumps([event.to_dict() for event in ledger.events], sort_keys=True)
        self.assertNotIn("do-not-log", serialized)
        self.assertIn("endpoint.selected", [event.event_type for event in ledger.events])
        self.assertIn("endpoint.request.completed", [event.event_type for event in ledger.events])

    def test_authentication_failure_is_explicit_and_not_retried(self) -> None:
        adapter = self.adapter()
        auth_error = HTTPError("https://gpu.example.test/v1/chat/completions", 401, "unauthorized", {}, None)
        with patch.dict(os.environ, {"AIRBENCH_REMOTE_TOKEN": "secret"}), patch(
            "contracts.adapters.remote_adapter.urlopen",
            side_effect=[Response(b"{}"), Response(b'{"data":[{"id":"target.remote"}]}'), auth_error],
        ) as call:
            with self.assertRaises(Exception) as raised:
                adapter.complete(self.request)
        self.assertEqual(raised.exception.failure.code, BackendErrorCode.authentication_failed)
        self.assertEqual(call.call_count, 3)

    def test_retry_is_bounded_and_requires_idempotency_key(self) -> None:
        adapter = self.adapter()
        responses = [
            Response(b"{}"), Response(b'{"data":[{"id":"target.remote"}]}'), URLError("timed out"),
            Response(b"{}"), Response(b'{"data":[{"id":"target.remote"}]}'),
            Response(b'{"choices":[{"message":{"content":"retried"},"finish_reason":"stop"}]}'),
        ]
        with patch.dict(os.environ, {"AIRBENCH_REMOTE_TOKEN": "secret"}), patch(
            "contracts.adapters.remote_adapter.urlopen", side_effect=responses
        ) as call:
            result = adapter.complete(self.request)
        self.assertEqual(result.output, "retried")
        self.assertEqual(call.call_count, 6)

        non_idempotent = make_request(make_call(idempotency_key=""))
        with patch.dict(os.environ, {"AIRBENCH_REMOTE_TOKEN": "secret"}), patch(
            "contracts.adapters.remote_adapter.urlopen", side_effect=[Response(b"{}"), Response(b'{"data":[{"id":"target.remote"}]}'), URLError("timed out")],
        ) as call:
            with self.assertRaises(Exception):
                adapter.complete(non_idempotent)
        self.assertEqual(call.call_count, 3)

    def test_unsupported_tool_calling_is_rejected_before_post(self) -> None:
        profile = sign_profile(replace(self.profile, capabilities=("text",)))
        adapter = self.adapter(profile=profile)
        tool = BackendTool("lookup", "look up a value", {"type": "object"})
        request = make_request(tools=(tool,))
        with patch.dict(os.environ, {"AIRBENCH_REMOTE_TOKEN": "secret"}), patch(
            "contracts.adapters.remote_adapter.urlopen", side_effect=healthy_responses()
        ) as call:
            with self.assertRaises(Exception) as raised:
                adapter.complete(request)
        self.assertEqual(raised.exception.failure.code, BackendErrorCode.unsupported_capability)
        self.assertEqual(call.call_count, 0)

    def test_cancelled_call_does_not_contact_endpoint(self) -> None:
        token = CancellationToken()
        token.cancel()
        adapter = self.adapter()
        with patch.dict(os.environ, {"AIRBENCH_REMOTE_TOKEN": "secret"}), patch("contracts.adapters.remote_adapter.urlopen") as call:
            with self.assertRaises(Exception) as raised:
                adapter.complete(self.request, token)
        self.assertEqual(raised.exception.failure.code, BackendErrorCode.cancelled)
        call.assert_not_called()

    def test_router_selects_remote_adapter_only_after_endpoint_preflight(self) -> None:
        adapter = self.adapter()
        registry = ModelRegistry(
            "registry.remote.test", "1.0", (self.target,), "e" * 64, "2099-01-01T00:00:00Z",
        )
        router = ModelRouter(
            registry, {adapter.adapter_id: adapter}, policy_version_hash="policy.remote.test",
            resource_admission=lambda _target, _request: "admitted",
        )
        with patch.dict(os.environ, {"AIRBENCH_REMOTE_TOKEN": "secret"}), patch(
            "contracts.adapters.remote_adapter.urlopen", side_effect=healthy_responses()
        ):
            result = router.route(self.call, pack_ref="pack.remote", hardware_profile_ref="hw.remote")
        self.assertEqual(result.decision.status, ContractStatus.accepted)
        self.assertEqual(result.decision.selected_target, self.target.target_id)

    def test_router_rejects_bad_endpoint_signature_without_contacting_endpoint(self) -> None:
        adapter = RemoteEndpointAdapter(
            self.profile, self.target, endpoint_signing_key=b"wrong-key", target_signing_key=KEY,
        )
        registry = ModelRegistry(
            "registry.remote.bad", "1.0", (self.target,), "e" * 64, "2099-01-01T00:00:00Z",
        )
        router = ModelRouter(
            registry, {adapter.adapter_id: adapter}, policy_version_hash="policy.remote.bad",
            resource_admission=lambda _target, _request: "admitted",
        )
        with patch.dict(os.environ, {"AIRBENCH_REMOTE_TOKEN": "secret"}), patch("contracts.adapters.remote_adapter.urlopen") as call:
            result = router.route(self.call, pack_ref="pack.remote", hardware_profile_ref="hw.remote")
        self.assertEqual(result.decision.status, ContractStatus.rejected)
        self.assertIsNone(result.target)
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
