import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Config } from "@wdio/types";

const here = path.dirname(fileURLToPath(import.meta.url));
const cargoTargetDir = process.env.CARGO_TARGET_DIR
  ? path.resolve(process.env.CARGO_TARGET_DIR)
  : path.join(here, "src-tauri", "target");
const appBinaryPath = path.join(cargoTargetDir, "debug", "airbench-desktop.exe");
const requestedDriverProvider = process.env.AIRBENCH_WDIO_DRIVER;
const driverProvider = requestedDriverProvider === "embedded" || requestedDriverProvider === "external"
  ? requestedDriverProvider
  : process.platform === "win32"
    ? "external"
    : "embedded";
const tauriDriverPath = process.env.TAURI_DRIVER_PATH;
const allowDriverDownloads = process.env.AIRBENCH_ALLOW_DRIVER_DOWNLOAD === "1";
const logDir = process.env.AIRBENCH_WDIO_LOG_DIR
  ? path.resolve(process.env.AIRBENCH_WDIO_LOG_DIR)
  : path.join(here, "artifacts", "webdriver-real-node");

export const config: Config = {
  runner: "local",
  outputDir: logDir,
  specs: ["./tests/desktop/real-node.smoke.ts"],
  maxInstances: 1,
  logLevel: "warn",
  framework: "mocha",
  reporters: [["spec", { addConsoleLogs: true }]],
  services: [
    ["tauri", {
      appBinaryPath,
      driverProvider,
      autoInstallTauriDriver: allowDriverDownloads,
      ...(process.platform === "win32" ? { autoDownloadEdgeDriver: allowDriverDownloads } : {}),
      ...(driverProvider === "external" && tauriDriverPath ? { tauriDriverPath } : {}),
      captureBackendLogs: true,
      captureFrontendLogs: true,
      backendLogLevel: "debug",
      frontendLogLevel: "debug",
      logDir,
    }],
  ],
  capabilities: [{
    browserName: "tauri",
    "wdio:tauriServiceOptions": {
      captureBackendLogs: true,
      captureFrontendLogs: true,
      backendLogLevel: "debug",
      frontendLogLevel: "debug",
      logDir,
    },
    "tauri:options": {
      application: appBinaryPath,
      driverProvider,
      windowLabel: "main",
    },
  }],
  mochaOpts: {
    timeout: 60000,
    require: [],
  },
};
