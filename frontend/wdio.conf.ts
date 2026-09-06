import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Config } from "@wdio/types";

const here = path.dirname(fileURLToPath(import.meta.url));
const appBinaryPath = path.join(here, "src-tauri", "target", "debug", "airbench-desktop.exe");
const driverProvider = process.env.AIRBENCH_WDIO_DRIVER === "external" ? "external" : "embedded";
const tauriDriverPath = process.env.TAURI_DRIVER_PATH;

export const config: Config = {
  runner: "local",
  specs: ["./tests/desktop/shell.smoke.ts"],
  maxInstances: 1,
  logLevel: "warn",
  framework: "mocha",
  reporters: [["spec", { addConsoleLogs: true }]],
  services: [
    ["tauri", {
      appBinaryPath,
      driverProvider,
      ...(driverProvider === "external" && tauriDriverPath ? { tauriDriverPath } : {}),
      captureBackendLogs: true,
      captureFrontendLogs: true,
      backendLogLevel: "debug",
      frontendLogLevel: "debug",
      logDir: path.join(here, "artifacts", "webdriver")
    }]
  ],
  capabilities: [{
    browserName: "tauri",
    "tauri:options": {
      application: appBinaryPath,
      driverProvider,
      windowLabel: "main"
    }
  }],
  mochaOpts: {
    timeout: 30000,
    require: []
  }
};
