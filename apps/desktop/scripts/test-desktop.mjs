import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL("..", import.meta.url));
const runRoot = mkdtempSync(join(tmpdir(), "AirBench-WebDriver-"));
const env = {
  ...process.env,
  CARGO_TARGET_DIR: join(runRoot, "cargo-target"),
  AIRBENCH_WDIO_LOG_DIR: join(runRoot, "wdio-logs"),
};
const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const mode = process.argv[2] === "multiremote" ? "multiremote" : "single";
const wdioConfig = mode === "multiremote" ? "wdio.multiremote.conf.ts" : "wdio.conf.ts";
let cleanupComplete = false;
let exitCode = 0;

function listWebDriverPids() {
  const processNames = process.platform === "win32"
    ? ["tauri-driver.exe", "msedgedriver.exe"]
    : ["tauri-driver", "msedgedriver"];
  const pids = [];
  for (const processName of processNames) {
    const result = process.platform === "win32"
      ? spawnSync("tasklist.exe", ["/FI", `IMAGENAME eq ${processName}`, "/FO", "CSV", "/NH"], {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
        windowsHide: true,
      })
      : spawnSync("pgrep", ["-x", processName], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
    if (result.status !== 0) continue;
    if (process.platform === "win32") {
      for (const match of result.stdout.matchAll(/"[^"]+","(\d+)"/g)) pids.push(Number(match[1]));
    } else {
      for (const line of (result.stdout ?? "").split(/\r?\n/)) if (/^\d+$/.test(line)) pids.push(Number(line));
    }
  }
  return [...new Set(pids)];
}

// Do not touch an operator's pre-existing WebDriver session. Only processes
// created after this wrapper starts are eligible for cleanup.
const webdriverBaselinePids = new Set(listWebDriverPids());

function stopStartedWebDriverProcesses() {
  const startedPids = listWebDriverPids().filter((pid) => !webdriverBaselinePids.has(pid));
  for (const pid of startedPids) {
    if (process.platform === "win32") {
      spawnSync("taskkill.exe", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
    } else {
      try { process.kill(pid, "SIGTERM"); } catch { /* process already exited */ }
    }
  }
  if (listWebDriverPids().some((pid) => !webdriverBaselinePids.has(pid))) {
    if (exitCode === 0) exitCode = 1;
    console.error("The WebDriver cleanup could not stop every process started by this run.");
  }
}

function cleanup() {
  if (cleanupComplete) return;
  cleanupComplete = true;
  stopStartedWebDriverProcesses();
  try {
    rmSync(runRoot, { recursive: true, force: true });
  } catch (error) {
    console.error(`WebDriver temporary-run cleanup failed for ${runRoot}:`, error);
    if (exitCode === 0) exitCode = 1;
  }
}

function handleSignal(signal) {
  exitCode = signal === "SIGINT" ? 130 : 143;
  console.error(`WebDriver run interrupted by ${signal}; cleaning ${runRoot}`);
  cleanup();
  process.exitCode = exitCode;
}

process.once("SIGINT", () => handleSignal("SIGINT"));
process.once("SIGTERM", () => handleSignal("SIGTERM"));

function runNpm(args) {
  const result = spawnSync(npm, args, {
    cwd: here,
    env,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.error) throw result.error;
  if (result.signal) {
    const error = new Error(`Command ${npm} ${args.join(" ")} terminated by ${result.signal}`);
    error.exitCode = 1;
    throw error;
  }
  if (result.status !== 0) {
    const error = new Error(`Command ${npm} ${args.join(" ")} failed with exit code ${result.status ?? 1}`);
    error.exitCode = result.status ?? 1;
    throw error;
  }
}

try {
  runNpm(["run", "check:webdriver"]);
  runNpm(["run", "tauri:build:webdriver"]);
  runNpm(["exec", "--", "wdio", "run", wdioConfig]);
  if (mode === "single") {
    const result = spawnSync(process.execPath, ["scripts/assert-wdio-log.mjs"], {
      cwd: here,
      env,
      stdio: "inherit",
    });
    if (result.error) throw result.error;
    if (result.signal) throw new Error(`node scripts/assert-wdio-log.mjs terminated by ${result.signal}`);
    if (result.status !== 0) throw new Error(`node scripts/assert-wdio-log.mjs failed with exit code ${result.status ?? 1}`);
  }
} catch (error) {
  console.error(error instanceof Error ? error.stack : error);
  exitCode = error && typeof error === "object" && "exitCode" in error && Number.isInteger(error.exitCode)
    ? error.exitCode
    : 1;
} finally {
  cleanup();
}

process.exitCode = exitCode;
