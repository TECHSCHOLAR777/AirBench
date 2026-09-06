import { describe, expect, it } from "vitest";
import { maySendConsequentialCommand, TaskEventStore } from "./eventStore";
import { applyEvent, projectionFromSnapshot, type TaskEvent, type TaskSnapshot } from "./protocol";

const snapshot: TaskSnapshot = {
  taskId: "task-1",
  schemaVersion: "0.1",
  snapshotId: "snapshot-1",
  asOfSequence: 4,
  title: "Inspection approval note",
  requestSummary: "Review a scanned inspection report.",
  status: "running",
  phase: "evidence",
  clearanceContext: "restricted",
  inputManifestRef: "manifest-1",
  evidence: [],
  facts: [],
  artifactRefs: [],
  unresolvedQuestions: [],
  nodeConnectionRef: "node-1",
  ledgerHeadRef: "ledger-4",
};

const event = (sequence: number, eventType: TaskEvent["eventType"], payload: TaskEvent["payload"]): TaskEvent => ({
  eventId: `event-${sequence}`,
  taskId: "task-1",
  sequence,
  schemaVersion: "0.1",
  occurredAt: "2026-09-06T00:00:00Z",
  actor: "orchestrator",
  clearanceContext: "restricted",
  payloadHash: `hash-${sequence}`,
  ledgerEventRef: `ledger-${sequence}`,
  eventType: eventType as never,
  payload: payload as never,
});

describe("sequence-numbered task projection", () => {
  it("applies the next event and preserves the authoritative activity", () => {
    const result = applyEvent(projectionFromSnapshot(snapshot), event(5, "task.paused", { phase: "paused", status: "stopped" }));
    expect(result.kind).toBe("applied");
    if (result.kind === "applied") {
      expect(result.projection.status).toBe("stopped");
      expect(result.projection.lastAppliedSequence).toBe(5);
      expect(result.projection.activity[0]?.ledgerEventRef).toBe("ledger-5");
    }
  });

  it("does not apply a duplicate event twice", () => {
    const projection = projectionFromSnapshot(snapshot);
    const first = applyEvent(projection, event(5, "task.paused", { phase: "paused", status: "stopped" }));
    expect(first.kind).toBe("applied");
    if (first.kind === "applied") {
      const duplicate = applyEvent(first.projection, event(5, "task.paused", { phase: "paused", status: "stopped" }));
      expect(duplicate.kind).toBe("duplicate");
      expect(duplicate.projection.activity).toHaveLength(1);
    }
  });

  it("stops on a gap and requests replay instead of guessing", () => {
    const result = applyEvent(projectionFromSnapshot(snapshot), event(7, "task.completed", { phase: "complete", status: "completed" }));
    expect(result.kind).toBe("gap");
    if (result.kind === "gap") {
      expect(result.expectedSequence).toBe(5);
      expect(result.projection.lastAppliedSequence).toBe(4);
      expect(result.projection.health).toBe("resynchronizing");
    }
  });

  it("preserves unknown events in diagnostics without mutating authority", () => {
    const unknown = event(5, "unknown", { originalType: "future.event", raw: { value: "data" } });
    const result = applyEvent(projectionFromSnapshot(snapshot), unknown);
    expect(result.kind).toBe("unknown");
    expect(result.projection.lastAppliedSequence).toBe(5);
    expect(result.projection.diagnostics[0]?.code).toBe("unknown_event");
  });

  it("requests replay and blocks consequential commands while a gap is open", () => {
    const store = new TaskEventStore();
    store.loadSnapshot(snapshot);
    const result = store.apply(event(7, "task.completed", { phase: "complete", status: "completed" }));
    expect(result.kind).toBe("replay_required");
    expect(store.requestForGap()).toEqual({ taskId: "task-1", fromSequence: 5 });
    expect(maySendConsequentialCommand(store.current())).toBe(false);
  });

  it("resynchronizes by replacing the projection with a fresh snapshot", () => {
    const store = new TaskEventStore();
    store.loadSnapshot(snapshot);
    store.apply(event(7, "task.completed", { phase: "complete", status: "completed" }));
    const replacement = { ...snapshot, snapshotId: "snapshot-2", asOfSequence: 8, status: "completed" as const, phase: "complete" };
    const projection = store.replaceSnapshot(replacement);
    expect(projection.lastAppliedSequence).toBe(8);
    expect(projection.status).toBe("completed");
    expect(projection.health).toBe("current");
    expect(maySendConsequentialCommand(projection)).toBe(true);
  });
});
