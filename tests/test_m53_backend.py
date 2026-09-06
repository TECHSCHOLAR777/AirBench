"""M5.3 provider-neutral backend contract and fake adapter tests."""

from __future__ import annotations

import unittest

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
    FakeBackend,
    ModelCallRequest,
    build_event,
)
from contracts.errors import ContractValidationError


ARTIFACT = "a" * 64


def model_call(*, modality: str = "text", timeout_ms: int = 1000) -> ModelCallRequest:
    return ModelCallRequest.from_dict({
        "request_id": "request-m53-1",
        "task_id": "task-m53-1",
        "team_id": "team-m53-1",
        "worker_id": "worker-m53-1",
        "task_kind": "inspection_review",
        "modality": modality,
        "required_capability": "reasoning",
        "evidence_summary": ["evidence-m53-1"],
        "clearance": "internal",
        "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 1000},
        "attempt": 1,
        "idempotency_key": "idempotency-m53-1",
        "timeout_ms": timeout_ms,
        "role": "reasoning",
        "resource_lease_id": "lease-m53-1",
    })


def request(*, output: BackendOutputSpec | None = None, tools: tuple[BackendTool, ...] = (),
            image: bool = False, stream: bool = False) -> BackendRequest:
    content = [BackendContent(kind="text", text="Summarize the inspected evidence.")]
    if image:
        content.append(BackendContent(
            kind="image", media_ref="evidence://image-1", media_type="image/png", content_hash="b" * 64,
        ))
    return BackendRequest(
        model_call=model_call(modality="image" if image else "text"),
        target_id="target-m53-fake",
        artifact_digest=ARTIFACT,
        backend_id="airbench.fake-backend",
        backend_version="1.0",
        messages=(BackendMessage(role="user", content=tuple(content)),),
        output=output or BackendOutputSpec(),
        tools=tools,
        stream=stream,
    )


def ledger_with_task() -> EventLedger:
    ledger = EventLedger()
    ledger.append(build_event(
        event_type="task.created", task_id="task-m53-1", actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={}, clearance="internal",
        idempotency="task-created-m53", sequence=0,
    ))
    return ledger


class M53BackendTests(unittest.TestCase):
    def test_request_round_trip_preserves_nested_typed_contracts(self) -> None:
        original = request(
            output=BackendOutputSpec(mode="json_schema", schema={"type": "object"}),
            tools=(BackendTool("calculator", "Perform a calculation", {"type": "object"}),),
            image=True,
        )
        restored = BackendRequest.from_dict(original.to_dict())
        self.assertIsInstance(restored.model_call, ModelCallRequest)
        self.assertIsInstance(restored.messages[0], BackendMessage)
        self.assertIsInstance(restored.messages[0].content[1], BackendContent)
        self.assertEqual(restored.output.mode, "json_schema")
        self.assertEqual(restored.tools[0].name, "calculator")

    def test_fake_backend_returns_provenance_usage_and_ledger_events(self) -> None:
        ledger = ledger_with_task()
        response = FakeBackend(ledger=ledger).complete(request())
        self.assertEqual(response.status.value, "verified")
        self.assertEqual(response.provenance.target_id, "target-m53-fake")
        self.assertEqual(response.provenance.taint.value, "untrusted")
        self.assertEqual(response.usage.total_tokens, response.usage.input_tokens + response.usage.output_tokens)
        self.assertEqual(
            [event.event_type for event in ledger.events],
            ["task.created", "model.call.started", "model.call.completed"],
        )
        self.assertNotIn("Summarize", ledger.events[-1].payload)
        self.assertIn("request_hash", ledger.events[-1].payload)

    def test_fake_backend_supports_structured_multimodal_and_tool_contracts(self) -> None:
        tool = BackendTool("calculator", "Perform a calculation", {"type": "object"})
        backend = FakeBackend(tool_call=BackendToolCall("calculator", {"expression": "2+2"}))
        response = backend.complete(request(
            output=BackendOutputSpec(mode="json_schema", schema={"type": "object"}),
            tools=(tool,), image=True,
        ))
        self.assertEqual(response.output, None)
        self.assertEqual(response.tool_calls[0].name, "calculator")
        self.assertEqual(response.tool_calls[0].arguments["expression"], "2+2")

    def test_unsupported_capability_is_explicit_and_non_retryable(self) -> None:
        backend = FakeBackend(capabilities=BackendCapabilities(modalities=("text",), streaming=False))
        with self.assertRaises(BackendCallError) as raised:
            backend.complete(request(image=True))
        self.assertEqual(raised.exception.failure.code, BackendErrorCode.unsupported_capability)
        self.assertFalse(raised.exception.failure.retryable)

    def test_resource_limit_is_explicit_and_retryable(self) -> None:
        backend = FakeBackend(max_context_tokens=10)
        with self.assertRaises(BackendCallError) as raised:
            backend.complete(request())
        self.assertEqual(raised.exception.failure.code, BackendErrorCode.resource_exhausted)
        self.assertTrue(raised.exception.failure.retryable)

    def test_unhealthy_and_not_ready_states_are_distinct_retryable_failures(self) -> None:
        backend = FakeBackend()
        backend.set_state(health=BackendHealth.unhealthy)
        with self.assertRaises(BackendCallError) as raised:
            backend.complete(request())
        self.assertEqual(raised.exception.failure.code, BackendErrorCode.unavailable)
        self.assertTrue(raised.exception.failure.retryable)

        backend.set_state(health=BackendHealth.healthy, readiness=BackendReadiness.not_ready)
        with self.assertRaises(BackendCallError) as raised:
            backend.complete(request())
        self.assertEqual(raised.exception.failure.code, BackendErrorCode.not_ready)

    def test_streaming_and_cancellation_are_explicit(self) -> None:
        ledger = ledger_with_task()
        backend = FakeBackend(ledger=ledger, output="one two three")
        chunks = list(backend.stream(request(stream=True)))
        self.assertEqual("".join(chunk.text for chunk in chunks), "one two three")
        self.assertTrue(chunks[-1].final)
        self.assertEqual(
            [event.event_type for event in ledger.events],
            ["task.created", "model.call.started", "model.call.completed"],
        )

        token = CancellationToken()
        token.cancel()
        with self.assertRaises(BackendCallError) as raised:
            list(backend.stream(request(stream=True), token))
        self.assertEqual(raised.exception.failure.code, BackendErrorCode.cancelled)

    def test_timeout_is_typed_retryable_and_recorded(self) -> None:
        ledger = ledger_with_task()
        backend = FakeBackend(ledger=ledger, delay_ms=1001)
        with self.assertRaises(BackendCallError) as raised:
            backend.complete(request())
        self.assertEqual(raised.exception.failure.code, BackendErrorCode.timeout)
        self.assertTrue(raised.exception.failure.retryable)
        self.assertEqual(ledger.events[-1].event_type, "model.call.failed")

    def test_invalid_media_provenance_is_rejected_before_execution(self) -> None:
        with self.assertRaises(ContractValidationError):
            BackendContent.from_dict({"kind": "image", "media_ref": "evidence://image-1", "media_type": "image/png"})


if __name__ == "__main__":
    unittest.main()
