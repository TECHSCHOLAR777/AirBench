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
  recovery: {
    preserved: string;
    retry: string;
    nextAction: string;
  };
}

export interface NodeRoutingReadiness {
  title: string;
  detail: string;
}

export interface NodeReadiness {
  connection: NodeConnectionReadiness;
  routing: NodeRoutingReadiness;
}

function displayValue(value: string | null): string {
  return value?.trim() || "Not supplied";
}

function transportLabel(profile: ApprovedNodeProfileReference | null): string {
  if (!profile) return "Not supplied";
  return profile.transport === "loopback" ? "Local workstation" : "Internal network";
}

function recovery(preserved: string, retry: string, nextAction: string) {
  return { preserved, retry, nextAction };
}

function matchesApprovedProfile(
  connection: NodeConnectionView,
  profile: ApprovedNodeProfileReference | null,
): boolean {
  return Boolean(
    profile
      && profile.approvedByPolicy
      && profile.profileId === connection.profileId
      && profile.nodeIdentity === connection.nodeIdentity,
  );
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
  const verified = connection.state === "connected"
    && connection.sovereignty === "verified"
    && matchesApprovedProfile(connection, profile);
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
        recovery: recovery(
          "The verified handshake proof and its ledger reference remain visible.",
          "Recheck only through the approved Node profile if the session becomes uncertain.",
          "Continue by submitting work to the Node for task-specific validation.",
        ),
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
        recovery: recovery(
          "The existing task view remains readable, but retained trust is not used for authority.",
          "No consequential command is retried while the connection is uncertain.",
          "Reconnect through the approved Node profile and wait for a fresh trust result.",
        ),
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
        recovery: recovery(
          "The selected profile remains available; no task or file has been submitted.",
          "Wait for this handshake instead of starting a second connection attempt.",
          "Wait for the native boundary to return a verified or blocked result.",
        ),
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
        recovery: recovery(
          "No consequential task action is accepted from this incomplete trust result.",
          "Do not retry from the desktop until the approved profile or Node response is corrected.",
          "Recheck the approved Node and wait for complete identity and clearance proof.",
        ),
        proof: [],
      },
      operational: operationalReadiness(false),
      routing,
    };
  }

  if (connection.state === "blocked" || connection.state === "failed") {
    const failureTitle: Record<string, string> = {
      trust_failed: "Node trust check failed",
      unauthorized: "Node authentication failed",
      incompatible: "Node protocol is incompatible",
      transport_failed: "Node connection failed",
    };
    return {
      connection: {
        tone: "blocked",
        title: failureTitle[connection.failure?.kind ?? "transport_failed"] ?? "Node connection blocked",
        detail: connection.failure?.message ?? "This desktop cannot use the selected Node path for consequential work.",
        recovery: recovery(
          "No task, file, or consequential command is authorized by this blocked result.",
          "Retry only after the Node or profile failure is resolved by approved policy.",
          "Review the blocked result, then recheck an organization-approved Node.",
        ),
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
      recovery: recovery(
        "Nothing has been submitted, and no local connection is treated as trusted.",
        "Select an installed approved profile when you are ready to connect.",
        "Open Node settings and choose an organization-approved Node.",
      ),
      proof: [],
    },
    operational: operationalReadiness(false),
    routing,
  };
}
