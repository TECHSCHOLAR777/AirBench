import type { NodeCommandResult } from "../../generated/core_contracts";

export type TaskCommandAction = "Plan approval" | "Stop request";
export type CommandOutcomeTone = "positive" | "attention" | "danger";

export interface CommandOutcomeGuidance {
  tone: CommandOutcomeTone;
  label: string;
  detail: string;
  preserved: string;
  retry: string;
  nextAction: string;
}

function reportedReason(result: NodeCommandResult): string | null {
  const reason = result.reason ?? result.message ?? result.code;
  return reason?.trim() || null;
}

function withReason(detail: string, result: NodeCommandResult): string {
  const reason = reportedReason(result);
  return reason ? `${detail} Node reason: ${reason}` : detail;
}

/**
 * Maps an already validated Node command receipt to operator guidance.
 * This is presentation-only: the receipt and the Node remain authoritative.
 */
export function commandOutcomeGuidance(action: TaskCommandAction, result: NodeCommandResult): CommandOutcomeGuidance {
  if (result.outcome === "accepted") {
    return action === "Plan approval"
      ? {
        tone: "positive",
        label: "Plan approval accepted by Node",
        detail: "The Node accepted the approval command. Execution state changes only after the authoritative task event arrives.",
        preserved: "The validated plan, command receipt, and Node ledger reference remain available.",
        retry: "Do not submit a second approval while the authoritative task event is pending.",
        nextAction: "Wait for the next ordered Node event before treating execution as started.",
      }
      : {
        tone: "positive",
        label: "Stop request accepted by Node",
        detail: "The Node accepted the stop request. The task state changes only after the authoritative stopped event arrives.",
        preserved: "The current task projection, command receipt, and Node ledger reference remain available.",
        retry: "Do not send a second stop request while the stopped event is pending.",
        nextAction: "Wait for the ordered stopped event, then confirm the task state from the Node.",
      };
  }

  if (result.outcome === "needs_review") {
    return {
      tone: "attention",
      label: `${action} needs Node review`,
      detail: withReason(`The Node did not authorize this ${action.toLowerCase()}. No local task state was changed.`, result),
      preserved: "The current Node task state and this command receipt remain available for review.",
      retry: "Do not retry or bypass the review until the Node supplies the required policy or task context.",
      nextAction: "Review the Node response and wait for a new authoritative result before taking consequential action.",
    };
  }

  return {
    tone: "danger",
    label: `${action} rejected by Node`,
    detail: withReason(`The Node rejected this ${action.toLowerCase()}. No local task state was changed.`, result),
    preserved: "The existing Node task state and the rejected command receipt remain available; no new state is implied.",
    retry: "Do not repeat the command with the same stale or unauthorized context.",
    nextAction: "Review the Node rejection, refresh the authoritative projection, and follow the next permitted Node action.",
  };
}

export function shouldRefreshTaskAfterCommand(result: NodeCommandResult): boolean {
  return result.outcome === "accepted";
}
