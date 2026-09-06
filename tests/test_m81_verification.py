import unittest
from dataclasses import replace
from tempfile import TemporaryDirectory

from airbench.verification import (VerificationError, VerificationOutcome,
                                   VerificationRequest, VerificationRule,
                                   VerificationRunner)
from contracts import (Clearance, EventLedger, FactEnvelope, SQLiteLedgerStore,
                       Taint, build_event)


def fact(fact_id, value, *, source="report:page-1", confidence=0.95,
         clearance=Clearance.internal, taint=Taint.untrusted, unit=None):
    return FactEnvelope(
        fact_id=fact_id,
        value=value,
        source_ref=source,
        confidence=confidence,
        clearance=clearance,
        taint=taint,
        extraction_method="fixture",
        observed_at="2026-01-01T00:00:00Z",
        ingested_at="2026-01-01T00:00:00Z",
        unit=unit,
    )


def ledger_for(task_id="task.verification-001"):
    ledger = EventLedger()
    ledger.append(build_event(
        event_type="task.created",
        task_id=task_id,
        actor_id="test",
        actor_type="test",
        payload_contract="TaskEnvelope",
        payload_version="1.0",
        payload={"state": "created"},
        clearance=Clearance.internal,
        idempotency="task-created",
        sequence=0,
    ))
    return ledger


