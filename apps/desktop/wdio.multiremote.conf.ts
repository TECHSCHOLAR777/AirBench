import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Config } from "@wdio/types";

const here = path.dirname(fileURLToPath(import.meta.url));
const appBinaryPath = path.join(here, "src-tauri", "target", "debug", "airbench-desktop.exe");
const requestedDriverProvider = process.env.AIRBENCH_WDIO_DRIVER;
const driverProvider = requestedDriverProvider === "embedded" || requestedDriverProvider === "external"
  ? requestedDriverProvider
  : process.platform === "win32"
    ? "external"
    : "embedded";
const tauriDriverPath = process.env.TAURI_DRIVER_PATH;
const allowDriverDownloads = process.env.AIRBENCH_ALLOW_DRIVER_DOWNLOAD === "1";
const options = {
  application: appBinaryPath,
  driverProvider: driverProvider as "embedded" | "external",
  ...(driverProvider === "external" && tauriDriverPath ? { tauriDriverPath } : {}),
  windowLabel: "main"
};

export const config: Config = {
  runner: "local",
  specs: ["./tests/desktop/multiremote.smoke.ts"],
  maxInstances: 1,
  logLevel: "warn",
  framework: "mocha",
  reporters: [["spec", { addConsoleLogs: true }]],
  services: [["tauri", {
    appBinaryPath,
    driverProvider,
    autoInstallTauriDriver: allowDriverDownloads,
    ...(process.platform === "win32" ? { autoDownloadEdgeDriver: allowDriverDownloads } : {}),
    ...(driverProvider === "external" && tauriDriverPath ? { tauriDriverPath } : {}),
    captureBackendLogs: true,
    captureFrontendLogs: true,
    logDir: path.join(here, "artifacts", "webdriver-multiremote")
  }]],
  capabilities: {
    operatorA: { capabilities: { browserName: "tauri", "tauri:options": options } },
    operatorB: { capabilities: { browserName: "tauri", "tauri:options": options } }
  },
  mochaOpts: { timeout: 45000, require: [] }
};
