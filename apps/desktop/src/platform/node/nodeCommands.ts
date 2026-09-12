import { invoke } from "@airbench/tauri-invoke";
import { CORE_CONTRACT_COMPATIBILITY_ID, CORE_CONTRACT_SCHEMA_VERSION, NODE_PROTOCOL_COMPATIBILITY_ID, NODE_PROTOCOL_VERSION } from "../../generated/core_contracts";
import type { ApprovedNodeProfileReference } from "./nodeConnection";
import type { Clearance, TaskSnapshot, Taint } from "../events/protocol";
import type { NodeArtifactReview, NodeCommandEnvelope, NodeCommandResult, NodeEvidenceRef, NodeFactRef, NodeProvenanceRef, NodeRouteTrace, NodeRouteTraceEntry, TaskEnvelope, TaskPlanReview } from "../../generated/core_contracts";

const TASK_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const COMMAND_ID = /^[a-z0-9][a-z0-9._:-]{0,127}$/;

export type TaskCommandType = "task.authorize" | "task.approve_plan" | "task.cancel" | "task.request_review" | "task.approve_artifact" | "task.return_artifact";

export interface CreateTaskResponse {
  task: TaskEnvelope;
  snapshot: TaskSnapshot;
  ledger_event_ref: string;
  command: NodeCommandResult;
}

class InvalidNodeResponse extends Error {
  readonly code = "invalid_node_response";
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new InvalidNodeResponse(`The Node returned an invalid ${label}.`);
  return value as Record<string, unknown>;
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) throw new InvalidNodeResponse(`The Node returned an invalid ${label}.`);
  return value;
}

function requireNodeReference(value: unknown, label: string): string {
  const result = requireString(value, label);
  if (result.length > 256 || result.includes("..") || !/^[A-Za-z0-9._:-]+$/.test(result)) {
    throw new InvalidNodeResponse(`The Node returned an invalid ${label} reference.`);
  }
  return result;
}

function optionalString(value: unknown, label: string): string | null {
  if (value === null || value === undefined) return null;
  return requireString(value, label);
}

function requireSequence(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new InvalidNodeResponse(`The Node returned an invalid ${label}.`);
  return value;
}

function requireBoolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new InvalidNodeResponse(`The Node returned an invalid ${label}.`);
  return value;
}

function requireClearance(value: unknown): Clearance {
  if (value !== "public" && value !== "internal" && value !== "restricted" && value !== "secret") {
    throw new InvalidNodeResponse("The Node returned an invalid response clearance.");
  }
  return value;
}

function requireStringList(value: unknown, label: string): string[] {
  if (!Array.isArray(value)) throw new InvalidNodeResponse(`The Node returned an invalid ${label}.`);
  return value.map((entry) => requireString(entry, label));
}

function requireNumberMap(value: unknown, label: string): Record<string, number> {
  const source = requireRecord(value, label);
  return Object.fromEntries(Object.entries(source).map(([key, entry]) => {
    if (!/^[A-Za-z0-9_.:-]{1,128}$/.test(key) || typeof entry !== "number" || !Number.isSafeInteger(entry) || entry < 0) {
      throw new InvalidNodeResponse(`The Node returned an invalid ${label}.`);
    }
    return [key, entry];
  }));
}

function requireStringMap(value: unknown, label: string): Record<string, string> {
  const source = requireRecord(value, label);
  return Object.fromEntries(Object.entries(source).map(([key, entry]) => [requireString(key, label), requireString(entry, label)]));
}

function requireDependencyGraph(value: unknown): Record<string, string[]> {
  const source = requireRecord(value, "plan dependency graph");
  return Object.fromEntries(Object.entries(source).map(([key, entry]) => [requireString(key, "plan stage"), requireStringList(entry, "plan dependency reference")]));
}

function optionalFailureField(value: unknown, label: string): string | null {
  return optionalString(value, label);
}

function requiredField(source: Record<string, unknown>, key: string, label: string): unknown {
  if (!Object.prototype.hasOwnProperty.call(source, key)) throw new InvalidNodeResponse(`The Node returned an invalid ${label}.`);
  return source[key];
}

function requiredNullableString(source: Record<string, unknown>, key: string, label: string): string | null {
  return optionalString(requiredField(source, key, label), label);
}

function requiredNullableRecord(source: Record<string, unknown>, key: string, label: string): Record<string, unknown> | null {
  const value = requiredField(source, key, label);
  return value === null ? null : requireRecord(value, label);
}

function requireConfidence(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    throw new InvalidNodeResponse(`The Node returned an invalid ${label}.`);
  }
  return value;
}

function requireTaint(value: unknown): Taint {
  if (value !== "clean" && value !== "untrusted" && value !== "contaminated") {
    throw new InvalidNodeResponse("The Node returned an invalid response taint.");
  }
  return value;
}

