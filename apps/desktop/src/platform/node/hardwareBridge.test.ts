import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { fetchNodeHardware, validateHardwareStatus } from "./hardwareBridge";
import type { ApprovedNodeProfile } from "./nodeConnection";

const profile: ApprovedNodeProfile = {
  profileId: "profile-1", displayName: "Plant Node", endpoint: "http://127.0.0.1:9443",
  transport: "loopback", nodeIdentity: "node-1", protocolVersion: "0.1",
  clearanceContext: "restricted", certificatePinSha256: null, trustedCaPem: null,
  credentialRef: "fixture-user", approvedByPolicy: true,
};

const configured = {
  configured: true, profile_id: "workstation-demo", gpu_model: "RTX PRO 6000",
  gpu_count: 1, vram_bytes: 102641958912, cpu_model: "EPYC", cpu_cores: 32,
  ram_bytes: 134217728000, safe_parallel_slots: 4, egress_policy: "deny-all", measurement_pending: false,
};

describe("hardware bridge", () => {
  beforeEach(() => invokeMock.mockReset());

  it("accepts a configured profile projection", () => {
    const status = validateHardwareStatus(configured);
    expect(status.configured).toBe(true);
    expect(status.profile_id).toBe("workstation-demo");
    expect(status.safe_parallel_slots).toBe(4);
  });

  it("accepts a disabled projection", () => {
    expect(validateHardwareStatus({ configured: false }).configured).toBe(false);
  });

  it("rejects a malformed projection", () => {
    expect(() => validateHardwareStatus({ configured: "yes" })).toThrow("invalid hardware status");
    expect(() => validateHardwareStatus(null)).toThrow("invalid hardware status");
  });

  it("fetches through the approved native command", async () => {
    invokeMock.mockResolvedValueOnce(configured);
    await fetchNodeHardware(profile);
    expect(invokeMock).toHaveBeenCalledWith("fetch_node_hardware", { profileId: "profile-1" });
  });

  it("rejects an unapproved profile before IPC", () => {
    expect(() => fetchNodeHardware({ ...profile, approvedByPolicy: false })).toThrow("approved by policy");
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
