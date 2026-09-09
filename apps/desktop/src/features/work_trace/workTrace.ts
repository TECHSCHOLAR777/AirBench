import type { TaskPlanReview } from "../../generated/core_contracts";
import type { EvidenceRef, TaskEvent, TaskProjection } from "../../platform/events/protocol";

export type WorkTraceStageId = "plan" | "execution" | "evidence" | "verification" | "review" | "artifacts" | "outcome";
export type WorkTraceState = "waiting" | "active" | "recorded" | "attention";
export type WorkTraceTone = "neutral" | "active" | "success" | "attention";

export interface WorkTraceActivity {
  eventId: string;
  eventType: TaskEvent["eventType"];
  sequence: number;
  occurredAt: string;
  actor: string;
  clearance: string;
  payloadHash: string;
  ledgerEventRef: string;
  stage: WorkTraceStageId | "system";
  tone: WorkTraceTone;
  label: string;
  summary: string;
  artifactId: string | null;
}

export interface WorkTraceStage {
  id: WorkTraceStageId;
  label: string;
  state: WorkTraceState;
  summary: string;
  events: WorkTraceActivity[];
}

export interface WorkTraceEvidenceRecord {
  evidenceId: string;
  contentHash: string;
  sourceDocumentId: string;
  sourceVersion: string;
  sourceLocation: EvidenceRef["source"]["location"];
  confidence: number;
  clearance: string;
  taint: string;
  extractionMethod: string;
  ledgerEventRef: string;
}

export interface WorkTraceRouting {
  state: "plan_context" | "not_supplied";
  executionMode: string | null;
  hardwareProfileRef: string | null;
  hardwareReason: string | null;
  capabilityLanes: Record<string, string>;
  planLedgerEventRef: string | null;
  planVersionHash: string | null;
  policyVersionHash: string | null;
  selectedTarget: null;
  fallbackReason: null;
  policyReason: null;
}

export type WorkTraceArtifactState = "ready" | "superseded" | "reference_only";

export interface WorkTraceArtifactRecord {
  artifactId: string;
  state: WorkTraceArtifactState;
  latestEvent: WorkTraceActivity | null;
}

export interface WorkTrace {
  activity: WorkTraceActivity[];
  latestActivity: WorkTraceActivity | null;
  stages: WorkTraceStage[];
  execution: { workers: WorkTraceActivity[]; tools: WorkTraceActivity[] };
  evidence: { records: WorkTraceEvidenceRecord[]; events: WorkTraceActivity[] };
  verification: { events: WorkTraceActivity[]; latest: WorkTraceActivity | null };
  review: { events: WorkTraceActivity[]; questions: string[] };
  artifacts: { events: WorkTraceActivity[]; ids: string[]; records: WorkTraceArtifactRecord[] };
  routing: WorkTraceRouting;
}

const stageOrder: Array<{ id: WorkTraceStageId; label: string }> = [
  { id: "plan", label: "Plan" },
  { id: "execution", label: "Work" },
  { id: "evidence", label: "Evidence" },
  { id: "verification", label: "Verification" },
  { id: "review", label: "Review" },
  { id: "artifacts", label: "Artifacts" },
  { id: "outcome", label: "Outcome" },
];

export function buildWorkTrace(projection: TaskProjection, plan: TaskPlanReview | null): WorkTrace {
  // Event delivery is normally ordered by TaskEventSynchronizer. Keep the trace
  // deterministic even when a fixture or a future transport adapter provides a
  // defensively valid but unsorted projection.
  const activity = [...projection.activity]
    .sort((first, second) => first.sequence - second.sequence)
    .map(toTraceActivity);
  const execution = {
    workers: activity.filter((item) => item.eventType === "worker.started" || item.eventType === "worker.completed"),
    tools: activity.filter((item) => item.eventType === "tool.started" || item.eventType === "tool.completed"),
  };
  const evidenceEvents = activity.filter((item) => item.stage === "evidence");
  const verificationEvents = activity.filter((item) => item.stage === "verification");
  const reviewEvents = activity.filter((item) => item.stage === "review");
  const artifactEvents = activity.filter((item) => item.stage === "artifacts");
  const artifactRecords = buildArtifactRecords(projection.artifactRefs, artifactEvents);
  const records = projection.evidence.map(toEvidenceRecord);
  const routing = routingFromPlan(plan);
  const stages = stageOrder.map(({ id, label }) => {
    const events = activity.filter((item) => item.stage === id);
    return {
      id,
      label,
      events,
      state: stageState(id, events, projection, plan),
      summary: stageSummary(id, events, projection, plan),
    };
  });

  return {
    activity,
    latestActivity: activity.at(-1) ?? null,
    stages,
    execution,
    evidence: { records, events: evidenceEvents },
    verification: { events: verificationEvents, latest: verificationEvents.at(-1) ?? null },
    review: { events: reviewEvents, questions: [...projection.unresolvedQuestions] },
    artifacts: { events: artifactEvents, ids: [...projection.artifactRefs], records: artifactRecords },
    routing,
  };
}

