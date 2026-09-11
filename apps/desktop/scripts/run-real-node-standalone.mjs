import { existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanupWdioSession, startWdioSession } from "@wdio/tauri-service";

const here = fileURLToPath(new URL("..", import.meta.url));
const appBinaryPath = join(here, "src-tauri", "target", "debug", "airbench-desktop.exe");
const driverProvider = process.env.AIRBENCH_WDIO_DRIVER === "embedded" ? "embedded" : "external";
const tauriDriverPath = process.env.TAURI_DRIVER_PATH;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function displayed(browser, selector) {
  assert(await browser.$(selector).isDisplayed(), `Expected ${selector} to be displayed.`);
}

async function contains(browser, selector, expected) {
  const text = await browser.$(selector).getText();
  assert(text.includes(expected), `Expected ${selector} to contain ${JSON.stringify(expected)}, got ${JSON.stringify(text)}.`);
}

let browser;
try {
  assert(existsSync(appBinaryPath), `The WebDriver application binary does not exist: ${appBinaryPath}`);
  const serviceOptions = {
    driverProvider,
    appBinaryPath,
    autoInstallTauriDriver: false,
    autoDownloadEdgeDriver: false,
    ...(tauriDriverPath ? { tauriDriverPath } : {}),
    captureBackendLogs: true,
    captureFrontendLogs: true,
    backendLogLevel: "debug",
    frontendLogLevel: "debug",
    logDir: process.env.AIRBENCH_WDIO_LOG_DIR,
  };
  const capabilities = {
    browserName: "tauri",
    "wdio:tauriServiceOptions": serviceOptions,
    "tauri:options": {
      application: appBinaryPath,
      driverProvider,
      windowLabel: "main",
    },
  };

  browser = await startWdioSession(capabilities, { rootDir: here });
  await displayed(browser, '[data-testid="task-composer"]');
  await browser.tauri.execute(() => console.info("[AIRBENCH_WDIO] frontend log capture marker"));

  await browser.$('[data-testid="node-chip"]').click();
  await browser.$("button*=Reload").click();
  await displayed(browser, ".profile-card");
  await browser.$(".profile-card button").click();
  await contains(browser, '[data-testid="node-readiness-panel"]', "Approved Node connection verified");

  await browser.$(".new-task-button").click();
  await browser.$('[aria-label="Task outcome"]').setValue("Review the uploaded inspection report and draft an approval note with the finding and required action.");
  await browser.$('[data-testid="attach-files"]').click();
  await contains(browser, ".selected-file", "inspection-report.pdf");
  await browser.$('[data-testid="start-task"]').click();
  await browser.$('[data-testid="task-workspace"]').waitForDisplayed({ timeout: 30000 });
  await contains(browser, '[data-testid="task-workspace"]', "SERIAL VIRTUAL TEAM");
  await displayed(browser, '[data-testid="plan-review"]');
  await contains(browser, '[data-testid="plan-review"]', "SERIAL VIRTUAL TEAM");

  await browser.$('[data-testid="approve-plan"]').click();
  await displayed(browser, '[aria-label="Plan approval result"]');
  await browser.$(".worktrace-artifact-list").waitForDisplayed({ timeout: 30000 });
  await contains(browser, ".worktrace-artifact-list", "READY");
  await browser.$(".worktrace-artifact-list .proof-record-button").click();
  await contains(browser, '[aria-label="Node-generated artifact preview"]', "AirBench local validation review note");
  await contains(browser, '[aria-label="Node artifact review"]', "Needs Review");
  await contains(browser, '[aria-label="Node artifact review"]', "visual artifact check is not passed");
  await browser.$(".proof-artifact-preview .compact-button").click();
  await contains(browser, ".proof-artifact-actions", "Ledger");

  console.log(JSON.stringify({
    status: "passed",
    session: "standalone @wdio/tauri-service",
    provider: driverProvider,
    evidence: ["real-handshake", "real-task-create", "real-query-upload", "real-plan-approval", "real-artifact-preview"],
  }));
} finally {
  if (browser) await cleanupWdioSession(browser);
}
