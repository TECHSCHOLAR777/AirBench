import { describe, expect, it } from "vitest";
import { toNativeEventProfile } from "./eventTransport";
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
  it("serializes the cursor request without exposing a secret", () => {
    expect(toNativeEventProfile(profile)).toMatchObject({
      profile_id: "node-profile-1",
      credential_ref: "fixture-user",
      approved_by_policy: true,
    });
    expect(JSON.stringify(toNativeEventProfile(profile))).not.toContain("token");
  });
});
