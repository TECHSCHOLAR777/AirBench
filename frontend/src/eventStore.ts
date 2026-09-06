import { applyEvent, projectionFromSnapshot, type TaskEvent, type TaskProjection, type TaskSnapshot } from "./protocol";

export type EventStoreOutcome =
  | { kind: "applied"; projection: TaskProjection }
  | { kind: "duplicate"; projection: TaskProjection }
  | { kind: "replay_required"; projection: TaskProjection; fromSequence: number }
  | { kind: "unknown"; projection: TaskProjection };

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

  current(): TaskProjection {
    if (!this.projection) throw new Error("A task snapshot is required before reading projection state.");
    return this.projection;
  }
}

export function maySendConsequentialCommand(projection: TaskProjection): boolean {
  return projection.health === "current";
}
