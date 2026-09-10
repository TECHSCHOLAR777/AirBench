import { CORE_CONTRACT_COMPATIBILITY_ID, CORE_CONTRACT_SCHEMA_VERSION, NODE_PROTOCOL_COMPATIBILITY_ID, NODE_PROTOCOL_VERSION } from "../../generated/core_contracts";
import type {
  Clearance as CoreClearance,
  NodeApprovalEventPayload,
  NodeArtifactEventPayload,
  NodeExecutionEventPayload,
  NodeEvidenceEventPayload,
  NodeEvidenceRef,
  NodeFactRef,
  NodeLifecycleEventPayload,
  NodeCommandEnvelope,
  NodeCommandResult,
  NodeSummaryEventPayload,
  NodeTaskEvent,
  NodeTaskEventBatch,
  NodeTaskSnapshot,
  NodeTaskStatus,
  Taint as CoreTaint,
  NodeUnknownEventPayload,
  NodeVerificationEventPayload,
  NodeWorkerEventPayload,
  NodeProvenanceRef,
} from "../../generated/core_contracts";

export const FRONTEND_PROTOCOL_VERSION = NODE_PROTOCOL_VERSION;
export const FRONTEND_PROTOCOL_COMPATIBILITY_ID = NODE_PROTOCOL_COMPATIBILITY_ID;

export type TaskStatus = NodeTaskStatus;
export type Clearance = CoreClearance;
export type Taint = CoreTaint;
export type ProjectionHealth = "current" | "replaying" | "resynchronizing" | "blocked";

export type ProvenanceRef = NodeProvenanceRef;
export type FactEnvelope = NodeFactRef;
export type EvidenceRef = NodeEvidenceRef;
export type TaskSnapshot = NodeTaskSnapshot;
export type TaskEventBase = Omit<NodeTaskEvent, "eventType" | "payload">;
type LifecycleEventType = "task.accepted" | "plan.created" | "plan.revised" | "plan.approved" | "task.paused" | "task.resumed" | "task.blocked" | "task.failed" | "task.stopped" | "task.completed";
type WorkerEventType = "worker.started" | "worker.completed" | "tool.started" | "tool.completed";
type ExecutionEventType = "team.created" | "team.execution.started" | "team.execution.completed" | "team.execution.failed" | "team.execution.cancelled" | "lifecycle.intercepted" | "lifecycle.blocked" | "worker.assigned" | "worker.failed" | "worker.handoff" | "worker.handoff.rejected" | "worker.handoff.late" | "worker.resource_reserved" | "worker.preempted" | "worker.cancelled" | "team.resource_plan.created" | "team.resource_plan.admitted" | "team.resource_plan.queued" | "team.resource_plan.degraded_needs_review" | "team.resource_plan.rejected" | "team.resource_plan.released" | "team.resource_plan.cancelled" | "resource.plan.admitted" | "resource.plan.queued" | "execution.mode.selected" | "execution.mode.changed" | "join_barrier.waiting" | "join_barrier.completed" | "join_barrier.resolved" | "barrier.waiting" | "barrier.completed" | "resource.exhaustion.detected" | "resource.recovered" | "resource.queue.updated" | "resource.lease.granted" | "resource.lease.activated" | "resource.lease.released" | "resource.lease.expired" | "resource.lease.cancelled" | "resource.lease.failed" | "resource.admission.degraded" | "background.work.yielded";
type SummaryEventType = "ledger.written" | "ledger.verification_changed" | "node.connection_changed" | "node.sovereignty_changed";

export type TaskEvent =
  | (TaskEventBase & { eventType: LifecycleEventType; payload: NodeLifecycleEventPayload })
  | (TaskEventBase & { eventType: WorkerEventType; payload: NodeWorkerEventPayload })
  | (TaskEventBase & { eventType: ExecutionEventType; payload: NodeExecutionEventPayload })
  | (TaskEventBase & { eventType: "evidence.added" | "evidence.revised"; payload: NodeEvidenceEventPayload })
  | (TaskEventBase & { eventType: "verification.completed" | "verification.failed"; payload: NodeVerificationEventPayload })
  | (TaskEventBase & { eventType: "approval.required" | "approval.recorded" | "approval.returned"; payload: NodeApprovalEventPayload })
  | (TaskEventBase & { eventType: "artifact.ready" | "artifact.superseded"; payload: NodeArtifactEventPayload })
  | (TaskEventBase & { eventType: SummaryEventType; payload: NodeSummaryEventPayload })
  | (TaskEventBase & { eventType: "unknown"; payload: NodeUnknownEventPayload });

/** Node command types are generated from the authoritative Python contract. */
export type Command = NodeCommandEnvelope;
export type CommandResult = NodeCommandResult;

