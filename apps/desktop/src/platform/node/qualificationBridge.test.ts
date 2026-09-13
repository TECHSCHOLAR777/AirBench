import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { fetchModelQualification, validateQualificationStatus } from "./qualificationBridge";
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

  it("maps pending/unknown statuses to unknown", () => {
    expect(validateQualificationStatus({ target_id: "t", status: "pending" }).status).toBe("unknown");
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
});