function buildArtifactRecords(artifactRefs: string[], artifactEvents: WorkTraceActivity[]): WorkTraceArtifactRecord[] {
  const records = new Map<string, WorkTraceArtifactRecord>();
  for (const event of artifactEvents) {
    const artifactId = event.artifactId;
    if (!artifactId) continue;
    records.set(artifactId, {
      artifactId,
      state: event.eventType === "artifact.superseded" ? "superseded" : "ready",
      latestEvent: event,
    });
  }
  for (const artifactId of artifactRefs) {
    if (!records.has(artifactId)) records.set(artifactId, { artifactId, state: "reference_only", latestEvent: null });
  }
  return [...records.values()];
}

export function formatTraceTime(occurredAt: string): string {
  return `Node time ${occurredAt}`;
}

function toTraceActivity(event: TaskEvent): WorkTraceActivity {
  return {
    eventId: event.eventId,
    eventType: event.eventType,
    sequence: event.sequence,
    occurredAt: event.occurredAt,
    actor: event.actor,
    clearance: event.clearanceContext,
    payloadHash: event.payloadHash,
    ledgerEventRef: event.ledgerEventRef,
    stage: stageForEvent(event),
    tone: toneForEvent(event),
    label: eventLabel(event),
    summary: eventSummary(event),
    artifactId: event.eventType === "artifact.ready" || event.eventType === "artifact.superseded" ? event.payload.artifactId : null,
  };
}

function toEvidenceRecord(evidence: EvidenceRef): WorkTraceEvidenceRecord {
  return {
    evidenceId: evidence.evidenceId,
    contentHash: evidence.contentHash,
    sourceDocumentId: evidence.source.sourceDocumentId,
    sourceVersion: evidence.source.sourceVersion,
    sourceLocation: evidence.source.location,
    confidence: evidence.confidence,
    clearance: evidence.clearance,
    taint: evidence.taint,
    extractionMethod: evidence.source.extractionMethod,
    ledgerEventRef: evidence.source.ledgerEventRef,
  };
}

function routingFromPlan(plan: TaskPlanReview | null): WorkTraceRouting {
  if (!plan) {
    return {
      state: "not_supplied",
      executionMode: null,
      hardwareProfileRef: null,
      hardwareReason: null,
      capabilityLanes: {},
      planLedgerEventRef: null,
      planVersionHash: null,
      policyVersionHash: null,
      selectedTarget: null,
      fallbackReason: null,
      policyReason: null,
    };
  }
  return {
    state: "plan_context",
    executionMode: plan.execution_mode,
    hardwareProfileRef: plan.hardware_profile_ref,
    hardwareReason: plan.hardware_reason,
    capabilityLanes: { ...plan.worker_capabilities },
    planLedgerEventRef: plan.ledger_event_ref,
    planVersionHash: plan.plan_version_hash,
    policyVersionHash: plan.policy_version_hash,
    selectedTarget: null,
    fallbackReason: null,
    policyReason: null,
  };
}

function stageForEvent(event: TaskEvent): WorkTraceStageId | "system" {
  switch (event.eventType) {
    case "task.accepted":
    case "plan.created":
    case "plan.revised":
    case "plan.approved":
      return "plan";
    case "worker.started":
    case "worker.completed":
    case "tool.started":
    case "tool.completed":
      return "execution";
    case "evidence.added":
    case "evidence.revised":
      return "evidence";
    case "verification.completed":
    case "verification.failed":
      return "verification";
    case "approval.required":
    case "approval.recorded":
    case "approval.returned":
      return "review";
    case "artifact.ready":
    case "artifact.superseded":
      return "artifacts";
    case "task.paused":
    case "task.resumed":
    case "task.blocked":
    case "task.failed":
    case "task.stopped":
    case "task.completed":
      return "outcome";
    default:
      return "system";
  }
}

function toneForEvent(event: TaskEvent): WorkTraceTone {
  if (event.eventType === "verification.failed" || event.eventType === "approval.returned" || event.eventType === "task.blocked" || event.eventType === "task.failed" || event.eventType === "task.stopped") return "attention";
  if (event.eventType === "worker.started" || event.eventType === "tool.started" || event.eventType === "task.resumed") return "active";
  if (event.eventType === "worker.completed" || event.eventType === "tool.completed" || event.eventType === "verification.completed" || event.eventType === "approval.recorded" || event.eventType === "artifact.ready" || event.eventType === "task.completed") return "success";
  return "neutral";
}