export type TaskEventBatch = Pick<NodeTaskEventBatch, "schema_version" | "compatibility_id" | "stream_id" | "node_identity" | "protocol_version" | "clearance_context" | "next_sequence" | "has_more" | "ledger_event_refs"> & { events: TaskEvent[] };

export interface TaskProjection {
  taskId: string;
  schemaVersion: string;
  compatibilityId: string;
  snapshotId: string;
  title: string;
  requestSummary: string;
  status: TaskStatus;
  phase: string;
  clearanceContext: Clearance;
  inputManifestRef: string;
  nodeConnectionRef: string;
  ledgerHeadRef: string;
  lastAppliedSequence: number;
  evidence: EvidenceRef[];
  facts: FactEnvelope[];
  artifactRefs: string[];
  unresolvedQuestions: string[];
  activity: TaskEvent[];
  diagnostics: Array<{ code: string; detail: string; sequence: number | null }>;
  health: ProjectionHealth;
}

export type ProjectionResult =
  | { kind: "applied"; projection: TaskProjection }
  | { kind: "duplicate"; projection: TaskProjection }
  | { kind: "gap"; projection: TaskProjection; expectedSequence: number; receivedSequence: number }
  | { kind: "unknown"; projection: TaskProjection };

export function projectionFromSnapshot(snapshot: TaskSnapshot): TaskProjection {
  assertNodeEnvelope(snapshot.schemaVersion, snapshot.compatibilityId);
  return {
    taskId: snapshot.taskId,
    schemaVersion: snapshot.schemaVersion,
    compatibilityId: snapshot.compatibilityId,
    snapshotId: snapshot.snapshotId,
    title: snapshot.title,
    requestSummary: snapshot.requestSummary,
    status: snapshot.status,
    phase: snapshot.phase,
    clearanceContext: snapshot.clearanceContext,
    inputManifestRef: snapshot.inputManifestRef,
    nodeConnectionRef: snapshot.nodeConnectionRef,
    ledgerHeadRef: snapshot.ledgerHeadRef,
    lastAppliedSequence: snapshot.asOfSequence,
    evidence: [...snapshot.evidence],
    facts: [...snapshot.facts],
    artifactRefs: [...snapshot.artifactRefs],
    unresolvedQuestions: [...snapshot.unresolvedQuestions],
    activity: [],
    diagnostics: [],
    health: "current",
  };
}

/** Convert a generated Node event into the safe, known projection union. */
export function normalizeTaskEvent(event: NodeTaskEvent): TaskEvent {
  const base: TaskEventBase = {
    schemaVersion: event.schemaVersion,
    compatibilityId: event.compatibilityId,
    eventId: event.eventId,
    taskId: event.taskId,
    sequence: event.sequence,
    occurredAt: event.occurredAt,
    actor: event.actor,
    clearanceContext: event.clearanceContext,
    payloadHash: event.payloadHash,
    ledgerEventRef: event.ledgerEventRef,
  };
  assertNodeEnvelope(event.schemaVersion, event.compatibilityId);
  const payload = event.payload;

  if (LIFECYCLE_EVENT_TYPES.has(event.eventType)) {
    const candidate = payload as Partial<NodeLifecycleEventPayload>;
    if (typeof candidate.phase === "string" && isTaskStatus(candidate.status)) {
      return { ...base, eventType: event.eventType as LifecycleEventType, payload: { phase: candidate.phase, status: candidate.status, summary: typeof candidate.summary === "string" ? candidate.summary : null } };
    }
  }
  if (WORKER_EVENT_TYPES.has(event.eventType)) {
    const candidate = payload as Partial<NodeWorkerEventPayload>;
    if (typeof candidate.role === "string" && typeof candidate.label === "string" && typeof candidate.status === "string") {
      const workerPayload: NodeWorkerEventPayload = { role: candidate.role, label: candidate.label, status: candidate.status };
      for (const [sourceKey, wireKey] of [["teamId", "teamId"], ["assignmentId", "assignmentId"], ["workerId", "workerId"], ["resourceLeaseId", "resourceLeaseId"]] as const) {
        const value = candidate[sourceKey];
        if (typeof value === "string") workerPayload[wireKey] = value;
      }
      return { ...base, eventType: event.eventType as WorkerEventType, payload: workerPayload };
    }
  }
  if (EXECUTION_EVENT_TYPES.has(event.eventType as ExecutionEventType)) {
    const candidate = payload as Partial<NodeExecutionEventPayload>;
    const executionPayload = normalizeExecutionPayload(candidate);
    if (executionPayload) return { ...base, eventType: event.eventType as ExecutionEventType, payload: executionPayload };
  }
  if (event.eventType === "evidence.added" || event.eventType === "evidence.revised") {
    const candidate = payload as Partial<NodeEvidenceEventPayload>;
    if (candidate.evidence && isEvidenceRef(candidate.evidence)) return { ...base, eventType: event.eventType, payload: { evidence: candidate.evidence } };
  }
  if (event.eventType === "verification.completed" || event.eventType === "verification.failed") {
    const candidate = payload as Partial<NodeVerificationEventPayload>;
    if (typeof candidate.summary === "string" && typeof candidate.passed === "boolean") return { ...base, eventType: event.eventType, payload: candidate as NodeVerificationEventPayload };
  }
  if (event.eventType === "approval.required" || event.eventType === "approval.recorded" || event.eventType === "approval.returned") {
    const candidate = payload as Partial<NodeApprovalEventPayload>;
    if (typeof candidate.reason === "string") return { ...base, eventType: event.eventType, payload: candidate as NodeApprovalEventPayload };
  }
  if (event.eventType === "artifact.ready" || event.eventType === "artifact.superseded") {
    const candidate = payload as Partial<NodeArtifactEventPayload>;
    if (typeof candidate.artifactId === "string") return { ...base, eventType: event.eventType, payload: candidate as NodeArtifactEventPayload };
  }
  if (SUMMARY_EVENT_TYPES.has(event.eventType)) {
    const candidate = payload as Partial<NodeSummaryEventPayload>;
    if (typeof candidate.summary === "string") return { ...base, eventType: event.eventType as SummaryEventType, payload: candidate as NodeSummaryEventPayload };
  }
  return { ...base, eventType: "unknown", payload: { originalType: event.eventType, raw: event.payload } };
}

