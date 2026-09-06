import { invoke } from "@airbench/tauri-invoke";
import type { ApprovedNodeProfileReference } from "./nodeConnection";
import { toNativeNodeProfileReference } from "./nodeBridge";
import type { Clearance, TaskEvent } from "./protocol";

export interface TaskEventBatch {
  stream_id: string;
  node_identity: string;
  protocol_version: string;
  clearance_context: Clearance;
  events: TaskEvent[];
  next_sequence: number;
  has_more: boolean;
  ledger_event_refs: string[];
}

export function toNativeEventProfile(profile: ApprovedNodeProfileReference) {
  return toNativeNodeProfileReference(profile);
}

/** Fetches a replayable cursor range through the Rust-owned Node transport. */
export function fetchTaskEventBatch(profile: ApprovedNodeProfileReference, taskId: string, afterSequence: number): Promise<TaskEventBatch> {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) throw new Error("The approved Node profile is incomplete or not approved by policy.");
  return invoke<TaskEventBatch>("fetch_task_events", {
    profileId: profile.profileId,
    taskId,
    afterSequence,
  });
}
