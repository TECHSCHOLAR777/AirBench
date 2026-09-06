import json
import socket
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from contracts import (Clearance, EventLedger, IdempotencyConflict, ProjectionBuilder,
                       ProvenanceRejected, ReplayRejected, SQLiteLedgerStore,
                       StorageFailure, build_event, verify_projection_export,
                       verify_signed_export)


FIXTURES = Path(__file__).parent / "fixtures" / "m2_acceptance"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_event(spec, sequence, previous=None):
    return build_event(event_type=spec["event_type"], task_id=spec["task_id"], actor_id=spec["actor_id"], actor_type=spec["actor_type"], payload_contract=spec["payload_contract"], payload_version=spec["payload_version"], payload=spec["payload"], clearance=Clearance(spec["clearance"]), idempotency=spec["idempotency"], sequence=sequence, previous_event_hash=previous)


class M24AcceptanceTests(unittest.TestCase):
    def test_fixture_chain_is_replayable_and_signed_exports_verify_offline(self):
        with TemporaryDirectory() as directory:
            key = b"m24-test-key"
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", key)
            events = []
            previous = None
            for sequence, spec in enumerate(fixture("events.json")):
                event = make_event(spec, sequence, previous)
                events.append(event)
                previous = event.event_hash
            store.append_batch(events, "transaction.m24-fixture")
            ledger_export = store.signed_export(Clearance.internal)
            projection_export = ProjectionBuilder(store, key).signed_export("evidence", Clearance.internal)
            with patch.object(socket, "socket", side_effect=AssertionError("network access is forbidden")):
                self.assertTrue(verify_signed_export(ledger_export, key))
                self.assertTrue(verify_projection_export(projection_export, key))
                tampered_export = dict(ledger_export)
                tampered_export["events"] = list(ledger_export["events"])
                tampered_export["events"][0] = dict(tampered_export["events"][0], actor_id="attacker")
                self.assertFalse(verify_signed_export(tampered_export, key))
            store.close()

    def test_tampering_duplicate_events_and_clearance_leaks_fail(self):
        ledger = EventLedger()
        original = make_event(fixture("events.json")[0], 0)
        ledger.append(original)
        with self.assertRaises(ReplayRejected):
            ledger.append(replace(original, idempotency_key="m24-tampered-replay", event_hash="f" * 64, sequence=1, previous_event_hash=original.event_hash))
        with self.assertRaises(IdempotencyConflict):
            ledger.append(replace(original, payload_hash="0" * 64, event_hash="0" * 64))

        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"key")
            events = []
            previous = None
            for sequence, spec in enumerate(fixture("events.json")):
                event = make_event(spec, sequence, previous)
                events.append(event)
                previous = event.event_hash
            store.append_batch(events, "transaction.clearance")
            public = ProjectionBuilder(store, b"key").signed_export("audit", Clearance.public)
            self.assertFalse(any(item["clearance"] in {"internal", "restricted", "secret"} for item in public["records"]))
            store.close()

    def test_missing_provenance_and_partial_transactions_leave_no_events(self):
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"key")
            first = make_event(fixture("events.json")[0], 0)
            missing = fixture("missing_provenance.json")
            invalid = make_event(missing, 1, first.event_hash)
            with self.assertRaises(StorageFailure) as caught:
                store.append_batch([first, invalid], "transaction.partial")
            self.assertIsInstance(caught.exception.__cause__, ProvenanceRejected)
            self.assertEqual(store.events, ())
            store.close()

    def test_failed_storage_write_is_visible_and_does_not_commit(self):
        class FailingConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, sql, *args):
                if sql.strip() == "BEGIN IMMEDIATE":
                    raise sqlite3.OperationalError("simulated disk failure")
                return self.connection.execute(sql, *args)

            def rollback(self):
                return self.connection.rollback()

        import sqlite3
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"key")
            event = make_event(fixture("events.json")[0], 0)
            underlying = store._db
            store._db = FailingConnection(underlying)
            with self.assertRaises(StorageFailure):
                store.append(event)
            store._db = underlying
            self.assertEqual(store.events, ())
            store.close()


if __name__ == "__main__":
    unittest.main()
