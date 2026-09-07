import { describe, expect, it } from "vitest";
import { operatorQuestionPresentation } from "./operatorQuestion";

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

  it("blocks a response presentation while the event stream is not current", () => {
    const presentation = operatorQuestionPresentation("running", "verification", false);

    expect(presentation.state).toContain("not current");
    expect(presentation.action).toContain("No response control");
  });
});
