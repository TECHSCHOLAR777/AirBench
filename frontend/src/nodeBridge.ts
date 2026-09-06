import { invoke } from "@tauri-apps/api/core";
import type { ApprovedNodeProfile } from "./nodeConnection";

export interface NativeNodeConnectionResult {
  state: "connected";
  profile_id: string;
  node_identity: string;
  protocol_version: string;
  clearance_context: string;
  sovereignty: "verified";
  ledger_event_ref: string;
}

export function toNativeNodeProfile(profile: ApprovedNodeProfile) {
  return {
    profile_id: profile.profileId,
    endpoint: profile.endpoint,
    transport: profile.transport,
    node_identity: profile.nodeIdentity,
    protocol_version: profile.protocolVersion,
    clearance_context: profile.clearanceContext,
    certificate_pin_sha256: profile.certificatePinSha256,
    approved_by_policy: profile.approvedByPolicy,
  };
}

/**
 * The webview has no network client. This is the only connection entry point,
 * and it crosses into the Rust-owned Tauri command boundary.
 */
export async function connectApprovedNode(profile: ApprovedNodeProfile): Promise<NativeNodeConnectionResult> {
  return invoke<NativeNodeConnectionResult>("connect_node", { profile: toNativeNodeProfile(profile) });
}