function eventLabel(event: TaskEvent): string {
  const labels: Record<TaskEvent["eventType"], string> = {
    "task.accepted": "Task accepted",
    "plan.created": "Plan created",
    "plan.revised": "Plan revised",
    "plan.approved": "Plan approved",
    "task.paused": "Task paused",
    "task.resumed": "Task resumed",
    "task.blocked": "Task blocked",
    "task.failed": "Task failed",
    "task.stopped": "Task stopped",
    "task.completed": "Task completed",
    "worker.started": "Worker started",
    "worker.completed": "Worker completed",
    "tool.started": "Tool started",
    "tool.completed": "Tool completed",
    "evidence.added": "Evidence added",
    "evidence.revised": "Evidence revised",
    "verification.completed": "Verification completed",
    "verification.failed": "Verification failed",
    "approval.required": "Approval required",
    "approval.recorded": "Approval recorded",
    "approval.returned": "Approval returned",
    "artifact.ready": "Artifact ready",
    "artifact.superseded": "Artifact superseded",
    "ledger.written": "Ledger entry recorded",
    "ledger.verification_changed": "Ledger verification changed",
    "node.connection_changed": "Node connection changed",
    "node.sovereignty_changed": "Node sovereignty changed",
    unknown: "Unknown Node event",
  };
  return labels[event.eventType];
}

function eventSummary(event: TaskEvent): string {
  switch (event.eventType) {
    case "task.accepted":
    case "plan.created":
    case "plan.revised":
    case "plan.approved":
    case "task.paused":
    case "task.resumed":
    case "task.blocked":
    case "task.failed":
    case "task.stopped":
    case "task.completed":
      return event.payload.summary?.trim() || `Node recorded ${event.payload.status} during ${event.payload.phase}.`;
    case "worker.started":
    case "worker.completed":
    case "tool.started":
    case "tool.completed":
      return `${event.payload.role}: ${event.payload.label} (${event.payload.status}).`;
    case "evidence.added":
    case "evidence.revised":
      return `Evidence ${event.payload.evidence.evidenceId} recorded from ${event.payload.evidence.source.sourceDocumentId} with ${Math.round(event.payload.evidence.confidence * 100)}% confidence.`;
    case "verification.completed":
    case "verification.failed":
      return event.payload.summary;
    case "approval.required":
    case "approval.recorded":
    case "approval.returned":
      return event.payload.reason;
    case "artifact.ready":
      return `Artifact ${event.payload.artifactId} is available from the Node.`;
    case "artifact.superseded":
      return `Artifact ${event.payload.artifactId} was superseded by the Node.`;
    case "ledger.written":
    case "ledger.verification_changed":
    case "node.connection_changed":
    case "node.sovereignty_changed":
      return event.payload.summary;
    case "unknown":
      return "The Node returned an event this desktop cannot safely interpret.";
  }
}

function stageState(stage: WorkTraceStageId, events: WorkTraceActivity[], projection: TaskProjection, plan: TaskPlanReview | null): WorkTraceState {
  if (events.some((event) => event.tone === "attention")) return "attention";
  if (stage === "outcome") {
    if (["failed", "blocked", "stopped"].includes(projection.status)) return "attention";
    if (projection.status === "completed") return "recorded";
    return projection.status === "running" ? "active" : "waiting";
  }
  if (stage === "review" && projection.unresolvedQuestions.length > 0) return "attention";
  if (stage === "plan" && plan && ["blocked", "rejected", "needs_review"].includes(plan.plan_state)) return "attention";
  if (events.some((event) => event.tone === "active")) return "active";
  if (events.length > 0) return "recorded";
  if (stage === "evidence" && projection.evidence.length > 0) return "recorded";
  if (stage === "artifacts" && projection.artifactRefs.length > 0) return "recorded";
  if (stage === "plan" && plan) return "recorded";
  if (stage === "execution" && projection.status === "running") return "active";
  return "waiting";
}

function stageSummary(stage: WorkTraceStageId, events: WorkTraceActivity[], projection: TaskProjection, plan: TaskPlanReview | null): string {
  const latest = events.at(-1);
  if (stage === "plan" && plan) return `Node plan: ${plan.execution_mode}; hardware context: ${plan.hardware_reason}`;
  if (stage === "evidence" && projection.evidence.length > 0) return `${projection.evidence.length} evidence record${projection.evidence.length === 1 ? "" : "s"} in the Node snapshot.`;
  if (stage === "review" && projection.unresolvedQuestions.length > 0) return `${projection.unresolvedQuestions.length} question${projection.unresolvedQuestions.length === 1 ? "" : "s"} waiting for a permitted response.`;
  if (stage === "artifacts" && projection.artifactRefs.length > 0) return `${projection.artifactRefs.length} artifact reference${projection.artifactRefs.length === 1 ? "" : "s"} in the Node snapshot.`;
  if (stage === "outcome") {
    return latest?.summary ?? `Node reports ${projection.status} in phase ${projection.phase}.`;
  }
  if (latest) return latest.summary;
  if (stage === "execution" && projection.status === "running") return `Node reports running work in phase ${projection.phase}; no worker or tool event is available in this cursor yet.`;
  return "No record has been supplied by the Node yet.";
}
