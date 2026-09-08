import type { ApprovedNodeProfileReference } from "./nodeConnection";
import type { NodeConnectionView } from "./nodeConnectionController";

export type NodeReadinessTone = "trusted" | "attention" | "blocked";

export interface NodeProofField {
  label: string;
  value: string;
}

export interface NodeConnectionReadiness {
  tone: NodeReadinessTone;
  title: string;
  detail: string;
  proof: NodeProofField[];
}

export interface NodeOperationalReadiness {
  state: "not_supplied" | "connection_required";
  title: string;
  detail: string;
  missing: string[];
}

export interface NodeRoutingReadiness {
  title: string;
  detail: string;
}

export interface NodeReadiness {
  connection: NodeConnectionReadiness;
  operational: NodeOperationalReadiness;
  routing: NodeRoutingReadiness;
}

function displayValue(value: string | null): string {
  return value?.trim() || "Not supplied";
}

function transportLabel(profile: ApprovedNodeProfileReference | null): string {
  if (!profile) return "Not supplied";
  return profile.transport === "loopback" ? "Local workstation" : "Internal network";
}

function operationalReadiness(verified: boolean): NodeOperationalReadiness {
  if (!verified) {
    return {
      state: "connection_required",
      title: "Operational status requires a verified Node",
      detail: "Hardware, sandbox, qualification, workload, and router detail remain unknown until an approved Node connection is verified.",
      missing: ["Hardware and capacity", "Sandbox health", "Qualified capability catalog", "Router decision history"],
    };
  }

  return {
    state: "not_supplied",
    title: "Operational status is not supplied",
    detail: "This verified handshake does not include hardware, sandbox, workload, model qualification, or router-history projections. AirBench does not infer them from a connection.",
    missing: ["Hardware and capacity", "Sandbox health", "Qualified capability catalog", "Router decision history"],
  };
}

/**
 * Builds a display-only Node readiness projection from the existing trusted
 * handshake. It never treats a connection as proof of operational health,
 * model qualification, routing, or policy authority.
 */
export function buildNodeReadiness(
  connection: NodeConnectionView,
  profile: ApprovedNodeProfileReference | null,
): NodeReadiness {
  const verified = connection.state === "connected" && connection.sovereignty === "verified";
  const routing: NodeRoutingReadiness = {
    title: "Routing authority stays with the Node",
    detail: "AirBench requests a qualified capability for each task. A model preference remains unavailable until the Node supplies a clearance-filtered qualified catalog.",
  };

  if (verified) {
    return {
      connection: {
        tone: "trusted",
        title: "Approved Node connection verified",
        detail: "The native handshake verified the Node identity, operator context, and clearance. The Node still decides whether a consequential task action is permitted.",
        proof: [
          { label: "Approved profile", value: profile?.displayName ?? "Not supplied" },
          { label: "Node identity", value: displayValue(connection.nodeIdentity) },
          { label: "Operator", value: displayValue(connection.authenticatedSubject) },
          { label: "Clearance", value: displayValue(connection.clearanceContext) },
          { label: "Domain pack", value: displayValue(connection.domainPackRef) },
          { label: "Transport", value: transportLabel(profile) },
          { label: "Protocol", value: displayValue(connection.protocolVersion) },
          { label: "Protocol contract", value: displayValue(connection.protocolCompatibilityId) },
          { label: "Handshake ledger", value: displayValue(connection.ledgerEventRef) },
        ],
      },
      operational: operationalReadiness(true),
      routing,
    };
  }

  if (connection.state === "reconnecting") {
    return {
      connection: {
        tone: "attention",
        title: "Reconnection required",
        detail: "The approved Node path was interrupted. AirBench will not use retained handshake details to authorize consequential work.",
        proof: [],
      },
      operational: operationalReadiness(false),
      routing,
    };
  }

  if (connection.state === "connecting") {
    return {
      connection: {
        tone: "attention",
        title: "Checking approved Node",
        detail: "The native boundary is validating the approved profile before the desktop receives a trusted connection result.",
        proof: [],
      },
      operational: operationalReadiness(false),
      routing,
    };
  }

  if (connection.state === "connected") {
    return {
      connection: {
        tone: "attention",
        title: "Connection proof needs attention",
        detail: "The trust response is incomplete, so the desktop cannot use this connection for consequential work.",
        proof: [],
      },
      operational: operationalReadiness(false),
      routing,
    };
  }

  if (connection.state === "blocked" || connection.state === "failed") {
    return {
      connection: {
        tone: "blocked",
        title: "Node connection blocked",
        detail: connection.failure?.message ?? "This desktop cannot use the selected Node path for consequential work.",
        proof: [],
      },
      operational: operationalReadiness(false),
      routing,
    };
  }

  return {
    connection: {
      tone: "attention",
      title: "No approved Node connection",
      detail: "Choose an organization-approved Node before AirBench can request work or verify a connection result.",
      proof: [],
    },
    operational: operationalReadiness(false),
    routing,
  };
}
