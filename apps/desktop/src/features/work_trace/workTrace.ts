import type { NodeExecutionEventPayload, NodeRouteTrace, NodeRouteTraceEntry, TaskPlanReview } from "../../generated/core_contracts";
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
  state: "plan_context" | "route_context" | "not_supplied";
  executionMode: string | null;
  hardwareProfileRef: string | null;
  hardwareReason: string | null;
  capabilityLanes: Record<string, string>;
  planLedgerEventRef: string | null;
  planVersionHash: string | null;
  policyVersionHash: string | null;
  selectedTarget: string | null;
  fallbackReason: string | null;
  policyReason: string | null;
  routeEntries: NodeRouteTraceEntry[];
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
  execution: { workers: WorkTraceActivity[]; tools: WorkTraceActivity[]; coordination: WorkTraceActivity[] };
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

export function buildWorkTrace(projection: TaskProjection, plan: TaskPlanReview | null, routeTrace: NodeRouteTrace | null = null): WorkTrace {
  // Event delivery is normally ordered by TaskEventSynchronizer. Keep the trace
  // deterministic even when a fixture or a future transport adapter provides a
  // defensively valid but unsorted projection.
  const activity = [...projection.activity]
    .sort((first, second) => first.sequence - second.sequence)
    .map(toTraceActivity);
  const execution = {
    workers: activity.filter((item) => item.eventType === "worker.started" || item.eventType === "worker.completed"),
    tools: activity.filter((item) => item.eventType === "tool.started" || item.eventType === "tool.completed"),
    coordination: activity.filter((item) => item.stage === "execution" && item.eventType !== "worker.started" && item.eventType !== "worker.completed" && item.eventType !== "tool.started" && item.eventType !== "tool.completed"),
  };
  const evidenceEvents = activity.filter((item) => item.stage === "evidence");
  const verificationEvents = activity.filter((item) => item.stage === "verification");
  const reviewEvents = activity.filter((item) => item.stage === "review");
  const artifactEvents = activity.filter((item) => item.stage === "artifacts");
  const artifactRecords = buildArtifactRecords(projection.artifactRefs, artifactEvents);
  const records = projection.evidence.map(toEvidenceRecord);
  const routing = routingFromPlan(plan, routeTrace);
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

function routingFromPlan(plan: TaskPlanReview | null, routeTrace: NodeRouteTrace | null): WorkTraceRouting {
  const routeEntries = routeTrace?.entries.map((entry) => ({ ...entry })) ?? [];
  if (!plan && !routeTrace) {
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
      routeEntries,
    };
  }
  const latestSelectedTarget = [...routeEntries].reverse().find((entry) => entry.selectedTarget)?.selectedTarget ?? null;
  const fallbackEntry = [...routeEntries].reverse().find((entry) => entry.fallbackTarget || entry.eventType === "routing.fallback.selected" || entry.eventType === "fallback.selected");
  const policyEntry = [...routeEntries].reverse().find((entry) => entry.decisionSource || entry.ruleOrThreshold || entry.reason);
  const fallbackReason = fallbackEntry ? [fallbackEntry.fallbackTarget, fallbackEntry.reason].filter(Boolean).join(" / ") || "Fallback was recorded by the Node." : null;
  const policyReason = policyEntry ? [policyEntry.decisionSource, policyEntry.ruleOrThreshold, policyEntry.reason].filter(Boolean).join(" / ") || "Routing policy context was recorded by the Node." : null;
  return {
    state: routeTrace ? "route_context" : "plan_context",
    executionMode: plan?.execution_mode ?? null,
    hardwareProfileRef: plan?.hardware_profile_ref ?? null,
    hardwareReason: plan?.hardware_reason ?? null,
    capabilityLanes: plan ? { ...plan.worker_capabilities } : {},
    planLedgerEventRef: plan?.ledger_event_ref ?? null,
    planVersionHash: plan?.plan_version_hash ?? null,
    policyVersionHash: plan?.policy_version_hash ?? null,
    selectedTarget: latestSelectedTarget,
    fallbackReason,
    policyReason,
    routeEntries,
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
    case "team.created":
    case "team.execution.started":
    case "team.execution.completed":
    case "team.execution.failed":
    case "team.execution.cancelled":
    case "lifecycle.intercepted":
    case "lifecycle.blocked":
    case "worker.assigned":
    case "worker.failed":
    case "worker.handoff":
    case "worker.handoff.rejected":
    case "worker.handoff.late":
    case "worker.resource_reserved":
    case "worker.preempted":
    case "worker.cancelled":
    case "team.resource_plan.created":
    case "team.resource_plan.admitted":
    case "team.resource_plan.queued":
    case "team.resource_plan.degraded_needs_review":
    case "team.resource_plan.rejected":
    case "team.resource_plan.released":
    case "team.resource_plan.cancelled":
    case "resource.plan.admitted":
    case "resource.plan.queued":
    case "execution.mode.selected":
    case "execution.mode.changed":
    case "join_barrier.waiting":
    case "join_barrier.completed":
    case "join_barrier.resolved":
    case "barrier.waiting":
    case "barrier.completed":
    case "resource.exhaustion.detected":
    case "resource.recovered":
    case "resource.queue.updated":
    case "resource.lease.granted":
    case "resource.lease.activated":
    case "resource.lease.released":
    case "resource.lease.expired":
    case "resource.lease.cancelled":
    case "resource.lease.failed":
    case "resource.admission.degraded":
    case "background.work.yielded":
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
  if (event.eventType === "verification.failed" || event.eventType === "approval.returned" || event.eventType === "task.blocked" || event.eventType === "task.failed" || event.eventType === "task.stopped" || event.eventType === "team.execution.failed" || event.eventType === "team.resource_plan.rejected" || event.eventType === "worker.failed" || event.eventType === "worker.handoff.rejected" || event.eventType === "worker.handoff.late" || event.eventType === "resource.exhaustion.detected" || event.eventType === "lifecycle.blocked" || event.eventType === "lifecycle.intercepted" || event.eventType === "resource.lease.failed") return "attention";
  if (event.eventType === "worker.started" || event.eventType === "tool.started" || event.eventType === "task.resumed" || event.eventType === "team.execution.started" || event.eventType === "worker.assigned" || event.eventType === "join_barrier.waiting" || event.eventType === "barrier.waiting" || event.eventType === "team.resource_plan.queued" || event.eventType === "resource.plan.queued" || event.eventType === "resource.queue.updated" || event.eventType === "resource.lease.activated") return "active";
  if (event.eventType === "worker.completed" || event.eventType === "tool.completed" || event.eventType === "verification.completed" || event.eventType === "approval.recorded" || event.eventType === "artifact.ready" || event.eventType === "task.completed" || event.eventType === "team.execution.completed" || event.eventType === "team.resource_plan.admitted" || event.eventType === "resource.plan.admitted" || event.eventType === "join_barrier.completed" || event.eventType === "barrier.completed" || event.eventType === "resource.recovered" || event.eventType === "resource.lease.released") return "success";
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
    "team.created": "Team created",
    "team.execution.started": "Team execution started",
    "team.execution.completed": "Team execution completed",
    "team.execution.failed": "Team execution failed",
    "team.execution.cancelled": "Team execution cancelled",
    "lifecycle.intercepted": "Execution intercepted",
    "lifecycle.blocked": "Execution blocked",
    "worker.assigned": "Worker assigned",
    "worker.failed": "Worker failed",
    "worker.handoff": "Worker handoff recorded",
    "worker.handoff.rejected": "Worker handoff rejected",
    "worker.handoff.late": "Worker handoff late",
    "worker.resource_reserved": "Worker resources reserved",
    "worker.preempted": "Worker preempted",
    "worker.cancelled": "Worker cancelled",
    "team.resource_plan.created": "Resource plan created",
    "team.resource_plan.admitted": "Resource plan admitted",
    "team.resource_plan.queued": "Resource plan queued",
    "team.resource_plan.degraded_needs_review": "Resource plan needs review",
    "team.resource_plan.rejected": "Resource plan rejected",
    "team.resource_plan.released": "Resource plan released",
    "team.resource_plan.cancelled": "Resource plan cancelled",
    "resource.plan.admitted": "Resource plan admitted",
    "resource.plan.queued": "Resource plan queued",
    "execution.mode.selected": "Execution mode selected",
    "execution.mode.changed": "Execution mode changed",
    "join_barrier.waiting": "Join barrier waiting",
    "join_barrier.completed": "Join barrier completed",
    "join_barrier.resolved": "Join barrier resolved",
    "barrier.waiting": "Barrier waiting",
    "barrier.completed": "Barrier completed",
    "resource.exhaustion.detected": "Resource exhaustion detected",
    "resource.recovered": "Resources recovered",
    "resource.queue.updated": "Resource queue updated",
    "resource.lease.granted": "Resource lease granted",
    "resource.lease.activated": "Resource lease activated",
    "resource.lease.released": "Resource lease released",
    "resource.lease.expired": "Resource lease expired",
    "resource.lease.cancelled": "Resource lease cancelled",
    "resource.lease.failed": "Resource lease failed",
    "resource.admission.degraded": "Resource admission degraded",
    "background.work.yielded": "Background work yielded",
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
    case "team.created":
    case "team.execution.started":
    case "team.execution.completed":
    case "team.execution.failed":
    case "team.execution.cancelled":
    case "lifecycle.intercepted":
    case "lifecycle.blocked":
    case "worker.assigned":
    case "worker.failed":
    case "worker.handoff":
    case "worker.handoff.rejected":
    case "worker.handoff.late":
    case "worker.resource_reserved":
    case "worker.preempted":
    case "worker.cancelled":
    case "team.resource_plan.created":
    case "team.resource_plan.admitted":
    case "team.resource_plan.queued":
    case "team.resource_plan.degraded_needs_review":
    case "team.resource_plan.rejected":
    case "team.resource_plan.released":
    case "team.resource_plan.cancelled":
    case "resource.plan.admitted":
    case "resource.plan.queued":
    case "execution.mode.selected":
    case "execution.mode.changed":
    case "join_barrier.waiting":
    case "join_barrier.completed":
    case "join_barrier.resolved":
    case "barrier.waiting":
    case "barrier.completed":
    case "resource.exhaustion.detected":
    case "resource.recovered":
    case "resource.queue.updated":
    case "resource.lease.granted":
    case "resource.lease.activated":
    case "resource.lease.released":
    case "resource.lease.expired":
    case "resource.lease.cancelled":
    case "resource.lease.failed":
    case "resource.admission.degraded":
    case "background.work.yielded":
      return executionSummary(event.payload);
    case "unknown":
      return "The Node returned an event this desktop cannot safely interpret.";
  }
}

function executionSummary(payload: NodeExecutionEventPayload): string {
  const details = [payload.teamId, payload.assignmentId, payload.workerId, payload.barrierId, payload.executionMode].filter(Boolean);
  return details.length > 0 ? `${payload.summary} [${details.join(" · ")}]` : payload.summary;
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
