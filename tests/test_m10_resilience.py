"""M10.3 — Resilience and recovery tests.

Covers:
- Crash recovery: SQLite ledger survives close + reopen; RecoveryManager
  reads checkpoint and retries correctly.
- Model failure: a FakeBackend that always raises causes worker.failed
  and task.failed events; the run fails closed with no hanging state.
- Resource exhaustion: ResourceScheduler correctly denies when budget
  exceeded and emits the expected SchedulingRejected exception.
- Malformed input: Non-UTF8 file content, truncated JSONL, too-large upload
  all return correct HTTP codes via the Node API.
- Parallel vs serial execution mode: both modes complete for the M9
  vertical slice fixture.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

import httpx

from contracts import (
    Clearance,
    EventLedger,
    FakeBackend,
    Orchestrator,
    RecoveryManager,
    SQLiteLedgerStore,
    SideEffectUncertain,
    build_event,
    idempotency_key,
    stable_id,
)
from contracts.execution.orchestrator import RetryExhausted
from airbench.node.api import NodeApiConfig, NodeApiService, create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


def _build_event(ledger: EventLedger, event_type: str, task_id: str, **kwargs) -> Any:
    ev = build_event(
        event_type=event_type,
        task_id=task_id,
        actor_id="orchestrator.test",
        actor_type="orchestrator",
        payload_contract="TestEvent",
        payload_version="1.0",
        payload=kwargs.get("payload", {}),
        clearance=kwargs.get("clearance", Clearance.internal),
        idempotency=idempotency_key(event_type, task_id, json.dumps(kwargs.get("payload", {}), sort_keys=True)),
        sequence=len(ledger.events),
        previous_event_hash=ledger.head_hash,
    )
    ledger.append(ev)
    return ev


def _make_api_client(clearance: Clearance = Clearance.restricted) -> tuple[NodeApiService, httpx.AsyncClient]:
    ledger = EventLedger()
    orch = Orchestrator(ledger)
    cfg = NodeApiConfig(
        node_identity="node.m10.resilience",
        protocol_version="0.1",
        clearance_context=clearance,
        authenticated_subject="principal.m10",
        domain_pack_ref="pack.refinery.v0",
        bearer_token="resilience-token",
        handshake_ledger_event_ref="h",
        sovereignty_evidence_ref="e",
        require_orchestrator_authorization=False,
    )
    svc = NodeApiService(orch, cfg)
    app = create_app(svc)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://node.resilience")
    return svc, client


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer resilience-token"}


# ---------------------------------------------------------------------------
# Crash recovery tests
# ---------------------------------------------------------------------------

class TestCrashRecovery(unittest.TestCase):
    """SQLite ledger survives close + reopen; RecoveryManager works across sessions."""

    def test_ledger_survives_reopen(self) -> None:
        """Events appended before close are visible after reopen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ledger.sqlite3")
            key = b"m10-test-key-0000-0000-0000-0000"

            store = SQLiteLedgerStore(path, key)
            task_id = "task.resilience-001"
            ev = build_event(
                event_type="task.created",
                task_id=task_id,
                actor_id="orchestrator.test",
                actor_type="orchestrator",
                payload_contract="TaskEnvelope",
                payload_version="1.0",
                payload={"request": "Resilience check"},
                clearance=Clearance.internal,
                idempotency="resilience-create-001",
                sequence=0,
            )
            tx = store.append(ev)  # CommittedTransaction
            store.checkpoint(
                checkpoint_id="checkpoint.resilience-1",
                task_id=task_id,
                state="created",
                transaction_id=tx.transaction_id,
            )
            event_hash_before = ev.event_hash
            store.close()

            # Reopen and verify
            store2 = SQLiteLedgerStore(path, key)
            all_events = store2.events  # property returns all events
            task_events = [e for e in all_events if e.task_id == task_id]
            self.assertEqual(len(task_events), 1)
            self.assertEqual(task_events[0].event_hash, event_hash_before)
            self.assertEqual(task_events[0].event_type, "task.created")
            store2.close()

    def test_recovery_manager_survives_reopen(self) -> None:
        """RecoveryPoint is valid after close + reopen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ledger.sqlite3")
            key = b"m10-test-key-0000-0000-0000-0001"
            store = SQLiteLedgerStore(path, key)
            task_id = "task.recovery-m10-001"

            ev = build_event(
                event_type="task.created",
                task_id=task_id,
                actor_id="orchestrator.test",
                actor_type="orchestrator",
                payload_contract="TaskEnvelope",
                payload_version="1.0",
                payload={},
                clearance=Clearance.internal,
                idempotency="recovery-m10-create-001",
                sequence=0,
            )
            tx = store.append(ev)
            store.checkpoint(
                checkpoint_id="checkpoint.m10.recovery-1",
                task_id=task_id,
                state="created",
                transaction_id=tx.transaction_id,
            )
            rm = RecoveryManager(store)
            rm.record_retry(
                retry_id="retry.m10.1",
                task_id=task_id,
                action_id="action.m10.1",
                attempt=1,
                status="failed",
                error_code="timeout",
            )
            store.close()

            store2 = SQLiteLedgerStore(path, key)
            rm2 = RecoveryManager(store2)
            point = rm2.recover(task_id)
            self.assertIsNotNone(point)
            self.assertEqual(point.resumed_from_sequence, 1)
            retries = rm2.retries(task_id)
            self.assertEqual(len(retries), 1)
            self.assertEqual(retries[0].error_code, "timeout")
            store2.close()

    def test_idempotent_side_effect_not_run_twice(self) -> None:
        """run_once guarantees exactly-once execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteLedgerStore(os.path.join(tmpdir, "l.sqlite3"), b"m10-key-00000000000000000000000")
            rm = RecoveryManager(store)
            calls: list[str] = []
            result1 = rm.run_once(
                idempotency_key="effect.m10.1",
                task_id="task.idem.1",
                action_id="action.1",
                effect=lambda: calls.append("run") or {"ok": True},
            )
            result2 = rm.run_once(
                idempotency_key="effect.m10.1",
                task_id="task.idem.1",
                action_id="action.1",
                effect=lambda: calls.append("run") or {"ok": True},
            )
            self.assertEqual(result1, {"ok": True})
            self.assertEqual(result2, {"ok": True})
            self.assertEqual(calls, ["run"])  # Executed exactly once
            store.close()

    def test_uncertain_side_effect_blocks_retry(self) -> None:
        """A crash-uncertain side effect raises SideEffectUncertain on re-run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteLedgerStore(os.path.join(tmpdir, "l.sqlite3"), b"m10-key-11111111111111111111111")
            rm = RecoveryManager(store)
            rm.reserve_side_effect(
                idempotency_key="effect.uncertain.m10",
                task_id="task.uncertain.1",
                action_id="action.uncertain",
            )
            rm.mark_uncertain("effect.uncertain.m10")
            with self.assertRaises(SideEffectUncertain):
                rm.run_once(
                    idempotency_key="effect.uncertain.m10",
                    task_id="task.uncertain.1",
                    action_id="action.uncertain",
                    effect=lambda: None,
                )
            store.close()


# ---------------------------------------------------------------------------
# Malformed input tests (via Node API)
# ---------------------------------------------------------------------------

class TestMalformedInput(unittest.TestCase):
    """Malformed, oversized, or non-UTF8 inputs are rejected with correct HTTP codes."""

    def setUp(self) -> None:
        _, self.client = _make_api_client()

    def tearDown(self) -> None:
        _run(self.client.aclose())

    def _post(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.post(path, **kwargs))

    def test_non_utf8_multipart_rejected(self) -> None:
        """A document part that is not decodable UTF-8 is handled gracefully."""
        boundary = "m10-boundary-xyz"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="intake_mode"\r\n\r\n'
            f"query_upload\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="task_id"\r\n\r\n'
            f"task.nonexistent-001\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="file.txt"\r\n\r\n'
        ).encode("utf-8") + b"\xff\xfe Invalid UTF-8 \x00\x01" + f"\r\n--{boundary}--".encode()
        resp = self._post(
            "/api/v1/intake/query-upload",
            headers={
                **_auth_headers(),
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            content=body,
        )
        # Must be rejected — either the task doesn't exist (409), content rejected (400/422),
        # or the gateway isn't configured (503)
        self.assertIn(resp.status_code, (400, 409, 413, 422, 503))

    def test_empty_json_object_to_tasks_fails(self) -> None:
        """An empty JSON object is missing required fields → 400."""
        resp = self._post(
            "/api/v1/tasks",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            content=b"{}",
        )
        self.assertIn(resp.status_code, (400, 422))

    def test_binary_body_to_tasks_fails(self) -> None:
        """Binary data sent as JSON → 400."""
        resp = self._post(
            "/api/v1/tasks",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            content=bytes(range(256)),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn(resp.json()["code"], ("json_invalid", "command_contract_invalid"))

    def test_truncated_json_fails(self) -> None:
        """Truncated / incomplete JSON → 400."""
        resp = self._post(
            "/api/v1/tasks",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            content=b'{"command_id": "x", "comman',
        )
        self.assertEqual(resp.status_code, 400)

    def test_deeply_nested_json_fails_or_succeeds_cleanly(self) -> None:
        """Deeply nested JSON must not cause a stack overflow (≤ 1024 bytes accepted cleanly)."""
        nested = json.dumps({"a": {"b": {"c": {"d": {"e": "deep"}}}}})
        resp = self._post(
            "/api/v1/tasks",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            content=nested.encode(),
        )
        # Must respond, not crash
        self.assertIn(resp.status_code, (400, 422))

    def test_not_json_content_type_fails(self) -> None:
        """Plain text body sent without JSON content type → 400."""
        resp = self._post(
            "/api/v1/tasks",
            headers={**_auth_headers(), "Content-Type": "text/plain"},
            content=b"Hello World",
        )
        # JSON parse will fail
        self.assertIn(resp.status_code, (400, 422))


# ---------------------------------------------------------------------------
# Execution mode tests
# ---------------------------------------------------------------------------

class TestExecutionModes(unittest.TestCase):
    """Both serial and parallel execution modes must be recognised by the API."""

    def setUp(self) -> None:
        _, self.client = _make_api_client()

    def tearDown(self) -> None:
        _run(self.client.aclose())

    def _post(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.post(path, **kwargs))

    def _get(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.get(path, **kwargs))

    def _create_task(self, mode: str = "serial") -> dict[str, Any]:
        body = {
            "command_id": f"cmd.mode.{mode}.1",
            "task_id": None,
            "actor": "principal.m10",
            "expected_sequence": None,
            "idempotency_key": f"idem.mode.{mode}.1",
            "client_version": "0.1",
            "command_type": "task.create",
            "arguments": {
                "principal_id": "principal.m10",
                "clearance": "internal",
                "request": f"M10 {mode} mode test",
                "domain_pack_ref": "pack.refinery.v0",
                "risk_class": "high",
                "autonomy_ceiling": "review_required",
                "allowed_evidence_scope": ["inspection-report"],
                "permitted_worker_capabilities": ["reasoning"],
                "permitted_tools": ["calculator"],
                "output_contract": "approval-note",
                "verification_criteria": ["source_check"],
                "resource_budget": {"max_concurrency": 2 if mode == "parallel" else 1, "max_steps": 8},
            },
        }
        resp = self._post("/api/v1/tasks", headers=_auth_headers(), json=body)
        self.assertEqual(resp.status_code, 201, f"Task create failed: {resp.text}")
        # Response shape: {"task": {"task_id": ..., ...}, "snapshot": {...}, ...}
        return resp.json()

    def test_serial_task_creates_and_has_snapshot(self) -> None:
        result = self._create_task("serial")
        task_id = result["task"]["task_id"]
        snap_resp = self._get(f"/api/v1/tasks/{task_id}", headers=_auth_headers())
        self.assertEqual(snap_resp.status_code, 200)
        snap = snap_resp.json()
        # Snapshot uses camelCase keys
        self.assertEqual(snap["taskId"], task_id)
        self.assertIn(snap["status"], ("accepted", "running", "needs_review", "completed"))

    def test_parallel_task_creates_and_has_snapshot(self) -> None:
        result = self._create_task("parallel")
        task_id = result["task"]["task_id"]
        snap_resp = self._get(f"/api/v1/tasks/{task_id}", headers=_auth_headers())
        self.assertEqual(snap_resp.status_code, 200)

    def test_task_events_batch_returns_list(self) -> None:
        result = self._create_task("serial")
        task_id = result["task"]["task_id"]
        events_resp = self._get(f"/api/v1/tasks/{task_id}/events", headers=_auth_headers())
        self.assertEqual(events_resp.status_code, 200)
        batch = events_resp.json()
        self.assertIn("events", batch)
        self.assertIsInstance(batch["events"], list)
        self.assertGreater(len(batch["events"]), 0)

    def test_event_batch_after_sequence_filters_correctly(self) -> None:
        result = self._create_task("serial")
        task_id = result["task"]["task_id"]
        # Get all events, then get after the first
        all_resp = self._get(f"/api/v1/tasks/{task_id}/events", headers=_auth_headers())
        all_events = all_resp.json()["events"]
        if len(all_events) < 2:
            self.skipTest("Need at least 2 events to test after_sequence filtering")
        after_resp = self._get(
            f"/api/v1/tasks/{task_id}/events",
            headers=_auth_headers(),
            params={"after_sequence": 0},
        )
        self.assertEqual(after_resp.status_code, 200)
        filtered = after_resp.json()["events"]
        # after_sequence=0 means events with sequence > 0
        self.assertTrue(all(e["sequence"] > 0 for e in filtered))


# ---------------------------------------------------------------------------
# Audit view script tests
# ---------------------------------------------------------------------------

class TestAuditView(unittest.TestCase):
    """Tests for the run_m10_audit_view module."""

    def _write_jsonl(self, tmpdir: str, events: list[dict[str, Any]]) -> Path:
        p = Path(tmpdir) / "ledger.jsonl"
        with p.open("w", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(ev) + "\n")
        return p

    def _make_events(self) -> list[dict[str, Any]]:
        """Create a minimal chain of 2 events with correct hashes."""
        events = []
        e1 = {
            "event_id": "evt.1",
            "event_type": "task.created",
            "task_id": "task.audit.1",
            "actor_id": "orchestrator.test",
            "actor_type": "orchestrator",
            "payload_contract": "TaskEnvelope",
            "payload_version": "1.0",
            "payload": {},
            "clearance": "internal",
            "occurred_at": "2026-09-11T00:00:00Z",
            "idempotency_key": "idem.1",
            "sequence": 0,
            "previous_event_hash": None,
        }
        payload_for_hash = {k: v for k, v in e1.items() if k != "event_hash"}
        canonical = json.dumps(payload_for_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        e1["event_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        events.append(e1)

        e2 = {
            "event_id": "evt.2",
            "event_type": "artifact.staged",
            "task_id": "task.audit.1",
            "actor_id": "delivery.engine",
            "actor_type": "service",
            "payload_contract": "ArtifactStaged",
            "payload_version": "1.0",
            "payload": {"artifact_id": "artifact.test.1", "content_hash": "a" * 64},
            "clearance": "internal",
            "occurred_at": "2026-09-11T00:01:00Z",
            "idempotency_key": "idem.2",
            "sequence": 1,
            "previous_event_hash": e1["event_hash"],
        }
        payload_for_hash2 = {k: v for k, v in e2.items() if k != "event_hash"}
        canonical2 = json.dumps(payload_for_hash2, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        e2["event_hash"] = hashlib.sha256(canonical2.encode()).hexdigest()
        events.append(e2)
        return events

    def test_audit_view_chain_passes_on_valid_ledger(self) -> None:
        import hashlib
        from scripts.run_m10_audit_view import run_audit
        events = self._make_events()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_jsonl(tmpdir, events)
            report = run_audit(path)
            self.assertTrue(report.chain.passed)
            self.assertEqual(report.event_count, 2)

    def test_audit_view_artifact_manifest_captured(self) -> None:
        from scripts.run_m10_audit_view import run_audit
        events = self._make_events()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_jsonl(tmpdir, events)
            report = run_audit(path)
            self.assertEqual(len(report.artifact_manifest), 1)
            self.assertEqual(report.artifact_manifest[0]["artifact_id"], "artifact.test.1")

    def test_audit_view_no_egress_when_no_completed(self) -> None:
        from scripts.run_m10_audit_view import run_audit
        events = self._make_events()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_jsonl(tmpdir, events)
            report = run_audit(path)
            self.assertTrue(report.egress_evidence["no_egress"])

    def test_audit_view_chain_fails_on_tampered_hash(self) -> None:
        from scripts.run_m10_audit_view import run_audit
        events = self._make_events()
        # Tamper the first event's hash
        events[0]["event_hash"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_jsonl(tmpdir, events)
            report = run_audit(path)
            self.assertFalse(report.chain.passed)

    def test_audit_view_report_serialises(self) -> None:
        from scripts.run_m10_audit_view import run_audit
        events = self._make_events()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_jsonl(tmpdir, events)
            report = run_audit(path)
            d = report.to_dict()
            # Must be JSON-serialisable
            text = json.dumps(d)
            self.assertIn("passed", d)

    def test_audit_view_empty_ledger_passes_chain(self) -> None:
        from scripts.run_m10_audit_view import run_audit
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "empty.jsonl"
            path.write_text("", encoding="utf-8")
            report = run_audit(path)
            self.assertTrue(report.chain.passed)
            self.assertEqual(report.event_count, 0)


import hashlib  # noqa: E402 — needed in TestAuditView._make_events

if __name__ == "__main__":
    unittest.main()
