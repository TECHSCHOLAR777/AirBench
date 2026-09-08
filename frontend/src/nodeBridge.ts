import { invoke } from "@airbench/tauri-invoke";
import type { ApprovedNodeProfile, ApprovedNodeProfileReference } from "./nodeConnection";
import type { Clearance } from "./protocol";

export interface NativeNodeConnectionResult {
  state: "connected";
  profile_id: string;
  node_identity: string;
  protocol_version: string;
  clearance_context: Clearance;
  authenticated_subject: string;
  domain_pack_ref: string;
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
    trusted_ca_pem: profile.trustedCaPem,
    credential_ref: profile.credentialRef,
    approved_by_policy: profile.approvedByPolicy,
  };
}

export function toNativeNodeProfileReference(profile: ApprovedNodeProfileReference) {
  return { profile_id: profile.profileId };
}

/**
 * The webview has no network client. This is the only connection entry point,
 * and it crosses into the Rust-owned Tauri command boundary.
 */
export async function connectApprovedNode(profile: ApprovedNodeProfileReference | ApprovedNodeProfile): Promise<NativeNodeConnectionResult> {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) throw new Error("The approved Node profile is incomplete or not approved by policy.");
  return invoke<NativeNodeConnectionResult>("connect_node", { profileId: profile.profileId });
}
