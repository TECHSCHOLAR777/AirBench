# Freeze Core Contracts and Ledger Event Schemas Before Implementation

## Issue type

M1 contracts issue: freeze the typed interfaces and event semantics shared by the orchestrator, harness, router, workers, tools, verification framework, deliverable engine, and audit ledger.

## Objective

Freeze the core interfaces before feature implementation so components cannot drift at their seams.

AirBench is a sovereign, auditable worker system. Its components must agree on exactly what is a request, assignment, proposal, evidence item, tool result, verified result, authority decision, state transition, and ledger event.

No feature implementation may begin against informal dictionaries, undocumented JSON, prompt conventions, or model-specific payloads. Every cross-component payload must use a versioned, validated contract from this issue.

## Why this issue exists

The orchestrator, model router, workers, Tool Gateway, verification framework, deliverable engine, and ledger are independently developed boundaries. If their payloads are not frozen first, the system can silently lose provenance, misinterpret authority, fail to replay after restart, or allow one component to bypass another component's checks.

This issue creates the official internal dictionary and rulebook for AirBench. It also defines enough example traces to prove that a complex refinery/PSU inspection task can be serialized, replayed, compacted, interrupted, and resumed without dropping source, confidence, clearance, taint, authority, or audit history.

## Scope

### In scope

- Typed schemas for all listed interfaces.
- Stable identifiers and parent-child relationships.
- Schema versions and compatibility policy.
- Explicit distinction between proposals, evidence, tool results, verified results, and authority decisions.
- Immutable ledger event envelope and event catalog.
- Task state-transition table.
- Replay, restart, checkpoint, handoff, and compaction semantics.
- Fail-closed validation and ledger-commit rules.
- Example complex inspection-task traces.
- Review by orchestrator, routing, verification, harness, tool, and ledger owners.

### Out of scope

- Domain-specific refinery rules.
- Model implementation or model quality qualification.
- GPU scheduling implementation.
- File parser implementation.
- Retrieval implementation.
- DOCX rendering implementation.
- Tool implementation beyond the common `ToolAction` and result boundary.
- Engineering drawing behavior.
- Cloud or remote execution.

## Contract package layout

Create the following package before feature implementation:

```text
contracts/
  schema_registry.yaml
  compatibility_policy.md
  task_envelope.schema.yaml
  team_plan.schema.yaml
  worker_assignment.schema.yaml
  work_packet.schema.yaml
  worker_result.schema.yaml
  completion_record.schema.yaml
  model_call_request.schema.yaml
  routing_decision.schema.yaml
  team_resource_plan.schema.yaml
  tool_action.schema.yaml
  tool_result.schema.yaml
  fact_envelope.schema.yaml
  untrusted_evidence.schema.yaml
  ledger_event_envelope.schema.yaml
  ledger_event_catalog.yaml
  state_transition_table.yaml
  examples/
    inspection_task_trace.jsonl
    inspection_task_compaction_trace.jsonl
    inspection_task_failure_trace.jsonl
    inspection_task_resume_trace.jsonl
```

The exact serialization format may be YAML, JSON, or a typed Python representation, but the exported schemas must be deterministic, versioned, machine-validatable, and independently readable offline.

## Common contract rules

Every contract must declare:

- schema name;
- schema version;
- compatibility identifier;
- required fields;
- optional fields and defaults;
- enum values;
- validation constraints;
- sensitivity/clearance behavior;
- producer;
- consumer;
- authority level;
- failure behavior;