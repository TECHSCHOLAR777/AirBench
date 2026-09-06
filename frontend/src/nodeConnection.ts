import type { Clearance } from "./protocol";

export type NodeTransport = "loopback" | "internal_https";
export type NodeConnectionState = "not_connected" | "connecting" | "connected" | "reconnecting" | "blocked" | "failed";

export interface ApprovedNodeProfile {
  profileId: string;
  displayName: string;
  endpoint: string;
  transport: NodeTransport;
  nodeIdentity: string;
  protocolVersion: string;
  clearanceContext: Clearance;
  certificatePinSha256: string | null;
  approvedByPolicy: boolean;
}

export interface NodeConnectionResult {
  state: NodeConnectionState;
  profileId: string;
  nodeIdentity: string | null;
  protocolVersion: string | null;
  clearanceContext: Clearance | null;
  sovereignty: "unknown" | "verified" | "blocked";
  failure: { code: string; message: string } | null;
}

export type ProfileValidation =
  | { valid: true; normalizedEndpoint: string }
  | { valid: false; code: "not_approved" | "invalid_endpoint" | "external_endpoint" | "credentials_in_endpoint" | "missing_certificate_pin" | "protocol_not_allowed"; message: string };

export function validateApprovedProfile(profile: ApprovedNodeProfile): ProfileValidation {
  if (!profile.approvedByPolicy) return { valid: false, code: "not_approved", message: "This Node profile has not been approved by policy." };
  let parsed: URL;
  try {
    parsed = new URL(profile.endpoint);
  } catch {
    return { valid: false, code: "invalid_endpoint", message: "The approved Node endpoint is not a valid URL." };
  }
  if (parsed.username || parsed.password) return { valid: false, code: "credentials_in_endpoint", message: "Credentials must not be embedded in a Node endpoint." };
  if (parsed.search || parsed.hash) return { valid: false, code: "invalid_endpoint", message: "Node endpoints cannot contain query or fragment data." };

  if (profile.transport === "loopback") {
    const loopback = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1" || parsed.hostname === "[::1]" || parsed.hostname === "::1";
    if (!loopback) return { valid: false, code: "external_endpoint", message: "A loopback profile may target only the local machine." };
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return { valid: false, code: "protocol_not_allowed", message: "A loopback profile must use the approved local transport." };
  }

  if (profile.transport === "internal_https") {
    if (parsed.protocol !== "https:") return { valid: false, code: "protocol_not_allowed", message: "Internal remote Nodes must use HTTPS." };
    if (!profile.certificatePinSha256) return { valid: false, code: "missing_certificate_pin", message: "An internal remote Node requires a pinned certificate." };
  }

  return { valid: true, normalizedEndpoint: parsed.origin + parsed.pathname.replace(/\/$/, "") };
}

export function blockedConnection(profile: ApprovedNodeProfile, validation: Extract<ProfileValidation, { valid: false }>): NodeConnectionResult {
  return {
    state: "blocked",
    profileId: profile.profileId,
    nodeIdentity: null,
    protocolVersion: null,
    clearanceContext: null,
    sovereignty: "blocked",
    failure: { code: validation.code, message: validation.message },
  };
}
