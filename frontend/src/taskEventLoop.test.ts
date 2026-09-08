import { afterEach, describe, expect, it, vi } from "vitest";
import { TaskEventLoop } from "./taskEventLoop";
import type { EventSyncResult } from "./eventStore";

function result(kind: EventSyncResult["kind"], status = "running"): EventSyncResult {
  return {
    kind,
    projection: { status } as EventSyncResult["projection"],
    state: { status: kind === "reconnecting" ? "reconnecting" : "connected" } as EventSyncResult["state"],
  };
}

describe("TaskEventLoop", () => {
  afterEach(() => vi.useRealTimers());

  it("does not overlap synchronization and continues from the next interval", async () => {
    vi.useFakeTimers();
    let resolveFirst: ((value: EventSyncResult) => void) | undefined;
    const first = new Promise<EventSyncResult>((resolve) => { resolveFirst = resolve; });
    const synchronize = vi.fn().mockReturnValueOnce(first).mockResolvedValue(result("current"));
    const onResult = vi.fn();
    const loop = new TaskEventLoop(synchronize, onResult, { intervalMs: 1_000 });

    loop.start();
    loop.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(synchronize).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(10_000);
    expect(synchronize).toHaveBeenCalledTimes(1);

    resolveFirst?.(result("current"));
    await vi.advanceTimersByTimeAsync(0);
    expect(onResult).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(999);
    expect(synchronize).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(synchronize).toHaveBeenCalledTimes(2);
    loop.stop();
  });

  it("uses a slower reconnect interval and stops after a terminal Node result", async () => {
    vi.useFakeTimers();
    const synchronize = vi.fn()
      .mockResolvedValueOnce(result("reconnecting"))
      .mockResolvedValueOnce(result("current", "completed"));
    const onResult = vi.fn();
    const loop = new TaskEventLoop(synchronize, onResult, { intervalMs: 1_000, reconnectIntervalMs: 2_000 });

    loop.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(onResult).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1_999);
    expect(synchronize).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(synchronize).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(synchronize).toHaveBeenCalledTimes(2);
    loop.stop();
  });

  it("does not publish a late result after stop", async () => {
    vi.useFakeTimers();
    let resolve: ((value: EventSyncResult) => void) | undefined;
    const pending = new Promise<EventSyncResult>((next) => { resolve = next; });
    const onResult = vi.fn();
    const loop = new TaskEventLoop(() => pending, onResult);

    loop.start();
    await vi.advanceTimersByTimeAsync(0);
    loop.stop();
    resolve?.(result("current"));
    await vi.advanceTimersByTimeAsync(0);
    expect(onResult).not.toHaveBeenCalled();
  });
});
