import type { TaskPlanReview } from "../../generated/core_contracts";

export interface PlanRecoveryGuidance {
  preserved: string;
  retry: string;
  nextAction: string;
}

export function planRecoveryGuidance(
  plan: Pick<TaskPlanReview, "plan_state">,
  synchronized: boolean,
  approved: boolean,
): PlanRecoveryGuidance {
  if (approved) {
    return {
      preserved: "The Node approval receipt and plan sequence remain visible.",
      retry: "Do not submit a second approval while the task event is pending.",
      nextAction: "Wait for the Node to record the next authoritative task event.",
    };
  }

  if (!synchronized) {
    return {
      preserved: "The last Node plan remains readable, but its state is not current.",
      retry: "Do not approve or cancel until the event stream is current again.",
      nextAction: "Reconnect or refresh the approved Node task projection.",
    };
  }

  switch (plan.plan_state) {
    case "queued":
      return {
        preserved: "The Node-accepted plan remains queued with its hardware admission context.",
        retry: "Do not create a duplicate task while hardware admission is pending.",
        nextAction: "Wait for the Node to admit the plan or return a policy result.",
      };
    case "blocked":
      return {
        preserved: "The task request and blocked plan record remain available for review.",
        retry: "No local retry can bypass the Node's policy or hardware decision.",
        nextAction: "Resolve the Node-reported blocker, then request a fresh plan.",
      };
    case "rejected":
      return {
        preserved: "The rejected plan and its Node record remain visible; no work has started.",
        retry: "Do not approve a rejected plan or resubmit it without a changed Node result.",
        nextAction: "Review the rejection and revise the task through the approved Node path.",
      };
    case "needs_review":
      return {
        preserved: "The Node plan remains available and no execution is treated as started.",
        retry: "Do not approve until the Node has supplied the required review context.",
        nextAction: "Review the Node-provided reason and wait for a ready plan.",
      };
    case "not_ready":
      return {
        preserved: "The task request remains recorded without an executable plan.",
        retry: "Do not retry approval while the plan is not ready.",
        nextAction: "Wait for the Node to return a ready plan or an explicit failure reason.",
      };
    default:
      return {
        preserved: "The Node plan projection remains visible as received.",
        retry: "No local action can promote an unrecognized plan state.",
        nextAction: "Refresh the approved Node projection before taking action.",
      };
  }
}
