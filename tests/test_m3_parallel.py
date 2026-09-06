import unittest
from tempfile import TemporaryDirectory

from contracts import (AuthorizationError, AuthorizationService, Clearance, CircuitOpen,
                       Orchestrator, PlanProposal, PlanStep, PlanValidationError,
                       PrincipalRecord, RetryExhausted, SQLiteLedgerStore, sign_reference)


class M3ParallelTests(unittest.TestCase):
    def service(self):
        principal = PrincipalRecord("principal.m3", Clearance.internal,
                                   frozenset({"inspection"}), frozenset({"calculator"}),
                                   frozenset({"high"}), {"max_concurrency": 2, "max_steps": 4})
        key = b"m3-signing-key"
        ref = sign_reference("local:refinery-pack", "pack-digest", key)
        policy = sign_reference("local:policy", "policy-digest", key)
        return AuthorizationService({principal.principal_id: principal}, pack=ref, policy=policy, verification_key=key)

    def task(self, orchestrator):
        return orchestrator.create_task(principal_id="principal.m3", clearance=Clearance.internal,
                                        request="inspect", domain_pack_ref="local:refinery-pack",
                                        risk_class="high", autonomy_ceiling="review_required",
                                        allowed_evidence_scope=("inspection",), permitted_tools=("calculator",),
                                        verification_criteria=("verified",), resource_budget={"max_concurrency": 2, "max_steps": 4},
                                        task_id="task.m3-parallel-001")

    def test_authorization_rejects_unresolved_or_overbroad_requests(self):
        service = self.service()
        with self.assertRaises(AuthorizationError):
            service.authorize(principal_id="missing", requested_clearance=Clearance.internal, evidence_scope=(), tools=(), risk_class="high", resource_budget={})
        with self.assertRaises(AuthorizationError):
            service.authorize(principal_id="principal.m3", requested_clearance=Clearance.restricted, evidence_scope=(), tools=(), risk_class="high", resource_budget={})

    def test_typed_plan_validation_rejects_scope_and_cycles(self):
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"m3-key")
            orchestrator = Orchestrator(store, authorization=self.service())
            task = self.task(orchestrator)
            orchestrator.authorize(task.task_id, authorization_ref="auth.m3")
            proposal = PlanProposal(task.task_id, "team.m3-001", (
                PlanStep("step.a", "retrieval", frozenset(), frozenset({"inspection"}), ("step.b",), 1000, 1),
                PlanStep("step.b", "verification", frozenset(), frozenset({"inspection"}), ("step.a",), 1000, 1),
            ), frozenset({"research"}), frozenset({"calculator"}), frozenset({"inspection"}), {"max_steps": 2}, frozenset({"verified"}))
            with self.assertRaises(PlanValidationError):
                orchestrator.commit_proposal(proposal)
            store.close()

    def test_executor_supports_failure_circuit_and_cancellation(self):
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"m3-key")
            orchestrator = Orchestrator(store, authorization=self.service())
            task = self.task(orchestrator)
            orchestrator.authorize(task.task_id, authorization_ref="auth.m3")
            proposal = PlanProposal(task.task_id, "team.m3-001", (PlanStep("step.a", "retrieval", frozenset(), frozenset({"inspection"}), (), 1000, 1),), frozenset(), frozenset(), frozenset({"inspection"}), {"max_steps": 1}, frozenset({"verified"}))
            orchestrator.commit_proposal(proposal)
            with self.assertRaises(RetryExhausted):
                orchestrator.execute_step(task.task_id, step_id="step.fail", action=lambda: (_ for _ in ()).throw(RuntimeError("dependency down")), timeout_ms=1000, max_attempts=3, dependency="retrieval")
            self.assertIn("retrieval", orchestrator._circuit_open)
            self.assertEqual(orchestrator.state(task.task_id), "failed")
            store.close()

    def test_cancellation_is_an_explicit_ledger_transition(self):
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"m3-key")
            orchestrator = Orchestrator(store, authorization=self.service())
            task = self.task(orchestrator)
            cancelled = orchestrator.cancel(task.task_id, reason="operator requested stop")
            self.assertEqual(cancelled.state, "cancelled")
            self.assertEqual(orchestrator.store.events[-1].event_type, "task.cancelled")
            store.close()


if __name__ == "__main__":
    unittest.main()
