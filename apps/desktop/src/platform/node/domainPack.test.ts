import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { domainPackSignatureTone, fetchDomainPack, validateDomainPackStatus } from "./domainPack";
import type { ApprovedNodeProfile } from "./nodeConnection";

const profile: ApprovedNodeProfile = {
  profileId: "profile-1",
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

const signedPack = {
  configured: true,
  status: "ready",
  pack_id: "refinery_psu_inspection_review_v0",
  pack_version: "1.0",
  compatibility_id: "airbench-core-contracts",
  signature_status: "signed",
  signature_verified: true,
  active_sections: ["decision_types", "document_profiles"],
  counts: { field_rules: 4 },
};

describe("domain pack bridge", () => {
  beforeEach(() => invokeMock.mockReset());

  it("accepts a signed pack projection", () => {
    const status = validateDomainPackStatus(signedPack);
    expect(status.pack_id).toBe("refinery_psu_inspection_review_v0");
    expect(status.signature_status).toBe("signed");
    expect(domainPackSignatureTone(status)).toBe("trusted");
  });

  it("accepts an unsigned pack but flags its tone", () => {
    const status = validateDomainPackStatus({ ...signedPack, signature_status: "unsigned", signature_verified: false });
    expect(domainPackSignatureTone(status)).toBe("attention");
  });

  it("accepts a disabled projection", () => {
    expect(validateDomainPackStatus({ configured: false, status: "disabled" }).configured).toBe(false);
  });

  it("rejects malformed pack metadata", () => {
    expect(() => validateDomainPackStatus({ ...signedPack, pack_id: null })).toThrow("incomplete");
    expect(() => validateDomainPackStatus({ ...signedPack, signature_status: "maybe" })).toThrow("signature status");
    expect(() => validateDomainPackStatus({ ...signedPack, active_sections: ["../escape"] })).toThrow("section name");
    expect(() => validateDomainPackStatus({ ...signedPack, counts: { field_rules: -1 } })).toThrow("count");
  });

  it("fetches through the approved native command", async () => {
    invokeMock.mockResolvedValueOnce(signedPack);
    await fetchDomainPack(profile);
    expect(invokeMock).toHaveBeenCalledWith("fetch_domain_pack", { profileId: "profile-1" });
  });

  it("rejects an unapproved profile before IPC", () => {
    expect(() => fetchDomainPack({ ...profile, approvedByPolicy: false })).toThrow("approved by policy");
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
