import { invoke } from "@airbench/tauri-invoke";
import type { ApprovedNodeProfileReference } from "../node/nodeConnection";
import { toNativeNodeProfileReference } from "../node/nodeBridge";
import { normalizeTaskEventBatch, type TaskEventBatch } from "./protocol";
import type { NodeTaskEventBatch } from "../../generated/core_contracts";

export type { TaskEventBatch } from "./protocol";

export function toNativeEventProfile(profile: ApprovedNodeProfileReference) {
  return toNativeNodeProfileReference(profile);
}

/** Fetches a replayable cursor range through the Rust-owned Node transport. */
export function fetchTaskEventBatch(profile: ApprovedNodeProfileReference, taskId: string, afterSequence: number): Promise<TaskEventBatch> {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) throw new Error("The approved Node profile is incomplete or not approved by policy.");
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(taskId)) throw new Error("The task identifier is invalid.");
  if (!Number.isSafeInteger(afterSequence) || afterSequence < 0) throw new Error("The event cursor is invalid.");
  return invoke<NodeTaskEventBatch>("fetch_task_events", {
    profileId: profile.profileId,
    taskId,
    afterSequence,
  }).then(normalizeTaskEventBatch);
}
