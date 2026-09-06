import { describe, expect, it } from "vitest";
import { toNativeNodeProfile } from "./nodeBridge";
import type { ApprovedNodeProfile } from "./nodeConnection";

const profile: ApprovedNodeProfile = {
  profileId: "node-profile-1",
  displayName: "Plant Node",
  endpoint: "https://node.plant.internal:9443",
  transport: "internal_https",
  nodeIdentity: "node-plant-01",
  protocolVersion: "0.1",
  clearanceContext: "restricted",
  certificatePinSha256: "sha256:approved-pin",
  trustedCaPem: null,
  credentialRef: "fixture-user",
  approvedByPolicy: true,
};

describe("Rust-owned Node bridge", () => {
  it("serializes only the approved profile contract", () => {
    expect(toNativeNodeProfile(profile)).toEqual({
      profile_id: "node-profile-1",
      endpoint: "https://node.plant.internal:9443",
      transport: "internal_https",
      node_identity: "node-plant-01",
      protocol_version: "0.1",
      clearance_context: "restricted",
      certificate_pin_sha256: "sha256:approved-pin",
      trusted_ca_pem: null,
      credential_ref: "fixture-user",
      approved_by_policy: true,
    });
  });
});