function requireTaskStatus(value: unknown): TaskSnapshot["status"] {
  if (value !== "accepted" && value !== "planning" && value !== "running" && value !== "needs_review" && value !== "completed" && value !== "blocked" && value !== "failed" && value !== "stopped") {
    throw new InvalidNodeResponse("The Node returned an invalid task status.");
  }
  return value;
}

function requireNodeEnvelope(source: Record<string, unknown>, label: string): { schemaVersion: string; compatibilityId: string } {
  const schemaVersion = requireString(source.schemaVersion, `${label} schema version`);
  const compatibilityId = requireString(source.compatibilityId, `${label} compatibility identity`);
  if (schemaVersion !== NODE_PROTOCOL_VERSION || compatibilityId !== NODE_PROTOCOL_COMPATIBILITY_ID) {
    throw new InvalidNodeResponse(`The Node returned an incompatible ${label}.`);
  }
  return { schemaVersion, compatibilityId };
}

function clearanceRank(value: Clearance): number {
  return { public: 0, internal: 1, restricted: 2, secret: 3 }[value];
}

function requireClearanceWithin(value: unknown, maximum: Clearance, label: string): Clearance {
  const clearance = requireClearance(value);
  if (clearanceRank(clearance) > clearanceRank(maximum)) {
    throw new InvalidNodeResponse(`The Node returned ${label} above the approved clearance.`);
  }
  return clearance;
}

function validateProvenanceRef(value: unknown): NodeProvenanceRef {
  const source = requireRecord(value, "provenance reference");
  const envelope = requireNodeEnvelope(source, "provenance reference");
  return {
    ...envelope,
    sourceDocumentId: requireString(source.sourceDocumentId, "source document identity"),
    sourceVersion: requireString(source.sourceVersion, "source document version"),
    location: requiredNullableRecord(source, "location", "provenance location"),
    extractionMethod: requireString(source.extractionMethod, "extraction method"),
    observedAt: requiredNullableString(source, "observedAt", "observation timestamp"),
    ingestedAt: requireString(source.ingestedAt, "ingestion timestamp"),
    ledgerEventRef: requireString(source.ledgerEventRef, "provenance ledger reference"),
  };
}

function validateEvidenceRef(value: unknown, maximumClearance: Clearance): NodeEvidenceRef {
  const source = requireRecord(value, "evidence reference");
  const envelope = requireNodeEnvelope(source, "evidence reference");
  const contentHash = requireString(source.contentHash, "evidence content hash");
  if (!/^[0-9a-fA-F]{64}$/.test(contentHash)) throw new InvalidNodeResponse("The Node returned an invalid evidence content hash.");
  return {
    ...envelope,
    evidenceId: requireString(source.evidenceId, "evidence identity"),
    contentHash: contentHash.toLowerCase(),
    source: validateProvenanceRef(source.source),
    confidence: requireConfidence(source.confidence, "evidence confidence"),
    clearance: requireClearanceWithin(source.clearance, maximumClearance, "evidence"),
    taint: requireTaint(source.taint),
  };
}

function validateFactRef(value: unknown, maximumClearance: Clearance): NodeFactRef {
  const source = requireRecord(value, "fact reference");
  const envelope = requireNodeEnvelope(source, "fact reference");
  const parentFactIds = requiredField(source, "parentFactIds", "parent fact references");
  const unit = requiredNullableString(source, "unit", "fact unit");
  const derivation = requiredNullableRecord(source, "derivation", "fact derivation");
  const supersededBy = requiredNullableString(source, "supersededBy", "fact supersession reference");
  return {
    ...envelope,
    factId: requireString(source.factId, "fact identity"),
    value: requiredField(source, "value", "fact value"),
    source: validateProvenanceRef(source.source),
    confidence: requireConfidence(source.confidence, "fact confidence"),
    clearance: requireClearanceWithin(source.clearance, maximumClearance, "fact"),
    taint: requireTaint(source.taint),
    parentFactIds: requireStringList(parentFactIds, "parent fact reference"),
    unit,
    derivation,
    supersededBy,
  };
}

/**
 * Re-validates the Node snapshot before it can enter task projection state.
 * Rust validates the remote response too; this webview check prevents a
 * malformed or over-cleared snapshot from becoming visible authority.
 */
