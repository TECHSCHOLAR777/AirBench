import type { EventSyncState, EventSyncStatus } from "../../platform/events/eventStore";
import type { TaskProjection } from "../../platform/events/protocol";

export type SyncRecoveryTone = "neutral" | "active" | "attention" | "blocked";

export interface SyncRecoveryGuidance {
  tone: SyncRecoveryTone;
  label: string;
  detail: string;
  preserved: string;
  retry: string;
  nextAction: string;
}

/**
 * Maps transport and replay state to an operator-facing recovery contract.
 * This is presentation guidance only. The Node still owns task state and
 * the event synchronizer still owns whether consequential commands are safe.
 */
export function taskSyncRecovery(
  status: EventSyncStatus,
  projection: TaskProjection,
  error: EventSyncState["error"] = null,
): SyncRecoveryGuidance {
  const ledger = projection.ledgerHeadRef || "the last accepted ledger context";
  if (status === "reconnecting") {
    return {
      tone: "attention",
      label: "Node connection interrupted",
      detail: error?.message ?? "AirBench is waiting for the approved Node to respond again.",
      preserved: `The last accepted task state, evidence, and ${ledger} remain visible as stale context.`,
      retry: "Reconnect is retried with backoff. Do not send a duplicate consequential command while the view is stale.",
      nextAction: "Reconnect the approved Node, then wait for the next ordered event or snapshot before approving or stopping work.",
    };
  }
  if (status === "replaying") {
    return {
      tone: "active",
      label: "Catching up recorded events",
      detail: "The Node returned an ordered range and the desktop is applying it from the current cursor.",
      preserved: `The existing projection and ${ledger} remain attached while the event range is replayed.`,
      retry: "Wait for replay to finish. The desktop does not reorder events or start a second synchronization.",
      nextAction: "Continue when the Node reports the task view current; consequential actions remain gated until then.",
    };
  }
  if (status === "blocked") {
    return {
      tone: "blocked",
      label: "Task view blocked",
      detail: error?.message ?? "The Node response could not be accepted safely.",
      preserved: `The last accepted projection and ${ledger} remain available for diagnosis.`,
      retry: "No automatic retry is performed after a protocol, identity, clearance, or replay failure.",
      nextAction: "Review the recorded error, reconnect or refresh through the approved Node path, and do not treat this view as current.",
    };
  }
  if (status === "syncing") {
    return {
      tone: "active",
      label: "Checking current Node state",
      detail: "The desktop is requesting the next sequence range from the approved Node.",
      preserved: `The existing projection and ${ledger} remain visible while the request is in flight.`,
      retry: "Wait for this request. The event loop prevents overlapping synchronization calls.",
      nextAction: "Wait for the Node result; no consequential action is presented as complete during the check.",
    };
  }
  if (status === "connected") {
    return {
      tone: "neutral",
      label: "Task view is current",
      detail: "The projection reflects the latest accepted Node snapshot and ordered event cursor.",
      preserved: `Task state, evidence, and ${ledger} remain attached to the current projection.`,
      retry: "No retry is needed while the Node is current.",
      nextAction: "Continue with the actions that the current Node plan and authorization state permit.",
    };
  }
  return {
    tone: "neutral",
    label: "Synchronization not started",
    detail: "The desktop has a Node snapshot but has not begun the task event check.",
    preserved: `The snapshot and ${ledger} remain available as the starting projection.`,
    retry: "No request is currently in flight.",
    nextAction: "Refresh the task through the approved Node path to establish a current event cursor.",
  };
}
