import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import {
  evaluateTaskConsistency,
  fetchTaskConsistency,
  justifyConsistencyDeviation,
  validateConsistencyReport,
} from "./consistencyBridge";
import type { ApprovedNodeProfile } from "./nodeConnection";

const profile: ApprovedNodeProfile = {
  profileId: "profile-1", displayName: "Plant Node", endpoint: "http://127.0.0.1:9443",
  transport: "loopback", nodeIdentity: "node-1", protocolVersion: "0.1",
  clearanceContext: "restricted", certificatePinSha256: null, trustedCaPem: null,
  credentialRef: "fixture-user", approvedByPolicy: true,
};

const report = {
  task_id: "task-1", status: "evaluated", decision_id: "decision-2", decision_type: "approval_note_review_status",
  object_id: "equipment.P-101", comparable_ids: ["decision-1"], superseded_ids: [],
  material_differences: [["severity", "low", "high"]], deviation: true, reason: "material difference",
  justified: false, justification: null, ledger_event_id: "ledger-1",
};

describe("consistency bridge", () => {
  beforeEach(() => invokeMock.mockReset());

  it("accepts and normalizes a report", () => {
    const parsed = validateConsistencyReport(report);
    expect(parsed.deviation).toBe(true);
    expect(parsed.material_differences).toEqual([{ feature: "severity", previous_value: "low", current_value: "high" }]);
  });

  it("rejects a report without a task id", () => {
    expect(() => validateConsistencyReport({ ...report, task_id: "" })).toThrow("consistency task_id");
    expect(() => validateConsistencyReport(null)).toThrow("invalid consistency report");
  });

  it("reads through the native commands with the right arguments", async () => {
    invokeMock.mockResolvedValueOnce(report);
    await fetchTaskConsistency(profile, "task-1");
    expect(invokeMock).toHaveBeenCalledWith("fetch_task_consistency", { profileId: "profile-1", taskId: "task-1" });

    invokeMock.mockResolvedValueOnce(report);
    await evaluateTaskConsistency(profile, "task-1", {
      decision_id: "decision-2", decision_type: "approval_note_review_status", object_id: "equipment.P-101",
      features: { severity: "high" }, decision: "approved", rule_ref: "rule-1", authority: "human_reviewer",
    });
    expect(invokeMock).toHaveBeenLastCalledWith("post_consistency_evaluate", expect.objectContaining({ profileId: "profile-1", taskId: "task-1" }));

    invokeMock.mockResolvedValueOnce({ ...report, justified: true, justification: "confirmed" });
    await justifyConsistencyDeviation(profile, "task-1", "operator-1", "  confirmed by inspection  ");
    expect(invokeMock).toHaveBeenLastCalledWith("post_consistency_justify", {
      profileId: "profile-1", taskId: "task-1", body: { operator_id: "operator-1", justification: "confirmed by inspection" },
    });
  });

  it("rejects an empty or oversized justification before IPC", () => {
    expect(() => justifyConsistencyDeviation(profile, "task-1", "operator-1", "   ")).toThrow("justification is required");
    expect(() => justifyConsistencyDeviation(profile, "task-1", "operator-1", "x".repeat(4001))).toThrow("4 000 characters");
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