export function validateTaskSnapshot(value: unknown, profile: ApprovedNodeProfileReference, expectedTaskId?: string): TaskSnapshot {
  const source = requireRecord(value, "task snapshot");
  const envelope = requireNodeEnvelope(source, "task snapshot");
  const taskId = requireString(source.taskId, "snapshot task identity");
  const nodeConnectionRef = requireString(source.nodeConnectionRef, "snapshot Node identity");
  const clearanceContext = requireClearance(source.clearanceContext);
  if (taskId !== expectedTaskId && expectedTaskId !== undefined || nodeConnectionRef !== profile.nodeIdentity || clearanceContext !== profile.clearanceContext) {
    throw new InvalidNodeResponse("The Node snapshot does not match the approved task or Node profile.");
  }
  const evidence = requiredField(source, "evidence", "snapshot evidence");
  const facts = requiredField(source, "facts", "snapshot facts");
  if (!Array.isArray(evidence) || !Array.isArray(facts)) throw new InvalidNodeResponse("The Node returned an invalid snapshot evidence or fact list.");
  return {
    ...envelope,
    taskId,
    snapshotId: requireString(source.snapshotId, "snapshot identity"),
    asOfSequence: requireSequence(source.asOfSequence, "snapshot sequence"),
    title: requireString(source.title, "snapshot title"),
    requestSummary: requireString(source.requestSummary, "snapshot request summary"),
    status: requireTaskStatus(source.status),
    phase: requireString(source.phase, "snapshot phase"),
    clearanceContext,
    inputManifestRef: typeof source.inputManifestRef === "string" ? source.inputManifestRef : (() => { throw new InvalidNodeResponse("The Node returned an invalid input manifest reference."); })(),
    evidence: evidence.map((item) => validateEvidenceRef(item, clearanceContext)),
    facts: facts.map((item) => validateFactRef(item, clearanceContext)),
    artifactRefs: requireStringList(source.artifactRefs, "snapshot artifact reference"),
    unresolvedQuestions: requireStringList(source.unresolvedQuestions, "snapshot unresolved question"),
    nodeConnectionRef,
    ledgerHeadRef: requireString(source.ledgerHeadRef, "snapshot ledger head reference"),
  };
}

function validateTaskEnvelope(value: unknown, maximumClearance: Clearance): TaskEnvelope {
  const source = requireRecord(value, "task envelope");
  const schemaVersion = requireString(source.schema_version, "task schema version");
  const compatibilityId = requireString(source.compatibility_id, "task compatibility identity");
  if (schemaVersion !== CORE_CONTRACT_SCHEMA_VERSION || compatibilityId !== CORE_CONTRACT_COMPATIBILITY_ID) throw new InvalidNodeResponse("The Node returned an incompatible task envelope.");
  const result: TaskEnvelope = {
    schema_version: schemaVersion,
    compatibility_id: compatibilityId,
    task_id: requireString(source.task_id, "task identity"),
    principal_id: requireString(source.principal_id, "task principal identity"),
    clearance: requireClearanceWithin(source.clearance, maximumClearance, "task"),
    request: requireString(source.request, "task request"),
    domain_pack_ref: requireString(source.domain_pack_ref, "task domain pack reference"),
    risk_class: requireString(source.risk_class, "task risk class"),
    autonomy_ceiling: requireString(source.autonomy_ceiling, "task autonomy ceiling"),
    allowed_evidence_scope: requireStringList(source.allowed_evidence_scope, "allowed evidence scope"),
    permitted_worker_capabilities: requireStringList(source.permitted_worker_capabilities, "permitted worker capability"),
    permitted_tools: requireStringList(source.permitted_tools, "permitted tool"),
    output_contract: requireString(source.output_contract, "task output contract"),
    verification_criteria: requireStringList(source.verification_criteria, "verification criterion"),
    resource_budget: requireNumberMap(source.resource_budget, "task resource budget"),
  };
  if (Object.prototype.hasOwnProperty.call(source, "title")) result.title = requireString(source.title, "task title");
  if (Object.prototype.hasOwnProperty.call(source, "project_ref")) result.project_ref = requiredNullableString(source, "project_ref", "task project reference");
  if (Object.prototype.hasOwnProperty.call(source, "priority")) result.priority = requireString(source.priority, "task priority");
  if (Object.prototype.hasOwnProperty.call(source, "deadline")) result.deadline = requiredNullableString(source, "deadline", "task deadline");
  if (Object.prototype.hasOwnProperty.call(source, "input_manifest_refs")) result.input_manifest_refs = requireStringList(source.input_manifest_refs, "task input manifest reference");
  if (Object.prototype.hasOwnProperty.call(source, "state")) result.state = requireString(source.state, "task state");
  if (Object.prototype.hasOwnProperty.call(source, "parent_task_id")) result.parent_task_id = requiredNullableString(source, "parent_task_id", "parent task reference");
  if (Object.prototype.hasOwnProperty.call(source, "created_at")) result.created_at = requireString(source.created_at, "task creation timestamp");
  return result;
}

