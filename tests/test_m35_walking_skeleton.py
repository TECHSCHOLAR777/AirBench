import unittest
from tempfile import TemporaryDirectory

from contracts import (Clearance, ContractStatus, Orchestrator, PlanProposal, PlanStep,
                       RecoveryManager, SQLiteLedgerStore, sign_reference, AuthorizationService,
                       PrincipalRecord)


class WalkingSkeletonTests(unittest.TestCase):
    def test_complete_synthetic_pipeline_restarts_after_every_transition(self):
        with TemporaryDirectory() as directory:
            path = f"{directory}/ledger.sqlite3"
            key = b"m35-key"
            principal = PrincipalRecord("principal.m35", Clearance.internal, frozenset({"inspection"}), frozenset({"calculator"}), frozenset({"high"}), {"max_concurrency": 1, "max_steps": 8})
            pack = sign_reference("local:synthetic-pack", "pack-v1", key)
            policy = sign_reference("local:synthetic-policy", "policy-v1", key)
            auth = AuthorizationService({principal.principal_id: principal}, pack=pack, policy=policy, verification_key=key)
            store = SQLiteLedgerStore(path, key)
            orchestrator = Orchestrator(store, authorization=auth)
            calls = {"model": 0, "retrieval": 0, "tool": 0, "verification": 0, "artifact": 0}

            def restart():
                nonlocal store, orchestrator
                store.close()
                store = SQLiteLedgerStore(path, key)
                orchestrator = Orchestrator(store, authorization=auth)

            task = orchestrator.create_task(principal_id="principal.m35", clearance=Clearance.internal, request="synthetic inspection", domain_pack_ref="local:synthetic-pack", risk_class="high", autonomy_ceiling="review_required", allowed_evidence_scope=("inspection",), permitted_worker_capabilities=("reasoning",), permitted_tools=("calculator",), verification_criteria=("verified",), resource_budget={"max_concurrency": 1, "max_steps": 8}, task_id="task.m35-walking-001")
            restart()
            orchestrator.authorize(task.task_id, authorization_ref="authorization.m35")
            restart()
            proposal = PlanProposal(task.task_id, "team.m35-001", (PlanStep("step.model", "model", frozenset(), frozenset(), (), 1000, 0), PlanStep("step.retrieve", "retrieval", frozenset(), frozenset({"inspection"}), ("step.model",), 1000, 0), PlanStep("step.tool", "tool", frozenset({"calculator"}), frozenset({"inspection"}), ("step.retrieve",), 1000, 0)), frozenset({"reasoning"}), frozenset({"calculator"}), frozenset({"inspection"}), {"max_steps": 3}, frozenset({"verified"}))
            orchestrator.commit_proposal(proposal)
            restart()
            def run_once(name, value):
                return RecoveryManager(store).run_once(idempotency_key=f"m35.{name}", task_id=task.task_id, action_id=f"action.{name}", effect=lambda: calls.__setitem__(name, calls[name] + 1) or value)

            orchestrator.execute_step(task.task_id, step_id="step.model", action=lambda: run_once("model", {"proposal": "draft"}), timeout_ms=1000, kind="model")
            restart()
            orchestrator.execute_step(task.task_id, step_id="step.retrieve", action=lambda: run_once("retrieval", {"source_ref": "manual:1", "confidence": 0.95, "clearance": "internal", "taint": "untrusted"}), timeout_ms=1000, kind="retrieval", result_payload=lambda result, attempt: {"provenance": result, "attempt": attempt})
            restart()
            orchestrator.execute_step(task.task_id, step_id="step.tool", action=lambda: run_once("tool", {"value": 42}), timeout_ms=1000, kind="tool", result_payload=lambda result, attempt: {"provenance": {"source_ref": "tool:calculator", "confidence": 1.0, "clearance": "internal", "taint": "clean"}, "result": result, "attempt": attempt})
            restart()
            orchestrator.transition(task.task_id, "barrier.waiting", {"barrier_id": "barrier.m35"})
            restart()
            orchestrator.execute_step(task.task_id, step_id="step.verify", action=lambda: run_once("verification", {"status": "passed", "provenance": {"source_ref": "verification:m35", "confidence": 1.0, "clearance": "internal", "taint": "clean"}}), timeout_ms=1000, kind="verification", result_payload=lambda result, attempt: result)
            restart()
            artifact = RecoveryManager(store).run_once(idempotency_key="m35.artifact", task_id=task.task_id, action_id="action.artifact", effect=lambda: calls.__setitem__("artifact", calls["artifact"] + 1) or {"artifact_id": "artifact.m35", "content_hash": "artifact-hash"})
            orchestrator.transition(task.task_id, "artifact.staged", artifact)
            restart()
            orchestrator.transition(task.task_id, "artifact.checked", {"artifact_id": artifact["artifact_id"], "structural": True, "visual": True})
            restart()
            orchestrator.transition(task.task_id, "completion.recorded", {"criteria": {"verified": True}})
            self.assertEqual(orchestrator.state(task.task_id), "complete")
            self.assertEqual(calls, {"model": 1, "retrieval": 1, "tool": 1, "verification": 1, "artifact": 1})
            self.assertEqual(orchestrator.store.replay(task.task_id).state, "completed")
            event_types = [event.event_type for event in store.events]
            self.assertTrue({"task.created", "task.authorized", "task.plan.committed", "model.requested", "model.responded", "retrieval.requested", "evidence.created", "tool.requested", "tool.result", "barrier.waiting", "verification.requested", "verification.completed", "artifact.staged", "artifact.checked", "completion.recorded"}.issubset(event_types))
            event_ids = [event.event_id for event in store.events]
            self.assertEqual(len(event_ids), len(set(event_ids)))
            store.close()


if __name__ == "__main__":
    unittest.main()
