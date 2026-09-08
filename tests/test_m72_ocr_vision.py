from __future__ import annotations

import time
import unittest
from dataclasses import replace
from hashlib import sha256

from airbench.vision import (
    LocalVisionAdapter,
    VisionError,
    VisionRequest,
    VisionResult,
    backend_text_extractor,
    static_text_extractor,
)
from contracts import BackendContent, BackendMessage, BackendRequest, CancellationToken, Clearance, EventLedger, FakeBackend, ModelCallRequest, Taint, build_event


def seed_task(ledger: EventLedger, task_id: str) -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
        clearance=Clearance.restricted, idempotency=f"created-{task_id}", sequence=0,
    ))


def request() -> VisionRequest:
    content = b"rendered page bytes"
    return VisionRequest(
        task_id="task.m72", intake_id="intake.m72", revision_id="revision.m72",
        page_id="page.m72.1", page_number=1, source_ref="upload:inspection.pdf",
        media_type="image/png", content=content, content_hash=sha256(content).hexdigest(),
        clearance=Clearance.restricted, taint=Taint.untrusted,
    )


class VisionAdapterTests(unittest.TestCase):
    def adapter(self, ledger: EventLedger | None = None, *, timeout_s: float = 1.0) -> LocalVisionAdapter:
        req = request()
        return LocalVisionAdapter(
            adapter_id="airbench.vision.qwen25vl",
            adapter_version="1.0",
            model_target_id="target.qwen25vl",
            qualification_reference="qualification.qwen25vl.m72",
            extractor=static_text_extractor(
                {req.page_id: "pump pressure 12 bar"},
                adapter_id="airbench.vision.qwen25vl", adapter_version="1.0",
                model_target_id="target.qwen25vl", qualification_reference="qualification.qwen25vl.m72",
            ),
            ledger=ledger, timeout_s=timeout_s, kind="vision",
        )

    def test_result_preserves_page_provenance_and_records_events(self) -> None:
        ledger = EventLedger()
        seed_task(ledger, "task.m72")
        result = self.adapter(ledger).extract(request())
        self.assertEqual(result.source_ref, "upload:inspection.pdf")
        self.assertEqual(result.page_id, "page.m72.1")
        self.assertEqual(result.taint, Taint.untrusted)
        self.assertEqual([event.event_type for event in ledger.events], ["task.created", "vision.requested", "vision.completed"])

    def test_clean_input_and_oversized_input_fail_before_adapter(self) -> None:
        req = request()
        with self.assertRaises(VisionError) as clean:
            replace(req, taint=Taint.clean)
        self.assertEqual(clean.exception.code, "clean_input")
        adapter = self.adapter()
        adapter._max_input_bytes = 1
        with self.assertRaises(VisionError) as large:
            adapter.extract(req)
        self.assertEqual(large.exception.code, "resource_exhausted")

    def test_timeout_is_typed_and_ledgered(self) -> None:
        ledger = EventLedger()
        seed_task(ledger, "task.m72")

        def slow(_: VisionRequest) -> VisionResult:
            time.sleep(0.05)
            raise AssertionError("should be cancelled by timeout")

        adapter = LocalVisionAdapter(
            adapter_id="airbench.ocr.local", adapter_version="1.0", model_target_id="target.ocr",
            qualification_reference="qualification.ocr.m72", extractor=slow, ledger=ledger, timeout_s=0.001, kind="ocr",
        )
        with self.assertRaises(VisionError) as caught:
            adapter.extract(request())
        self.assertEqual(caught.exception.code, "timeout")
        self.assertEqual(ledger.events[-1].event_type, "vision.failed")

    def test_cancellation_is_fail_closed(self) -> None:
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(VisionError) as caught:
            self.adapter().extract(request(), token)
        self.assertEqual(caught.exception.code, "cancelled")

    def test_m5_backend_bridge_uses_typed_multimodal_request(self) -> None:
        backend = FakeBackend(output="table row: pump | 12 bar")

        def build_request(vision_request: VisionRequest) -> BackendRequest:
            return BackendRequest(
                model_call=ModelCallRequest.from_dict({
                    "request_id": "request-m72-bridge", "task_id": vision_request.task_id,
                    "team_id": "team-m72", "worker_id": "worker-m72", "task_kind": "ocr",
                    "modality": "image", "required_capability": "vision", "evidence_summary": [vision_request.page_id],
                    "clearance": vision_request.clearance.value, "action_risk": "analysis",
                    "resource_budget": {"context_tokens": 1000}, "attempt": 1,
                    "idempotency_key": "idempotency-m72-bridge", "timeout_ms": 1000,
                    "role": "vision", "resource_lease_id": "lease-m72", "stage": "extraction",
                }),
                target_id="target-m72-vision", artifact_digest="a" * 64,
                backend_id="airbench.fake-backend", backend_version="1.0",
                messages=(BackendMessage(role="user", content=(
                    BackendContent(kind="image", media_ref=vision_request.page_id,
                                   media_type=vision_request.media_type, content_hash=vision_request.content_hash),
                )),),
            )

        extractor = backend_text_extractor(
            backend, build_request, adapter_id="airbench.vision.qwen25vl", adapter_version="1.0",
            model_target_id="target.qwen25vl", qualification_reference="qualification.qwen25vl.m72",
        )
        result = extractor(request())
        self.assertEqual(result.text, "table row: pump | 12 bar")
        self.assertEqual(result.taint, Taint.untrusted)
        self.assertEqual(result.model_target_id, "target.qwen25vl")


if __name__ == "__main__":
    unittest.main()
