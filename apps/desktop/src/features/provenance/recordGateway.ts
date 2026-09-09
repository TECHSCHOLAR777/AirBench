import type { TaskProjection } from "../../platform/events/protocol";

export type RecordGatewayDestination = "review" | "artifacts" | "history" | "audit";
export type RecordGatewayState = "node_unavailable" | "projection_not_current" | "query_not_supplied";

export interface RecordGatewayContext {
  taskId: string;
  title: string;
  status: TaskProjection["status"];
  phase: string;
  ledgerHeadRef: string;
}

export interface RecordGateway {
  destination: RecordGatewayDestination;
  eyebrow: string;
  title: string;
  description: string;
  state: RecordGatewayState;
  stateLabel: string;
  stateDescription: string;
  requiredProjection: string;
  currentTask: RecordGatewayContext | null;
}

const destinationCopy: Record<RecordGatewayDestination, Omit<RecordGateway, "state" | "stateLabel" | "stateDescription" | "currentTask">> = {
  review: {
    destination: "review",
    eyebrow: "NODE RECORDS",
    title: "Review queue is not supplied",
    description: "AirBench cannot determine whether a deliverable needs your decision until the approved Node provides a clearance-filtered review queue.",
    requiredProjection: "A Node-issued review queue with authority, clearance, reason, and ledgered decision commands.",
  },
  artifacts: {
    destination: "artifacts",
    eyebrow: "NODE RECORDS",
    title: "Artifact library is not supplied",
    description: "AirBench only presents durable outputs after the approved Node returns their status, clearance, version, and permitted actions.",
    requiredProjection: "A Node-issued artifact library with version, verification, clearance, provenance, and permitted download or review actions.",
  },
  history: {
    destination: "history",
    eyebrow: "NODE RECORDS",
    title: "Task history is not supplied",
    description: "AirBench does not reconstruct prior tasks in the desktop app. History must come from authoritative snapshots and ledger references.",
    requiredProjection: "A paged Node history projection with redaction behavior, task snapshots, and policy-permitted recovery actions.",
  },
  audit: {
    destination: "audit",
    eyebrow: "NODE RECORDS",
    title: "Audit ledger query is not supplied",
    description: "AirBench does not create a second audit record in the desktop app. Ledger inspection and export must come from the approved Node.",
    requiredProjection: "A read-only Node ledger query with chain status, redaction behavior, integrity references, and permitted offline export.",
  },
};

/**
 * Produces an honest pre-contract state for record destinations. It never
 * interprets absent data as an empty queue, library, history, or ledger.
 */
export function buildRecordGateway(
  destination: RecordGatewayDestination,
  nodeConnected: boolean,
  currentTask: TaskProjection | null,
): RecordGateway {
  const copy = destinationCopy[destination];
  if (!nodeConnected) {
    return {
      ...copy,
      state: "node_unavailable",
      stateLabel: "Connect an approved Node",
      stateDescription: "No approved Node path is currently connected, so AirBench cannot request this record safely.",
      currentTask: null,
    };
  }

  if (currentTask && currentTask.health !== "current") {
    return {
      ...copy,
      state: "projection_not_current",
      stateLabel: "Task context is not current",
      stateDescription: "The approved Node connection is active, but the current task projection is resynchronizing or blocked. AirBench will not show it as current context for this record view.",
      currentTask: null,
    };
  }

  return {
    ...copy,
    state: "query_not_supplied",
    stateLabel: "Record query not supplied",
    stateDescription: "The Node connection is active, but this desktop protocol does not yet include the required record projection.",
    currentTask: currentTask ? {
      taskId: currentTask.taskId,
      title: currentTask.title,
      status: currentTask.status,
      phase: currentTask.phase,
      ledgerHeadRef: currentTask.ledgerHeadRef,
    } : null,
  };
}
