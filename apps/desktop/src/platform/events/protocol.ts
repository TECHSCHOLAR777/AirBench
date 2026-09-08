import { CORE_CONTRACT_COMPATIBILITY_ID, CORE_CONTRACT_SCHEMA_VERSION, NODE_PROTOCOL_COMPATIBILITY_ID, NODE_PROTOCOL_VERSION } from "../../generated/core_contracts";
import type {
  Clearance as CoreClearance,
  NodeApprovalEventPayload,
  NodeArtifactEventPayload,
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
type SummaryEventType = "ledger.written" | "ledger.verification_changed" | "node.connection_changed" | "node.sovereignty_changed";

export type TaskEvent =
  | (TaskEventBase & { eventType: LifecycleEventType; payload: NodeLifecycleEventPayload })
  | (TaskEventBase & { eventType: WorkerEventType; payload: NodeWorkerEventPayload })
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
      return { ...base, eventType: event.eventType as WorkerEventType, payload: { role: candidate.role, label: candidate.label, status: candidate.status } };
    }
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
const SUMMARY_EVENT_TYPES = new Set(["ledger.written", "ledger.verification_changed", "node.connection_changed", "node.sovereignty_changed"]);

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
