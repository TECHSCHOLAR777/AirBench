import copy
import json
import unittest
from pathlib import Path

from contracts import (CompletionRecord, ContractValidationError, FactEnvelope,
                       LedgerEventEnvelope, TaskEnvelope, TeamPlan,
                       WorkerAssignment, WorkerResult, WorkPacket, HardwareProfile,
                       ModelCallRequest, RoutingDecision, TeamResourcePlan, ToolAction, Clearance,
                       Taint, UntrustedEvidence, idempotency_key, stable_id)


FIXTURES = Path(__file__).parent / "fixtures"


class ContractTests(unittest.TestCase):
  def test_m12_valid_task_team_and_worker_fixtures_are_typed(self):
    task = TaskEnvelope.from_dict(json.loads((FIXTURES / "task_valid.json").read_text()))
    team = TeamPlan.from_dict(json.loads((FIXTURES / "team_valid.json").read_text()))
    assignment = WorkerAssignment.from_dict(json.loads((FIXTURES / "worker_assignment_valid.json").read_text()))
    packet = WorkPacket.from_dict(json.loads((FIXTURES / "work_packet_valid.json").read_text()))
    result = WorkerResult.from_dict(json.loads((FIXTURES / "worker_result_valid.json").read_text()))
    completion = CompletionRecord.from_dict(json.loads((FIXTURES / "completion_valid.json").read_text()))
    assert task.task_id == "task.inspection-001"
    assert team.task_id == task.task_id
    assert assignment.team_id == team.team_id
    assert packet.team_id == team.team_id
    assert result.assignment_id == assignment.assignment_id
    assert completion.task_id == task.task_id


  def test_m12_invalid_fixtures_fail_closed(self):
    invalid = [
        (TeamPlan, "team_invalid_unknown.json"),
        (WorkerAssignment, "worker_assignment_invalid_timeout.json"),
        (WorkPacket, "work_packet_invalid_provenance.json"),
        (WorkerResult, "worker_result_invalid_authority.json"),
        (CompletionRecord, "completion_invalid_criteria.json"),
    ]
    for contract, filename in invalid:
      with self.subTest(contract=contract.__name__):
        with self.assertRaises(ContractValidationError):
          contract.from_dict(json.loads((FIXTURES / filename).read_text()))


  def test_worker_result_cannot_claim_verification_or_completion(self):
    payload = json.loads((FIXTURES / "worker_result_valid.json").read_text())
    payload["status"] = "verified"
    with self.assertRaises(ContractValidationError):
      WorkerResult.from_dict(payload)


  def test_team_requires_verification_and_positive_concurrency(self):
    payload = json.loads((FIXTURES / "team_valid.json").read_text())
    payload["required_verification"] = False
    with self.assertRaises(ContractValidationError):
      TeamPlan.from_dict(payload)


  def test_m13_valid_routing_resource_and_hardware_fixtures_are_typed(self):
    hardware = HardwareProfile.from_dict(json.loads((FIXTURES / "hardware_profile_96gb_valid.json").read_text()))
    request = ModelCallRequest.from_dict(json.loads((FIXTURES / "model_call_request_valid.json").read_text()))
    route = RoutingDecision.from_dict(json.loads((FIXTURES / "routing_decision_valid.json").read_text()))
    resource = TeamResourcePlan.from_dict(json.loads((FIXTURES / "team_resource_plan_valid.json").read_text()))
    assert hardware.vram_bytes == 96 * 1024**3
    assert request.role == "vision_worker"
    assert route.resource_admission == "admitted"
    assert resource.verifier_capacity == 1


  def test_m13_security_and_resource_failures_are_rejected(self):
    hardware = json.loads((FIXTURES / "hardware_profile_96gb_valid.json").read_text())
    hardware["vram_bytes"] = -1
    with self.assertRaises(ContractValidationError):
      HardwareProfile.from_dict(hardware)
    request = json.loads((FIXTURES / "model_call_request_valid.json").read_text())
    request["resource_lease_id"] = ""
    with self.assertRaises(ContractValidationError):
      ModelCallRequest.from_dict(request)
    action = json.loads((FIXTURES / "tool_action_invalid_taint.json").read_text())
    with self.assertRaises(ContractValidationError):
      ToolAction.from_dict(action)
    payload = json.loads((FIXTURES / "team_valid.json").read_text())
    payload["concurrency_ceiling"] = 0
    with self.assertRaises(ContractValidationError):
      TeamPlan.from_dict(payload)
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


  def test_invalid_enum_is_a_structured_contract_error(self):
    payload = json.loads((FIXTURES / "task_valid.json").read_text())
    payload["clearance"] = "top-secret-unknown"
    with self.assertRaises(ContractValidationError) as caught:
        TaskEnvelope.from_dict(payload)
    self.assertTrue(any(i.code == "enum" for i in caught.exception.issues))


if __name__ == "__main__":
    unittest.main()
