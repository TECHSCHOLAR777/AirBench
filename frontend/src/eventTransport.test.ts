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

  it("normalizes a typed Node batch and retains both envelopes", async () => {
    invokeMock.mockResolvedValue({
      schema_version: "1.0",
      compatibility_id: "airbench-core-contracts",
      stream_id: "task-1",
      node_identity: "node-1",
      protocol_version: "0.1",
      clearance_context: "restricted",
      events: [{
        eventId: "event-1",
        taskId: "task-1",
        sequence: 1,
        schemaVersion: "0.1",
        compatibilityId: "airbench-node-protocol",
        eventType: "task.accepted",
        occurredAt: "2026-09-09T00:00:00Z",
        actor: "node-1",
        clearanceContext: "restricted",
        payloadHash: "hash-1",
        ledgerEventRef: "ledger-1",
        payload: { phase: "accepted", status: "accepted" },
      }],
      next_sequence: 1,
      has_more: false,
      ledger_event_refs: ["ledger-1"],
    });

    const result = await fetchTaskEventBatch(profile, "task-1", 0);

    expect(result.schema_version).toBe("1.0");
    expect(result.compatibility_id).toBe("airbench-core-contracts");
    expect(result.events[0]?.compatibilityId).toBe("airbench-node-protocol");
    expect(result.events[0]?.eventType).toBe("task.accepted");
  });
});