/**
 * Validates the complete creation receipt. The desktop only presents a task
 * after the task envelope, initial snapshot, command receipt, and shared
 * ledger reference agree with one another.
 */
export function validateCreateTaskResponse(value: unknown, profile: ApprovedNodeProfileReference, command: NodeCommandEnvelope): CreateTaskResponse {
  const source = requireRecord(value, "task creation response");
  const snapshot = validateTaskSnapshot(source.snapshot, profile);
  const task = validateTaskEnvelope(source.task, profile.clearanceContext);
  if (task.task_id !== snapshot.taskId) throw new InvalidNodeResponse("The Node task envelope and snapshot identify different tasks.");
  const ledgerEventRef = requireString(source.ledger_event_ref, "task creation ledger reference");
  const commandResult = validateNodeCommandResult(source.command, profile, command, snapshot.taskId);
  if (commandResult.ledger_event_ref !== ledgerEventRef) throw new InvalidNodeResponse("The Node task creation receipt has mismatched ledger references.");
  return { task, snapshot, ledger_event_ref: ledgerEventRef, command: commandResult };
}

/**
 * Re-validates the Node plan projection before it can drive approval or work
 * trace presentation. Rust validates the remote response too; this guard
 * keeps a malformed IPC result from becoming a ready plan in the webview.
 */
export function validateTaskPlanReview(value: unknown, profile: ApprovedNodeProfileReference, taskId: string): TaskPlanReview {
  const source = requireRecord(value, "task plan");
  const schemaVersion = requireString(source.schema_version, "plan schema version");
  const compatibilityId = requireString(source.compatibility_id, "plan compatibility identity");
  const responseTaskId = requireString(source.task_id, "plan task identity");
  const nodeIdentity = requireString(source.node_identity, "plan Node identity");
  const protocolVersion = requireString(source.protocol_version, "plan protocol version");
  const clearanceContext = requireClearance(source.clearance_context);
  if (schemaVersion !== CORE_CONTRACT_SCHEMA_VERSION || compatibilityId !== CORE_CONTRACT_COMPATIBILITY_ID || responseTaskId !== taskId || nodeIdentity !== profile.nodeIdentity || protocolVersion !== profile.protocolVersion || clearanceContext !== profile.clearanceContext) {
    throw new InvalidNodeResponse("The Node plan does not match the approved task or Node profile.");
  }

  const planState = requireString(source.plan_state, "plan state");
  if (planState !== "not_ready" && planState !== "ready" && planState !== "queued" && planState !== "needs_review" && planState !== "blocked" && planState !== "rejected") {
    throw new InvalidNodeResponse("The Node plan state is not supported by this client.");
  }
  const executionMode = requireString(source.execution_mode, "plan execution mode");
  if (executionMode !== "parallel" && executionMode !== "pipelined" && executionMode !== "serial_virtual_team" && executionMode !== "not_selected") {
    throw new InvalidNodeResponse("The Node plan execution mode is not supported by this client.");
  }

  const teamId = optionalString(source.team_id, "plan team identity");
  const planVersionHash = optionalString(source.plan_version_hash, "plan version hash");
  const failureCode = optionalFailureField(source.failure_code, "plan failure code");
  const failureReason = optionalFailureField(source.failure_reason, "plan failure reason");
  if (!requireBoolean(source.required_verification, "plan verification requirement")) {
    throw new InvalidNodeResponse("The Node plan did not require independent verification.");
  }
  if (planState === "ready" && (!teamId || !planVersionHash || executionMode === "not_selected")) {
    throw new InvalidNodeResponse("The Node returned a ready plan without complete team or hardware admission context.");
  }
  if ((planState === "blocked" || planState === "rejected") && (!failureCode || !failureReason)) {
    throw new InvalidNodeResponse("The Node returned a blocked plan without a failure reason.");
  }

  return {
    schema_version: schemaVersion,
    compatibility_id: compatibilityId,
    task_id: responseTaskId,
    node_identity: nodeIdentity,
    protocol_version: protocolVersion,
    clearance_context: clearanceContext,
    plan_state: planState,
    task_sequence: requireSequence(source.task_sequence, "plan task sequence"),
    team_id: teamId,
    assignments: requireStringList(source.assignments, "plan assignment"),
    dependency_graph: requireDependencyGraph(source.dependency_graph),
    concurrency_ceiling: requireSequence(source.concurrency_ceiling, "plan concurrency ceiling"),
    execution_mode: executionMode,
    worker_capabilities: requireStringMap(source.worker_capabilities, "plan worker capabilities"),
    hardware_profile_ref: optionalString(source.hardware_profile_ref, "hardware profile reference"),
    hardware_reason: requireString(source.hardware_reason, "hardware reason"),
    required_verification: true,
    completion_criteria: requireStringList(source.completion_criteria, "completion criterion"),
    required_authority: requireString(source.required_authority, "required authority"),
    authority_reason: requireString(source.authority_reason, "authority reason"),
    plan_version_hash: planVersionHash,
    policy_version_hash: optionalString(source.policy_version_hash, "policy version hash"),
    ledger_event_ref: optionalString(source.ledger_event_ref, "plan ledger reference"),
    failure_code: failureCode,
    failure_reason: failureReason,
  };
}

