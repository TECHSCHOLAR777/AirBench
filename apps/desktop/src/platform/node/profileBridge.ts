import { invoke } from "@airbench/tauri-invoke";
import type { ApprovedNodeProfileReference, NodeTransport } from "./nodeConnection";
import type { Clearance } from "../events/protocol";

interface NativeApprovedNodeProfile {
  profile_id: string;
  display_name: string;
  transport: NodeTransport;
  node_identity: string;
  protocol_version: string;
  clearance_context: Clearance;
  approved_by_policy: boolean;
}

class InvalidNodeProfileCatalog extends Error {
  readonly code = "invalid_profile_catalog";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isClearance(value: unknown): value is Clearance {
  return value === "public" || value === "internal" || value === "restricted" || value === "secret";
}

function parseNativeProfile(value: unknown, index: number): NativeApprovedNodeProfile {
  if (!isRecord(value)
    || typeof value.profile_id !== "string"
    || typeof value.display_name !== "string"
    || (value.transport !== "loopback" && value.transport !== "internal_https")
    || typeof value.node_identity !== "string"
    || typeof value.protocol_version !== "string"
    || !isClearance(value.clearance_context)
    || value.approved_by_policy !== true) {
    throw new InvalidNodeProfileCatalog(`The approved Node catalog entry ${index + 1} is incomplete or not approved by policy.`);
  }

  const profile = value as unknown as NativeApprovedNodeProfile;
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(profile.profile_id)
    || !profile.display_name.trim()
    || !profile.node_identity.trim()
    || !profile.protocol_version.trim()) {
    throw new InvalidNodeProfileCatalog(`The approved Node catalog entry ${index + 1} has an invalid identity.`);
  }
  return profile;
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
  return invoke<unknown>("list_approved_node_profiles").then((value) => {
    if (!Array.isArray(value)) throw new InvalidNodeProfileCatalog("The approved Node catalog is not a list.");
    const seen = new Set<string>();
    return value.map((candidate, index) => {
      const profile = parseNativeProfile(candidate, index);
      if (seen.has(profile.profile_id)) throw new InvalidNodeProfileCatalog("The approved Node catalog contains duplicate profile identities.");
      seen.add(profile.profile_id);
      return fromNativeProfile(profile);
    });
  });
}
