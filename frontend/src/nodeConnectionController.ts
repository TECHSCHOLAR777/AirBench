import { connectApprovedNode, type NativeNodeConnectionResult } from "./nodeBridge";
import {
  blockedConnection,
  type ApprovedNodeProfileReference,
  type NodeConnectionState,
  validateApprovedProfile,
} from "./nodeConnection";
import type { Clearance } from "./protocol";

export interface NodeConnectionView {
  state: NodeConnectionState;
  profileId: string | null;
  nodeIdentity: string | null;
  protocolVersion: string | null;
  clearanceContext: Clearance | null;
  authenticatedSubject: string | null;
  domainPackRef: string | null;
  sovereignty: "unknown" | "verified" | "blocked";
  ledgerEventRef: string | null;
  failure: { code: string; message: string } | null;
}

export interface NodeConnector {
  (profile: ApprovedNodeProfileReference): Promise<NativeNodeConnectionResult>;
}

const initialConnection: NodeConnectionView = {
  state: "not_connected",
  profileId: null,
  nodeIdentity: null,
  protocolVersion: null,
    clearanceContext: null,
    authenticatedSubject: null,
    domainPackRef: null,
  sovereignty: "unknown",
  ledgerEventRef: null,
  failure: null,
};

/**
 * Owns only the desktop connection presentation state. Rust and the Node
 * remain authoritative for trust, identity, clearance, and ledger outcomes.
 */
export class NodeConnectionController {
  private view: NodeConnectionView = initialConnection;
  private approvedProfile: ApprovedNodeProfileReference | null = null;

  constructor(private readonly connector: NodeConnector = connectApprovedNode) {}

  snapshot(): NodeConnectionView {
    return { ...this.view, failure: this.view.failure ? { ...this.view.failure } : null };
  }

  async connect(profile: ApprovedNodeProfileReference): Promise<NodeConnectionView> {
    const validation = validateApprovedProfile(profile);
    if (!validation.valid) {
      const blocked = blockedConnection(profile, validation);
      this.approvedProfile = null;
      this.view = {
        ...initialConnection,
        state: blocked.state,
        profileId: blocked.profileId,
        sovereignty: blocked.sovereignty,
        failure: blocked.failure,
      };
      return this.snapshot();
    }

    this.approvedProfile = profile;
    this.view = {
      ...initialConnection,
      state: "connecting",
      profileId: profile.profileId,
    };

    try {
      const result = await this.connector(profile);
      this.view = {
        state: "connected",
        profileId: result.profile_id,
        nodeIdentity: result.node_identity,
        protocolVersion: result.protocol_version,
        clearanceContext: result.clearance_context,
        authenticatedSubject: result.authenticated_subject,
        domainPackRef: result.domain_pack_ref,
        sovereignty: result.sovereignty,
        ledgerEventRef: result.ledger_event_ref,
        failure: null,
      };
    } catch {
      this.view = {
        ...this.view,
        state: "failed",
        sovereignty: "blocked",
        failure: {
          code: "transport_failed",
          message: "The approved Node connection failed. No consequential work is permitted.",
        },
      };
    }

    return this.snapshot();
  }

  markDisconnected(): NodeConnectionView {
    if (this.view.state === "connected") {
      this.view = {
        ...this.view,
        state: "reconnecting",
        failure: {
          code: "node_disconnected",
          message: "The approved Node connection was interrupted. Reconnect before continuing consequential work.",
        },
      };
    }
    return this.snapshot();
  }

  async reconnect(): Promise<NodeConnectionView> {
    if (!this.approvedProfile) {
      this.view = {
        ...initialConnection,
        state: "blocked",
        sovereignty: "blocked",
        failure: {
          code: "no_approved_profile",
          message: "An approved Node profile is required before reconnecting.",
        },
      };
      return this.snapshot();
    }
    return this.connect(this.approvedProfile);
  }

  canSendConsequential(): boolean {
    return this.view.state === "connected" && this.view.sovereignty === "verified";
  }
}
