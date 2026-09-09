import { describe, expect, it } from "vitest";
import type { NodeCommandResult } from "../../generated/core_contracts";
import { commandOutcomeGuidance, shouldRefreshTaskAfterCommand } from "./commandOutcome";

function result(outcome: NodeCommandResult["outcome"], reason: string | null = null): NodeCommandResult {
  return {
    schema_version: "1.0",
    compatibility_id: "airbench-core-contracts",
    outcome,
    command_id: "command.test.1",
    task_id: "task.test.1",
    idempotency_key: "idempotency.test.1",
    ledger_event_ref: "ledger.test.1",
    sequence: 8,
    state: null,
    node_identity: "node.test",
    protocol_version: "0.1",
    clearance_context: "internal",
    event_type: null,
    code: null,
    message: null,
    reason,
  };
}

describe("command outcome guidance", () => {
  it("does not treat a deferred plan approval as accepted", () => {
    const guidance = commandOutcomeGuidance("Plan approval", result("needs_review", "hardware admission is pending"));

    expect(guidance.tone).toBe("attention");
    expect(guidance.label).toBe("Plan approval needs Node review");
    expect(guidance.detail).toContain("hardware admission is pending");
    expect(guidance.detail).toContain("No local task state was changed");
    expect(guidance.retry).toContain("Do not retry");
  });

  it("keeps a rejected stop request distinct from a successful stop", () => {
    const guidance = commandOutcomeGuidance("Stop request", result("rejected", "task is already complete"));

    expect(guidance.tone).toBe("danger");
    expect(guidance.label).toBe("Stop request rejected by Node");
    expect(guidance.detail).toContain("task is already complete");
    expect(guidance.nextAction).toContain("refresh the authoritative projection");
  });

  it("only describes the authoritative event as the completion point for acceptance", () => {
    const guidance = commandOutcomeGuidance("Stop request", result("accepted"));

    expect(guidance.tone).toBe("positive");
    expect(guidance.detail).toContain("stopped event");
    expect(guidance.retry).toContain("second stop request");
  });

  it("refreshes only after an accepted command receipt", () => {
    expect(shouldRefreshTaskAfterCommand(result("accepted"))).toBe(true);
    expect(shouldRefreshTaskAfterCommand(result("needs_review"))).toBe(false);
    expect(shouldRefreshTaskAfterCommand(result("rejected"))).toBe(false);
  });
});
