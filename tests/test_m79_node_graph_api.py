from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

import httpx

from airbench.knowledge.graph_store import SqliteGraphStore
from airbench.knowledge.world_model import CandidateFact, CandidateFactWriter, WorldModelError, WorldModelStore, candidate_id
from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from contracts import Clearance, EventLedger, FactEnvelope, Orchestrator, Taint, build_event


def _fact(fact_id: str, *, confidence: float = 0.9) -> FactEnvelope:
    return FactEnvelope(
        fact_id=fact_id, value={"entity_id": fact_id, "object_type": "equipment", "attributes": {"tag": "P-101"}},
        source_ref="upload:report.pdf#page-1", confidence=confidence, clearance=Clearance.internal,
        taint=Taint.untrusted, extraction_method="entity_extractor:fixture",
        observed_at="2026-01-01T00:00:00Z", ingested_at="2026-01-01T00:00:01Z",
    )


def _candidate(fact: FactEnvelope) -> CandidateFact:
    identity = candidate_id("task.graph", fact)
    return CandidateFact(identity, "task.graph", fact, ("evidence.1",), "consistency.1", "verification.1")


class NodeGraphApiTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.directory = tempfile.TemporaryDirectory()
        self.ledger = EventLedger()
        self.ledger.append(build_event(
            event_type="task.created", task_id="task.graph", actor_id="principal.api", actor_type="human",
            payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
            clearance=Clearance.internal, idempotency="task.graph.created", sequence=0,
        ))
        self.ledger.append(build_event(
            event_type="task.created", task_id="knowledge.graph", actor_id="principal.api", actor_type="service",
            payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
            clearance=Clearance.internal, idempotency="knowledge.graph.created", sequence=1,
            previous_event_hash=self.ledger.head_hash,
        ))
        self.store = SqliteGraphStore(f"{self.directory.name}/graph.sqlite")
        self.world = WorldModelStore(backend=self.store, ledger=self.ledger)
        writer = CandidateFactWriter(self.world, consistency_gate=lambda _: True, verification_gate=lambda _: True)
        committed = _candidate(_fact("fact.pump.1"))
        writer.stage(committed)
        writer.commit(committed.candidate_id)
        pending = _candidate(_fact("fact.valve.1", confidence=0.4))
        writer.stage(pending)
        with self.assertRaises(WorldModelError):
            writer.reconcile(pending.candidate_id, review_floor=0.6)
        self.pending_id = pending.candidate_id

        self.service = NodeApiService(
            Orchestrator(self.ledger),
            NodeApiConfig(
                node_identity="node.graph.test", protocol_version="0.1", clearance_context=Clearance.internal,
                authenticated_subject="principal.api", domain_pack_ref="pack.refinery.v0", bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.test", sovereignty_evidence_ref="evidence.sovereignty.test",
                require_orchestrator_authorization=False,
            ),
            world_model=self.world,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.service)), base_url="http://node.graph.test",
        )

    def tearDown(self):
        asyncio.run(self.client.aclose())
        self.store.close()
        self.directory.cleanup()

    def _request(self, method, path, **kwargs):
        async def run():
            return await self.client.request(method, path, headers={"Authorization": "Bearer test-token"}, **kwargs)

        return asyncio.run(run())

    def test_stats_and_query(self):
        stats = self._request("GET", "/api/v1/knowledge/graph/stats")
        self.assertEqual(stats.status_code, 200, stats.text)
        body = stats.json()
        self.assertTrue(body["configured"])
        self.assertEqual(body["node_count"], 1)
        self.assertEqual(body["review_queue_count"], 1)
        self.assertEqual(body["backend"], "SqliteGraphStore")

        query = self._request("POST", "/api/v1/knowledge/graph/query", json={"key": "entity_id"})
        self.assertEqual(query.status_code, 200, query.text)
        self.assertEqual(query.json()["result_count"], 1)
        self.assertEqual(query.json()["facts"][0]["fact_id"], "fact.pump.1")
        self.assertEqual(query.json()["facts"][0]["taint"], "untrusted")

    def test_query_rejects_clearance_widening(self):
        response = self._request("POST", "/api/v1/knowledge/graph/query", json={"key": "entity_id", "clearance": "restricted"})
        self.assertEqual(response.status_code, 403, response.text)

    def test_review_queue_and_resolution(self):
        queue = self._request("GET", "/api/v1/knowledge/graph/review-queue")
        self.assertEqual(queue.status_code, 200, queue.text)
        items = queue.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["candidate_id"], self.pending_id)
        self.assertEqual(items[0]["source_ref"], "upload:report.pdf#page-1")

        reject = self._request("POST", "/api/v1/knowledge/graph/review/resolve", json={"candidate_id": self.pending_id, "accept": False})
        self.assertEqual(reject.status_code, 200, reject.text)
        self.assertEqual(reject.json()["decision"], "reject")
        self.assertIsNone(reject.json()["fact_id"])
        self.assertEqual(self.ledger.events[-1].actor_id, "principal.api")
        self.assertEqual(self._request("GET", "/api/v1/knowledge/graph/stats").json()["node_count"], 1)

    def test_review_accept_commits_and_missing_is_404(self):
        accept = self._request("POST", "/api/v1/knowledge/graph/review/resolve", json={"candidate_id": self.pending_id, "accept": True})
        self.assertEqual(accept.status_code, 200, accept.text)
        self.assertEqual(accept.json()["fact_id"], "fact.valve.1")
        self.assertEqual(self._request("GET", "/api/v1/knowledge/graph/stats").json()["node_count"], 2)
        missing = self._request("POST", "/api/v1/knowledge/graph/review/resolve", json={"candidate_id": "candidate.missing", "accept": True})
        self.assertEqual(missing.status_code, 404)

    def test_graph_requires_authentication(self):
        async def run():
            return await self.client.get("/api/v1/knowledge/graph/stats")

        self.assertEqual(asyncio.run(run()).status_code, 401)


if __name__ == "__main__":
    unittest.main()
