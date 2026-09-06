import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { createTask, fetchTaskPlan, fetchTaskSnapshot, sendTaskCommand } from "./nodeCommands";
import type { NodeCommandEnvelope } from "./generated/core_contracts";
import type { ApprovedNodeProfileReference } from "./nodeConnection";

const profile: ApprovedNodeProfileReference = {
  profileId: "profile-1",
  displayName: "Plant Node",
  transport: "loopback",
  nodeIdentity: "node-1",
  protocolVersion: "0.1",
  clearanceContext: "restricted",
  approvedByPolicy: true,
};

const createCommand: NodeCommandEnvelope = {
  schema_version: "1.0",
  compatibility_id: "airbench-core-contracts",
  command_id: "command.create.1",
  task_id: null,
  actor: "principal.api",
  expected_sequence: null,
  idempotency_key: "idempotency.create.1",
  client_version: "0.1",
  command_type: "task.create",
  arguments: { request: "Review the report" },
};

describe("typed Node command transport", () => {
  beforeEach(() => invokeMock.mockReset());

  it("routes snapshot reads through the Rust-owned bridge", () => {
    fetchTaskSnapshot(profile, "task-1");
    expect(invokeMock).toHaveBeenCalledWith("fetch_task_snapshot", {
      profileId: "profile-1",
      taskId: "task-1",
    });
    fetchTaskPlan(profile, "task-1");
    expect(invokeMock).toHaveBeenLastCalledWith("fetch_task_plan", {
      profileId: "profile-1",
      taskId: "task-1",
    });
  });

  it("serializes creation and consequential commands as one envelope", () => {
    createTask(profile, createCommand);
    expect(invokeMock).toHaveBeenCalledWith("create_task", {
      profileId: "profile-1",
      command: createCommand,
    });

    const command: NodeCommandEnvelope = {
      ...createCommand,
      command_id: "command.cancel.1",
      task_id: "task-1",
      expected_sequence: 3,
      idempotency_key: "idempotency.cancel.1",
      command_type: "task.cancel",
      arguments: { reason: "operator stopped the task" },
    };
    sendTaskCommand(profile, command);
    expect(invokeMock).toHaveBeenLastCalledWith("send_task_command", {
      profileId: "profile-1",
      command,
    });

    const approval: NodeCommandEnvelope = {
      ...createCommand,
      command_id: "command.approve.1",
      task_id: "task-1",
      expected_sequence: 5,
      idempotency_key: "idempotency.approve.1",
      command_type: "task.approve_plan",
      arguments: { approval_ref: "operator.confirmed.plan-review" },
    };
    sendTaskCommand(profile, approval);
    expect(invokeMock).toHaveBeenLastCalledWith("send_task_command", {
      profileId: "profile-1",
      command: approval,
    });
  });

  it("fails closed before IPC for unsafe profiles, targets, or envelopes", () => {
    expect(() => fetchTaskSnapshot({ ...profile, approvedByPolicy: false }, "task-1")).toThrow(/approved by policy/);
    expect(() => fetchTaskSnapshot(profile, "../secret")).toThrow(/task identifier/);
    expect(() => createTask(profile, { ...createCommand, task_id: "task-1" })).toThrow(/creation command/);
    expect(() => sendTaskCommand(profile, { ...createCommand, task_id: "../secret", expected_sequence: 0, command_type: "task.cancel" })).toThrow(/task identifier/);
    expect(() => fetchTaskPlan(profile, "../secret")).toThrow(/task identifier/);
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
