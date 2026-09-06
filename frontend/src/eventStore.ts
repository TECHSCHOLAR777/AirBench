import { applyEvent, FRONTEND_PROTOCOL_VERSION, projectionFromSnapshot, type TaskEvent, type TaskProjection, type TaskSnapshot } from "./protocol";
import type { TaskEventBatch } from "./eventTransport";

export type EventStoreOutcome =
  | { kind: "applied"; projection: TaskProjection }
  | { kind: "duplicate"; projection: TaskProjection }
  | { kind: "replay_required"; projection: TaskProjection; fromSequence: number }
  | { kind: "unknown"; projection: TaskProjection };

export type EventSyncStatus = "idle" | "syncing" | "connected" | "reconnecting" | "replaying" | "blocked";

export interface EventSyncState {
  status: EventSyncStatus;
  attempt: number;
  lastAppliedSequence: number;
  lastLedgerEventRefs: string[];
  error: { code: string; message: string } | null;
}

export type EventSyncResult =
  | { kind: "current"; projection: TaskProjection; state: EventSyncState }
  | { kind: "reconnecting"; projection: TaskProjection; state: EventSyncState }
  | { kind: "blocked"; projection: TaskProjection; state: EventSyncState };

export interface EventBatchFetcher {
  (taskId: string, afterSequence: number): Promise<TaskEventBatch>;
}

export interface SnapshotFetcher {
  (taskId: string): Promise<TaskSnapshot>;
}

export interface EventSyncRetryOptions {
  maxAttempts?: number;
  baseDelayMs?: number;
  sleep?: (durationMs: number) => Promise<void>;
}

class EventSyncProtocolError extends Error {
  readonly code = "event_protocol_invalid";
}

export interface ReplayRequest {
  taskId: string;
  fromSequence: number;
}

export class TaskEventStore {
  private projection: TaskProjection | null = null;

  loadSnapshot(snapshot: TaskSnapshot): TaskProjection {
    this.projection = projectionFromSnapshot(snapshot);
    return this.projection;
  }

  replaceSnapshot(snapshot: TaskSnapshot): TaskProjection {
    return this.loadSnapshot(snapshot);
  }

  apply(event: TaskEvent): EventStoreOutcome {
    if (!this.projection) throw new Error("A task snapshot is required before applying events.");
    const result = applyEvent(this.projection, event);
    this.projection = result.projection;
    if (result.kind === "gap") {
      return { kind: "replay_required", projection: result.projection, fromSequence: result.expectedSequence };
    }
    if (result.kind === "duplicate") return { kind: "duplicate", projection: result.projection };
    if (result.kind === "unknown") return { kind: "unknown", projection: result.projection };
    return { kind: "applied", projection: result.projection };
  }

  requestForGap(): ReplayRequest | null {
    if (!this.projection || this.projection.health !== "resynchronizing") return null;
    return { taskId: this.projection.taskId, fromSequence: this.projection.lastAppliedSequence + 1 };
  }

  applyBatch(batch: TaskEventBatch): EventStoreOutcome[] {
    const results: EventStoreOutcome[] = [];
    for (const event of batch.events) {
      results.push(this.apply(event));
      if (this.projection?.health === "resynchronizing") break;
    }
    return results;
  }

  current(): TaskProjection {
    if (!this.projection) throw new Error("A task snapshot is required before reading projection state.");
    return this.projection;
  }

  block(): TaskProjection {
    if (!this.projection) throw new Error("A task snapshot is required before blocking the projection.");
    this.projection = { ...this.projection, health: "blocked" };
    return this.projection;
  }
}

export class CommandDeduplicator {
  private readonly submitted = new Set<string>();

  tryReserve(idempotencyKey: string): boolean {
    if (this.submitted.has(idempotencyKey)) return false;
    this.submitted.add(idempotencyKey);
    return true;
  }

  release(idempotencyKey: string): void {
    this.submitted.delete(idempotencyKey);
  }
}

export function maySendConsequentialCommand(projection: TaskProjection, syncStatus: EventSyncStatus = "idle"): boolean {
  return projection.health === "current" && syncStatus === "connected";
}

