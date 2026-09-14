import type { EventSyncResult } from "../../platform/events/eventStore";

export interface TaskEventLoopOptions {
  intervalMs?: number;
  reconnectIntervalMs?: number;
  schedule?: (callback: () => void, delayMs: number) => ReturnType<typeof setTimeout>;
  cancel?: (handle: ReturnType<typeof setTimeout>) => void;
  onTransportUncertain?: () => void;
  onError?: (error: unknown) => void;
}

// Terminal for the event loop: the Node will not emit further task events
// from these states without a new operator command, so polling stops
// (Phase 3: polling must stop on completed, failed, blocked, or needs-review).
const TERMINAL_STATUSES = new Set(["completed", "failed", "stopped", "needs_review"]);

/**
 * Polls the authoritative Node event cursor without creating a second task
 * authority in the desktop. One synchronization can be in flight at a time,
 * and a stopped loop never publishes a late result into a new task view.
 */
export class TaskEventLoop {
  private readonly intervalMs: number;
  private readonly reconnectIntervalMs: number;
  private readonly schedule: NonNullable<TaskEventLoopOptions["schedule"]>;
  private readonly cancel: NonNullable<TaskEventLoopOptions["cancel"]>;
  private readonly onTransportUncertain: (() => void) | undefined;
  private readonly onError: ((error: unknown) => void) | undefined;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private running = false;
  private inFlight = false;

  constructor(
    private readonly synchronize: () => Promise<EventSyncResult>,
    private readonly onResult: (result: EventSyncResult) => void,
    options: TaskEventLoopOptions = {},
  ) {
    this.intervalMs = Math.max(250, options.intervalMs ?? 1_000);
    this.reconnectIntervalMs = Math.max(this.intervalMs, options.reconnectIntervalMs ?? 2_000);
    this.schedule = options.schedule ?? ((callback, delayMs) => setTimeout(callback, delayMs));
    this.cancel = options.cancel ?? ((handle) => clearTimeout(handle));
    this.onTransportUncertain = options.onTransportUncertain;
    this.onError = options.onError;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.scheduleNext(0);
  }

  stop(): void {
    this.running = false;
    if (this.timer !== null) {
      this.cancel(this.timer);
      this.timer = null;
    }
  }

  private scheduleNext(delayMs: number): void {
    if (!this.running || this.timer !== null) return;
    this.timer = this.schedule(() => {
      this.timer = null;
      void this.tick();
    }, delayMs);
  }

  private async tick(): Promise<void> {
    if (!this.running || this.inFlight) return;
    this.inFlight = true;
    try {
      const result = await this.synchronize();
      if (!this.running) return;
      if (result.kind === "reconnecting") this.onTransportUncertain?.();
      this.onResult(result);
      if (result.kind === "blocked" || TERMINAL_STATUSES.has(result.projection.status)) {
        this.stop();
        return;
      }
      this.scheduleNext(result.kind === "reconnecting" ? this.reconnectIntervalMs : this.intervalMs);
    } catch (error) {
      if (!this.running) return;
      this.onTransportUncertain?.();
      this.onError?.(error);
      this.scheduleNext(this.reconnectIntervalMs);
    } finally {
      this.inFlight = false;
    }
  }
}