export function normalizeTaskEventBatch(batch: NodeTaskEventBatch): TaskEventBatch {
  assertCoreEnvelope(batch.schema_version, batch.compatibility_id);
  return { ...batch, events: batch.events.map(normalizeTaskEvent) };
}

function assertCoreEnvelope(schemaVersion: string, compatibilityId: string): void {
  if (schemaVersion !== CORE_CONTRACT_SCHEMA_VERSION || compatibilityId !== CORE_CONTRACT_COMPATIBILITY_ID) {
    throw new Error("The Node event batch core contract is not compatible with this application.");
  }
}

function assertNodeEnvelope(schemaVersion: string, compatibilityId: string): void {
  if (schemaVersion !== FRONTEND_PROTOCOL_VERSION || compatibilityId !== FRONTEND_PROTOCOL_COMPATIBILITY_ID) {
    throw new Error("The Node response protocol is not compatible with this application.");
  }
}

function isTaskStatus(value: unknown): value is TaskStatus {
  return typeof value === "string" && ["accepted", "planning", "running", "needs_review", "completed", "blocked", "failed", "stopped"].includes(value);
}

function isEvidenceRef(value: unknown): value is EvidenceRef {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<EvidenceRef>;
  return candidate.schemaVersion === FRONTEND_PROTOCOL_VERSION && candidate.compatibilityId === FRONTEND_PROTOCOL_COMPATIBILITY_ID && typeof candidate.evidenceId === "string" && typeof candidate.contentHash === "string" && typeof candidate.confidence === "number" && candidate.confidence >= 0 && candidate.confidence <= 1 && typeof candidate.source === "object" && candidate.source !== null && (candidate.source as ProvenanceRef).schemaVersion === FRONTEND_PROTOCOL_VERSION && (candidate.source as ProvenanceRef).compatibilityId === FRONTEND_PROTOCOL_COMPATIBILITY_ID && typeof candidate.clearance === "string" && typeof candidate.taint === "string";
}

const LIFECYCLE_EVENT_TYPES = new Set(["task.accepted", "plan.created", "plan.revised", "plan.approved", "task.paused", "task.resumed", "task.blocked", "task.failed", "task.stopped", "task.completed"]);
const WORKER_EVENT_TYPES = new Set(["worker.started", "worker.completed", "tool.started", "tool.completed"]);
const EXECUTION_EVENT_TYPES = new Set<ExecutionEventType>(["team.created", "team.execution.started", "team.execution.completed", "team.execution.failed", "team.execution.cancelled", "lifecycle.intercepted", "lifecycle.blocked", "worker.assigned", "worker.failed", "worker.handoff", "worker.handoff.rejected", "worker.handoff.late", "worker.resource_reserved", "worker.preempted", "worker.cancelled", "team.resource_plan.created", "team.resource_plan.admitted", "team.resource_plan.queued", "team.resource_plan.degraded_needs_review", "team.resource_plan.rejected", "team.resource_plan.released", "team.resource_plan.cancelled", "resource.plan.admitted", "resource.plan.queued", "execution.mode.selected", "execution.mode.changed", "join_barrier.waiting", "join_barrier.completed", "join_barrier.resolved", "barrier.waiting", "barrier.completed", "resource.exhaustion.detected", "resource.recovered", "resource.queue.updated", "resource.lease.granted", "resource.lease.activated", "resource.lease.released", "resource.lease.expired", "resource.lease.cancelled", "resource.lease.failed", "resource.admission.degraded", "background.work.yielded"]);
const SUMMARY_EVENT_TYPES = new Set(["ledger.written", "ledger.verification_changed", "node.connection_changed", "node.sovereignty_changed"]);

