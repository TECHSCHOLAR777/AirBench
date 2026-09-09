import { describe, expect, it } from "vitest";
import { operatorQuestionAnnouncement, operatorQuestionPresentation } from "./operatorQuestion";

describe("operator question presentation", () => {
  it("shows a waiting state without inventing a response action", () => {
    const presentation = operatorQuestionPresentation("needs_review", "approval", true);

    expect(presentation.title).toContain("waiting");
    expect(presentation.state).toContain("Node");
    expect(presentation.action).toContain("typed, sequence-aware command");
  });

  it("keeps stale terminal questions as records rather than reopening work", () => {
    const presentation = operatorQuestionPresentation("completed", "release", true);

    expect(presentation.eyebrow).toBe("RECORDED NODE QUESTION");
    expect(presentation.state).toContain("will not reopen or change");
    expect(presentation.action).toContain("terminal task state");
  });

  it("keeps questions read-only when the Node has blocked the task", () => {
    const presentation = operatorQuestionPresentation("blocked", "sandbox", true);

    expect(presentation.title).toBe("This task is blocked");
    expect(presentation.state).toContain("cannot reopen or change");
    expect(presentation.continuation).toContain("new Node projection");
    expect(presentation.action).toContain("No response control");
  });

  it("blocks a response presentation while the event stream is not current", () => {
    const presentation = operatorQuestionPresentation("running", "verification", false);

    expect(presentation.state).toContain("not current");
    expect(presentation.action).toContain("No response control");
  });

  it("keeps the live announcement bounded to the decision state", () => {
    const presentation = operatorQuestionPresentation("needs_review", "approval", true);

    expect(operatorQuestionAnnouncement(presentation)).toBe("The Node is waiting for an authorized response");
    expect(operatorQuestionAnnouncement(presentation)).not.toContain("typed, sequence-aware command");
  });
});
