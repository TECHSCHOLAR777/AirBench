import { describe, expect, it } from "vitest";
import type { ApprovedNodeProfileReference } from "./nodeConnection";
import type { NodeConnectionView } from "./nodeConnectionController";
import { buildNodeReadiness } from "./nodeReadiness";

const profile: ApprovedNodeProfileReference = {
  profileId: "operations-node",
  displayName: "Operations Node",
  transport: "internal_https",
  nodeIdentity: "node-ops-01",
  protocolVersion: "0.1",
  clearanceContext: "restricted",
  approvedByPolicy: true,
};

const verifiedConnection: NodeConnectionView = {
  state: "connected",
  profileId: "operations-node",
  nodeIdentity: "node-ops-01",
  protocolVersion: "0.1",
  protocolCompatibilityId: "airbench-node-protocol",
  clearanceContext: "restricted",
  authenticatedSubject: "operator-17",
  domainPackRef: "organization-pack.v3",
  sovereignty: "verified",
  ledgerEventRef: "ledger-connect-42",
  failure: null,
};

describe("Node readiness summary", () => {
  it("renders only verified handshake proof and marks operational data as not supplied", () => {
    const summary = buildNodeReadiness(verifiedConnection, profile);

    expect(summary.connection).toMatchObject({
      tone: "trusted",
      title: "Approved Node connection verified",
      detail: expect.stringMatching(/identity, operator context, and clearance/i),
    });
    expect(summary.connection.proof).toEqual(expect.arrayContaining([
      { label: "Node identity", value: "node-ops-01" },
      { label: "Operator", value: "operator-17" },
      { label: "Clearance", value: "restricted" },
      { label: "Domain pack", value: "organization-pack.v3" },
      { label: "Transport", value: "Internal network" },
      { label: "Protocol contract", value: "airbench-node-protocol" },
      { label: "Handshake ledger", value: "ledger-connect-42" },
    ]));
    expect(summary.operational).toMatchObject({
      state: "not_supplied",
      title: "Operational status is not supplied",
    });
    expect(summary.connection.recovery.nextAction).toContain("task-specific validation");
    expect(JSON.stringify(summary)).not.toMatch(/gpu ready|qualified model|endpoint|certificate|credential/i);
  });

  it("fails closed during reconnect and hides retained handshake fields", () => {
    const summary = buildNodeReadiness({
      ...verifiedConnection,
      state: "reconnecting",
      failure: { code: "node_disconnected", message: "Connection interrupted." },
    }, profile);

    expect(summary.connection).toMatchObject({
      tone: "attention",
      title: "Reconnection required",
      proof: [],
    });
    expect(summary.connection.recovery).toEqual({
      preserved: "The existing task view remains readable, but retained trust is not used for authority.",
      retry: "No consequential command is retried while the connection is uncertain.",
      nextAction: "Reconnect through the approved Node profile and wait for a fresh trust result.",
    });
    expect(JSON.stringify(summary)).not.toContain("operator-17");
    expect(JSON.stringify(summary)).not.toContain("ledger-connect-42");
  });

  it("does not call an unverified connection sovereign or ready", () => {
    const summary = buildNodeReadiness({
      ...verifiedConnection,
      sovereignty: "unknown",
    }, profile);

    expect(summary.connection).toMatchObject({
      tone: "attention",
      title: "Connection proof needs attention",
      proof: [],
    });
    expect(summary.connection.detail).not.toMatch(/verified|ready/i);
  });
});
