// AUTO-GENERATED FILE. DO NOT EDIT.
// Source of truth: contracts/models.py and its ledger event catalog.

export const CORE_CONTRACT_SCHEMA_VERSION = "1.0" as const;
export const CORE_CONTRACT_COMPATIBILITY_ID = "airbench-core-contracts" as const;

export type Clearance = "public" | "internal" | "restricted" | "secret";
export type Taint = "clean" | "untrusted" | "contaminated";
export type ContractStatus = "proposed" | "accepted" | "rejected" | "failed" | "needs_review" | "queued" | "cancelled" | "verified";

export const LEDGER_EVENT_TYPES = [
  "artifact.checked",
  "artifact.integrity.verified",
  "artifact.staged",
  "backend.airgap_startup.checked",
  "backend.compatibility.completed",
  "backend.compatibility.started",
  "backend.nim.checked",
  "background.work.yielded",
  "barrier.completed",
  "barrier.waiting",
  "checkpoint.committed",
  "completion.blocked",
  "completion.ready",
  "completion.recorded",
  "crash.recovered",
  "escalation.required",
  "evidence.created",
  "execution.mode.changed",
  "execution.mode.selected",
  "fact.candidate",
  "fact.committed",
  "fallback.selected",
  "hardware.measurement.completed",
  "hardware.measurement.started",
  "hardware.profile.loaded",
  "hardware.profile.measured",
  "human.review.required",
  "human.signoff",
  "join_barrier.completed",
  "join_barrier.waiting",
  "model.artifact.integrity.verified",
  "model.benchmark.completed",
  "model.benchmark.started",
  "model.call.completed",
  "model.call.failed",
  "model.call.started",
  "model.evicted",
  "model.failed",
  "model.lifecycle.tested",
  "model.loaded",
  "model.multimodal.tested",
  "model.qualification.checked",
  "model.registry.loaded",
  "model.registry.signature.verified",
  "model.requested",
  "model.resident",
  "model.responded",
  "model.structured_output.tested",
  "model.target.qualified",
  "model.target.rejected",
  "model.tool_call.tested",
  "model.unloaded",
  "model.variant.qualified",
  "projection.exported",
  "projection.rebuilt",
  "recovery.resumed",
  "resource.admission.degraded",
  "resource.exhaustion.detected",
  "resource.lease.granted",
  "resource.lease.released",
  "resource.plan.admitted",
  "resource.plan.queued",
  "resource.queue.updated",
  "resource.recovered",
  "retrieval.requested",
  "retry.completed",
  "retry.failed",
  "retry.started",
  "routing.decided",
  "routing.decision",
  "routing.fallback.selected",
  "routing.queued",
  "side_effect.committed",
  "side_effect.reserved",
  "side_effect.uncertain",
  "task.authorized",
  "task.cancelled",
  "task.checkpoint.committed",
  "task.created",
  "task.failed",
  "task.plan.committed",
  "team.created",
  "team.resource_plan.admitted",
  "team.resource_plan.created",
  "team.resource_plan.degraded_needs_review",
  "team.resource_plan.queued",
  "team.resource_plan.rejected",
  "tool.authorized",
  "tool.denied",
  "tool.requested",
  "tool.result",
  "verification.completed",
  "verification.requested",
  "verification.reservation.confirmed",
  "worker.assigned",
  "worker.cancelled",
  "worker.completed",
  "worker.failed",
  "worker.handoff",
  "worker.preempted",
  "worker.resource_reserved",
  "worker.started",
  "world_model.requested",
] as const;
export type LedgerEventType = typeof LEDGER_EVENT_TYPES[number];

export interface ContractEnvelope {
  schema_version: string;
  compatibility_id: string;
}

export interface TaskEnvelope extends ContractEnvelope {
  task_id: string;
  principal_id: string;
  clearance: Clearance;
  request: string;
  domain_pack_ref: string;
  risk_class: string;
  autonomy_ceiling: string;
  allowed_evidence_scope: Array<string>;
  permitted_worker_capabilities: Array<string>;
  permitted_tools: Array<string>;
  output_contract: string;
  verification_criteria: Array<string>;
  resource_budget: Record<string, number>;
  state?: string;
  parent_task_id?: string | null;
  created_at?: string;
}

export interface TeamPlan extends ContractEnvelope {
  team_id: string;
  task_id: string;
  assignments: Array<string>;
  dependency_graph: Record<string, Array<string>>;
  concurrency_ceiling: number;
  required_verification: boolean;
  completion_criteria: Array<string>;
  plan_version_hash: string;
  policy_version_hash: string;
  status?: ContractStatus;
}

export interface WorkerAssignment extends ContractEnvelope {
  assignment_id: string;
  team_id: string;
  task_id: string;
  worker_id: string;
  role: string;
  stage: string;
  input_schema: string;
  output_schema: string;
  evidence_refs: Array<string>;
  allowed_tools: Array<string>;
  clearance: Clearance;
  taint: Taint;
  capability_requirement: string;
  deadline: string;
  idempotency_key: string;
  status?: ContractStatus;
}

