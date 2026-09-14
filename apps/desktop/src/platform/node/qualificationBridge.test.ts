import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { fetchModelQualification, fetchQualificationRoster, validateQualificationRoster, validateQualificationStatus } from "./qualificationBridge";
import type { ApprovedNodeProfile } from "./nodeConnection";

const profile: ApprovedNodeProfile = {
  profileId: "profile-1", displayName: "Plant Node", endpoint: "http://127.0.0.1:9443",
  transport: "loopback", nodeIdentity: "node-1", protocolVersion: "0.1",
  clearanceContext: "restricted", certificatePinSha256: null, trustedCaPem: null,
  credentialRef: "fixture-user", approvedByPolicy: true,
};

describe("qualification bridge", () => {
  beforeEach(() => invokeMock.mockReset());

  it("accepts a qualified status", () => {
    const status = validateQualificationStatus({ target_id: "airbench-gemma-4-e2b", status: "qualified", routing_tier: "efficient" });
    expect(status.status).toBe("qualified");
    expect(status.routing_tier).toBe("efficient");
  });

  it("preserves the Node's pending/not_listed states", () => {
    expect(validateQualificationStatus({ target_id: "t", status: "pending" }).status).toBe("pending");
    expect(validateQualificationStatus({ target_id: "t", status: "pending" }).measurement_pending).toBe(true);
    expect(validateQualificationStatus({ target_id: "t", status: "not_listed" }).status).toBe("not_listed");
    expect(validateQualificationStatus({}).status).toBe("unknown");
  });

  it("rejects a non-object payload", () => {
    expect(() => validateQualificationStatus(null)).toThrow("Invalid qualification status");
  });

  it("fetches through the approved native command", async () => {
    invokeMock.mockResolvedValueOnce({ target_id: "airbench-gemma-4-e2b", status: "pending" });
    await fetchModelQualification(profile, "airbench-gemma-4-e2b");
    expect(invokeMock).toHaveBeenCalledWith("fetch_model_qualification", {
      profileId: "profile-1", targetId: "airbench-gemma-4-e2b",
    });
  });

  it("validates and fetches the full roster in one call", async () => {
    const roster = { configured: true, count: 2, targets: [
      { target_id: "airbench-gemma-4-e2b", status: "qualified" },
      { target_id: "airbench-gemma-4-12b", status: "pending" },
    ] };
    expect(validateQualificationRoster(roster).targets.map((t) => t.status)).toEqual(["qualified", "pending"]);
    invokeMock.mockResolvedValueOnce(roster);
    await fetchQualificationRoster(profile);
    expect(invokeMock).toHaveBeenCalledWith("fetch_qualification_roster", { profileId: "profile-1" });
  });
});
