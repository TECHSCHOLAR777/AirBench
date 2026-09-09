import { describe, expect, it } from "vitest";
import { planRecoveryGuidance } from "./planRecovery";

describe("plan recovery guidance", () => {
  it("keeps queued hardware work distinct from a failed or duplicate task", () => {
    expect(planRecoveryGuidance({ plan_state: "queued" }, true, false)).toEqual({
      preserved: "The Node-accepted plan remains queued with its hardware admission context.",
      retry: "Do not create a duplicate task while hardware admission is pending.",
      nextAction: "Wait for the Node to admit the plan or return a policy result.",
    });
  });

  it("blocks stale plan actions until the Node projection is current", () => {
    const guidance = planRecoveryGuidance({ plan_state: "ready" }, false, false);
    expect(guidance.retry).toContain("Do not approve or cancel");
    expect(guidance.nextAction).toContain("Reconnect or refresh");
  });

  it("does not offer a second approval after the Node accepts one", () => {
    const guidance = planRecoveryGuidance({ plan_state: "ready" }, true, true);
    expect(guidance.retry).toContain("second approval");
    expect(guidance.nextAction).toContain("next authoritative task event");
  });
});