class M81VerificationTests(unittest.TestCase):
    def request(self, *, rules, facts, clearance=Clearance.internal):
        return VerificationRequest(
            verification_id="verification.001",
            task_id="task.verification-001",
            rules=tuple(rules),
            facts=tuple(facts),
            clearance=clearance,
            evidence_refs=("evidence.report-1",),
            rule_set_version="pack.rules.v1",
            idempotency_key="verification-request-001",
        )

    def test_all_core_check_families_pass_and_are_ledgered(self):
        facts = (
            fact("fact.a", 8, unit="bar"),
            fact("fact.b", 2, unit="bar"),
            fact("fact.total", 10, unit="bar"),
        )
        rules = (
            VerificationRule("rule.source", "source", ("fact.a",), source_prefixes=("report:",)),
            VerificationRule("rule.confidence", "confidence", ("fact.a",), confidence_floor=0.9),
            VerificationRule("rule.unit", "unit", ("fact.a",), expected_unit="bar"),
            VerificationRule("rule.bounds", "bounds", ("fact.a",), lower_bound=0, upper_bound=10),
            VerificationRule("rule.cross", "cross_fact", ("fact.a", "fact.b"), operator="gt"),
            VerificationRule("rule.calculation", "calculation", ("fact.a", "fact.b"), operator="add", expected_fact_id="fact.total"),
        )
        ledger = ledger_for()
        result = VerificationRunner(ledger).run(self.request(rules=rules, facts=facts))

        self.assertEqual(result.outcome, VerificationOutcome.passed)
        self.assertEqual(result.confidence, 0.95)
        self.assertEqual(result.taint, Taint.untrusted)
        self.assertEqual(len(result.ledger_event_ids), 2)
        self.assertEqual([event.event_type for event in ledger.events], [
            "task.created", "verification.requested", "verification.completed",
        ])
        self.assertEqual(ledger.events[-1].payload["provenance"]["taint"], "untrusted")

    def test_failed_check_is_distinct_from_missing_evidence_review(self):
        failed = VerificationRunner(ledger_for()).run(self.request(
            rules=(VerificationRule("rule.bounds", "bounds", ("fact.a",), upper_bound=5),),
            facts=(fact("fact.a", 8),),
        ))
        self.assertEqual(failed.outcome, VerificationOutcome.failed)

        review = VerificationRunner(ledger_for()).run(self.request(
            rules=(VerificationRule("rule.missing", "source", ("fact.missing",)),),
            facts=(),
        ))
        self.assertEqual(review.outcome, VerificationOutcome.needs_review)
        self.assertIn("unavailable", review.checks[0].reason)

    def test_clearance_is_not_downgraded_and_taint_is_not_cleaned(self):
        result = VerificationRunner(ledger_for()).run(self.request(
            rules=(VerificationRule("rule.source", "source", ("fact.secret",)),),
            facts=(fact("fact.secret", "value", clearance=Clearance.secret),),
        ))
        self.assertEqual(result.outcome, VerificationOutcome.needs_review)
        self.assertEqual(result.taint, Taint.untrusted)
        self.assertEqual(result.clearance, Clearance.secret)
        self.assertEqual(result.checks[0].clearance, Clearance.secret)

    def test_missing_calculation_target_is_needs_review_not_an_exception(self):
        result = VerificationRunner(ledger_for()).run(self.request(
            rules=(VerificationRule("rule.calculation", "calculation", ("fact.a",), operator="add", expected_fact_id="fact.target"),),
            facts=(fact("fact.a", 1),),
        ))
        self.assertEqual(result.outcome, VerificationOutcome.needs_review)
        self.assertIn("unavailable", result.checks[0].reason)

    def test_timeout_and_resource_limits_fail_closed_before_completion(self):
        clock_values = iter((0.0, 1.0))
        timed_out_request = self.request(
            rules=(VerificationRule("rule.timeout", "source", ("fact.a",)),),
            facts=(fact("fact.a", 1),),
        )
        timed_out_request = replace(timed_out_request, timeout_ms=1)
        result = VerificationRunner(ledger_for(), clock=lambda: next(clock_values)).run(timed_out_request)
        self.assertEqual(result.outcome, VerificationOutcome.needs_review)
        self.assertIn("time budget", result.checks[0].reason)

        ledger = ledger_for()
        too_many_rules = tuple(
            VerificationRule(f"rule.{index}", "source", ("fact.a",))
            for index in range(1001)
        )
        with self.assertRaises(VerificationError):
            VerificationRunner(ledger).run(self.request(
                rules=too_many_rules,
                facts=(fact("fact.a", 1),),
            ))
        self.assertEqual(len(ledger.events), 1)

    def test_runner_works_with_the_durable_signed_ledger(self):
        with TemporaryDirectory() as directory:
            ledger = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"verification-key")
            ledger.append(build_event(
                event_type="task.created",
                task_id="task.verification-001",
                actor_id="test",
                actor_type="test",
                payload_contract="TaskEnvelope",
                payload_version="1.0",
                payload={"state": "created"},
                clearance=Clearance.internal,
                idempotency="task-created",
                sequence=0,
            ))
            result = VerificationRunner(ledger).run(self.request(
                rules=(VerificationRule("rule.source", "source", ("fact.a",)),),
                facts=(fact("fact.a", 1),),
            ))
            self.assertEqual(result.outcome, VerificationOutcome.passed)
            self.assertEqual([event.event_type for event in ledger.events], [
                "task.created", "verification.requested", "verification.completed",
            ])
            ledger.close()

    def test_completed_run_replays_without_appending_a_second_result(self):
        ledger = ledger_for()
        runner = VerificationRunner(ledger)
        request = self.request(
            rules=(VerificationRule("rule.source", "source", ("fact.a",)),),
            facts=(fact("fact.a", 1),),
        )
        first = runner.run(request)
        second = runner.run(request)
        self.assertEqual(second.outcome, first.outcome)
        self.assertEqual(second.ledger_event_ids, first.ledger_event_ids)
        self.assertEqual(len(ledger.events), 3)

    def test_invalid_rule_fails_before_ledger_mutation(self):
        ledger = ledger_for()
        with self.assertRaises(VerificationError):
            VerificationRunner(ledger).run(self.request(
                rules=(VerificationRule("rule.bad", "calculation", ("fact.a",), operator="divide"),),
                facts=(fact("fact.a", 1),),
            ))
        self.assertEqual(len(ledger.events), 1)


if __name__ == "__main__":
    unittest.main()
