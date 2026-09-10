from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from contracts import Clearance, EventLedger, Orchestrator, Taint, build_event
from airbench.delivery import DeliverableEngine, DeliverableRequest, DeterministicValue, LocalArtifactStore
from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.deliverable_gateway import LocalDeliverableGateway


TEMPLATE = """
templates:
  - id: generic_memo_v1
    version: "1.0"
    format: docx
    required_sections: [summary, deterministic_calculations]
    structural_check: required
    visual_check: false
"""


def _task_event(ledger: EventLedger, task_id: str) -> None:
    ledger.append(
        build_event(
            event_type="task.created",
            task_id=task_id,
            actor_id="fixture.operator",
            actor_type="human",
            payload_contract="TaskEnvelope",
            payload_version="1.0",
            payload={"task": {"task_id": task_id}},
            clearance=Clearance.internal,
            idempotency="fixture.task.created",
            sequence=0,
            previous_event_hash=None,
        )
    )


def _request(task_id: str) -> DeliverableRequest:
    value = DeterministicValue(
        name="total",
        value_text="42",
        unit="items",
        value_origin="deterministic_calculation",
        source_refs=("intake:report-001",),
        evidence_refs=("evidence:report-001",),
        verification_refs=("verification:report-001",),
        confidence=0.96,
        clearance=Clearance.internal,
        taint=Taint.clean,
        derivation={"operation": "count", "input_refs": ["fact:items"]},
        verified=True,
    )
    return DeliverableRequest(
        task_id=task_id,
        template_id="generic_memo_v1",
        title="Local review memo",
        prose_sections={
            "summary": "The verified total is {{total}}.",
            "deterministic_calculations": "Values in this section are inserted by the engine.",
        },
        values=(value,),
        source_refs=("intake:report-001",),
        evidence_refs=("evidence:report-001",),
        verification_refs=("verification:report-001",),
        clearance=Clearance.internal,
        taint=Taint.clean,
        confidence=0.96,
        idempotency_key="render.memo.001",
    )


@pytest.fixture()
def node_fixture(tmp_path: Path):
    task_id = "task.deliverable-001"
    ledger = EventLedger()
    _task_event(ledger, task_id)
    template_path = tmp_path / "templates.yaml"
    template_path.write_text(TEMPLATE, encoding="utf-8")
    artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    engine = DeliverableEngine(template_path=template_path, artifact_store=artifact_store, ledger=ledger)
    artifact = engine.render(_request(task_id))
    gateway = LocalDeliverableGateway(
        ledger=ledger,
        artifact_store=artifact_store,
        node_identity="node.test.local",
        protocol_version="0.1",
        clearance_context=Clearance.restricted,
    )
    service = NodeApiService(
        Orchestrator(ledger),
        NodeApiConfig(
            node_identity="node.test.local",
            protocol_version="0.1",
            clearance_context=Clearance.restricted,
            authenticated_subject="principal.api",
            domain_pack_ref="pack.refinery.v0",
            bearer_token="test-token",
            handshake_ledger_event_ref="ledger.handshake.test",
            sovereignty_evidence_ref="evidence.sovereignty.test",
            require_orchestrator_authorization=False,
        ),
        deliverable_gateway=gateway,
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(service)), base_url="http://node.test")
    try:
        yield client, artifact, ledger, task_id
    finally:
        asyncio.run(client.aclose())


def test_node_exposes_review_preview_and_integrity_checked_download(node_fixture):
    client, artifact, ledger, task_id = node_fixture
    headers = {"Authorization": "Bearer test-token"}

    async def run():
        review = await client.get(f"/api/v1/tasks/{task_id}/artifact-review", headers=headers)
        preview = await client.get(f"/api/v1/artifacts/{artifact.artifact_id}/preview", headers=headers)
        download = await client.get(f"/api/v1/artifacts/{artifact.artifact_id}/download", headers=headers)
        return review, preview, download

    review, preview, download = asyncio.run(run())
    assert review.status_code == 200, review.text
    review_body = review.json()
    assert review_body["artifactId"] == artifact.artifact_id
    assert review_body["status"] == "verified_draft"
    assert review_body["verificationStatus"] == "passed"
    assert review_body["sourceRefs"] == ["intake:report-001"]
    assert review_body["deterministicValueRefs"] == ["total"]
    assert review_body["approvalState"] == "pending"
    assert review_body["clearance"] == "internal"
    assert review_body["taint"] == "clean"

    assert preview.status_code == 200, preview.text
    assert preview.json()["preview_kind"] == "structured_document"
    assert any(block["text"] == "The verified total is 42." for block in preview.json()["blocks"])

    assert download.status_code == 200, download.text
    assert download.headers["x-airbench-artifact-hash"] == f"sha256:{artifact.content_hash}"
    assert download.content == artifact.path.read_bytes()
    assert {event.event_type for event in ledger.events} >= {"artifact.previewed", "artifact.downloaded"}


def test_node_does_not_treat_source_intake_reference_as_generated_deliverable(node_fixture):
    client, _, _, _ = node_fixture

    async def run():
        return await client.get("/api/v1/artifacts/intake-source-001/preview", headers={"Authorization": "Bearer test-token"})

    response = asyncio.run(run())
    assert response.status_code == 503
