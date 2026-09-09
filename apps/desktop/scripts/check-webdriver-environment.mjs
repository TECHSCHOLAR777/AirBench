import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";

const provider = process.env.AIRBENCH_WDIO_DRIVER || (process.platform === "win32" ? "external" : "embedded");
const allowDownloads = process.env.AIRBENCH_ALLOW_DRIVER_DOWNLOAD === "1";

if (!new Set(["embedded", "external"]).has(provider)) {
  console.error(`Invalid AIRBENCH_WDIO_DRIVER: ${provider}. Use embedded or external.`);
  process.exit(1);
}

if (allowDownloads) {
  console.warn("WebDriver preflight: driver download/install fallback is explicitly enabled for this run.");
  process.exit(0);
}

if (provider === "embedded") {
  console.log("WebDriver preflight passed: embedded provider selected and no external driver is required.");
  process.exit(0);
}

const missing = [];
if (!resolveExecutable(process.env.TAURI_DRIVER_PATH, "tauri-driver")) missing.push("tauri-driver");
if (process.platform === "win32" && !resolveExecutable(undefined, "msedgedriver.exe")) missing.push("msedgedriver.exe");

if (missing.length > 0) {
  console.error(`WebDriver preflight failed: ${missing.join(" and ")} ${missing.length === 1 ? "is" : "are"} not available locally.`);
  console.error("Install matching drivers on the test host, set TAURI_DRIVER_PATH when needed, then rerun.");
  console.error("For a deliberately connected setup only, set AIRBENCH_ALLOW_DRIVER_DOWNLOAD=1 for this command.");
  process.exit(1);
}

console.log("WebDriver preflight passed: external Tauri and native drivers are available locally; no download is permitted.");

function resolveExecutable(explicitPath, command) {
  if (explicitPath) return existsSync(explicitPath);
  try {
    const lookup = process.platform === "win32" ? "where.exe" : "which";
    execFileSync(lookup, [command], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}
