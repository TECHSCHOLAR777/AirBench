import { browser, expect } from "@wdio/globals";

describe("AirBench desktop shell", () => {
  it("renders the private-by-design task surface", async () => {
    await expect(browser.$("h1")).toHaveText("What should AirBench complete?");
    await expect(browser.$('[data-testid="task-composer"]')).toBeDisplayed();
    await expect(browser.$('[data-testid="start-task"]')).toBeDisabled();
  });

  it("uses IPC mocking for native file selection", async () => {
    const pickFile = await browser.tauri.mock("pick_query_file");
    await pickFile.mockReturnValue({
      selection_id: "webdriver-selection",
      file_name: "inspection-report.pdf",
      byte_size: 4096
    });

    await browser.$('[data-testid="attach-files"]').click();
    await expect(browser.$(".selected-file")).toHaveText(expect.stringContaining("inspection-report.pdf"));
    await expect(browser.$('[role="status"]')).toHaveText(expect.stringContaining("File selected"));
  });

  it("navigates to trusted Node settings without exposing an endpoint editor", async () => {
    await browser.$('[data-testid="open-node-settings"]').click();
    await expect(browser.$("h1")).toHaveText("Node and settings");
    await expect(browser.$("body")).not.toHaveText(expect.stringContaining("http://"));
    await expect(browser.$("body")).not.toHaveText(expect.stringContaining("https://"));
  });

  it("executes a Tauri-side assertion and captures frontend logs", async () => {
    const location = await browser.tauri.execute(() => window.location.href);
    expect(location).toBeTruthy();
    await browser.tauri.execute(() => console.info("airbench webdriver smoke"));
    const logs = await browser.getLogs("browser");
    expect(logs.some((entry) => entry.message.includes("airbench webdriver smoke"))).toBe(true);
  });
});
