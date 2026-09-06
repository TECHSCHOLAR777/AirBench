import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { fetchTaskEventBatch, toNativeEventProfile } from "./eventTransport";
import type { ApprovedNodeProfile } from "./nodeConnection";

const profile: ApprovedNodeProfile = {
  profileId: "node-profile-1",
  displayName: "Plant Node",
  endpoint: "http://127.0.0.1:9443",
  transport: "loopback",
  nodeIdentity: "node-1",
  protocolVersion: "0.1",
  clearanceContext: "restricted",
  certificatePinSha256: null,
  trustedCaPem: null,
  credentialRef: "fixture-user",
  approvedByPolicy: true,
};

describe("Rust-owned event transport", () => {
  beforeEach(() => {
    invokeMock.mockReset();
  });

  it("serializes the cursor request without exposing a secret", () => {
    expect(toNativeEventProfile(profile)).toMatchObject({
      profile_id: "node-profile-1",
    });
    expect(toNativeEventProfile(profile)).not.toHaveProperty("credential_ref");
    expect(toNativeEventProfile(profile)).not.toHaveProperty("endpoint");
    expect(JSON.stringify(toNativeEventProfile(profile))).not.toContain("token");
  });

  it("rejects an unapproved profile before the event command crosses IPC", () => {
    expect(() => fetchTaskEventBatch({ ...profile, approvedByPolicy: false }, "task-1", 0)).toThrowError(/approved by policy/);
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it("rejects unsafe task identifiers and cursors before IPC", () => {
    expect(() => fetchTaskEventBatch(profile, "../secret", 0)).toThrowError(/task identifier/);
    expect(() => fetchTaskEventBatch(profile, "task-1", -1)).toThrowError(/event cursor/);
    expect(() => fetchTaskEventBatch(profile, "task-1", Number.MAX_SAFE_INTEGER + 1)).toThrowError(/event cursor/);
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