export function validateTaskArtifactReview(value: unknown, profile: ApprovedNodeProfileReference, taskId: string): NodeArtifactReview {
  const source = requireRecord(value, "task artifact review");
  const envelope = requireNodeEnvelope(source, "task artifact review");
  const responseTaskId = requireString(source.taskId, "artifact review task identity");
  const artifactId = requireString(source.artifactId, "artifact identity");
  const nodeIdentity = requireString(source.nodeIdentity, "artifact review Node identity");
  const protocolVersion = requireString(source.protocolVersion, "artifact review protocol version");
  const clearanceContext = requireClearance(source.clearanceContext);
  if (responseTaskId !== taskId || nodeIdentity !== profile.nodeIdentity || protocolVersion !== profile.protocolVersion || clearanceContext !== profile.clearanceContext) {
    throw new InvalidNodeResponse("The Node artifact review does not match the approved task or Node profile.");
  }
  if (!TASK_ID.test(responseTaskId) || !TASK_ID.test(artifactId)) throw new InvalidNodeResponse("The Node artifact review identity is invalid.");
  const clearance = requireClearanceWithin(source.clearance, clearanceContext, "artifact");
  const taint = requireTaint(source.taint);
  if (taint === "contaminated") throw new InvalidNodeResponse("The Node returned a contaminated artifact review.");
  const sourceRefs = requireStringList(source.sourceRefs, "artifact source reference");
  const evidenceRefs = requireStringList(source.evidenceRefs, "artifact evidence reference");
  const verificationRefs = requireStringList(source.verificationRefs, "artifact verification reference");
  if (sourceRefs.length === 0 || evidenceRefs.length === 0 || verificationRefs.length === 0) {
    throw new InvalidNodeResponse("The Node artifact review is missing provenance references.");
  }
  const contentHash = requireString(source.contentHash, "artifact content hash");
  if (!/^[0-9a-fA-F]{64}$/.test(contentHash)) throw new InvalidNodeResponse("The Node returned an invalid artifact content hash.");
  const status = requireString(source.status, "artifact status");
  if (!["staged", "verified_draft", "needs_review", "approved", "returned", "rejected", "superseded"].includes(status)) throw new InvalidNodeResponse("The Node returned an unsupported artifact status.");
  const verificationStatus = requireString(source.verificationStatus, "artifact verification status");
  if (!["not_run", "passed", "failed", "needs_review", "unavailable"].includes(verificationStatus)) throw new InvalidNodeResponse("The Node returned an unsupported artifact verification status.");
  const structuralCheck = requireString(source.structuralCheck, "artifact structural check");
  if (!["not_required", "passed", "failed"].includes(structuralCheck)) throw new InvalidNodeResponse("The Node returned an unsupported structural check status.");
  const visualCheck = requireString(source.visualCheck, "artifact visual check");
  if (!["not_required", "passed", "failed", "unavailable"].includes(visualCheck)) throw new InvalidNodeResponse("The Node returned an unsupported visual check status.");
  const approvalState = requireString(source.approvalState, "artifact approval state");
  if (!["not_ready", "pending", "approved", "returned", "rejected", "unavailable"].includes(approvalState)) throw new InvalidNodeResponse("The Node returned an unsupported artifact approval state.");
  const byteSize = requireSequence(source.byteSize, "artifact byte size");
  if (byteSize < 1 || byteSize > 100 * 1024 * 1024) throw new InvalidNodeResponse("The Node artifact size is outside the supported limit.");
  const confidence = requireConfidence(source.confidence, "artifact confidence");
  return {
    ...envelope,
    taskId: responseTaskId,
    artifactId,
    nodeIdentity,
    protocolVersion,
    clearanceContext,
    title: requireString(source.title, "artifact title"),
    mediaType: requireString(source.mediaType, "artifact media type"),
    fileFormat: requireString(source.fileFormat, "artifact format"),
    templateId: requireString(source.templateId, "artifact template identity"),
    templateVersion: requireString(source.templateVersion, "artifact template version"),
    contentHash: contentHash.toLowerCase(),
    byteSize,
    status,
    verificationStatus,
    structuralCheck,
    visualCheck,
    approvalState,
    approvalBlockingReasons: requireStringList(source.approvalBlockingReasons, "artifact approval blocker"),
    sourceRefs,
    evidenceRefs,
    verificationRefs,
    deterministicValueRefs: requireStringList(source.deterministicValueRefs, "deterministic value reference"),
    confidence,
    clearance,
    taint,
    derivation: requireRecord(source.derivation, "artifact derivation"),
    previewRef: requireNodeReference(source.previewRef, "artifact preview"),
    downloadRef: requireNodeReference(source.downloadRef, "artifact download"),
    ledgerEventRef: requireNodeReference(source.ledgerEventRef, "artifact ledger event"),
    artifactSequence: requireSequence(source.artifactSequence, "artifact sequence"),
    createdAt: requireString(source.createdAt, "artifact creation time"),
  };
}

