import { invoke } from "@airbench/tauri-invoke";
import type { ApprovedNodeProfileReference } from "./nodeConnection";
import type { TaskSnapshot } from "./protocol";
import type { NodeCommandEnvelope, NodeCommandResult } from "./generated/core_contracts";

const TASK_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const COMMAND_ID = /^[a-z0-9][a-z0-9._:-]{0,127}$/;

export type TaskCommandType = "task.authorize" | "task.cancel" | "task.request_review";

export interface CreateTaskResponse {
  task: unknown;
  snapshot: TaskSnapshot;
  ledger_event_ref: string;
  command: NodeCommandResult;
}

function assertApprovedProfile(profile: ApprovedNodeProfileReference): void {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) {
    throw new Error("The approved Node profile is incomplete or not approved by policy.");
  }
}

function assertCommand(command: NodeCommandEnvelope): void {
  if (!COMMAND_ID.test(command.command_id)) throw new Error("The command identifier is invalid.");
  if (!command.actor.trim() || !command.idempotency_key.trim()) throw new Error("The command identity is incomplete.");
  if (!command.client_version.trim()) throw new Error("The command protocol version is missing.");
  if (!command.arguments || typeof command.arguments !== "object" || Array.isArray(command.arguments)) {
    throw new Error("The command arguments must be an object.");
  }
}

function assertTaskCommand(command: NodeCommandEnvelope): asserts command is NodeCommandEnvelope & { task_id: string; expected_sequence: number } {
  assertCommand(command);
  if (!command.task_id || !TASK_ID.test(command.task_id)) throw new Error("The command task identifier is invalid.");
  const expectedSequence = command.expected_sequence;
  if (expectedSequence === null || !Number.isSafeInteger(expectedSequence) || expectedSequence < 0) {
    throw new Error("The command expected sequence is invalid.");
  }
  if (!["task.authorize", "task.cancel", "task.request_review"].includes(command.command_type)) {
    throw new Error("The command type is not supported by this transport.");
  }
}

export function fetchTaskSnapshot(profile: ApprovedNodeProfileReference, taskId: string): Promise<TaskSnapshot> {
  assertApprovedProfile(profile);
  if (!TASK_ID.test(taskId)) throw new Error("The task identifier is invalid.");
  return invoke<TaskSnapshot>("fetch_task_snapshot", {
    profileId: profile.profileId,
    taskId,
  });
}

export function createTask(profile: ApprovedNodeProfileReference, command: NodeCommandEnvelope): Promise<CreateTaskResponse> {
  assertApprovedProfile(profile);
  assertCommand(command);
  if (command.command_type !== "task.create" || command.task_id !== null || command.expected_sequence !== null) {
    throw new Error("The task creation command envelope is invalid.");
  }
  return invoke<CreateTaskResponse>("create_task", {
    profileId: profile.profileId,
    command,
  });
}

export function sendTaskCommand(profile: ApprovedNodeProfileReference, command: NodeCommandEnvelope): Promise<NodeCommandResult> {
  assertApprovedProfile(profile);
  assertTaskCommand(command);
  return invoke<NodeCommandResult>("send_task_command", {
    profileId: profile.profileId,
    command,
  });
}
