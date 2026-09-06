import { invoke } from "@airbench/tauri-invoke";
import { assertApprovedNodeProfile, type ApprovedNodeProfile } from "./nodeConnection";
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

export function toNativeEventProfile(profile: ApprovedNodeProfile) {
  return {
    profile_id: profile.profileId,
    endpoint: profile.endpoint,
    transport: profile.transport,
    node_identity: profile.nodeIdentity,
    protocol_version: profile.protocolVersion,
    clearance_context: profile.clearanceContext,
    certificate_pin_sha256: profile.certificatePinSha256,
    trusted_ca_pem: profile.trustedCaPem,
    credential_ref: profile.credentialRef,
    approved_by_policy: profile.approvedByPolicy,
  };
}

/** Fetches a replayable cursor range through the Rust-owned Node transport. */
export function fetchTaskEventBatch(profile: ApprovedNodeProfile, taskId: string, afterSequence: number): Promise<TaskEventBatch> {
  const approvedProfile = assertApprovedNodeProfile(profile);
  return invoke<TaskEventBatch>("fetch_task_events", {
    profile: toNativeEventProfile(approvedProfile),
    taskId,
    afterSequence,
  });
}
