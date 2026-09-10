import asyncio
import tempfile
import unittest

import httpx

from airbench.intake import FileIntakeLayer, LocalIntakeStore
from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.intake_gateway import LocalNodeIntakeGateway
from contracts import Clearance, EventLedger, Orchestrator


class NodeIntakeApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.ledger = EventLedger()
        self.orchestrator = Orchestrator(self.ledger)
        store = LocalIntakeStore(self.directory.name)
        layer = FileIntakeLayer(self.ledger, store=store)
        gateway = LocalNodeIntakeGateway(
            layer=layer,
            store=store,
            ledger=self.ledger,
            clearance_context=Clearance.restricted,
        )
        self.service = NodeApiService(
            self.orchestrator,
            NodeApiConfig(
                node_identity="node.intake.test",
                protocol_version="0.1",
                clearance_context=Clearance.restricted,
                authenticated_subject="principal.api",
                domain_pack_ref="pack.refinery.v0",
                bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.test",
                sovereignty_evidence_ref="evidence.sovereignty.test",
                require_orchestrator_authorization=False,
            ),
            intake_gateway=gateway,
        )
        self.task = self.orchestrator.create_task(
            principal_id="principal.api",
            clearance=Clearance.restricted,
            request="Review the uploaded source",
            domain_pack_ref="pack.refinery.v0",
            risk_class="low",
            autonomy_ceiling="review_required",
            verification_criteria=("source_hash",),
            task_id="task.intake.test",
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.service)),
            base_url="http://node.intake.test",
        )

    def tearDown(self):
        asyncio.run(self.client.aclose())
        self.directory.cleanup()

    def request(self, method, path, **kwargs):
        async def run():
            return await self.client.request(method, path, **kwargs)

        return asyncio.run(run())

    def headers(self):
        return {"Authorization": "Bearer test-token"}

    def test_query_upload_preview_and_download_use_real_intake_store(self):
        content = b"Inspection finding remains untrusted source data."
        upload = self.request(
            "POST",
            "/api/v1/intake/query-upload",
            headers=self.headers(),
            data={"intake_mode": "query_upload", "task_id": self.task.task_id, "source_file_size": str(len(content))},
            files={"document": ("inspection-report.txt", content, "text/plain")},
        )

        self.assertEqual(upload.status_code, 200, upload.text)
        manifest = upload.json()
        expected_hash = "sha256:" + __import__("hashlib").sha256(content).hexdigest()
        self.assertEqual(manifest["source_hash"], expected_hash)
        self.assertEqual(manifest["taint"], "untrusted")
        self.assertEqual(manifest["ocr_status"], "not_applicable")
        self.assertEqual(manifest["vision_status"], "not_applicable")
        self.assertEqual(manifest["preview_ref"], manifest["intake_id"])
        self.assertEqual(manifest["artifact_ref"], manifest["intake_id"])

        retry_upload = self.request(
            "POST",
            "/api/v1/intake/query-upload",
            headers=self.headers(),
            data={"intake_mode": "query_upload", "task_id": self.task.task_id, "source_file_size": str(len(content))},
            files={"document": ("inspection-report.txt", content, "text/plain")},
        )
        self.assertEqual(retry_upload.status_code, 200, retry_upload.text)
        self.assertEqual(retry_upload.json()["intake_id"], manifest["intake_id"])

        snapshot = self.request(
            "GET",
            f"/api/v1/tasks/{self.task.task_id}",
            headers=self.headers(),
        )
        self.assertEqual(snapshot.status_code, 200, snapshot.text)
        self.assertEqual(snapshot.json()["inputManifestRef"], manifest["intake_id"])

        preview = self.request(
            "GET",
            f"/api/v1/intake/{manifest['preview_ref']}/preview",
            headers=self.headers(),
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["source_hash"], expected_hash)
        self.assertEqual(preview.json()["text"], content.decode())
        first_preview_ledger_ref = preview.json()["ledger_event_ref"]
        self.assertTrue(first_preview_ledger_ref)

        retry = self.request(
            "GET",
            f"/api/v1/intake/{manifest['preview_ref']}/preview",
            headers=self.headers(),
        )
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["ledger_event_ref"], first_preview_ledger_ref)

        artifact_preview = self.request(
            "GET",
            f"/api/v1/artifacts/{manifest['artifact_ref']}/preview",
            headers=self.headers(),
        )
        self.assertEqual(artifact_preview.status_code, 200, artifact_preview.text)
        self.assertEqual(artifact_preview.json()["artifact_id"], manifest["artifact_ref"])
        self.assertEqual(artifact_preview.json()["taint"], "untrusted")
        self.assertEqual(artifact_preview.json()["blocks"][0]["text"], content.decode())

        download = self.request(
            "GET",
            f"/api/v1/artifacts/{manifest['artifact_ref']}/download",
            headers=self.headers(),
        )
        self.assertEqual(download.status_code, 200, download.text)
        self.assertEqual(download.content, content)
        self.assertEqual(download.headers["x-airbench-artifact-hash"], expected_hash)
        self.assertTrue(download.headers["x-airbench-ledger-event-ref"])
        self.assertEqual(self.orchestrator.state(self.task.task_id), "created")
        self.assertEqual(len(self.ledger.events), 5)
        self.assertEqual([event.event_type for event in self.ledger.events], [
            "task.created", "evidence.created", "artifact.previewed", "artifact.previewed", "artifact.downloaded",
        ])

    def test_scan_without_qualified_ocr_does_not_claim_ready_processing(self):
        # A structurally valid image is accepted as untrusted data, but the
        # built-in parser intentionally does not claim OCR or vision output.
        from io import BytesIO
        from PIL import Image

        image = BytesIO()
        Image.new("RGB", (12, 12), color=(20, 40, 60)).save(image, format="PNG")
        content = image.getvalue()
        upload = self.request(
            "POST",
            "/api/v1/intake/query-upload",
            headers=self.headers(),
            data={"intake_mode": "query_upload", "task_id": self.task.task_id, "source_file_size": str(len(content))},
            files={"document": ("scanned-page.png", content, "image/png")},
        )

        self.assertEqual(upload.status_code, 200, upload.text)
        manifest = upload.json()
        self.assertEqual(manifest["ocr_status"], "unavailable")
        self.assertEqual(manifest["vision_status"], "unavailable")
        preview = self.request(
            "GET",
            f"/api/v1/intake/{manifest['preview_ref']}/preview",
            headers=self.headers(),
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["preview_kind"], "image")
        self.assertEqual(preview.json()["confidence"], 0.0)
        self.assertEqual(preview.json()["taint"], "untrusted")

    def test_multipart_contract_and_missing_intake_fail_closed(self):
        missing_mode = self.request(
            "POST",
            "/api/v1/intake/query-upload",
            headers={**self.headers(), "Content-Type": "application/octet-stream"},
            content=b"untrusted bytes",
        )
        self.assertEqual(missing_mode.status_code, 400)
        self.assertEqual(missing_mode.json()["code"], "multipart_required")

        missing = self.request(
            "GET",
            "/api/v1/intake/00000000-0000-0000-0000-000000000000/preview",
            headers=self.headers(),
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["code"], "intake_not_found")

        unsupported = self.request(
            "POST",
            "/api/v1/intake/query-upload",
            headers=self.headers(),
            data={"intake_mode": "query_upload", "task_id": self.task.task_id},
            files={"document": ("payload.exe", b"MZ untrusted data", "application/octet-stream")},
        )
        self.assertEqual(unsupported.status_code, 415, unsupported.text)
        self.assertEqual(unsupported.json()["code"], "intake_unsupported_media")


if __name__ == "__main__":
    unittest.main()
