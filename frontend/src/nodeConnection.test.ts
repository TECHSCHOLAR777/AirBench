import { describe, expect, it } from "vitest";
import { validateApprovedProfile, type ApprovedNodeProfile } from "./nodeConnection";

const baseProfile: ApprovedNodeProfile = {
  profileId: "node-profile-1",
  displayName: "Plant Node",
  endpoint: "https://node.plant.internal:9443",
  transport: "internal_https",
  nodeIdentity: "node-plant-01",
  protocolVersion: "0.1",
  clearanceContext: "restricted",
  certificatePinSha256: "sha256/approved-pin",
  trustedCaPem: null,
  credentialRef: "fixture-user",
  approvedByPolicy: true,
};

describe("approved Node connection profiles", () => {
  it("accepts an approved internal HTTPS profile with a certificate pin", () => {
    expect(validateApprovedProfile(baseProfile)).toEqual({
      valid: true,
      normalizedEndpoint: "https://node.plant.internal:9443",
    });
  });

  it("rejects arbitrary external endpoints even when the transport says loopback", () => {
    const result = validateApprovedProfile({ ...baseProfile, transport: "loopback", endpoint: "http://example.com:9443" });
    expect(result.valid).toBe(false);
    if (!result.valid) expect(result.code).toBe("external_endpoint");
  });

  it("rejects credentials embedded in an endpoint", () => {
    const result = validateApprovedProfile({ ...baseProfile, endpoint: "https://user:secret@node.plant.internal:9443" });
    expect(result.valid).toBe(false);
    if (!result.valid) expect(result.code).toBe("credentials_in_endpoint");
  });

  it("rejects an unpinned remote HTTPS profile", () => {
    const result = validateApprovedProfile({ ...baseProfile, certificatePinSha256: null });
    expect(result.valid).toBe(false);
    if (!result.valid) expect(result.code).toBe("missing_certificate_pin");
  });

  it("allows only loopback hosts for a local fixture profile", () => {
    expect(validateApprovedProfile({ ...baseProfile, transport: "loopback", endpoint: "http://127.0.0.1:9443", certificatePinSha256: null }).valid).toBe(true);
    expect(validateApprovedProfile({ ...baseProfile, transport: "loopback", endpoint: "http://192.168.1.10:9443", certificatePinSha256: null }).valid).toBe(false);
  });
});
