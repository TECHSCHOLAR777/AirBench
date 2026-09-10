"""M10.3 — API latency smoke tests.

These tests verify that the Node API stays within acceptable response-time
bounds under deterministic, in-memory conditions (no real model calls).

Thresholds:
- Health round-trip: < 150 ms
- Task create + snapshot: < 300 ms
- Event-batch read for a task with multiple events: < 300 ms

All thresholds are deliberately generous (CI may be slow).  They are designed
to catch gross regressions (e.g. accidentally blocking I/O in the hot path)
rather than serve as tight SLOs.  The measurements are also written to a JSON
fixture for inclusion in the M10 evidence package.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import tempfile
import unittest
from pathlib import Path
from typing import Any

import httpx

from contracts import (
    Clearance,
    EventLedger,
    Orchestrator,
    build_event,
    idempotency_key,
)
from airbench.node.api import NodeApiConfig, NodeApiService, create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


def _make_client(clearance: Clearance = Clearance.restricted) -> tuple[NodeApiService, httpx.AsyncClient]:
    ledger = EventLedger()
    orch = Orchestrator(ledger)
    cfg = NodeApiConfig(
        node_identity="node.m10.latency",
        protocol_version="0.1",
        clearance_context=clearance,
        authenticated_subject="principal.m10",
        domain_pack_ref="pack.refinery.v0",
        bearer_token="latency-token",
        handshake_ledger_event_ref="h",
        sovereignty_evidence_ref="e",
        require_orchestrator_authorization=False,
    )
    svc = NodeApiService(orch, cfg)
    app = create_app(svc)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://node.latency")
    return svc, client


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer latency-token"}


def _task_body(suffix: str = "1") -> dict[str, Any]:
    return {
        "command_id": f"cmd.latency.{suffix}",
        "task_id": None,
        "actor": "principal.m10",
        "expected_sequence": None,
        "idempotency_key": f"idem.latency.{suffix}",
        "client_version": "0.1",
        "command_type": "task.create",
        "arguments": {
            "principal_id": "principal.m10",
            "clearance": "internal",
            "request": f"Latency test task {suffix}",
            "domain_pack_ref": "pack.refinery.v0",
            "risk_class": "high",
            "autonomy_ceiling": "review_required",
            "allowed_evidence_scope": ["inspection-report"],
            "permitted_worker_capabilities": ["reasoning"],
            "permitted_tools": [],
            "output_contract": "approval-note",
            "verification_criteria": [],
            "resource_budget": {"max_concurrency": 1, "max_steps": 4},
        },
    }


# ---------------------------------------------------------------------------
# Latency measurements storage
# ---------------------------------------------------------------------------

_MEASUREMENTS: list[dict[str, Any]] = []


def _measure(name: str, duration_ms: float) -> None:
    _MEASUREMENTS.append({"name": name, "duration_ms": round(duration_ms, 3)})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

HEALTH_THRESHOLD_MS = 150
TASK_THRESHOLD_MS = 300
EVENTS_THRESHOLD_MS = 300


class TestApiLatency(unittest.TestCase):
    def setUp(self) -> None:
        self.svc, self.client = _make_client()

    def tearDown(self) -> None:
        _run(self.client.aclose())

    def _get(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.get(path, **kwargs))

    def _post(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.post(path, **kwargs))

    def _timed_get(self, path: str, **kwargs) -> tuple[httpx.Response, float]:
        t0 = time.perf_counter()
        resp = self._get(path, **kwargs)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return resp, elapsed_ms

    def _timed_post(self, path: str, **kwargs) -> tuple[httpx.Response, float]:
        t0 = time.perf_counter()
        resp = self._post(path, **kwargs)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return resp, elapsed_ms

    def test_health_round_trip_latency(self) -> None:
        """GET /api/v1/health must respond in < 150 ms (in-memory transport)."""
        # Warm up
        self._get("/api/v1/health", headers=_auth())

        resp, elapsed = self._timed_get("/api/v1/health", headers=_auth())
        _measure("health_round_trip_ms", elapsed)
        self.assertEqual(resp.status_code, 200)
        self.assertLess(
            elapsed, HEALTH_THRESHOLD_MS,
            f"Health endpoint took {elapsed:.1f} ms (threshold {HEALTH_THRESHOLD_MS} ms)",
        )

    def test_handshake_latency(self) -> None:
        """GET /api/v1/node/handshake must respond in < 150 ms."""
        self._get("/api/v1/node/handshake", headers=_auth())  # warm-up
        resp, elapsed = self._timed_get("/api/v1/node/handshake", headers=_auth())
        _measure("handshake_ms", elapsed)
        self.assertEqual(resp.status_code, 200)
        self.assertLess(elapsed, HEALTH_THRESHOLD_MS)

    def test_task_create_latency(self) -> None:
        """POST /api/v1/tasks must complete in < 300 ms."""
        resp, elapsed = self._timed_post("/api/v1/tasks", headers=_auth(), json=_task_body("lt1"))
        _measure("task_create_ms", elapsed)
        self.assertEqual(resp.status_code, 201)
        self.assertLess(
            elapsed, TASK_THRESHOLD_MS,
            f"Task create took {elapsed:.1f} ms (threshold {TASK_THRESHOLD_MS} ms)",
        )

    def test_task_snapshot_latency(self) -> None:
        """GET /api/v1/tasks/{id} must respond in < 300 ms."""
        create_resp = self._post("/api/v1/tasks", headers=_auth(), json=_task_body("lt2"))
        self.assertEqual(create_resp.status_code, 201)
        task_id = create_resp.json()["task"]["task_id"]

        resp, elapsed = self._timed_get(f"/api/v1/tasks/{task_id}", headers=_auth())
        _measure("task_snapshot_ms", elapsed)
        self.assertEqual(resp.status_code, 200)
        self.assertLess(
            elapsed, TASK_THRESHOLD_MS,
            f"Snapshot took {elapsed:.1f} ms (threshold {TASK_THRESHOLD_MS} ms)",
        )

    def test_event_batch_latency(self) -> None:
        """GET /api/v1/tasks/{id}/events must respond in < 300 ms."""
        create_resp = self._post("/api/v1/tasks", headers=_auth(), json=_task_body("lt3"))
        self.assertEqual(create_resp.status_code, 201)
        task_id = create_resp.json()["task"]["task_id"]

        resp, elapsed = self._timed_get(f"/api/v1/tasks/{task_id}/events", headers=_auth())
        _measure("event_batch_ms", elapsed)
        self.assertEqual(resp.status_code, 200)
        self.assertLess(
            elapsed, EVENTS_THRESHOLD_MS,
            f"Event batch took {elapsed:.1f} ms (threshold {EVENTS_THRESHOLD_MS} ms)",
        )

    def test_task_create_and_snapshot_combined_latency(self) -> None:
        """Create + snapshot combined must complete in < 600 ms."""
        t0 = time.perf_counter()
        create_resp = self._post("/api/v1/tasks", headers=_auth(), json=_task_body("lt4"))
        self.assertEqual(create_resp.status_code, 201)
        task_id = create_resp.json()["task"]["task_id"]
        snap_resp = self._get(f"/api/v1/tasks/{task_id}", headers=_auth())
        self.assertEqual(snap_resp.status_code, 200)
        elapsed = (time.perf_counter() - t0) * 1000
        _measure("create_plus_snapshot_ms", elapsed)
        self.assertLess(elapsed, TASK_THRESHOLD_MS * 2)

    def test_evidence_endpoint_latency(self) -> None:
        """GET /api/v1/tasks/{id}/evidence must respond in < 300 ms."""
        create_resp = self._post("/api/v1/tasks", headers=_auth(), json=_task_body("lt5"))
        self.assertEqual(create_resp.status_code, 201)
        task_id = create_resp.json()["task"]["task_id"]

        resp, elapsed = self._timed_get(f"/api/v1/tasks/{task_id}/evidence", headers=_auth())
        _measure("evidence_ms", elapsed)
        self.assertEqual(resp.status_code, 200)
        self.assertLess(elapsed, EVENTS_THRESHOLD_MS)

    def test_route_trace_latency(self) -> None:
        """GET /api/v1/tasks/{id}/route-trace must respond in < 300 ms."""
        create_resp = self._post("/api/v1/tasks", headers=_auth(), json=_task_body("lt6"))
        self.assertEqual(create_resp.status_code, 201)
        task_id = create_resp.json()["task"]["task_id"]

        resp, elapsed = self._timed_get(f"/api/v1/tasks/{task_id}/route-trace", headers=_auth())
        _measure("route_trace_ms", elapsed)
        self.assertEqual(resp.status_code, 200)
        self.assertLess(elapsed, EVENTS_THRESHOLD_MS)


# ---------------------------------------------------------------------------
# Write measurements to fixture on suite completion
# ---------------------------------------------------------------------------

class TestLatencyEvidenceExport(unittest.TestCase):
    """Write all latency measurements to a JSON file as evidence."""

    def test_measurements_are_positive(self) -> None:
        """All recorded measurements must be positive numbers."""
        # This test runs after the other tests in alphabetical order within the module.
        # _MEASUREMENTS may be empty if run standalone.
        for m in _MEASUREMENTS:
            self.assertGreater(m["duration_ms"], 0, f"Measurement {m['name']} is not positive")

    def test_write_measurements_fixture(self) -> None:
        """Write measurements to the scratch directory as evidence."""
        if not _MEASUREMENTS:
            self.skipTest("No measurements recorded yet (run full latency suite)")
        output_dir = Path(__file__).parent.parent / "acceptance"
        output_dir.mkdir(exist_ok=True)
        out_path = output_dir / "m10_latency_measurements.json"
        out_path.write_text(
            json.dumps(
                {
                    "description": "M10.3 API latency smoke tests (in-memory transport)",
                    "thresholds": {
                        "health_ms": HEALTH_THRESHOLD_MS,
                        "task_ms": TASK_THRESHOLD_MS,
                        "events_ms": EVENTS_THRESHOLD_MS,
                    },
                    "measurements": _MEASUREMENTS,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self.assertTrue(out_path.exists())


if __name__ == "__main__":
    unittest.main()
