export const FRONTEND_PROTOCOL_VERSION = "0.1" as const;

export type TaskStatus = "accepted" | "planning" | "running" | "needs_review" | "completed" | "blocked" | "failed" | "stopped";
export type Clearance = "public" | "internal" | "restricted" | "highly_restricted";
export type Taint = "untrusted" | "screened" | "trusted";
export type ProjectionHealth = "current" | "replaying" | "resynchronizing" | "blocked";

export interface ProvenanceRef {
  sourceDocumentId: string;
  sourceVersion: string;
  location: { page?: number; span?: string; cell?: string; region?: string } | null;
  extractionMethod: string;
  observedAt: string | null;
  ingestedAt: string;
  ledgerEventRef: string;
}

export interface FactEnvelope<TValue = unknown> {
  factId: string;
  schemaVersion: string;
  value: TValue;
  unit: string | null;
  source: ProvenanceRef;
  confidence: number;
  clearance: Clearance;
  taint: Taint;
  parentFactIds: string[];
  derivation: { method: string; inputFactIds: string[] } | null;
  supersededBy: string | null;
}

export interface EvidenceRef {
  evidenceId: string;
  contentHash: string;
  source: ProvenanceRef;
  confidence: number;
  clearance: Clearance;
  taint: Taint;
}

export interface TaskSnapshot {
  taskId: string;
  schemaVersion: string;
  snapshotId: string;
  asOfSequence: number;
  title: string;
  requestSummary: string;
  status: TaskStatus;
  phase: string;
  clearanceContext: Clearance;
  inputManifestRef: string;
  evidence: EvidenceRef[];
  facts: FactEnvelope[];
  artifactRefs: string[];
  unresolvedQuestions: string[];
  nodeConnectionRef: string;
  ledgerHeadRef: string;
}

export interface TaskEventBase {
  eventId: string;
  taskId: string;
  sequence: number;
  schemaVersion: string;
  occurredAt: string;
  actor: string;
  clearanceContext: Clearance;
  payloadHash: string;
  ledgerEventRef: string;
}

export type TaskEvent =
  | (TaskEventBase & { eventType: "task.accepted" | "plan.created" | "plan.revised" | "task.paused" | "task.resumed" | "task.blocked" | "task.failed" | "task.stopped" | "task.completed"; payload: { phase: string; status: TaskStatus; summary?: string } })
  | (TaskEventBase & { eventType: "worker.started" | "worker.completed" | "tool.started" | "tool.completed"; payload: { role: string; label: string; status: string } })
  | (TaskEventBase & { eventType: "evidence.added" | "evidence.revised"; payload: { evidence: EvidenceRef } })
  | (TaskEventBase & { eventType: "verification.completed" | "verification.failed"; payload: { summary: string; passed: boolean } })
  | (TaskEventBase & { eventType: "approval.required" | "approval.recorded" | "approval.returned"; payload: { reason: string } })
  | (TaskEventBase & { eventType: "artifact.ready" | "artifact.superseded"; payload: { artifactId: string } })
  | (TaskEventBase & { eventType: "ledger.written" | "ledger.verification_changed" | "node.connection_changed" | "node.sovereignty_changed"; payload: { summary: string } })
  | (TaskEventBase & { eventType: "unknown"; payload: { originalType: string; raw: unknown } });

export interface CommandBase {
  commandId: string;
  taskId: string | null;
  actor: string;
  expectedSequence: number | null;
  idempotencyKey: string;
  clientVersion: string;
}

export type Command =
  | (CommandBase & { commandType: "task.create"; arguments: { title: string; requestSummary: string; inputManifestRef: string } })
  | (CommandBase & { commandType: "task.submit" | "task.pause" | "task.stop" | "task.resume"; arguments: Record<string, never> })
  | (CommandBase & { commandType: "task.answer_question"; arguments: { questionId: string; answer: string } })
  | (CommandBase & { commandType: "artifact.approve" | "artifact.return_for_changes"; arguments: { artifactId: string; reason?: string } })
  | (CommandBase & { commandType: "node.recheck"; arguments: Record<string, never> });

export type CommandResult =
  | { outcome: "accepted"; commandId: string; ledgerEventRef: string }
  | { outcome: "rejected"; commandId: string; code: string; message: string; ledgerEventRef: string | null }
  | { outcome: "needs_review"; commandId: string; reason: string; ledgerEventRef: string };

export interface TaskProjection {
  taskId: string;
  schemaVersion: string;
  snapshotId: string;
  title: string;
  requestSummary: string;
  status: TaskStatus;
  phase: string;
  clearanceContext: Clearance;
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
  return {
    taskId: snapshot.taskId,
    schemaVersion: snapshot.schemaVersion,
    snapshotId: snapshot.snapshotId,
    title: snapshot.title,
    requestSummary: snapshot.requestSummary,
    status: snapshot.status,
    phase: snapshot.phase,
    clearanceContext: snapshot.clearanceContext,
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

  if (event.eventType === "task.accepted" || event.eventType === "plan.created" || event.eventType === "plan.revised" || event.eventType === "task.paused" || event.eventType === "task.resumed" || event.eventType === "task.blocked" || event.eventType === "task.failed" || event.eventType === "task.stopped" || event.eventType === "task.completed") {
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