function normalizeExecutionPayload(candidate: Partial<NodeExecutionEventPayload>): NodeExecutionEventPayload | null {
  if (typeof candidate.status !== "string" || typeof candidate.summary !== "string") return null;
  const payload: NodeExecutionEventPayload = { status: candidate.status, summary: candidate.summary };
  const stringFields = [
    ["executionMode", "executionMode"], ["teamId", "teamId"], ["planId", "planId"], ["assignmentId", "assignmentId"],
    ["workerId", "workerId"], ["role", "role"], ["label", "label"], ["barrierId", "barrierId"], ["resourceLeaseId", "resourceLeaseId"],
    ["hardwareProfileRef", "hardwareProfileRef"], ["modelTargetId", "modelTargetId"], ["qualificationId", "qualificationId"],
  ] as const;
  for (const [sourceKey, wireKey] of stringFields) {
    const value = candidate[sourceKey];
    if (value !== undefined && value !== null && typeof value !== "string") return null;
    if (typeof value === "string") payload[wireKey] = value;
  }
  if (candidate.dependencyIds !== undefined) {
    if (!Array.isArray(candidate.dependencyIds) || candidate.dependencyIds.some((item) => typeof item !== "string")) return null;
    payload.dependencyIds = [...candidate.dependencyIds];
  }
  if (candidate.queuePosition !== undefined && candidate.queuePosition !== null) {
    if (!Number.isInteger(candidate.queuePosition) || candidate.queuePosition < 0) return null;
    payload.queuePosition = candidate.queuePosition;
  }
  return payload;
}

export function applyEvent(projection: TaskProjection, event: TaskEvent): ProjectionResult {
  if (event.taskId !== projection.taskId) {
    return { kind: "unknown", projection: withDiagnostic({ ...projection, health: "blocked" }, "task_mismatch", `Event belongs to ${event.taskId}`, event.sequence) };
  }
  if (event.sequence <= projection.lastAppliedSequence) return { kind: "duplicate", projection };
  if (event.sequence > projection.lastAppliedSequence + 1) {
    return {
      kind: "gap",
      projection: { ...projection, health: "resynchronizing" },
      expectedSequence: projection.lastAppliedSequence + 1,
      receivedSequence: event.sequence,
    };
  }
  if (event.eventType === "unknown") {
    return { kind: "unknown", projection: withDiagnostic({ ...projection, health: "blocked" }, "unknown_event", event.payload.originalType, event.sequence) };
  }

  const next: TaskProjection = {
    ...projection,
    lastAppliedSequence: event.sequence,
    activity: [...projection.activity, event],
    health: "current",
  };

  if (event.eventType === "task.accepted" || event.eventType === "plan.created" || event.eventType === "plan.revised" || event.eventType === "plan.approved" || event.eventType === "task.paused" || event.eventType === "task.resumed" || event.eventType === "task.blocked" || event.eventType === "task.failed" || event.eventType === "task.stopped" || event.eventType === "task.completed") {
    next.status = event.payload.status;
    next.phase = event.payload.phase;
  }
  if (event.eventType === "evidence.added" || event.eventType === "evidence.revised") {
    next.evidence = upsertEvidence(next.evidence, event.payload.evidence);
  }
  if (event.eventType === "artifact.ready") next.artifactRefs = [...new Set([...next.artifactRefs, event.payload.artifactId])];
  if (event.eventType === "artifact.superseded") next.artifactRefs = next.artifactRefs.filter((id) => id !== event.payload.artifactId);
  return { kind: "applied", projection: next };
}

function withDiagnostic(projection: TaskProjection, code: string, detail: string, sequence: number | null): TaskProjection {
  return { ...projection, diagnostics: [...projection.diagnostics, { code, detail, sequence }] };
}

function upsertEvidence(items: EvidenceRef[], next: EvidenceRef): EvidenceRef[] {
  const index = items.findIndex((item) => item.evidenceId === next.evidenceId);
  if (index < 0) return [...items, next];
  return items.map((item, itemIndex) => itemIndex === index ? next : item);
}
