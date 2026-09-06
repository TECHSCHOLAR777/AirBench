import type { NodeCommandEnvelope } from "./generated/core_contracts";
import type { Clearance } from "./protocol";

export interface TaskComposerInput {
  actor: string;
  clearance: Clearance;
  domainPackRef: string;
  request: string;
  title: string;
  projectRef: string | null;
  outputContract: string;
  priority: string;
  deadline: string | null;
  inputManifestRefs: string[];
}

const MAX_REQUEST_LENGTH = 65_536;

function required(value: string, label: string, maximum: number): string {
  const normalized = value.trim();
  if (!normalized || normalized.length > maximum) throw new Error(`${label} is required and must be at most ${maximum} characters.`);
  return normalized;
}

function optional(value: string | null, label: string, maximum: number): string | null {
  if (value === null) return null;
  const normalized = value.trim();
  if (!normalized) return null;
  if (normalized.length > maximum) throw new Error(`${label} must be at most ${maximum} characters.`);
  return normalized;
}

export function buildCreateTaskCommand(input: TaskComposerInput, commandId: string, idempotencyKey: string): NodeCommandEnvelope {
  const actor = required(input.actor, "The authenticated subject", 256);
  const domainPackRef = required(input.domainPackRef, "The approved domain pack", 512);
  const request = required(input.request, "The desired outcome", MAX_REQUEST_LENGTH);
  const title = required(input.title || request.slice(0, 256), "The task title", 256);
  const outputContract = required(input.outputContract, "The deliverable type", 512);
  const priority = required(input.priority, "The task priority", 64);
  const projectRef = optional(input.projectRef, "The project reference", 256);
  const deadline = optional(input.deadline, "The deadline", 64);
  if (!commandId.trim() || !idempotencyKey.trim()) throw new Error("The task command identity is incomplete.");
  if (!Number.isSafeInteger(input.inputManifestRefs.length) || input.inputManifestRefs.length > 100) {
    throw new Error("The input manifest list is invalid.");
  }

  return {
    schema_version: "1.0",
    compatibility_id: "airbench-core-contracts",
    command_id: commandId,
    task_id: null,
    actor,
    expected_sequence: null,
    idempotency_key: idempotencyKey,
    client_version: "0.1",
    command_type: "task.create",
    arguments: {
      principal_id: actor,
      clearance: input.clearance,
      domain_pack_ref: domainPackRef,
      request,
      title,
      project_ref: projectRef,
      output_contract: outputContract,
      priority,
      deadline,
      risk_class: "operator_requested",
      autonomy_ceiling: "review_required",
      allowed_evidence_scope: [],
      permitted_worker_capabilities: ["general"],
      permitted_tools: [],
      verification_criteria: [],
      resource_budget: { max_concurrency: 1, max_steps: 32 },
      input_manifest_refs: [...input.inputManifestRefs],
    },
  };
}

export function buildApprovePlanCommand(
  actor: string,
  taskId: string,
  expectedSequence: number,
  approvalRef: string,
  commandId: string,
  idempotencyKey: string,
): NodeCommandEnvelope {
  const normalizedActor = required(actor, "The authenticated subject", 256);
  const normalizedTaskId = required(taskId, "The task identifier", 128);
  const normalizedApprovalRef = required(approvalRef, "The plan approval reference", 512);
  if (!Number.isSafeInteger(expectedSequence) || expectedSequence < 0) {
    throw new Error("The plan task sequence is invalid.");
  }
  if (!commandId.trim() || !idempotencyKey.trim()) throw new Error("The plan approval command identity is incomplete.");
  return {
    schema_version: "1.0",
    compatibility_id: "airbench-core-contracts",
    command_id: commandId,
    task_id: normalizedTaskId,
    actor: normalizedActor,
    expected_sequence: expectedSequence,
    idempotency_key: idempotencyKey,
    client_version: "0.1",
    command_type: "task.approve_plan",
    arguments: { approval_ref: normalizedApprovalRef },
  };
}
