import type { TaskProjection } from "./protocol";
import { buildWorkTrace } from "./workTrace";

export interface HomeWorkSummary {
  taskId: string;
  title: string;
  requestSummary: string;
  status: TaskProjection["status"];
  statusLabel: string;
  phase: string;
  health: TaskProjection["health"];
  healthLabel: string;
  lastAppliedSequence: number;
  ledgerHeadRef: string;
  latestActivity: {
    label: string;
    summary: string;
    occurredAt: string;
    sequence: number;
    ledgerEventRef: string;
  } | null;
}

const statusLabels: Record<TaskProjection["status"], string> = {
  accepted: "Accepted",
  planning: "Planning",
  running: "Running",
  needs_review: "Needs review",
  completed: "Completed",
  blocked: "Blocked",
  failed: "Failed",
  stopped: "Stopped",
};

const healthLabels: Record<TaskProjection["health"], string> = {
  current: "Current snapshot",
  replaying: "Replaying events",
  resynchronizing: "Resynchronizing",
  blocked: "Stream blocked",
};

/**
 * Creates a deliberately small Home projection from the existing task snapshot.
 * It reuses the trace's deterministic sequence ordering, but excludes raw
 * payloads, model reasoning, and transport hashes from the Home surface.
 */
export function buildHomeWorkSummary(projection: TaskProjection): HomeWorkSummary {
  const latestActivity = buildWorkTrace(projection, null).latestActivity;

  return {
    taskId: projection.taskId,
    title: projection.title,
    requestSummary: projection.requestSummary,
    status: projection.status,
    statusLabel: statusLabels[projection.status],
    phase: projection.phase,
    health: projection.health,
    healthLabel: healthLabels[projection.health],
    lastAppliedSequence: projection.lastAppliedSequence,
    ledgerHeadRef: projection.ledgerHeadRef,
    latestActivity: latestActivity ? {
      label: latestActivity.label,
      summary: latestActivity.summary,
      occurredAt: latestActivity.occurredAt,
      sequence: latestActivity.sequence,
      ledgerEventRef: latestActivity.ledgerEventRef,
    } : null,
  };
}
