import { describe, expect, it } from "vitest";
import type { TaskProjection } from "./protocol";
import { buildHomeWorkSummary } from "./homeWorkSummary";

const projection: TaskProjection = {
  taskId: "task-inspection-1",
  schemaVersion: "0.1",
  compatibilityId: "airbench-node-protocol",
  snapshotId: "snapshot-1",
  title: "Inspection approval note",
  requestSummary: "Review a scanned inspection report and prepare the approval note.",
  status: "running",
  phase: "verification",
  clearanceContext: "restricted",
  inputManifestRef: "intake-1",
  nodeConnectionRef: "node-1",
  ledgerHeadRef: "ledger-head-12",
  lastAppliedSequence: 12,
  evidence: [],
  facts: [],
  artifactRefs: [],
  unresolvedQuestions: [],
  diagnostics: [],
  health: "current",
  activity: [],
};

describe("Home current-work summary", () => {
  it("shows the latest typed Node record in deterministic sequence order", () => {
    const summary = buildHomeWorkSummary({
      ...projection,
      activity: [
        {
          eventId: "event-12",
          taskId: projection.taskId,
          sequence: 12,
          schemaVersion: "0.1",
          compatibilityId: "airbench-node-protocol",
          eventType: "verification.completed",
          occurredAt: "2026-09-07T10:32:00Z",
          actor: "verifier",
          clearanceContext: "restricted",
          payloadHash: "payload-12",
          ledgerEventRef: "ledger-12",
          payload: { summary: "Required verification checks passed.", passed: true },
        },
        {
          eventId: "event-11",
          taskId: projection.taskId,
          sequence: 11,
          schemaVersion: "0.1",
          compatibilityId: "airbench-node-protocol",
          eventType: "worker.completed",
          occurredAt: "2026-09-07T10:31:00Z",
          actor: "orchestrator",
          clearanceContext: "restricted",
          payloadHash: "payload-11",
          ledgerEventRef: "ledger-11",
          payload: { role: "research", label: "Review source report", status: "completed" },
        },
      ],
    });

    expect(summary).toMatchObject({
      taskId: "task-inspection-1",
      status: "running",
      statusLabel: "Running",
      healthLabel: "Current snapshot",
      lastAppliedSequence: 12,
      ledgerHeadRef: "ledger-head-12",
      latestActivity: {
        label: "Verification completed",
        summary: "Required verification checks passed.",
        sequence: 12,
        ledgerEventRef: "ledger-12",
      },
    });
    expect(summary.latestActivity).not.toHaveProperty("payloadHash");
  });

  it("labels a non-current projection without treating it as completed or actionable", () => {
    const summary = buildHomeWorkSummary({ ...projection, status: "needs_review", health: "resynchronizing" });

    expect(summary).toMatchObject({ statusLabel: "Needs review", healthLabel: "Resynchronizing", latestActivity: null });
  });
});
