import type { TaskStatus } from "../../platform/events/protocol";

export interface OperatorQuestionPresentation {
  eyebrow: string;
  title: string;
  state: string;
  continuation: string;
  action: string;
}

export function operatorQuestionAnnouncement(presentation: OperatorQuestionPresentation): string {
  return presentation.title;
}

export function operatorQuestionPresentation(
  taskStatus: TaskStatus,
  phase: string,
  synchronized: boolean,
): OperatorQuestionPresentation {
  if (!synchronized) {
    return {
      eyebrow: "NODE QUESTION RECORDED",
      title: "A decision may be waiting",
      state: "This desktop is not current with the approved Node, so the task state is preserved and no response can be sent here.",
      continuation: "Whether other work may continue is not available until the event stream is current.",
      action: "No response control is available while synchronization is incomplete.",
    };
  }

  if (["completed", "failed", "stopped"].includes(taskStatus)) {
    return {
      eyebrow: "RECORDED NODE QUESTION",
      title: "This question is retained for the task record",
      state: `The Node reports the task as ${taskStatus} in ${phase}. The desktop will not reopen or change that state locally.`,
      continuation: "Whether follow-up work is permitted must come from a new Node projection.",
      action: "No response control is available for a terminal task state.",
    };
  }

  if (taskStatus === "blocked") {
    return {
      eyebrow: "RECORDED NODE QUESTION",
      title: "This task is blocked",
      state: `The Node reports the task as blocked in ${phase}. The question is retained as evidence and cannot reopen or change the task locally.`,
      continuation: "Whether the block can be resolved must come from a new Node projection and permitted command.",
      action: "No response control is available for a blocked task until the Node supplies a typed, sequence-aware command.",
    };
  }

  if (taskStatus === "needs_review") {
    return {
      eyebrow: "DECISION NEEDED",
      title: "The Node is waiting for an authorized response",
      state: `The latest Node snapshot reports needs review in ${phase}. The task state remains on the Node.`,
      continuation: "The current question record does not state whether unrelated work may continue.",
      action: "Answer, pause, resume, and revision controls appear only after the Node supplies a typed, sequence-aware command.",
    };
  }

  return {
    eyebrow: "NODE QUESTION RECORDED",
    title: "AirBench needs a permitted decision",
    state: `The Node reported a question while the task is ${taskStatus} in ${phase}. No local task transition has occurred.`,
    continuation: "The current question record does not state whether unrelated work may continue.",
    action: "Answer, pause, resume, and revision controls appear only after the Node supplies a typed, sequence-aware command.",
  };
}