/**
 * Re-validates the clearance-filtered route proof before it enters the task
 * workspace. The desktop receives selected targets and decision metadata only;
 * it never receives the router's private request or model prompt payload.
 */
export function validateTaskRouteTrace(value: unknown, profile: ApprovedNodeProfileReference, taskId: string): NodeRouteTrace {
  const source = requireRecord(value, "task routing trace");
  const envelope = requireNodeEnvelope(source, "task routing trace");
  const responseTaskId = requireString(source.taskId, "routing trace task identity");
  const nodeIdentity = requireString(source.nodeIdentity, "routing trace Node identity");
  const protocolVersion = requireString(source.protocolVersion, "routing trace protocol version");
  const clearanceContext = requireClearance(source.clearanceContext);
  if (responseTaskId !== taskId || nodeIdentity !== profile.nodeIdentity || protocolVersion !== profile.protocolVersion || clearanceContext !== profile.clearanceContext) {
    throw new InvalidNodeResponse("The Node routing trace does not match the approved task or Node profile.");
  }
  const rawEntries = requiredField(source, "entries", "routing trace entries");
  if (!Array.isArray(rawEntries) || rawEntries.length > 1000) throw new InvalidNodeResponse("The Node returned an invalid routing trace entry list.");
  let previousSequence = 0;
  const entries: NodeRouteTraceEntry[] = rawEntries.map((value, index) => {
    const entry = requireRecord(value, `routing trace entry ${index + 1}`);
    const entryEnvelope = requireNodeEnvelope(entry, `routing trace entry ${index + 1}`);
    if (entryEnvelope.schemaVersion !== envelope.schemaVersion || entryEnvelope.compatibilityId !== envelope.compatibilityId) {
      throw new InvalidNodeResponse("The Node routing trace entry envelope does not match the trace envelope.");
    }
    const sequence = requireSequence(entry.sequence, "routing trace sequence");
    if (sequence < 1 || sequence <= previousSequence) throw new InvalidNodeResponse("The Node routing trace entries are not strictly ordered.");
    previousSequence = sequence;
    const entryClearance = requireClearance(entry.clearanceContext);
    if (entryClearance !== profile.clearanceContext) throw new InvalidNodeResponse("The Node returned a routing trace entry above the approved clearance.");
    const eligibleTargets = requireStringList(entry.eligibleTargets, "eligible routing target");
    return {
      ...entryEnvelope,
      sequence,
      eventType: requireString(entry.eventType, "routing trace event type"),
      occurredAt: requireString(entry.occurredAt, "routing trace event time"),
      actor: requireString(entry.actor, "routing trace actor"),
      clearanceContext: entryClearance,
      ledgerEventRef: requireString(entry.ledgerEventRef, "routing trace ledger reference"),
      payloadHash: requireString(entry.payloadHash, "routing trace payload hash"),
      requestId: optionalString(entry.requestId, "routing request identity"),
      workerId: optionalString(entry.workerId, "routing worker identity"),
      role: optionalString(entry.role, "routing worker role"),
      taskKind: optionalString(entry.taskKind, "routing task kind"),
      requiredCapability: optionalString(entry.requiredCapability, "routing capability"),
      selectedTarget: optionalString(entry.selectedTarget, "selected routing target"),
      decisionSource: optionalString(entry.decisionSource, "routing decision source"),
      ruleOrThreshold: optionalString(entry.ruleOrThreshold, "routing rule or threshold"),
      qualificationCertificate: optionalString(entry.qualificationCertificate, "routing qualification certificate"),
      fallbackTarget: optionalString(entry.fallbackTarget, "routing fallback target"),
      reason: optionalString(entry.reason, "routing decision reason"),
      status: optionalString(entry.status, "routing decision status"),
      eligibleTargets,
    };
  });
  return {
    ...envelope,
    taskId: responseTaskId,
    nodeIdentity,
    protocolVersion,
    clearanceContext,
    entries,
  };
}

function optionalResponseString(value: unknown, label: string): string | null {
  if (value === null || value === undefined) return null;
  return requireString(value, label);
}

