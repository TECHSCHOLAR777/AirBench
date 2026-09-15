import { existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { startWdioSession } from "@wdio/tauri-service";

const here = fileURLToPath(new URL("..", import.meta.url));
const tauriRoot = join(here, "src-tauri");
const cargoTargetDir = process.env.CARGO_TARGET_DIR ?? join(tauriRoot, "target");
const appBinaryPath = join(cargoTargetDir, "debug", "airbench-desktop.exe");
const driverProvider = process.env.AIRBENCH_WDIO_DRIVER === "embedded" ? "embedded" : "external";
const tauriDriverPath = process.env.TAURI_DRIVER_PATH;
const allowDriverDownloads = process.env.AIRBENCH_ALLOW_DRIVER_DOWNLOAD === "1";
let exitCode = 0;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function displayed(browser, selector) {
  const element = await browser.$(selector);
  await element.waitForDisplayed({ timeout: 30000 });
  assert(await element.isDisplayed(), `Expected ${selector} to be displayed.`);
}

async function contains(browser, selector, expected) {
  const element = await browser.$(selector);
  await element.waitUntil(async () => (await element.getText()).includes(expected), {
    timeout: 30000,
    interval: 250,
    timeoutMsg: `Expected ${selector} to contain ${JSON.stringify(expected)} within 30 seconds.`,
  });
  const text = await element.getText();
  assert(text.includes(expected), `Expected ${selector} to contain ${JSON.stringify(expected)}, got ${JSON.stringify(text)}.`);
}

async function closeBrowserSession(browser) {
  if (!browser) return;
  try {
    await browser.deleteSession();
  } catch (error) {
    console.warn("WebDriver session deletion did not complete; the parent runner will reap its test processes.", error);
  }
}

let browser;
try {
  assert(existsSync(appBinaryPath), `The WebDriver application binary does not exist: ${appBinaryPath}`);
  const serviceOptions = {
    driverProvider,
    appBinaryPath,
    autoInstallTauriDriver: allowDriverDownloads,
    autoDownloadEdgeDriver: allowDriverDownloads,
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

  browser = await startWdioSession(capabilities, {
    rootDir: here,
    autoInstallTauriDriver: allowDriverDownloads,
    autoDownloadEdgeDriver: allowDriverDownloads,
  });
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
} catch (error) {
  console.error(error instanceof Error ? error.stack : error);
  exitCode = 1;
} finally {
  await closeBrowserSession(browser);
  // @wdio/tauri-service's standalone lifecycle teardown can remain pending on
  // Windows after deleteSession has completed. The parent runner owns the
  // driver processes and reaps them after this child exits.
  process.exit(exitCode);
}
