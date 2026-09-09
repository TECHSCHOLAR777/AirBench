import { describe, expect, it } from "vitest";
import type { TaskProjection } from "../../platform/events/protocol";
import { buildRecordGateway } from "./recordGateway";

const task: TaskProjection = {
  taskId: "task-1",
  schemaVersion: "0.1",
  compatibilityId: "airbench-node-protocol",
  snapshotId: "snapshot-1",
  title: "Inspection approval note",
  requestSummary: "Review the report.",
  status: "needs_review",
  phase: "review",
  clearanceContext: "restricted",
  inputManifestRef: "intake-1",
  nodeConnectionRef: "node-1",
  ledgerHeadRef: "ledger-head-9",
  lastAppliedSequence: 9,
  evidence: [],
  facts: [],
  artifactRefs: [],
  unresolvedQuestions: [],
  activity: [],
  diagnostics: [],
  health: "current",
};

describe("record gateway", () => {
  it("does not describe a missing review query as an empty queue", () => {
    const gateway = buildRecordGateway("review", true, null);

    expect(gateway).toMatchObject({
      title: "Review queue is not supplied",
      state: "query_not_supplied",
      stateLabel: "Record query not supplied",
      currentTask: null,
    });
    expect(`${gateway.description} ${gateway.stateDescription}`).not.toMatch(/nothing is waiting|no review items/i);
  });

  it("fails closed while disconnected and does not reveal locally-held task context", () => {
    const gateway = buildRecordGateway("audit", false, task);

    expect(gateway).toMatchObject({
      state: "node_unavailable",
      stateLabel: "Connect an approved Node",
      currentTask: null,
    });
  });

  it("retains a permitted current-task reference without fabricating a record query", () => {
    const gateway = buildRecordGateway("artifacts", true, task);

    expect(gateway.currentTask).toEqual({
      taskId: "task-1",
      title: "Inspection approval note",
      status: "needs_review",
      phase: "review",
      ledgerHeadRef: "ledger-head-9",
    });
    expect(gateway.requiredProjection).toMatch(/Node-issued artifact library/);
  });

  it("does not present a stale task projection as current record context", () => {
    const gateway = buildRecordGateway("review", true, { ...task, health: "resynchronizing" });

    expect(gateway).toMatchObject({
      state: "projection_not_current",
      stateLabel: "Task context is not current",
      currentTask: null,
    });
    expect(gateway.stateDescription).toContain("will not show it as current context");
  });
});
