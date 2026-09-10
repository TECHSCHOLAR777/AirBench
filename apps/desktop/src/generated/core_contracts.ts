// AUTO-GENERATED FILE. DO NOT EDIT.
// Source of truth: src/contracts/models.py and its ledger event catalog.

export const CORE_CONTRACT_SCHEMA_VERSION = "1.0" as const;
export const CORE_CONTRACT_COMPATIBILITY_ID = "airbench-core-contracts" as const;
export const NODE_PROTOCOL_VERSION = "0.1" as const;
export const NODE_PROTOCOL_COMPATIBILITY_ID = "airbench-node-protocol" as const;

export type Clearance = "public" | "internal" | "restricted" | "secret";
export type Taint = "clean" | "untrusted" | "contaminated";
export type ContractStatus = "proposed" | "accepted" | "rejected" | "failed" | "needs_review" | "queued" | "cancelled" | "verified";
export type LeaseStatus = "requested" | "granted" | "active" | "released" | "expired" | "cancelled" | "revoked" | "failed";
export type BarrierStatus = "waiting" | "completed" | "missing" | "conflicting" | "timed_out" | "cancelled" | "needs_review";
export type NodeTaskStatus = "accepted" | "planning" | "running" | "needs_review" | "completed" | "blocked" | "failed" | "stopped";

