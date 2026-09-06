import { describe, expect, it } from "vitest";
import { initialPresentationState } from "./contracts";

describe("initial AirBench presentation state", () => {
  it("fails closed before an approved Node is connected", () => {
    expect(initialPresentationState.node.state).toBe("not_connected");
    expect(initialPresentationState.node.sovereignty).toBe("unknown");
    expect(initialPresentationState.node.address).not.toMatch(/^https?:/);
  });

  it("starts with no invented task records", () => {
    expect(initialPresentationState.recentTasks).toEqual([]);
    expect(initialPresentationState.screen).toBe("home");
  });
});