/**
 * Coordinates cursor replay without becoming a second task authority.
 * The Node remains responsible for snapshots, events, and all transitions.
 */
export class TaskEventSynchronizer {
  private readonly store = new TaskEventStore();
  private syncState: EventSyncState = {
    status: "idle",
    attempt: 0,
    lastAppliedSequence: 0,
    lastLedgerEventRefs: [],
    error: null,
  };

  constructor(
    private readonly fetchBatch: EventBatchFetcher,
    private readonly fetchSnapshot?: SnapshotFetcher,
  ) {}

  loadSnapshot(snapshot: TaskSnapshot): TaskProjection {
    const projection = this.store.loadSnapshot(snapshot);
    this.setState({
      status: "idle",
      attempt: 0,
      lastAppliedSequence: projection.lastAppliedSequence,
      lastLedgerEventRefs: [snapshot.ledgerHeadRef],
      error: null,
    });
    return projection;
  }

  current(): TaskProjection {
    return this.store.current();
  }

  state(): EventSyncState {
    return { ...this.syncState, lastLedgerEventRefs: [...this.syncState.lastLedgerEventRefs] };
  }

  async synchronizeOnce(): Promise<EventSyncResult> {
    const current = this.store.current();
    this.setState({ status: "syncing", error: null, lastAppliedSequence: current.lastAppliedSequence });

    try {
      for (let pass = 0; pass < 8; pass += 1) {
        const before = this.store.current();
        const batch = await this.fetchBatch(before.taskId, before.lastAppliedSequence);
        this.validateBatch(batch, before.taskId, before.lastAppliedSequence);
        this.setState({
          status: batch.events.length > 0 ? "replaying" : "syncing",
          lastLedgerEventRefs: batch.ledger_event_refs,
          lastAppliedSequence: before.lastAppliedSequence,
          error: null,
        });

        const outcomes = this.store.applyBatch(batch);
        const gap = outcomes.find((outcome): outcome is Extract<EventStoreOutcome, { kind: "replay_required" }> => outcome.kind === "replay_required");
        const unknown = outcomes.find((outcome): outcome is Extract<EventStoreOutcome, { kind: "unknown" }> => outcome.kind === "unknown");
        const after = this.store.current();
        if (unknown) return this.blocked("unknown_event_schema", "The Node returned an event schema this client cannot safely interpret.");
        if (gap) {
          this.setState({ status: "replaying", lastAppliedSequence: after.lastAppliedSequence });
          continue;
        }

        if (batch.has_more) {
          if (after.lastAppliedSequence <= before.lastAppliedSequence && batch.events.length === 0) {
            throw new EventSyncProtocolError("The Node returned more events without advancing the cursor.");
          }
          continue;
        }

        return this.currentResult("current", after, {
          status: "connected",
          lastAppliedSequence: after.lastAppliedSequence,
          error: null,
        });
      }

      return this.resynchronize("event_replay_not_converging");
    } catch (error) {
      if (error instanceof EventSyncProtocolError) {
        return this.blocked(error.code, error.message);
      }
      return this.currentResult("reconnecting", this.store.current(), {
        status: "reconnecting",
        error: { code: "node_unavailable", message: safeSyncError(error) },
      });
    }
  }

  async synchronizeWithRetry(options: EventSyncRetryOptions = {}): Promise<EventSyncResult> {
    const maxAttempts = Math.max(1, options.maxAttempts ?? 3);
    const baseDelayMs = Math.max(0, options.baseDelayMs ?? 250);
    const sleep = options.sleep ?? ((durationMs: number) => new Promise<void>((resolve) => setTimeout(resolve, durationMs)));

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      this.setState({ attempt, status: attempt === 1 ? "syncing" : "reconnecting" });
      const result = await this.synchronizeOnce();
      if (result.kind !== "reconnecting" || attempt === maxAttempts) return result;
      await sleep(baseDelayMs * 2 ** (attempt - 1));
    }