export const LEDGER_EVENT_TYPES = [
  "artifact.checked",
  "artifact.downloaded",
  "artifact.integrity.verified",
  "artifact.previewed",
  "artifact.staged",
  "authority.decided",
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
  "consistency.checked",
  "crash.recovered",
  "endpoint.egress.denied",
  "endpoint.rejected",
  "endpoint.request.completed",
  "endpoint.request.failed",
  "endpoint.request.started",
  "endpoint.selected",
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
  "index.completed",
  "index.failed",
  "index.requested",
  "join_barrier.completed",
  "join_barrier.resolved",
  "join_barrier.waiting",
  "lifecycle.blocked",
  "lifecycle.intercepted",
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
  "resource.lease.activated",
  "resource.lease.cancelled",
  "resource.lease.expired",
  "resource.lease.failed",
  "resource.lease.granted",
  "resource.lease.released",
  "resource.plan.admitted",
  "resource.plan.queued",
  "resource.queue.updated",
  "resource.recovered",
  "retrieval.completed",
  "retrieval.failed",
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
  "task.plan.approved",
  "task.plan.committed",
  "team.created",
  "team.execution.cancelled",
  "team.execution.completed",
  "team.execution.failed",
  "team.execution.started",
  "team.resource_plan.admitted",
  "team.resource_plan.cancelled",
  "team.resource_plan.created",
  "team.resource_plan.degraded_needs_review",
  "team.resource_plan.queued",
  "team.resource_plan.rejected",
  "team.resource_plan.released",
  "tool.authorized",
  "tool.denied",
  "tool.requested",
  "tool.result",
  "verification.completed",
  "verification.evaluator.completed",
  "verification.evaluator.requested",
  "verification.requested",
  "verification.reservation.confirmed",
  "vision.completed",
  "vision.failed",
  "vision.requested",
  "worker.assigned",
  "worker.cancelled",
  "worker.completed",
  "worker.context.compacted",
  "worker.failed",
  "worker.handoff",
  "worker.handoff.late",
  "worker.handoff.rejected",
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

export interface NodeWireContractEnvelope {
  schemaVersion: string;
  compatibilityId: string;
}

export interface NodeLifecycleEventPayload {
  phase: string;
  status: NodeTaskStatus;
  summary?: string | null;
}

export interface NodeWorkerEventPayload {
  role: string;
  label: string;
  status: string;
  teamId?: string | null;
  assignmentId?: string | null;
  workerId?: string | null;
  resourceLeaseId?: string | null;
}

export interface NodeExecutionEventPayload {
  status: string;
  summary: string;
  executionMode?: string | null;
  teamId?: string | null;
  planId?: string | null;
  assignmentId?: string | null;
  workerId?: string | null;
  role?: string | null;
  label?: string | null;
  barrierId?: string | null;
  dependencyIds?: Array<string>;
  resourceLeaseId?: string | null;
  queuePosition?: number | null;
  hardwareProfileRef?: string | null;
  modelTargetId?: string | null;
  qualificationId?: string | null;
}

export interface NodeEvidenceEventPayload {
  evidence: NodeEvidenceRef;
}

export interface NodeVerificationEventPayload {
  summary: string;
  passed: boolean;
}

export interface NodeApprovalEventPayload {
  reason: string;
}

export interface NodeArtifactEventPayload {
  artifactId: string;
}

export interface NodeSummaryEventPayload {
  summary: string;
}

export interface NodeUnknownEventPayload {
  originalType: string;
  raw: unknown;
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
  title?: string;
  project_ref?: string | null;
  priority?: string;
  deadline?: string | null;
  input_manifest_refs?: Array<string>;
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

export interface TaskPlanReview extends ContractEnvelope {
  task_id: string;
  node_identity: string;
  protocol_version: string;
  clearance_context: Clearance;
  plan_state: string;
  task_sequence: number;
  team_id: string | null;
  assignments: Array<string>;
  dependency_graph: Record<string, Array<string>>;
  concurrency_ceiling: number;
  execution_mode: string;
  worker_capabilities: Record<string, string>;
  hardware_profile_ref: string | null;
  hardware_reason: string;
  required_verification: boolean;
  completion_criteria: Array<string>;
  required_authority: string;
  authority_reason: string;
  plan_version_hash: string | null;
  policy_version_hash: string | null;
  ledger_event_ref: string | null;
  failure_code?: string | null;
  failure_reason?: string | null;
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

export interface HandoffSubmission extends ContractEnvelope {
  handoff_id: string;
  task_id: string;
  team_id: string;
  source_assignment_id: string;
  source_worker_id: string;
  destination_assignment_id: string;
  destination_stage: string;
  packet: WorkPacket;
  packet_hash: string;
  barrier_id: string;
  barrier_version: number;
  source_lease_id: string;
  plan_version: string;
  policy_version_hash: string;
  clearance: Clearance;
  taint: Taint;
  submitted_at: string;
  deadline: string;
  idempotency_key: string;
  artifact_hashes?: Array<[string, string]>;
  attempt?: number;
}

export interface JoinBarrier extends ContractEnvelope {
  barrier_id: string;
  task_id: string;
  team_id: string;
  destination_assignment_id: string;
  destination_stage: string;
  plan_version: string;
  barrier_version: number;
  required_predecessor_assignment_ids: Array<string>;
  accepted_handoff_ids: Array<string>;
  accepted_packet_hashes: Array<[string, string]>;
  missing_assignment_ids: Array<string>;
  conflict_packet_refs: Array<[string, string]>;
  deadline: string;
  join_policy: string;
  status: BarrierStatus;
  clearance: Clearance;
  taint: Taint;
  policy_version_hash: string;
  idempotency_key: string;
  created_at: string;
  unresolved_questions?: Array<string>;
  lease_refs?: Array<string>;
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

export interface StageSignals extends ContractEnvelope {
  exploration?: boolean;
  error_severity?: string;
  spinning?: boolean;
  recent_production?: boolean;
  test_result?: string;
  context_pressure?: string;
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
  stage?: string;
  previous_verification_status?: string;
  stage_signals?: StageSignals;
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
  stage?: string;
  stage_signals?: StageSignals;
  routing_mode?: string;
  escalation_sticky?: boolean;
  attempt?: number;
  task_id?: string;
  team_id?: string;
  worker_id?: string;
  resource_lease_id?: string;
  hardware_profile_ref?: string;
  selected_artifact_digest?: string;
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
  plan_id?: string;
  hardware_profile_id?: string;
  plan_version?: string;
  created_at?: string;
  requested_mode?: string;
  admitted_mode?: string;
  admission_reason?: string;
  dependency_graph?: Record<string, Array<string>>;
  scheduling?: Record<string, string>;
  safety_invariants?: Record<string, boolean | string>;
  provenance?: Record<string, unknown>;
  residency_requests?: Record<string, string>;
  reservation_records?: Array<ResourceReservation>;
}

export interface ResourceReservation extends ContractEnvelope {
  worker_id: string;
  role: string;
  capability: string;
  model_target_id: string;
  qualification_id: string;
  gpu_indices: Array<number>;
  vram_reserved_bytes: number;
  cpu_reserved_millicores: number;
  ram_reserved_bytes: number;
  scratch_reserved_bytes: number;
  context_tokens_reserved: number;
  kv_cache_reserved_bytes: number;
  residency: string;
  slots_reserved?: number;
  start_deadline?: string | null;
  execution_deadline?: string | null;
}

export interface ResourceLease extends ContractEnvelope {
  lease_id: string;
  task_id: string;
  team_id: string;
  plan_id: string;
  worker_id: string;
  role: string;
  capability: string;
  hardware_profile_ref: string;
  measurement_id: string;
  reservation: Array<[string, number]>;
  residency: string;
  clearance: Clearance;
  taint: Taint;
  policy_version_hash: string;
  idempotency_key: string;
  issued_at: string;
  expires_at: string;
  status: LeaseStatus;
  model_target_id?: string | null;
  qualification_id?: string | null;
  version?: number;
  provenance_refs?: Array<string>;
  gpu_indices?: Array<number>;
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

export interface NodeHandshake extends ContractEnvelope {
  node_identity: string;
  protocol_version: string;
  protocol_compatibility_id: string;
  supported_protocol_versions: Array<string>;
  clearance_context: Clearance;
  authenticated_subject: string;
  domain_pack_ref: string;
  ledger_event_ref: string;
}

export interface NodeProvenanceRef extends NodeWireContractEnvelope {
  sourceDocumentId: string;
  sourceVersion: string;
  location: Record<string, unknown> | null;
  extractionMethod: string;
  observedAt: string | null;
  ingestedAt: string;
  ledgerEventRef: string;
}

export interface NodeEvidenceRef extends NodeWireContractEnvelope {
  evidenceId: string;
  contentHash: string;
  source: NodeProvenanceRef;
  confidence: number;
  clearance: Clearance;
  taint: Taint;
}

export interface NodeFactRef extends NodeWireContractEnvelope {
  factId: string;
  value: unknown;
  source: NodeProvenanceRef;
  confidence: number;
  clearance: Clearance;
  taint: Taint;
  parentFactIds: Array<string>;
  unit: string | null;
  derivation: Record<string, unknown> | null;
  supersededBy: string | null;
}

export interface NodeRouteTraceEntry extends NodeWireContractEnvelope {
  sequence: number;
  eventType: string;
  occurredAt: string;
  actor: string;
  clearanceContext: Clearance;
  ledgerEventRef: string;
  payloadHash: string;
  requestId?: string | null;
  workerId?: string | null;
  role?: string | null;
  taskKind?: string | null;
  requiredCapability?: string | null;
  selectedTarget?: string | null;
  decisionSource?: string | null;
  ruleOrThreshold?: string | null;
  qualificationCertificate?: string | null;
  fallbackTarget?: string | null;
  reason?: string | null;
  status?: string | null;
  eligibleTargets?: Array<string>;
}

export interface NodeRouteTrace extends NodeWireContractEnvelope {
  taskId: string;
  nodeIdentity: string;
  protocolVersion: string;
  clearanceContext: Clearance;
  entries: Array<NodeRouteTraceEntry>;
}

export interface NodeTaskSnapshot extends NodeWireContractEnvelope {
  taskId: string;
  snapshotId: string;
  asOfSequence: number;
  title: string;
  requestSummary: string;
  status: NodeTaskStatus;
  phase: string;
  clearanceContext: Clearance;
  inputManifestRef: string;
  evidence: Array<NodeEvidenceRef>;
  facts: Array<NodeFactRef>;
  artifactRefs: Array<string>;
  unresolvedQuestions: Array<string>;
  nodeConnectionRef: string;
  ledgerHeadRef: string;
}

export interface NodeArtifactReview extends NodeWireContractEnvelope {
  taskId: string;
  artifactId: string;
  nodeIdentity: string;
  protocolVersion: string;
  clearanceContext: Clearance;
  title: string;
  mediaType: string;
  fileFormat: string;
  templateId: string;
  templateVersion: string;
  contentHash: string;
  byteSize: number;
  status: string;
  verificationStatus: string;
  structuralCheck: string;
  visualCheck: string;
  approvalState: string;
  approvalBlockingReasons: Array<string>;
  sourceRefs: Array<string>;
  evidenceRefs: Array<string>;
  verificationRefs: Array<string>;
  deterministicValueRefs: Array<string>;
  confidence: number;
  clearance: Clearance;
  taint: Taint;
  derivation: Record<string, unknown>;
  previewRef: string;
  downloadRef: string;
  ledgerEventRef: string;
  artifactSequence: number;
  createdAt: string;
}

export interface NodeTaskEvent extends NodeWireContractEnvelope {
  eventId: string;
  taskId: string;
  sequence: number;
  eventType: string;
  occurredAt: string;
  actor: string;
  clearanceContext: Clearance;
  payloadHash: string;
  ledgerEventRef: string;
  payload: Record<string, unknown>;
}

export interface NodeTaskEventBatch extends ContractEnvelope {
  stream_id: string;
  node_identity: string;
  protocol_version: string;
  clearance_context: Clearance;
  events: Array<NodeTaskEvent>;
  next_sequence: number;
  has_more: boolean;
  ledger_event_refs: Array<string>;
}
