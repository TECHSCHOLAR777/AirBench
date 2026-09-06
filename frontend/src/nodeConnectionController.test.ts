import { describe, expect, it } from "vitest";
import { NodeConnectionController } from "./nodeConnectionController";
import type { NativeNodeConnectionResult } from "./nodeBridge";
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

const connected: NativeNodeConnectionResult = {
  state: "connected" as const,
  profile_id: "profile-1",
  node_identity: "node-1",
  protocol_version: "0.1",
  clearance_context: "restricted",
  authenticated_subject: "operator-1",
  domain_pack_ref: "fixture-pack.v0",
  sovereignty: "verified" as const,
  ledger_event_ref: "ledger-connect-1",
};

describe("NodeConnectionController", () => {
  it("blocks an unapproved profile before crossing into Rust", async () => {
    let calls = 0;
    const controller = new NodeConnectionController(async () => {
      calls += 1;
      return connected;
    });

    const result = await controller.connect({ ...profile, approvedByPolicy: false });

    expect(result.state).toBe("blocked");
    expect(result.sovereignty).toBe("blocked");
    expect(result.failure?.code).toBe("not_approved");
    expect(calls).toBe(0);
    expect(controller.canSendConsequential()).toBe(false);
  });

  it("exposes the verified Node identity, clearance, and ledger reference", async () => {
    const controller = new NodeConnectionController(async () => connected);

    const result = await controller.connect(profile);

    expect(result).toMatchObject({
      state: "connected",
      nodeIdentity: "node-1",
      protocolVersion: "0.1",
      clearanceContext: "restricted",
      authenticatedSubject: "operator-1",
      domainPackRef: "fixture-pack.v0",
      sovereignty: "verified",
      ledgerEventRef: "ledger-connect-1",
    });
    expect(controller.canSendConsequential()).toBe(true);
  });

  it("fails closed on disconnect and reconnects only the saved approved profile", async () => {
    let calls = 0;
    const controller = new NodeConnectionController(async (receivedProfile) => {
      calls += 1;
      expect(receivedProfile.profileId).toBe("profile-1");
      return connected;
    });

    await controller.connect(profile);
    const disconnected = controller.markDisconnected();
    expect(disconnected.state).toBe("reconnecting");
    expect(controller.canSendConsequential()).toBe(false);

    const reconnected = await controller.reconnect();
    expect(reconnected.state).toBe("connected");
    expect(calls).toBe(2);
    expect(controller.canSendConsequential()).toBe(true);
  });

  it("does not expose connector errors or claim sovereignty after failure", async () => {
    const controller = new NodeConnectionController(async () => {
      throw new Error("secret-token=must-not-leak");
    });

    const result = await controller.connect(profile);

    expect(result.state).toBe("failed");
    expect(result.sovereignty).toBe("blocked");
    expect(result.failure?.message).not.toContain("secret-token");
    expect(controller.canSendConsequential()).toBe(false);
  });
});
