"""M10.4 — Clean-node acceptance suite.

Proves that the AirBench backend is deployable, restartable, observable, and
sovereign on a clean local node.  Uses the M9 vertical slice machinery with
deterministic fixtures — no real model calls, no network egress.

Acceptance criteria (from GitHub issue M10):
  A. Backend installs and starts offline from verified assets.
  B. All M10.1 authenticated endpoints respond correctly.
  C. The refinery vertical slice completes in serial mode.
  D. The ledger can be replayed from JSONL and the chain verifies.
  E. No-egress evidence is present in the replayed ledger.
  F. Audit view script produces a passing report.
  G. All criteria pass → emit ``acceptance.run.completed`` log entry.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

import httpx

from contracts import (
    Clearance,
    EventLedger,
    Orchestrator,
    RecoveryManager,
    SQLiteLedgerStore,
    build_event,
    idempotency_key,
)
from contracts.models import NODE_PROTOCOL_VERSION
from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.server import NodeServerConfig, build_node_app, run_startup_checks
from airbench.node.bundle import AssetRecord, BundleManifest, StartupVerifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


def _make_client(
    token: str = "acceptance-token",
    clearance: Clearance = Clearance.restricted,
) -> tuple[NodeApiService, httpx.AsyncClient]:
    ledger = EventLedger()
    orch = Orchestrator(ledger)
    cfg = NodeApiConfig(
        node_identity="node.m10.acceptance",
        protocol_version=NODE_PROTOCOL_VERSION,
        clearance_context=clearance,
        authenticated_subject="principal.acceptance",
        domain_pack_ref="pack.refinery.v0",
        bearer_token=token,
        handshake_ledger_event_ref="ledger.acceptance",
        sovereignty_evidence_ref="evidence.acceptance",
        require_orchestrator_authorization=False,
    )
    svc = NodeApiService(orch, cfg)
    app = create_app(svc)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://node.acceptance")
    return svc, client


def _auth(token: str = "acceptance-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _task_body(suffix: str = "a1", clearance: str = "internal") -> dict[str, Any]:
    return {
        "command_id": f"cmd.acceptance.{suffix}",
        "task_id": None,
        "actor": "principal.acceptance",
        "expected_sequence": None,
        "idempotency_key": f"idem.acceptance.{suffix}",
        "client_version": "0.1",
        "command_type": "task.create",
        "arguments": {
            "principal_id": "principal.acceptance",
            "clearance": clearance,
            "request": f"M10 acceptance test task {suffix}",
            "domain_pack_ref": "pack.refinery.v0",
            "risk_class": "high",
            "autonomy_ceiling": "review_required",
            "allowed_evidence_scope": ["inspection-report"],
            "permitted_worker_capabilities": ["reasoning"],
            "permitted_tools": ["calculator"],
            "output_contract": "approval-note",
            "verification_criteria": ["source_check"],
            "resource_budget": {"max_concurrency": 1, "max_steps": 8},
        },
    }


# ---------------------------------------------------------------------------
# Acceptance criterion A: Startup checks pass on a clean in-memory node
# ---------------------------------------------------------------------------

class TestAcceptanceCriterionA(unittest.TestCase):
    """A. Backend starts offline from verified configuration."""

    def test_startup_checks_pass_on_valid_config(self) -> None:
        cfg = NodeServerConfig(
            node_identity="node.acceptance.a",
            bearer_token="acceptance-token",
            domain_pack_ref="pack.refinery.v0",
            clearance=Clearance.restricted,
            subject="principal.acceptance",
        )
        result = run_startup_checks(cfg)
        self.assertTrue(result.passed, f"Startup checks failed: {result.as_dict()}")

    def test_build_node_app_succeeds_in_memory(self) -> None:
        cfg = NodeServerConfig(
            node_identity="node.acceptance.a2",
            bearer_token="acceptance-token-a2",
            domain_pack_ref="pack.refinery.v0",
            clearance=Clearance.restricted,
            subject="principal.acceptance",
        )
        app = build_node_app(cfg, skip_startup_check=True)
        self.assertIsNotNone(app)

    def test_bundle_verification_passes_for_real_source_file(self) -> None:
        """Verify that at least one real AirBench source file can be bundled and verified."""
        source_file = Path(__file__).parent.parent / "src" / "airbench" / "node" / "bundle.py"
        self.assertTrue(source_file.exists(), f"Source file not found: {source_file}")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            import shutil
            shutil.copy(source_file, root / "bundle.py")

            manifest = BundleManifest.build(
                "airbench.acceptance.v0",
                "0.1.0",
                [("src.airbench.node.bundle", "file", root / "bundle.py")],
                bundle_root=root,
            )
            key = b"acceptance-signing-key-000000000"
            signed = manifest.sign(key)

            verifier = StartupVerifier(signed, bundle_root=root, signing_key=key)
            result = verifier.verify()
            self.assertTrue(result.passed, f"Bundle verification failed: {result.to_dict()}")
            self.assertTrue(result.signature_valid)


# ---------------------------------------------------------------------------
# Acceptance criterion B: All authenticated endpoints respond correctly
# ---------------------------------------------------------------------------

class TestAcceptanceCriterionB(unittest.TestCase):
    """B. All M10.1 authenticated endpoints respond correctly."""

    def setUp(self) -> None:
        self.svc, self.client = _make_client()

    def tearDown(self) -> None:
        _run(self.client.aclose())

    def _get(self, path: str, **kw) -> httpx.Response:
        return _run(self.client.get(path, **kw))

    def _post(self, path: str, **kw) -> httpx.Response:
        return _run(self.client.post(path, **kw))

    def test_b1_handshake_authenticated(self) -> None:
        resp = self._get("/api/v1/node/handshake", headers=_auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # Handshake uses snake_case keys
        self.assertEqual(body["node_identity"], "node.m10.acceptance")
        self.assertEqual(body["protocol_version"], NODE_PROTOCOL_VERSION)

    def test_b2_health_returns_ready(self) -> None:
        resp = self._get("/api/v1/health", headers=_auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ready")

    def test_b3_unauthenticated_returns_401(self) -> None:
        resp = self._get("/api/v1/health")
        self.assertEqual(resp.status_code, 401)

    def test_b4_wrong_token_returns_401(self) -> None:
        resp = self._get("/api/v1/health", headers=_auth("wrong-token"))
        self.assertEqual(resp.status_code, 401)

    def test_b5_task_create_returns_201(self) -> None:
        resp = self._post("/api/v1/tasks", headers=_auth(), json=_task_body("b5"))
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("task", body)
        self.assertIn("task_id", body["task"])

    def test_b6_unknown_task_returns_404(self) -> None:
        resp = self._get("/api/v1/tasks/task.does-not-exist", headers=_auth())
        self.assertEqual(resp.status_code, 404)

    def test_b7_clearance_exceeded_returns_403(self) -> None:
        svc, client = _make_client(clearance=Clearance.public)
        body = _task_body("b7", clearance="restricted")
        resp = _run(client.post("/api/v1/tasks", headers=_auth(), json=body))
        _run(client.aclose())
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Acceptance criterion C: Task lifecycle over Node API (serial mode)
# ---------------------------------------------------------------------------

class TestAcceptanceCriterionC(unittest.TestCase):
    """C. Task create → snapshot → events → evidence → route-trace all respond."""

    def setUp(self) -> None:
        self.svc, self.client = _make_client()

    def tearDown(self) -> None:
        _run(self.client.aclose())

    def _get(self, path: str, **kw) -> httpx.Response:
        return _run(self.client.get(path, **kw))

    def _post(self, path: str, **kw) -> httpx.Response:
        return _run(self.client.post(path, **kw))

    def test_c1_full_task_lifecycle_api(self) -> None:
        """Create a task and query all its projection endpoints."""
        create_resp = self._post("/api/v1/tasks", headers=_auth(), json=_task_body("c1"))
        self.assertEqual(create_resp.status_code, 201, create_resp.text)
        task_id = create_resp.json()["task"]["task_id"]

        # Snapshot
        snap = self._get(f"/api/v1/tasks/{task_id}", headers=_auth())
        self.assertEqual(snap.status_code, 200)
        snap_body = snap.json()
        self.assertEqual(snap_body["taskId"], task_id)
        self.assertIn(snap_body["status"], ("accepted",))

        # Events
        events = self._get(f"/api/v1/tasks/{task_id}/events", headers=_auth())
        self.assertEqual(events.status_code, 200)
        event_list = events.json()["events"]
        self.assertGreater(len(event_list), 0)
        # First event must be task.accepted (projected from task.created)
        # Node events use camelCase: eventType
        self.assertEqual(event_list[0]["eventType"], "task.accepted")

        # Evidence
        evidence = self._get(f"/api/v1/tasks/{task_id}/evidence", headers=_auth())
        self.assertEqual(evidence.status_code, 200)

        # Route trace
        route_trace = self._get(f"/api/v1/tasks/{task_id}/route-trace", headers=_auth())
        self.assertEqual(route_trace.status_code, 200)

    def test_c2_event_sequence_numbers_are_monotonic(self) -> None:
        create_resp = self._post("/api/v1/tasks", headers=_auth(), json=_task_body("c2"))
        self.assertEqual(create_resp.status_code, 201)
        task_id = create_resp.json()["task"]["task_id"]
        events_resp = self._get(f"/api/v1/tasks/{task_id}/events", headers=_auth())
        event_list = events_resp.json()["events"]
        sequences = [e["sequence"] for e in event_list]
        self.assertEqual(sequences, sorted(sequences))

    def test_c3_handshake_returns_correct_domain_pack_ref(self) -> None:
        resp = self._get("/api/v1/node/handshake", headers=_auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # Handshake uses snake_case
        self.assertEqual(body.get("domain_pack_ref"), "pack.refinery.v0")


# ---------------------------------------------------------------------------
# Acceptance criterion D: Ledger JSONL export and replay
# ---------------------------------------------------------------------------

class TestAcceptanceCriterionD(unittest.TestCase):
    """D. Ledger can be exported to JSONL and replayed with chain verification."""

    def _export_ledger(self, ledger: EventLedger, path: Path) -> None:
        """Export all events to JSONL."""
        with path.open("w", encoding="utf-8") as fh:
            for ev in ledger.events:
                fh.write(json.dumps(json.loads(ev.canonical_json())) + "\n")

    def test_d1_ledger_export_and_chain_verify(self) -> None:
        """Create tasks, export ledger, verify chain integrity."""
        svc, client = _make_client()
        create_resp = _run(client.post(
            "/api/v1/tasks",
            headers=_auth(),
            json=_task_body("d1"),
        ))
        _run(client.aclose())
        self.assertEqual(create_resp.status_code, 201)

        ledger = svc._ledger
        self.assertGreater(len(ledger.events), 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "ledger.jsonl"
            self._export_ledger(ledger, jsonl_path)

            # Import and verify with audit view
            from scripts.run_m10_audit_view import run_audit
            report = run_audit(jsonl_path)
            self.assertEqual(report.event_count, len(ledger.events))
            # Chain integrity should pass (all events written by the same ledger)
            self.assertTrue(report.chain.passed, f"Chain failed: {report.chain.detail}")

    def test_d2_no_egress_evidence_in_offline_run(self) -> None:
        """An in-memory run with no external calls must report no_egress=True."""
        svc, client = _make_client()
        _run(client.post("/api/v1/tasks", headers=_auth(), json=_task_body("d2")))
        _run(client.aclose())

        ledger = svc._ledger
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "ledger.jsonl"
            self._export_ledger(ledger, jsonl_path)
            from scripts.run_m10_audit_view import run_audit
            report = run_audit(jsonl_path)
            self.assertTrue(report.egress_evidence["no_egress"])


# ---------------------------------------------------------------------------
# Acceptance criterion E: SQLite persistence + recovery
# ---------------------------------------------------------------------------

class TestAcceptanceCriterionE(unittest.TestCase):
    """E. SQLite ledger survives close + reopen; recovery is correct."""

    def test_e1_sqlite_persist_and_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = os.path.join(tmpdir, "acceptance.sqlite3")
            signing_key = b"acceptance-signing-key-000000000"
            store = SQLiteLedgerStore(ledger_path, signing_key)

            task_id = "task.acceptance-e1"
            ev = build_event(
                event_type="task.created",
                task_id=task_id,
                actor_id="orchestrator.acceptance",
                actor_type="orchestrator",
                payload_contract="TaskEnvelope",
                payload_version="1.0",
                payload={"request": "Acceptance persistence test"},
                clearance=Clearance.restricted,
                idempotency="acceptance-persist-001",
                sequence=0,
            )
            tx = store.append(ev)
            store.checkpoint(
                checkpoint_id="checkpoint.acceptance.e1",
                task_id=task_id,
                state="created",
                transaction_id=tx.transaction_id,
            )
            store.close()

            # Reopen and verify
            store2 = SQLiteLedgerStore(ledger_path, signing_key)
            recovered_events = [e for e in store2.events if e.task_id == task_id]
            self.assertEqual(len(recovered_events), 1)
            self.assertEqual(recovered_events[0].event_type, "task.created")

            rm = RecoveryManager(store2)
            point = rm.recover(task_id)
            self.assertIsNotNone(point)
            self.assertEqual(point.resumed_from_sequence, 1)
            store2.close()


# ---------------------------------------------------------------------------
# Acceptance criterion F + G: Full acceptance run and gate
# ---------------------------------------------------------------------------

class TestAcceptanceCriterionFG(unittest.TestCase):
    """F. Audit view produces passing report. G. All criteria pass."""

    def test_fg_acceptance_gate(self) -> None:
        """Run a complete acceptance check and record the result."""
        results: dict[str, Any] = {
            "node_identity": "node.m10.acceptance",
            "protocol_version": NODE_PROTOCOL_VERSION,
            "criteria": {},
        }
        all_passed = True

        # --- Criterion A: startup ---
        try:
            cfg = NodeServerConfig(
                node_identity="node.m10.gate",
                bearer_token="gate-token",
                domain_pack_ref="pack.refinery.v0",
                clearance=Clearance.restricted,
                subject="principal.gate",
            )
            startup = run_startup_checks(cfg)
            results["criteria"]["A_startup"] = startup.passed
            if not startup.passed:
                all_passed = False
        except Exception as exc:
            results["criteria"]["A_startup"] = False
            results["A_error"] = str(exc)
            all_passed = False

        # --- Criterion B: authenticated endpoints ---
        try:
            svc, client = _make_client("gate-token-b")
            health_resp = _run(client.get("/api/v1/health", headers=_auth("gate-token-b")))
            unauth_resp = _run(client.get("/api/v1/health"))
            _run(client.aclose())
            b_passed = health_resp.status_code == 200 and unauth_resp.status_code == 401
            results["criteria"]["B_endpoints"] = b_passed
            if not b_passed:
                all_passed = False
        except Exception as exc:
            results["criteria"]["B_endpoints"] = False
            all_passed = False

        # --- Criterion C: task lifecycle ---
        try:
            svc_c, client_c = _make_client("gate-token-c")
            create = _run(client_c.post("/api/v1/tasks", headers=_auth("gate-token-c"), json=_task_body("fg1")))
            if create.status_code == 201:
                task_id = create.json()["task"]["task_id"]
                snap = _run(client_c.get(f"/api/v1/tasks/{task_id}", headers=_auth("gate-token-c")))
                events = _run(client_c.get(f"/api/v1/tasks/{task_id}/events", headers=_auth("gate-token-c")))
                c_passed = snap.status_code == 200 and events.status_code == 200
            else:
                c_passed = False
            _run(client_c.aclose())
            results["criteria"]["C_lifecycle"] = c_passed
            if not c_passed:
                all_passed = False
        except Exception as exc:
            results["criteria"]["C_lifecycle"] = False
            all_passed = False

        # --- Criterion D: ledger replay ---
        try:
            svc_d, client_d = _make_client("gate-token-d")
            _run(client_d.post("/api/v1/tasks", headers=_auth("gate-token-d"), json=_task_body("fg2")))
            _run(client_d.aclose())
            with tempfile.TemporaryDirectory() as tmpdir:
                ledger = svc_d._ledger
                jsonl_path = Path(tmpdir) / "gate_ledger.jsonl"
                with jsonl_path.open("w", encoding="utf-8") as fh:
                    for ev in ledger.events:
                        fh.write(json.dumps(json.loads(ev.canonical_json())) + "\n")
                from scripts.run_m10_audit_view import run_audit
                audit_report = run_audit(jsonl_path)
                d_passed = audit_report.chain.passed and audit_report.egress_evidence["no_egress"]
                results["criteria"]["D_ledger_replay"] = d_passed
                results["D_event_count"] = audit_report.event_count
                if not d_passed:
                    all_passed = False
        except Exception as exc:
            results["criteria"]["D_ledger_replay"] = False
            all_passed = False

        # --- Final gate ---
        results["passed"] = all_passed
        results["completed_at"] = __import__("datetime").datetime.utcnow().isoformat() + "Z"

        # Write acceptance evidence
        evidence_dir = Path(__file__).parent.parent / "acceptance"
        evidence_dir.mkdir(exist_ok=True)
        evidence_path = evidence_dir / "m10_acceptance_run.json"
        evidence_path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

        # Emit the completion log
        if all_passed:
            import logging
            logging.getLogger(__name__).info(
                "acceptance.run.completed node=%s protocol=%s criteria=%s",
                results["node_identity"],
                results["protocol_version"],
                list(results["criteria"].keys()),
            )

        self.assertTrue(
            all_passed,
            f"M10 acceptance gate failed. Results: {json.dumps(results, indent=2)}",
        )


if __name__ == "__main__":
    unittest.main()
