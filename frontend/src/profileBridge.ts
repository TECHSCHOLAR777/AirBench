import { invoke } from "@airbench/tauri-invoke";
import type { ApprovedNodeProfileReference, NodeTransport } from "./nodeConnection";
import type { Clearance } from "./protocol";

interface NativeApprovedNodeProfile {
  profile_id: string;
  display_name: string;
  transport: NodeTransport;
  node_identity: string;
  protocol_version: string;
  clearance_context: Clearance;
  approved_by_policy: boolean;
}

function fromNativeProfile(profile: NativeApprovedNodeProfile): ApprovedNodeProfileReference {
  return {
    profileId: profile.profile_id,
    displayName: profile.display_name || profile.profile_id,
    transport: profile.transport,
    nodeIdentity: profile.node_identity,
    protocolVersion: profile.protocol_version,
    clearanceContext: profile.clearance_context,
    approvedByPolicy: profile.approved_by_policy,
  };
}

/**
 * Loads only administrator-provisioned profiles from the native boundary.
 * The webview never accepts or constructs an endpoint for connection.
 */
export function listApprovedNodeProfiles(): Promise<ApprovedNodeProfileReference[]> {
  return invoke<NativeApprovedNodeProfile[]>("list_approved_node_profiles").then((profiles) => profiles.map(fromNativeProfile));
}