export interface WorkPacket extends ContractEnvelope {
  packet_id: string;
  task_id: string;
  team_id: string;
  source_worker_id: string;
  destination_stage: string;
  fact_refs: Array<string>;
  evidence_refs: Array<string>;
  artifact_refs: Array<string>;
  checks: Record<string, boolean>;
  unresolved_questions: Array<string>;
  proposed_next_result: string;
  clearance: Clearance;
  taint: Taint;
  packet_hash: string;
}

export interface WorkerResult extends ContractEnvelope {
  result_id: string;
  assignment_id: string;
  task_id: string;
  status: ContractStatus;
  output?: unknown;
  packet_ref?: string | null;
  failure_code?: string | null;
  retryable?: boolean;
  completed_at?: string;
}

export interface CompletionRecord extends ContractEnvelope {
  completion_id: string;
  task_id: string;
  final_state: string;
  required_evidence_refs: Array<string>;
  verification_refs: Array<string>;
  artifact_hashes: Array<string>;
  human_review_ref: string | null;
  policy_version_hash: string;
  pack_version_hash: string;
  model_identities: Array<string>;
  hardware_identity: string;
  completed_at?: string;
}

export interface ModelCallRequest extends ContractEnvelope {
  request_id: string;
  task_id: string;
  team_id: string | null;
  worker_id: string | null;
  task_kind: string;
  modality: string;
  required_capability: string;
  evidence_summary: Array<string>;
  clearance: Clearance;
  action_risk: string;
  resource_budget: Record<string, number>;
  attempt: number;
  idempotency_key: string;
  timeout_ms: number;
  role?: string;
  resource_lease_id?: string;
}

export interface RoutingDecision extends ContractEnvelope {
  decision_id: string;
  request_id: string;
  eligible_targets: Array<string>;
  selected_target: string | null;
  policy_version_hash: string;
  decision_source: string;
  rule_or_threshold: string;
  qualification_certificate: string;
  session_affinity: string;
  fallback_target: string | null;
  resource_admission: string;
  status: ContractStatus;
  reason: string;
}

export interface TeamResourcePlan extends ContractEnvelope {
  team_id: string;
  hardware_profile_ref: string;
  worker_capabilities: Record<string, string>;
  reservations: Record<string, Record<string, number>>;
  concurrency_ceiling: number;
  execution_mode: string;
  priority: string;
  verifier_capacity: number;
  admission: string;
  reason: string;
  task_id?: string;
}

export interface HardwareProfile extends ContractEnvelope {
  profile_id: string;
  gpu_model: string;
  gpu_count: number;
  vram_bytes: number;
  driver_version: string;
  accelerator_runtime: string;
  cpu_model: string;
  cpu_cores: number;
  ram_bytes: number;
  storage_bytes: number;
  scratch_bytes: number;
  model_context_tokens: number;
  kv_cache_bytes: number;
  safe_parallel_slots: number;
  egress_policy: string;
  measurement_hash: string;
  supported_execution_modes?: Array<string>;
  network_check_id?: string;
  sandbox_runtime?: string;
  benchmark_result_ref?: string;
}

export interface ToolAction extends ContractEnvelope {
  action_id: string;
  task_id: string;
  worker_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  path_scope: Array<string>;
  clearance: Clearance;
  taint: Taint;
  risk_class: string;
  timeout_ms: number;
  idempotency_key: string;
  status?: ContractStatus;
}

export interface FactEnvelope extends ContractEnvelope {
  fact_id: string;
  value: unknown;
  source_ref: string;
  confidence: number;
  clearance: Clearance;
  taint: Taint;
  extraction_method: string;
  observed_at: string;
  ingested_at: string;
  parent_fact_ids?: Array<string>;
  unit?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  supersedes_fact_id?: string | null;
}

export interface UntrustedEvidence extends ContractEnvelope {
  evidence_id: string;
  source_ref: string;
  content_hash: string;
  media_type: string;
  clearance: Clearance;
  taint?: Taint;
  captured_at?: string;
  byte_size?: number;
  excerpt_ref?: string | null;
}

export interface LedgerEventEnvelope extends ContractEnvelope {
  event_id: string;
  event_type: LedgerEventType;
  task_id: string;
  parent_event_id: string | null;
  sequence: number;
  occurred_at: string;
  actor_id: string;
  actor_type: string;
  clearance: Clearance;
  payload_contract: string;
  payload_version: string;
  payload_hash: string;
  idempotency_key: string;
  previous_event_hash: string | null;
  event_hash: string;
  immutable?: boolean;
  payload?: Record<string, unknown>;
}

export interface NodeCommandEnvelope extends ContractEnvelope {
  command_id: string;
  task_id: string | null;
  actor: string;
  expected_sequence: number | null;
  idempotency_key: string;
  client_version: string;
  command_type: string;
  arguments: Record<string, unknown>;
}

export interface NodeCommandResult extends ContractEnvelope {
  outcome: "accepted" | "rejected" | "needs_review";
  command_id: string;
  task_id: string | null;
  idempotency_key: string;
  ledger_event_ref: string | null;
  sequence: number | null;
  state: string | null;
  node_identity: string;
  protocol_version: string;
  clearance_context: Clearance;
  event_type?: string | null;
  code?: string | null;
  message?: string | null;
  reason?: string | null;
}
