import { readdirSync, rmSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_MAX_AGE_HOURS = 24;
const RUN_PREFIXES = [
  "airbench-",
  "AirBenchValidation-",
  "AirBenchCargo",
  "AirBenchNodeValidation-",
  "AirBenchPythonNodeValidation-",
  "AirBenchRustCheck-",
  "AirBench-WebDriver-",
];

function isRunArtifact(name) {
  return RUN_PREFIXES.some((prefix) => name.toLowerCase().startsWith(prefix.toLowerCase()));
}

function parseMaxAgeHours(argv) {
  const option = argv.find((argument) => argument.startsWith("--max-age-hours="));
  if (!option) return DEFAULT_MAX_AGE_HOURS;
  const value = Number(option.slice("--max-age-hours=".length));
  if (!Number.isFinite(value) || value < 1) {
    throw new Error("--max-age-hours must be a number greater than or equal to 1");
  }
  return value;
}

export function findStaleRuns({ root = tmpdir(), maxAgeHours = DEFAULT_MAX_AGE_HOURS, now = Date.now() } = {}) {
  const cutoff = now - maxAgeHours * 60 * 60 * 1000;
  return readdirSync(root, { withFileTypes: true })
    .filter((entry) => isRunArtifact(entry.name))
    .map((entry) => {
      const fullPath = path.join(root, entry.name);
      return {
        name: entry.name,
        path: fullPath,
        isDirectory: entry.isDirectory(),
        lastWriteTime: statSync(fullPath).mtime,
      };
    })
    .filter((entry) => entry.lastWriteTime.getTime() < cutoff)
    .sort((left, right) => left.lastWriteTime - right.lastWriteTime);
}

export function hasActiveWebDriverProcesses() {
  if (process.platform === "win32") {
    return ["tauri-driver.exe", "msedgedriver.exe"].some((imageName) => {
      const result = spawnSync(
        "tasklist.exe",
        ["/FI", `IMAGENAME eq ${imageName}`, "/FO", "CSV", "/NH"],
        { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], windowsHide: true },
      );
      return result.status === 0 && new RegExp(`"${imageName}"`, "i").test(result.stdout ?? "");
    });
  }

  return ["tauri-driver", "msedgedriver"].some(
    (processName) => spawnSync("pgrep", ["-x", processName], { stdio: "ignore" }).status === 0,
  );
}

export function cleanupStaleRuns({ apply = false, root = tmpdir(), maxAgeHours = DEFAULT_MAX_AGE_HOURS } = {}) {
  const candidates = findStaleRuns({ root, maxAgeHours });
  if (!apply) return { candidates, removed: [], blocked: false };
  if (candidates.length > 0 && hasActiveWebDriverProcesses()) {
    return { candidates, removed: [], blocked: true };
  }

  const removed = [];
  for (const candidate of candidates) {
    rmSync(candidate.path, { recursive: true, force: true, maxRetries: 3, retryDelay: 250 });
    removed.push(candidate);
  }
  return { candidates, removed, blocked: false };
}

function main() {
  const argv = process.argv.slice(2);
  const apply = argv.includes("--apply");
  const maxAgeHours = parseMaxAgeHours(argv);
  const result = cleanupStaleRuns({ apply, maxAgeHours });

  if (result.candidates.length === 0) {
    console.log(`No AirBench temporary runs older than ${maxAgeHours} hours were found in ${tmpdir()}.`);
    return;
  }
  if (!apply) {
    console.log("Dry run. The following stale AirBench temporary runs are eligible:");
    for (const candidate of result.candidates) console.log(`- ${candidate.path}`);
    console.log("Re-run with --apply after all AirBench WebDriver processes are closed.");
    return;
  }
  if (result.blocked) throw new Error("Cleanup refused because tauri-driver or msedgedriver is still running.");
  console.log(`Removed ${result.removed.length} stale AirBench temporary run(s).`);
}

const thisFile = path.resolve(fileURLToPath(import.meta.url));
const invokedFile = process.argv[1] ? path.resolve(process.argv[1]) : null;
if (invokedFile === thisFile) main();
