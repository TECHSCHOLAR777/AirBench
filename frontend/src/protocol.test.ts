import { describe, expect, it } from "vitest";
import { maySendConsequentialCommand, CommandDeduplicator, TaskEventStore, TaskEventSynchronizer } from "./eventStore";
import type { TaskEventBatch } from "./eventTransport";
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

const batch = (events: TaskEvent[], nextSequence: number, hasMore = false): TaskEventBatch => ({
  stream_id: "task-1",
  node_identity: "node-1",
  protocol_version: "0.1",
  clearance_context: "restricted",
  events,
  next_sequence: nextSequence,
  has_more: hasMore,
  ledger_event_refs: events.map((item) => item.ledgerEventRef),
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
    expect(projection.snapshotId).toBe("snapshot-2");
    expect(projection.ledgerHeadRef).toBe("ledger-4");
    expect(projection.health).toBe("current");
    expect(maySendConsequentialCommand(projection, "connected")).toBe(true);
  });

  it("applies a cursor batch until a gap and prevents duplicate command reservation", () => {
    const store = new TaskEventStore();
    store.loadSnapshot(snapshot);
    const results = store.applyBatch({
      stream_id: "task-1",
      node_identity: "node-1",
      protocol_version: "0.1",
      clearance_context: "restricted",
      events: [
        event(5, "worker.started", { role: "planner", label: "Plan", status: "running" }),
        event(7, "task.completed", { phase: "complete", status: "completed" }),
      ],
      next_sequence: 7,
      has_more: false,
      ledger_event_refs: ["ledger-5", "ledger-7"],
    });
    expect(results.map((result) => result.kind)).toEqual(["applied", "replay_required"]);
    expect(store.requestForGap()).toEqual({ taskId: "task-1", fromSequence: 6 });

    const deduplicator = new CommandDeduplicator();
    expect(deduplicator.tryReserve("idem-1")).toBe(true);
    expect(deduplicator.tryReserve("idem-1")).toBe(false);
    deduplicator.release("idem-1");
    expect(deduplicator.tryReserve("idem-1")).toBe(true);
  });

  it("replays a gap from the applied cursor before returning current", async () => {
    const calls: Array<[string, number]> = [];
    const batches = [
      batch([
        event(5, "worker.started", { role: "planner", label: "Plan", status: "running" }),
        event(7, "task.completed", { phase: "complete", status: "completed" }),
      ], 7),
      batch([
        event(6, "tool.completed", { role: "file_intake", label: "Read report", status: "completed" }),
        event(7, "task.completed", { phase: "complete", status: "completed" }),
      ], 7),
    ];
    const synchronizer = new TaskEventSynchronizer(async (taskId, afterSequence) => {
      calls.push([taskId, afterSequence]);
      return batches.shift() as TaskEventBatch;
    });
    synchronizer.loadSnapshot(snapshot);

    const result = await synchronizer.synchronizeOnce();

    expect(result.kind).toBe("current");
    expect(result.projection.lastAppliedSequence).toBe(7);
    expect(calls).toEqual([["task-1", 4], ["task-1", 5]]);
    expect(maySendConsequentialCommand(result.projection, result.state.status)).toBe(true);
  });

  it("retries a temporary disconnect and gates commands while reconnecting", async () => {
    let calls = 0;
    const sleeps: number[] = [];
    const synchronizer = new TaskEventSynchronizer(async () => {
      calls += 1;
      if (calls < 3) throw new Error("The approved Node could not be reached.");
      return batch([], 4);
    });
    synchronizer.loadSnapshot(snapshot);

    const result = await synchronizer.synchronizeWithRetry({
      maxAttempts: 3,
      baseDelayMs: 10,
      sleep: async (durationMs) => { sleeps.push(durationMs); },
    });

    expect(result.kind).toBe("current");
    expect(result.state.attempt).toBe(3);
    expect(sleeps).toEqual([10, 20]);
    expect(maySendConsequentialCommand(result.projection, "reconnecting")).toBe(false);
  });

  it("replaces the projection after replay refuses to converge", async () => {
    let snapshotCalls = 0;
    const synchronizer = new TaskEventSynchronizer(
      async () => batch([event(7, "task.completed", { phase: "complete", status: "completed" })], 7),
      async () => {
        snapshotCalls += 1;
        return { ...snapshot, snapshotId: "snapshot-3", asOfSequence: 8, status: "completed", phase: "complete", ledgerHeadRef: "ledger-8" };
      },
    );
    synchronizer.loadSnapshot(snapshot);

    const result = await synchronizer.synchronizeOnce();

    expect(result.kind).toBe("current");
    expect(snapshotCalls).toBe(1);
    expect(result.projection.lastAppliedSequence).toBe(8);
    expect(result.projection.status).toBe("completed");
    expect(result.state.lastLedgerEventRefs).toEqual(["ledger-8"]);
  });

  it("fails closed for a protocol batch from another task", async () => {
    const synchronizer = new TaskEventSynchronizer(async () => ({ ...batch([], 4), stream_id: "other-task" }));
    synchronizer.loadSnapshot(snapshot);

    const result = await synchronizer.synchronizeOnce();

    expect(result.kind).toBe("blocked");
    expect(result.state.status).toBe("blocked");
    expect(result.state.error?.code).toBe("event_protocol_invalid");
    expect(result.projection.health).toBe("blocked");
    expect(maySendConsequentialCommand(result.projection, result.state.status)).toBe(false);
  });

  it("does not treat a loaded snapshot as command-ready before synchronization", () => {
    expect(maySendConsequentialCommand(projectionFromSnapshot(snapshot))).toBe(false);
  });
});
