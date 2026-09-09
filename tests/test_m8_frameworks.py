import unittest
from tempfile import TemporaryDirectory
from contracts import Clearance, EventLedger, Taint, build_event, idempotency_key, Orchestrator, SQLiteLedgerStore, TeamPlan
from airbench.knowledge.consistency import ConsistencyEngine, DecisionRecord
from airbench.verification.autonomy import ActionProposal, AutonomyGovernor
from airbench.verification.gate import CrossFrameworkGate
from airbench.verification.independent import CompletionGate, EvaluatorInput, EvaluatorResult, EvaluatorUnavailable, IndependentEvaluator
from airbench.verification.runner import VerificationResult, VerificationOutcome

def _request():
    return EvaluatorInput("task.m8", "eval.1", "worker.generator", "verification-worker", "proposal.1", ("packet.1",), ("evidence.1",), ("evidence",), Clearance.internal, 0.9, Taint.clean)

def _ledger():
    ledger = EventLedger()
    ledger.append(build_event(event_type="task.created", task_id="task.m8", actor_id="test", actor_type="test", payload_contract="TaskEnvelope", payload_version="1.0", payload={"task_id": "task.m8"}, clearance=Clearance.internal, idempotency=idempotency_key("task.created", "task.m8"), sequence=0))
    return ledger

class M8FrameworkTests(unittest.TestCase):
    def test_unavailable_evaluator_and_completion_fail_closed(self):
        ledger = _ledger(); request = _request(); result = IndependentEvaluator(ledger).evaluate(request)
        self.assertEqual(result.outcome, "needs_review")
        decision = CompletionGate(ledger).decide(request, result, deterministic_checks={"source": "passed"}, evidence_refs=("evidence.1",))
        self.assertEqual(decision.outcome, "needs_review")
        self.assertIn("completion.blocked", [event.event_type for event in ledger.events])

    def test_evaluator_cannot_self_grade(self):
        ledger = _ledger()
        def grade(request):
            return EvaluatorResult(request.evaluation_id, request.task_id, "passed", (("evidence", True),), "ok", 1.0, request.clearance, request.taint, request.generator_worker_id)
        with self.assertRaises(EvaluatorUnavailable): IndependentEvaluator(ledger, grade).evaluate(_request())

    def test_unknown_risk_escalates_and_consistency_flags_deviation(self):
        ledger = _ledger(); authority = AutonomyGovernor(ledger).decide(ActionProposal("task.m8", "action.1", "unknown", "worker.generator", "proposal.1", 1.0, Clearance.internal, Taint.clean))
        self.assertEqual(authority.outcome, "escalate")
        old = DecisionRecord("decision.old", "old", "approval", "asset.1", (("mode", "normal"),), "reject", "rule.1", "senior")
        current = DecisionRecord("decision.new", "task.m8", "approval", "asset.1", (("mode", "normal"),), "approve", "rule.1", "senior")
        self.assertTrue(ConsistencyEngine(ledger, (old,)).compare(current).deviation)

    def test_cross_framework_gate_rejects_any_failed_gate(self):
        ledger = _ledger(); verification = VerificationResult("verification.1", "task.m8", VerificationOutcome.failed, (), 0.2, Clearance.internal, Taint.clean, "failed")
        completion = type("Decision", (), {"outcome": "needs_review", "ledger_event_id": "event.completion"})(); authority = type("Authority", (), {"outcome": "allow", "ledger_event_id": "event.authority"})(); consistency = type("Consistency", (), {"deviation": False, "ledger_event_id": "event.consistency"})()
        self.assertEqual(CrossFrameworkGate(ledger).evaluate("task.m8", verification, completion, authority, consistency).outcome, "needs_review")

    def test_orchestrator_is_the_only_completion_transition_owner(self):
        with TemporaryDirectory() as directory:
            orchestrator = Orchestrator(SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"m8-test-key"))
            try:
                task = orchestrator.create_task(principal_id="principal.m8", clearance=Clearance.internal,
                    request="verify", domain_pack_ref="pack.test", risk_class="low", autonomy_ceiling="draft",
                    verification_criteria=("evidence",), task_id="task.m8-orchestrator")
                orchestrator.authorize(task.task_id, authorization_ref="auth.m8")
                orchestrator.commit_plan(TeamPlan(
                    team_id="team.m8", task_id=task.task_id, assignments=("assignment.m8",), dependency_graph={},
                    concurrency_ceiling=1, required_verification=True, completion_criteria=("evidence",),
                    plan_version_hash="plan", policy_version_hash="policy"))
                orchestrator.transition(task.task_id, "worker.started", {"worker_id": "worker.m8"})
                orchestrator.transition(task.task_id, "barrier.waiting", {"barrier_id": "join.m8"})
                orchestrator.transition(task.task_id, "verification.completed", {"status": "passed", "provenance": {"source_ref": "verification:m8", "confidence": 1.0, "clearance": "internal", "taint": "clean"}})
                completed = orchestrator.finalize_with_completion_gate(task.task_id, gate_outcome="passed", reason="all gates passed", criteria={"evidence": True})
                self.assertEqual(completed.state, "complete")
            finally:
                orchestrator.store.close()

if __name__ == "__main__": unittest.main()
