import { browser, expect } from "@wdio/globals";

describe("AirBench desktop with the real local Python Node", () => {
  it("completes task creation, intake, approval, trace, preview, and download", async () => {
    await expect(browser.$('[data-testid="task-composer"]')).toBeDisplayed();
    await browser.tauri.execute(() => console.info("[AIRBENCH_WDIO] frontend log capture marker"));

    await browser.$('[data-testid="node-chip"]').click();
    await browser.$("button*=Reload").click();
    await expect(browser.$(".profile-card")).toBeDisplayed();
    await browser.$(".profile-card button").click();
    await expect(browser.$('[data-testid="node-readiness-panel"]')).toHaveText(expect.stringContaining("Approved Node connection verified"));

    await browser.$(".new-task-button").click();
    await browser.$('[aria-label="Task outcome"]').setValue("Review the uploaded inspection report and draft an approval note with the finding and required action.");
    await browser.$('[data-testid="attach-files"]').click();
    await expect(browser.$(".selected-file")).toHaveText(expect.stringContaining("inspection-report.pdf"));
    await browser.$('[data-testid="start-task"]').click();

    try {
      await browser.$('[data-testid="task-workspace"]').waitForDisplayed({ timeout: 30000 });
    } catch (error) {
      console.info("[AIRBENCH_WDIO_REAL_NODE_FAILURE_STATE]", await browser.$("body").getText());
      throw error;
    }
    await expect(browser.$('[data-testid="task-workspace"]')).toHaveText(expect.stringContaining("SERIAL VIRTUAL TEAM"));
    await expect(browser.$('[data-testid="plan-review"]')).toBeDisplayed();
    await expect(browser.$('[data-testid="plan-review"]')).toHaveText(expect.stringContaining("SERIAL VIRTUAL TEAM"));

    await browser.$('[data-testid="approve-plan"]').click();
    await expect(browser.$('[aria-label="Plan approval result"]')).toBeDisplayed();
    await browser.$(".worktrace-artifact-list").waitForDisplayed({ timeout: 30000 });
    await expect(browser.$(".worktrace-artifact-list")).toHaveText(expect.stringContaining("READY"));

    await browser.$(".worktrace-artifact-list .proof-record-button").click();
    await expect(browser.$('[aria-label="Node-generated artifact preview"]')).toHaveText(expect.stringContaining("AirBench local validation review note"));
    await expect(browser.$('[aria-label="Node artifact review"]')).toHaveText(expect.stringContaining("Needs Review"));
    await expect(browser.$('[aria-label="Node artifact review"]')).toHaveText(expect.stringContaining("visual artifact check is not passed"));
    await browser.$(".proof-artifact-preview .compact-button").click();
    await expect(browser.$(".proof-artifact-actions")).toHaveText(expect.stringContaining("Ledger"));
  });
});
