import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { listApprovedNodeProfiles } from "./profileBridge";

describe("administrator-provisioned Node profile bridge", () => {
  beforeEach(() => invokeMock.mockReset());

  it("maps the native profile without creating a user-entered endpoint path", async () => {
    invokeMock.mockResolvedValue([{
      profile_id: "profile-1",
      display_name: "Plant Node",
      endpoint: "https://node.plant.internal:9443",
      transport: "internal_https",
      node_identity: "node-1",
      protocol_version: "0.1",
      clearance_context: "restricted",
      certificate_pin_sha256: "sha256:pin",
      trusted_ca_pem: null,
      credential_ref: "operator-credential",
      approved_by_policy: true,
    }]);

    await expect(listApprovedNodeProfiles()).resolves.toEqual([expect.objectContaining({
      profileId: "profile-1",
      displayName: "Plant Node",
      transport: "internal_https",
      clearanceContext: "restricted",
    })]);
    expect(invokeMock).toHaveBeenCalledWith("list_approved_node_profiles");
  });
});

