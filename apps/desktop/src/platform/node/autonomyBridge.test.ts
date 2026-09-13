import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import {
  authorizeAutonomyEscalation,
  fetchTaskAutonomy,
  validateAutonomyAuthorization,
  validateAutonomyStatus,
} from "./autonomyBridge";
import type { ApprovedNodeProfile } from "./nodeConnection";

const profile: ApprovedNodeProfile = {
  profileId: "profile-1", displayName: "Plant Node", endpoint: "http://127.0.0.1:9443",
  transport: "loopback", nodeIdentity: "node-1", protocolVersion: "0.1",
  clearanceContext: "restricted", certificatePinSha256: null, trustedCaPem: null,
  credentialRef: "fixture-user", approvedByPolicy: true,
};

describe("autonomy bridge", () => {
  beforeEach(() => invokeMock.mockReset());

  it("accepts a status with a fail-closed unknown outcome", () => {
    const status = validateAutonomyStatus({
      task_id: "task-1", is_blocked: true,
      decisions: [{ action_id: "a-1", action_kind: "release_approval_note", outcome: "mystery", required_authority: "authorized_approver", required_checks: ["risk_rule"], reason: "high harm", ledger_event_ref: "ledger-1" }],
    });
    expect(status.is_blocked).toBe(true);
    expect(status.decisions[0].outcome).toBe("escalate");
  });

  it("rejects a status without a task id", () => {
    expect(() => validateAutonomyStatus({ task_id: "" })).toThrow("autonomy task_id");
    expect(() => validateAutonomyStatus(null)).toThrow("invalid autonomy status");
  });

  it("validates an authorization receipt", () => {
    expect(validateAutonomyAuthorization({ task_id: "task-1", authorized: true, action_id: "a-1" }).authorized).toBe(true);
  });

  it("reads and authorizes through the native commands", async () => {
    invokeMock.mockResolvedValueOnce({ task_id: "task-1", is_blocked: false, decisions: [] });
    await fetchTaskAutonomy(profile, "task-1");
    expect(invokeMock).toHaveBeenLastCalledWith("fetch_task_autonomy", { profileId: "profile-1", taskId: "task-1" });

    invokeMock.mockResolvedValueOnce({ task_id: "task-1", authorized: true, action_id: "a-1" });
    await authorizeAutonomyEscalation(profile, "task-1", "operator-1", "a-1");
    expect(invokeMock).toHaveBeenLastCalledWith("post_autonomy_authorize", {
      profileId: "profile-1", taskId: "task-1", body: { operator_id: "operator-1", action_id: "a-1" },
    });
  });

  it("requires an operator identity before IPC", () => {
    expect(() => authorizeAutonomyEscalation(profile, "task-1", "   ", "a-1")).toThrow("operator identity is required");
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