/**
 * Re-validates a successful state-changing command result before the UI can
 * show acceptance. The Node remains authoritative, but a result is not
 * trusted unless it is bound to the submitted command and carries its ledger
 * record and current Node context.
 */
export function validateNodeCommandResult(value: unknown, profile: ApprovedNodeProfileReference, command: NodeCommandEnvelope, expectedTaskId: string | null = command.task_id): NodeCommandResult {
  const source = requireRecord(value, "Node command result");
  const schemaVersion = requireString(source.schema_version, "command result schema version");
  const compatibilityId = requireString(source.compatibility_id, "command result compatibility identity");
  const outcome = requireString(source.outcome, "command result outcome");
  if (schemaVersion !== CORE_CONTRACT_SCHEMA_VERSION || compatibilityId !== CORE_CONTRACT_COMPATIBILITY_ID || (outcome !== "accepted" && outcome !== "rejected" && outcome !== "needs_review")) {
    throw new InvalidNodeResponse("The Node command result is not compatible with this application.");
  }
  const commandId = requireString(source.command_id, "command result command identity");
  const taskId = optionalResponseString(source.task_id, "command result task identity");
  const idempotencyKey = requireString(source.idempotency_key, "command result idempotency key");
  if (commandId !== command.command_id || taskId !== expectedTaskId || idempotencyKey !== command.idempotency_key) {
    throw new InvalidNodeResponse("The Node command result does not match the submitted command.");
  }
  const nodeIdentity = requireString(source.node_identity, "command result Node identity");
  const protocolVersion = requireString(source.protocol_version, "command result protocol version");
  const clearanceContext = requireClearance(source.clearance_context);
  if (nodeIdentity !== profile.nodeIdentity || protocolVersion !== profile.protocolVersion || clearanceContext !== profile.clearanceContext) {
    throw new InvalidNodeResponse("The Node command result does not match the approved Node profile.");
  }
  const ledgerEventRef = optionalResponseString(source.ledger_event_ref, "command result ledger reference");
  if (!ledgerEventRef) throw new InvalidNodeResponse("The Node command result is missing its ledger reference.");
  return {
    schema_version: schemaVersion,
    compatibility_id: compatibilityId,
    outcome,
    command_id: commandId,
    task_id: taskId,
    idempotency_key: idempotencyKey,
    ledger_event_ref: ledgerEventRef,
    sequence: source.sequence === null || source.sequence === undefined ? null : requireSequence(source.sequence, "command result sequence"),
    state: optionalResponseString(source.state, "command result state"),
    node_identity: nodeIdentity,
    protocol_version: protocolVersion,
    clearance_context: clearanceContext,
    event_type: optionalResponseString(source.event_type, "command result event type"),
    code: optionalResponseString(source.code, "command result code"),
    message: optionalResponseString(source.message, "command result message"),
    reason: optionalResponseString(source.reason, "command result reason"),
  };
}

function assertApprovedProfile(profile: ApprovedNodeProfileReference): void {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) {
    throw new Error("The approved Node profile is incomplete or not approved by policy.");
  }
}

function assertCommand(command: NodeCommandEnvelope): void {
  if (command.schema_version !== CORE_CONTRACT_SCHEMA_VERSION || command.compatibility_id !== CORE_CONTRACT_COMPATIBILITY_ID) throw new Error("The command contract is not supported by this Node.");
  if (!COMMAND_ID.test(command.command_id)) throw new Error("The command identifier is invalid.");
  if (!command.actor.trim() || !command.idempotency_key.trim()) throw new Error("The command identity is incomplete.");
  if (!command.client_version.trim()) throw new Error("The command protocol version is missing.");
  if (!command.arguments || typeof command.arguments !== "object" || Array.isArray(command.arguments)) {
    throw new Error("The command arguments must be an object.");
  }
}

function assertTaskCommand(command: NodeCommandEnvelope): asserts command is NodeCommandEnvelope & { task_id: string; expected_sequence: number } {
  assertCommand(command);
  if (!command.task_id || !TASK_ID.test(command.task_id)) throw new Error("The command task identifier is invalid.");
  const expectedSequence = command.expected_sequence;
  if (expectedSequence === null || !Number.isSafeInteger(expectedSequence) || expectedSequence < 0) {
    throw new Error("The command expected sequence is invalid.");
  }
  if (!["task.authorize", "task.approve_plan", "task.cancel", "task.request_review", "task.approve_artifact", "task.return_artifact"].includes(command.command_type)) {
    throw new Error("The command type is not supported by this transport.");
  }
}