    return this.currentResult("reconnecting", this.store.current(), {
      status: "reconnecting",
      error: { code: "retry_exhausted", message: "The approved Node did not reconnect." },
    });
  }

  private async resynchronize(code: string): Promise<EventSyncResult> {
    if (!this.fetchSnapshot) return this.blocked(code, "The event replay did not converge and no snapshot resync is available.");
    try {
      const snapshot = await this.fetchSnapshot(this.store.current().taskId);
      const projection = this.store.replaceSnapshot(snapshot);
      return this.currentResult("current", projection, {
        status: "connected",
        lastAppliedSequence: projection.lastAppliedSequence,
        lastLedgerEventRefs: [snapshot.ledgerHeadRef],
        error: null,
      });
    } catch (error) {
      return this.blocked("snapshot_resync_failed", safeSyncError(error));
    }
  }

  private validateBatch(batch: TaskEventBatch, taskId: string, afterSequence: number): void {
    if (batch.stream_id !== taskId) throw new EventSyncProtocolError("The Node returned an event batch for a different task.");
    const projection = this.store.current();
    if (typeof batch.node_identity !== "string" || !batch.node_identity.trim()) {
      throw new EventSyncProtocolError("The Node returned an empty identity in the event batch.");
    }
    if (batch.node_identity !== projection.nodeConnectionRef) {
      throw new EventSyncProtocolError("The Node returned events from a different Node identity.");
    }
    if (batch.protocol_version !== FRONTEND_PROTOCOL_VERSION) {
      throw new EventSyncProtocolError("The Node event protocol version is not supported by this client.");
    }
    if (batch.clearance_context !== projection.clearanceContext) {
      throw new EventSyncProtocolError("The Node event clearance context does not match the task.");
    }
    if (!Array.isArray(batch.events) || !Array.isArray(batch.ledger_event_refs) || typeof batch.has_more !== "boolean") {
      throw new EventSyncProtocolError("The Node returned an invalid event batch shape.");
    }
    if (batch.ledger_event_refs.length !== batch.events.length) {
      throw new EventSyncProtocolError("The Node event batch is not aligned with its ledger references.");
    }
    if (!Number.isSafeInteger(batch.next_sequence) || batch.next_sequence < afterSequence) {
      throw new EventSyncProtocolError("The Node returned an older or invalid event cursor.");
    }
    let previousSequence = afterSequence;
    for (const [index, event] of batch.events.entries()) {
      if (event.taskId !== taskId) throw new EventSyncProtocolError("The Node returned an event for a different task.");
      if (!Number.isSafeInteger(event.sequence) || event.sequence <= previousSequence) {
        throw new EventSyncProtocolError("The Node event sequence is not strictly increasing.");
      }
      if (event.schemaVersion !== batch.protocol_version || event.clearanceContext !== batch.clearance_context) {
        throw new EventSyncProtocolError("The Node event metadata does not match the event batch.");
      }
      if (event.ledgerEventRef !== batch.ledger_event_refs[index]) {
        throw new EventSyncProtocolError("The Node event ledger reference does not match the batch reference.");
      }
      previousSequence = event.sequence;
    }
    if (batch.has_more && batch.events.length === 0) {
      throw new EventSyncProtocolError("The Node marked an empty event batch as having more events.");
    }
    const expectedCursor = batch.events.length === 0 ? afterSequence : previousSequence;
    if (!batch.has_more && batch.next_sequence !== expectedCursor) {
      throw new EventSyncProtocolError("The Node final event cursor does not match the returned events.");
    }
    if (batch.has_more && batch.next_sequence < previousSequence) {
      throw new EventSyncProtocolError("The Node event cursor precedes the returned events.");
    }
  }

  private blocked(code: string, message: string): EventSyncResult {
    const projection = this.store.block();
    return this.currentResult("blocked", projection, {
      status: "blocked",
      lastAppliedSequence: projection.lastAppliedSequence,
      error: { code, message },
    });
  }

  private currentResult(kind: EventSyncResult["kind"], projection: TaskProjection, patch: Partial<EventSyncState>): EventSyncResult {
    this.setState({ ...patch, lastAppliedSequence: projection.lastAppliedSequence });
    return { kind, projection, state: this.state() } as EventSyncResult;
  }

  private setState(patch: Partial<EventSyncState>): void {
    this.syncState = { ...this.syncState, ...patch };
  }
}

function safeSyncError(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return "The approved Node connection failed.";
}
