import { describe, expect, it } from "vitest";
import { taskSyncRecovery } from "./syncRecovery";
import type { TaskProjection } from "../../platform/events/protocol";

const projection = { ledgerHeadRef: "ledger-4" } as TaskProjection;

describe("task synchronization recovery guidance", () => {
  it("explains what remains safe during reconnect", () => {
    const guidance = taskSyncRecovery("reconnecting", projection, { code: "node_unavailable", message: "The approved Node could not be reached." });
    expect(guidance.tone).toBe("attention");
    expect(guidance.label).toBe("Node connection interrupted");
    expect(guidance.preserved).toContain("ledger-4");
    expect(guidance.retry).toContain("duplicate");
    expect(guidance.nextAction).toContain("ordered event or snapshot");
  });

  it("separates replay from reconnect and keeps command gating explicit", () => {
    const guidance = taskSyncRecovery("replaying", projection);
    expect(guidance.tone).toBe("active");
    expect(guidance.detail).toContain("ordered range");
    expect(guidance.retry).toContain("reorder");
    expect(guidance.nextAction).toContain("gated");
  });

  it("fails closed after protocol or replay failure", () => {
    const guidance = taskSyncRecovery("blocked", projection, { code: "event_protocol_invalid", message: "The Node returned an invalid event batch." });
    expect(guidance.tone).toBe("blocked");
    expect(guidance.detail).toContain("invalid event batch");
    expect(guidance.retry).toContain("No automatic retry");
    expect(guidance.nextAction).toContain("do not treat this view as current");
  });

  it("describes the in-flight and current states without inventing progress", () => {
    expect(taskSyncRecovery("syncing", projection).nextAction).toContain("Node result");
    expect(taskSyncRecovery("connected", projection).label).toBe("Task view is current");
    expect(taskSyncRecovery("idle", projection).nextAction).toContain("Refresh");
  });
});
