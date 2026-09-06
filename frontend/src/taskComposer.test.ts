import { describe, expect, it } from "vitest";
import { buildCreateTaskCommand } from "./taskComposer";

const base = {
  actor: "operator-1" as const,
  clearance: "restricted" as const,
  domainPackRef: "approved-pack.v0" as const,
  request: "Review the attached report" as const,
  title: "Inspection review" as const,
  projectRef: "unit-4" as const,
  outputContract: "document" as const,
  priority: "high" as const,
  deadline: "2026-10-01T12:00:00Z" as const,
  inputManifestRefs: ["intake-1"],
};

describe("task composer command", () => {
  it("builds a server-authoritative create envelope with the Node-selected pack and manifest", () => {
    const command = buildCreateTaskCommand(base, "command.create.1", "idempotency.create.1");
    expect(command.command_type).toBe("task.create");
    expect(command.arguments).toMatchObject({
      domain_pack_ref: "approved-pack.v0",
      input_manifest_refs: ["intake-1"],
      output_contract: "document",
      priority: "high",
    });
  });

  it("fails closed for missing outcome or oversized metadata", () => {
    expect(() => buildCreateTaskCommand({ ...base, request: "" }, "command.create.1", "idempotency.create.1")).toThrow(/desired outcome/);
    expect(() => buildCreateTaskCommand({ ...base, title: "x".repeat(257) }, "command.create.1", "idempotency.create.1")).toThrow(/task title/);
    expect(() => buildCreateTaskCommand({ ...base, domainPackRef: "" }, "command.create.1", "idempotency.create.1")).toThrow(/domain pack/);
  });
});