export function fetchTaskSnapshot(profile: ApprovedNodeProfileReference, taskId: string): Promise<TaskSnapshot> {
  assertApprovedProfile(profile);
  if (!TASK_ID.test(taskId)) throw new Error("The task identifier is invalid.");
  return invoke<unknown>("fetch_task_snapshot", {
    profileId: profile.profileId,
    taskId,
  }).then((value) => validateTaskSnapshot(value, profile, taskId));
}

export function fetchTaskPlan(profile: ApprovedNodeProfileReference, taskId: string): Promise<TaskPlanReview> {
  assertApprovedProfile(profile);
  if (!TASK_ID.test(taskId)) throw new Error("The task identifier is invalid.");
  return invoke<unknown>("fetch_task_plan", {
    profileId: profile.profileId,
    taskId,
  }).then((value) => validateTaskPlanReview(value, profile, taskId));
}

export function fetchTaskArtifactReview(profile: ApprovedNodeProfileReference, taskId: string): Promise<NodeArtifactReview> {
  assertApprovedProfile(profile);
  if (!TASK_ID.test(taskId)) throw new Error("The task identifier is invalid.");
  return invoke<unknown>("fetch_task_artifact_review", {
    profileId: profile.profileId,
    taskId,
  }).then((value) => validateTaskArtifactReview(value, profile, taskId));
}

export function fetchTaskRouteTrace(profile: ApprovedNodeProfileReference, taskId: string): Promise<NodeRouteTrace> {
  assertApprovedProfile(profile);
  if (!TASK_ID.test(taskId)) throw new Error("The task identifier is invalid.");
  return invoke<unknown>("fetch_task_route_trace", {
    profileId: profile.profileId,
    taskId,
  }).then((value) => validateTaskRouteTrace(value, profile, taskId));
}

export function createTask(profile: ApprovedNodeProfileReference, command: NodeCommandEnvelope): Promise<CreateTaskResponse> {
  assertApprovedProfile(profile);
  assertCommand(command);
  if (command.command_type !== "task.create" || command.task_id !== null || command.expected_sequence !== null) {
    throw new Error("The task creation command envelope is invalid.");
  }
  return invoke<unknown>("create_task", {
    profileId: profile.profileId,
    command,
  }).then((value) => validateCreateTaskResponse(value, profile, command));
}

export function sendTaskCommand(profile: ApprovedNodeProfileReference, command: NodeCommandEnvelope): Promise<NodeCommandResult> {
  assertApprovedProfile(profile);
  assertTaskCommand(command);
  return invoke<unknown>("send_task_command", {
    profileId: profile.profileId,
    command,
  }).then((value) => validateNodeCommandResult(value, profile, command));
}

export function approveArtifact(profile: ApprovedNodeProfileReference, taskId: string, artifactId: string, reason: string, expectedSequence: number, actor: string): Promise<NodeCommandResult> {
  assertApprovedProfile(profile);
  if (!TASK_ID.test(taskId)) throw new Error("The task identifier is invalid.");
  if (!TASK_ID.test(artifactId)) throw new Error("The artifact identifier is invalid.");
  if (!reason.trim()) throw new Error("The approval reason is required.");
  const commandId = `command.approve-artifact.${crypto.randomUUID()}`;
  const command: NodeCommandEnvelope = {
    schema_version: CORE_CONTRACT_SCHEMA_VERSION,
    compatibility_id: CORE_CONTRACT_COMPATIBILITY_ID,
    command_id: commandId,
    actor,
    task_id: taskId,
    expected_sequence: expectedSequence,
    idempotency_key: `idempotency.${commandId}`,
    client_version: NODE_PROTOCOL_VERSION,
    command_type: "task.approve_artifact",
    arguments: { artifact_id: artifactId, reason },
  };
  return sendTaskCommand(profile, command);
}

export function returnArtifactForRevision(profile: ApprovedNodeProfileReference, taskId: string, artifactId: string, reason: string, expectedSequence: number, actor: string): Promise<NodeCommandResult> {
  assertApprovedProfile(profile);
  if (!TASK_ID.test(taskId)) throw new Error("The task identifier is invalid.");
  if (!TASK_ID.test(artifactId)) throw new Error("The artifact identifier is invalid.");
  if (!reason.trim()) throw new Error("The revision reason is required.");
  const commandId = `command.return-artifact.${crypto.randomUUID()}`;
  const command: NodeCommandEnvelope = {
    schema_version: CORE_CONTRACT_SCHEMA_VERSION,
    compatibility_id: CORE_CONTRACT_COMPATIBILITY_ID,
    command_id: commandId,
    actor,
    task_id: taskId,
    expected_sequence: expectedSequence,
    idempotency_key: `idempotency.${commandId}`,
    client_version: NODE_PROTOCOL_VERSION,
    command_type: "task.return_artifact",
    arguments: { artifact_id: artifactId, reason },
  };
  return sendTaskCommand(profile, command);
}
