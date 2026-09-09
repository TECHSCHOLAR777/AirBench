import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { createTask, fetchTaskPlan, fetchTaskSnapshot, sendTaskCommand, validateNodeCommandResult, validateTaskPlanReview } from "./nodeCommands";
import type { NodeCommandEnvelope, NodeCommandResult } from "../../generated/core_contracts";
import type { TaskPlanReview } from "../../generated/core_contracts";
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

const plan: TaskPlanReview = {
  schema_version: "1.0",
  compatibility_id: "airbench-core-contracts",
  task_id: "task-1",
  node_identity: "node-1",
  protocol_version: "0.1",
  clearance_context: "restricted",
  plan_state: "not_ready",
  task_sequence: 4,
  team_id: null,
  assignments: [],
  dependency_graph: {},
  concurrency_ceiling: 0,
  execution_mode: "not_selected",
  worker_capabilities: {},
  hardware_profile_ref: null,
  hardware_reason: "The Node has accepted the task but has not committed a plan yet.",
  required_verification: true,
  completion_criteria: ["A reviewed approval note is produced."],
  required_authority: "operator_approval",
  authority_reason: "An authorized operator must approve this plan before execution.",
  plan_version_hash: null,
  policy_version_hash: null,
  ledger_event_ref: null,
  failure_code: "plan_not_ready",
  failure_reason: "The orchestration engine has not committed a validated plan.",
};

const commandResult: NodeCommandResult = {
  schema_version: "1.0",
  compatibility_id: "airbench-core-contracts",
  outcome: "accepted",
  command_id: "command.approve.1",
  task_id: "task-1",
  idempotency_key: "idempotency.approve.1",
  ledger_event_ref: "ledger-command-1",
  sequence: 5,
  state: "accepted",
  node_identity: "node-1",
  protocol_version: "0.1",
  clearance_context: "restricted",
  event_type: "task.plan.approved",
  code: null,
  message: null,
  reason: null,
};

describe("typed Node command transport", () => {
  beforeEach(() => invokeMock.mockReset());

  it("routes snapshot reads through the Rust-owned bridge", () => {
    invokeMock.mockResolvedValue(plan);
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

  it("validates the plan response before it reaches approval or trace state", async () => {
    invokeMock.mockResolvedValueOnce(plan);

    await expect(fetchTaskPlan(profile, "task-1")).resolves.toEqual(plan);
  });

  it("rejects a ready plan without complete authority and hardware context", () => {
    expect(() => validateTaskPlanReview({ ...plan, plan_state: "ready", team_id: null, plan_version_hash: null, execution_mode: "not_selected" }, profile, "task-1")).toThrow("complete team or hardware admission context");
    expect(() => validateTaskPlanReview({ ...plan, plan_state: "blocked", failure_code: null, failure_reason: null }, profile, "task-1")).toThrow("failure reason");
    expect(() => validateTaskPlanReview({ ...plan, required_verification: false }, profile, "task-1")).toThrow("independent verification");
  });

  it("rejects a plan returned for another task or Node", () => {
    expect(() => validateTaskPlanReview({ ...plan, task_id: "task-2" }, profile, "task-1")).toThrow("does not match");
    expect(() => validateTaskPlanReview({ ...plan, node_identity: "other-node" }, profile, "task-1")).toThrow("does not match");
  });

  it("serializes creation and consequential commands as one envelope", () => {
    invokeMock.mockImplementation((_name, args) => {
      const submitted = (args as { command?: NodeCommandEnvelope } | undefined)?.command;
      return Promise.resolve({
        ...commandResult,
        command_id: submitted?.command_id ?? commandResult.command_id,
        task_id: submitted?.task_id ?? commandResult.task_id,
        idempotency_key: submitted?.idempotency_key ?? commandResult.idempotency_key,
      });
    });
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

  it("accepts a command result only when it is bound to the command and ledger", () => {
    const command: NodeCommandEnvelope = {
      ...createCommand,
      command_id: "command.approve.1",
      task_id: "task-1",
      expected_sequence: 5,
      idempotency_key: "idempotency.approve.1",
      command_type: "task.approve_plan",
    };

    expect(validateNodeCommandResult({ ...commandResult, unexpected: "ignored" }, profile, command)).toEqual(commandResult);
    expect(() => validateNodeCommandResult({ ...commandResult, command_id: "command.other.1" }, profile, command)).toThrow("does not match the submitted command");
    expect(() => validateNodeCommandResult({ ...commandResult, ledger_event_ref: null }, profile, command)).toThrow("missing its ledger");
    expect(() => validateNodeCommandResult({ ...commandResult, node_identity: "other-node" }, profile, command)).toThrow("approved Node profile");
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
