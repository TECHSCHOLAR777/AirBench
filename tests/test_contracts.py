import copy
import json
import unittest
from pathlib import Path

from contracts import ContractValidationError, Clearance, FactEnvelope, LedgerEventEnvelope, TaskEnvelope, Taint, UntrustedEvidence, idempotency_key, stable_id


FIXTURES = Path(__file__).parent / "fixtures"


class ContractTests(unittest.TestCase):
  def test_valid_task_is_typed_versioned_and_canonical(self):
    payload = json.loads((FIXTURES / "task_valid.json").read_text())
    task = TaskEnvelope.from_dict(payload)
    assert task.schema_version == "1.0"
    assert json.loads(task.canonical_json())["schema_version"] == "1.0"
    assert task.digest() == task.digest()


  def test_unknown_fields_are_rejected_without_echoing_value(self):
    payload = json.loads((FIXTURES / "task_invalid_unknown.json").read_text())
    with self.assertRaises(ContractValidationError) as caught:
        TaskEnvelope.from_dict(payload)
    error = caught.exception.to_dict()
    assert any(issue["code"] == "unknown_field" for issue in error["issues"])
    assert "secret-value" not in str(error)


  def test_wrong_primitive_type_fails_loudly(self):
    payload = json.loads((FIXTURES / "task_valid.json").read_text())
    payload["resource_budget"] = "untrusted"
    with self.assertRaises(ContractValidationError) as caught:
        TaskEnvelope.from_dict(payload)
    assert any(i.code == "type" for i in caught.exception.issues)


  def test_backward_compatible_payload_may_omit_schema_metadata(self):
    payload = json.loads((FIXTURES / "task_backward_compatible.json").read_text())
    assert TaskEnvelope.from_dict(payload).schema_version == "1.0"


  def test_stable_ids_and_idempotency_are_replayable(self):
    assert stable_id("task", "abc") == stable_id("task", "abc")
    assert stable_id("task", "abc") != stable_id("task", "def")
    assert idempotency_key("model.call", "task-1", 1) == idempotency_key("model.call", "task-1", 1)


  def test_provenance_and_taint_are_required_and_preserved(self):
    fact = FactEnvelope.from_dict({"fact_id": "fact.1", "value": 4, "source_ref": "doc:1#p2", "confidence": 0.9, "clearance": "restricted", "taint": "untrusted", "extraction_method": "ocr", "observed_at": "2026-01-01T00:00:00Z", "ingested_at": "2026-01-01T00:00:01Z"})
    assert fact.source_ref and fact.clearance.value == "restricted" and fact.taint.value == "untrusted"
    with self.assertRaises(ContractValidationError):
        UntrustedEvidence.from_dict({"evidence_id": "evidence.1", "source_ref": "upload:1", "content_hash": "a" * 64, "media_type": "text/plain", "clearance": "internal", "taint": "clean"})


  def test_resource_and_security_limits_fail_closed(self):
    payload = json.loads((FIXTURES / "task_valid.json").read_text())
    payload["request"] = "x" * 65537
    with self.assertRaises(ContractValidationError):
        TaskEnvelope.from_dict(payload)


  def test_ledger_envelope_is_versioned_and_immutable(self):
    event = LedgerEventEnvelope.from_dict({"event_id": "event.1", "event_type": "task.created", "task_id": "task.1", "parent_event_id": None, "sequence": 0, "occurred_at": "2026-01-01T00:00:00Z", "actor_id": "orchestrator.1", "actor_type": "service", "clearance": "internal", "payload_contract": "TaskEnvelope", "payload_version": "1.0", "payload_hash": "a" * 64, "idempotency_key": "b" * 64, "previous_event_hash": None, "event_hash": "c" * 64})
    self.assertTrue(event.immutable)
    with self.assertRaises((AttributeError, TypeError)):
        event.event_type = "tampered"


if __name__ == "__main__":
    unittest.main()
