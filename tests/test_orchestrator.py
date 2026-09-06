import unittest
from dataclasses import replace
from tempfile import TemporaryDirectory

from contracts import (AuthorizationRejected, Clearance, ContractStatus, Orchestrator, PlanRejected,
                       RetryExhausted, SQLiteLedgerStore, StepTimeout, TaskEnvelope,
                       TeamPlan, TransitionRejected)


class OrchestratorTests(unittest.TestCase):
    def make_orchestrator(self, directory):
        return Orchestrator(SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"orchestrator-key"))

    def make_task(self, orchestrator):
        return orchestrator.create_task(
            principal_id="principal.1", clearance=Clearance.internal,
            request="review inspection report", domain_pack_ref="pack.refinery.v0",
            risk_class="high", autonomy_ceiling="review_required",
            allowed_evidence_scope=("inspection-report",),
            permitted_worker_capabilities=("reasoning",), permitted_tools=("calculator",),
            verification_criteria=("source_check",),
            resource_budget={"max_concurrency": 1, "max_step_attempts": 2},
            task_id="task.orchestrator-001")

    def make_plan(self, task):
        return TeamPlan(team_id="team.orchestrator-001", task_id=task.task_id,
                        assignments=("assignment.reasoning-001",), dependency_graph={},
                        concurrency_ceiling=1, required_verification=True,
                        completion_criteria=("source_check",), plan_version_hash="plan-hash",
                        policy_version_hash="policy-hash", status=ContractStatus.proposed)

    def prepare(self, orchestrator):
        task = self.make_task(orchestrator)
        orchestrator.authorize(task.task_id, authorization_ref="auth.1")
        orchestrator.commit_plan(self.make_plan(task))
        return task

    def test_fake_worker_can_finish_only_through_orchestrator_transitions(self):
        with TemporaryDirectory() as directory:
            orchestrator = self.make_orchestrator(directory)
            task = self.prepare(orchestrator)
            proposal = orchestrator.execute_step(task.task_id, step_id="step.1", action=lambda: {"complete": True}, timeout_ms=1000)
            self.assertEqual(proposal.result, {"complete": True})
            self.assertEqual(orchestrator.state(task.task_id), "executing")
            orchestrator.transition(task.task_id, "barrier.waiting", {"barrier_id": "join.1"})
            orchestrator.transition(task.task_id, "verification.completed", {"status": "passed", "provenance": {"source_ref": "verification:step.1", "confidence": 1.0, "clearance": "internal", "taint": "clean"}})
            completed = orchestrator.transition(task.task_id, "completion.recorded", {"criteria": {"source_check": True}})
            self.assertEqual(completed.state, "complete")
            self.assertEqual(orchestrator.store.latest_checkpoint(task.task_id).state, "complete")
            orchestrator.store.close()

    def test_invalid_transition_and_authorization_fail_closed(self):
        with TemporaryDirectory() as directory:
            orchestrator = self.make_orchestrator(directory)
            task = self.make_task(orchestrator)
            with self.assertRaises(AuthorizationRejected):
                orchestrator.authorize(task.task_id, authorization_ref=" ")
            with self.assertRaises(TransitionRejected):
                orchestrator.transition(task.task_id, "completion.recorded", {"criteria": {"source_check": True}})
            orchestrator.store.close()

    def test_replan_cannot_expand_authority_or_reduce_verification(self):
        with TemporaryDirectory() as directory:
            orchestrator = self.make_orchestrator(directory)
            task = self.make_task(orchestrator)
            expanded = replace(task, clearance=Clearance.secret)
            with self.assertRaises(PlanRejected):
                orchestrator.validate_replan(task, expanded)
            reduced = replace(task, verification_criteria=())
            with self.assertRaises(PlanRejected):
                orchestrator.validate_replan(task, reduced)
            orchestrator.store.close()

    def test_timeout_retries_are_bounded_and_end_in_typed_failure(self):
        with TemporaryDirectory() as directory:
            orchestrator = self.make_orchestrator(directory)
            task = self.prepare(orchestrator)
            attempts = []
            def timed_out():
                attempts.append(1)
                raise TimeoutError("worker timeout")
            with self.assertRaises(RetryExhausted):
                orchestrator.execute_step(task.task_id, step_id="step.timeout", action=timed_out, timeout_ms=1, max_attempts=2)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(orchestrator.state(task.task_id), "failed")
            self.assertEqual([event.event_type for event in orchestrator.store.events].count("retry.started"), 2)
            orchestrator.store.close()


if __name__ == "__main__":
    unittest.main()
