from __future__ import annotations

from pathlib import Path
import base64
from hashlib import sha256

from airbench.intake import FileIntakeLayer, LocalIntakeStore
from airbench.intake.pid.records import PIDRecord, PidComponent, PidRelation
from airbench.knowledge.world_model import WorldModelStore
from airbench.node.api import NodeApiConfig, NodeApiService
from airbench.node.intake_gateway import LocalNodeIntakeGateway
from contracts import Clearance, EventLedger, Orchestrator, Taint


class _PidAdapter:
    def process(self, **kwargs):
        return PIDRecord(
            task_id=kwargs["task_id"], intake_id=kwargs["intake_id"], revision_id=kwargs["revision_id"],
            source_ref=kwargs["source_ref"], content_hash=kwargs["content_hash"], media_type=kwargs["media_type"],
            clearance=kwargs["clearance"], taint=kwargs["taint"],
            components=(
                PidComponent("pump-1", "pump", "P-101", (1, 2, 3, 4), 0.95),
                PidComponent("exchanger-1", "exchanger", "E-201", (5, 6, 7, 8), 0.9),
            ),
            relations=(PidRelation("line-1", "pump-1", "exchanger-1", "downstream", 0.88),),
        )


def test_pid_upload_uses_intake_and_commits_gated_world_model_candidates(tmp_path: Path) -> None:
    ledger = EventLedger()
    orchestrator = Orchestrator(ledger)
    task = orchestrator.create_task(
        principal_id="principal.pid", clearance=Clearance.internal, request="Digitize P&ID",
        domain_pack_ref="pack.refinery.v0", risk_class="low", autonomy_ceiling="review_required",
        verification_criteria=("source_check",), task_id="task.pid.integration",
    )
    intake = LocalIntakeStore(tmp_path / "intake")
    gateway = LocalNodeIntakeGateway(
        layer=FileIntakeLayer(ledger, store=intake), store=intake, ledger=ledger,
        clearance_context=Clearance.internal,
    )
    world = WorldModelStore(ledger=ledger)
    service = NodeApiService(
        orchestrator,
        NodeApiConfig(
            node_identity="node.pid.integration", protocol_version="0.1", clearance_context=Clearance.internal,
            authenticated_subject="principal.pid", domain_pack_ref="pack.refinery.v0", bearer_token="token",
            handshake_ledger_event_ref="ledger.handshake", sovereignty_evidence_ref="evidence.sovereignty",
            require_orchestrator_authorization=False,
        ),
        intake_gateway=gateway, pid_adapter=_PidAdapter(), pid_workspace=tmp_path / "pid", world_model=world,
    )

    valid_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    result = service.pid_extract(
        "principal.pid", task_id=task.task_id, file_name="unit4-pid.png",
        content=valid_png,
    )

    assert result["graph"]["status"] == "committed"
    assert result["graph"]["committed"] == 2
    assert len(world.facts) == 2
    assert len(world.relations) == 1
    pid_event = next(event for event in ledger.events if event.event_type == "pid.extracted")
    assert pid_event.payload["content_hash"] == sha256(valid_png).hexdigest()
    assert any(event.event_type == "evidence.created" for event in ledger.events)
    assert any(event.event_type == "fact.committed" for event in ledger.events)
    assert all(fact.taint == Taint.untrusted for fact in world.facts)
