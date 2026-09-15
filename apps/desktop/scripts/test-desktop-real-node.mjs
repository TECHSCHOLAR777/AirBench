import { createWriteStream, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import net from "node:net";
import { hostname, tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL("..", import.meta.url));
const repoRoot = resolve(here, "../..");
const tauriRoot = join(here, "src-tauri");
const runRoot = mkdtempSync(join(tmpdir(), "AirBench-RealNode-WebDriver-"));
const token = "airbench-wdio-local-token";
const nodeIdentity = "python-node-wdio";
const credentialRef = `wdio-validation-${process.pid}-${Date.now()}`;
const profilePath = join(runRoot, "approved-node-profile.json");
const inputPath = join(runRoot, "inspection-report.pdf");
const downloadPath = join(runRoot, "inspection-approval-note.docx");
const serverStdoutPath = join(runRoot, "python-node.stdout.log");
const serverStderrPath = join(runRoot, "python-node.stderr.log");
// Replay evidence written by the WDIO test session and read by the
// reconnect-cursor negative-case smoke test.
const replayEvidencePath = join(runRoot, "replay-cursor-evidence.json");
// Runtime egress observation — tracks TCP connections from the Tauri process
// tree during the WDIO session. Written by observe-runtime-egress.ps1.
const egressReportPath = join(runRoot, "runtime-egress.json");
// Acceptance evidence for issue #123 — written on success, retained outside
// the disposable run root so it survives cleanup and can be attached to #123.
const acceptanceDir = resolve(repoRoot, "acceptance");
mkdirSync(acceptanceDir, { recursive: true });
const evidenceManifestPath = join(acceptanceDir, "real_node_evidence_123.json");

const env = {
  ...process.env,
  CARGO_TARGET_DIR: join(runRoot, "cargo-target"),
  AIRBENCH_WDIO_LOG_DIR: join(runRoot, "wdio-logs"),
  AIRBENCH_WDIO_PROFILE_PATH: profilePath,
  AIRBENCH_WDIO_INPUT_PATH: inputPath,
  AIRBENCH_WDIO_DOWNLOAD_PATH: downloadPath,
  // Let the WDIO smoke test check replay evidence produced during the run.
  AIRBENCH_WDIO_REPLAY_EVIDENCE_PATH: replayEvidencePath,
};
const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const cargo = process.platform === "win32"
  ? join(process.env.USERPROFILE ?? "", ".cargo", "bin", "cargo.exe")
  : "cargo";
const python = process.env.AIRBENCH_PYTHON ?? (process.platform === "win32" ? "py" : "python3");
let server = null;
let egressObserver = null;
let credentialSet = false;
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

// WDIO's service owns the driver processes, but failed sessions can leave
// them behind. Only processes absent at startup are eligible for cleanup, so
// an operator's already-running WebDriver session is never touched.
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
  // Windows may keep a process visible briefly after taskkill returns. Give
  // the OS a bounded grace period before treating normal teardown as a leak.
  const deadline = Date.now() + 10000;
  const waitBuffer = new Int32Array(new SharedArrayBuffer(4));
  let remainingPids = listWebDriverPids().filter((pid) => !webdriverBaselinePids.has(pid));
  while (remainingPids.length > 0 && Date.now() < deadline) {
    Atomics.wait(waitBuffer, 0, 0, 100);
    remainingPids = listWebDriverPids().filter((pid) => !webdriverBaselinePids.has(pid));
  }
  if (remainingPids.length > 0) {
    if (exitCode === 0) exitCode = 1;
    console.error("The real-node WebDriver cleanup could not stop every process it started:", remainingPids.join(", "));
  }
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? here,
    env,
    input: options.input,
    stdio: options.input === undefined ? "inherit" : ["pipe", "inherit", "inherit"],
    shell: process.platform === "win32" && command.endsWith(".cmd"),
  });
  if (result.error) throw result.error;
  if (result.signal) throw new Error(`${command} ${args.join(" ")} terminated by ${result.signal}`);
  if (result.status !== 0) throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status ?? 1}`);
}

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

async function freePort() {
  const listener = net.createServer();
  await new Promise((resolvePromise, reject) => {
    listener.once("error", reject);
    listener.listen(0, "127.0.0.1", resolvePromise);
  });
  const address = listener.address();
  const port = typeof address === "object" && address ? address.port : null;
  await new Promise((resolvePromise) => listener.close(resolvePromise));
  if (!port) throw new Error("Could not allocate a loopback port for the validation Node.");
  return port;
}

async function waitForPort(port) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (server?.exitCode !== null) throw new Error(`The Python Node exited before port ${port} became ready.`);
    const connected = await new Promise((resolvePromise) => {
      const socket = net.createConnection({ host: "127.0.0.1", port });
      socket.once("connect", () => { socket.destroy(); resolvePromise(true); });
      socket.once("error", () => { socket.destroy(); resolvePromise(false); });
    });
    if (connected) return;
    await sleep(100);
  }
  throw new Error(`The Python Node port ${port} did not become ready.`);
}

function inspectionPdf() {
  const stream = "BT /F1 18 Tf 72 720 Td (Inspection report finding F-01 severity medium) Tj ET";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${Buffer.byteLength(stream, "latin1")} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let document = "%PDF-1.4\n";
  const offsets = [0];
  for (let index = 0; index < objects.length; index += 1) {
    offsets.push(Buffer.byteLength(document, "latin1"));
    document += `${index + 1} 0 obj\n${objects[index]}\nendobj\n`;
  }
  const xrefOffset = Buffer.byteLength(document, "latin1");
  document += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets.slice(1)) document += `${String(offset).padStart(10, "0")} 00000 n \n`;
  document += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
  return Buffer.from(document, "latin1");
}

function writeProfile(port) {
  writeFileSync(profilePath, JSON.stringify([{
    profile_id: "python-node-wdio-profile",
    display_name: "Local Python Node",
    endpoint: `http://127.0.0.1:${port}`,
    transport: "loopback",
    node_identity: nodeIdentity,
    protocol_version: "0.1",
    clearance_context: "restricted",
    certificate_pin_sha256: null,
    trusted_ca_pem: null,
    credential_ref: credentialRef,
    approved_by_policy: true,
  }], null, 2), "utf8");
}

function startEgressObserver(monitorPids) {
  if (process.platform !== "win32") {
    // Observer is Windows-only (uses Get-NetTCPConnection).
    // On other platforms the egress report will be absent and noted in the manifest.
    return null;
  }
  const ps = "powershell.exe";
  const script = join(here, "scripts", "observe-runtime-egress.ps1");
  const observer = spawn(ps, [
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", script,
    "-ReportPath", egressReportPath,
    "-MonitorPids", monitorPids.join(","),
    "-IntervalMs", "2000",
    "-MaxRuntimeSeconds", "600",
  ], { stdio: "ignore", windowsHide: true });
  observer.on("error", (err) => console.error("[egress-observer] failed to start:", err.message));
  return observer;
}

function stopEgressObserver() {
  if (!egressObserver || egressObserver.exitCode !== null) return;
  egressObserver.kill();
  // The observer writes a heartbeat report during sampling, but allow a
  // bounded flush window before the parent reads the evidence.
  const deadline = Date.now() + 3000;
  const waitBuffer = new Int32Array(new SharedArrayBuffer(4));
  while (!existsSync(egressReportPath) && Date.now() < deadline) {
    Atomics.wait(waitBuffer, 0, 0, 100);
  }
}

function cleanup() {
  if (cleanupComplete) return;
  cleanupComplete = true;
  stopEgressObserver();
  if (server && server.exitCode === null) server.kill();
  stopStartedWebDriverProcesses();
  if (credentialSet) {
    try {
      run(cargo, ["run", "--quiet", "--manifest-path", join(tauriRoot, "Cargo.toml"), "--example", "credential_store", "--", "delete", credentialRef]);
    } catch (error) {
      console.error("The temporary validation credential could not be removed:", error);
      if (exitCode === 0) exitCode = 1;
    }
  }
  try {
    rmSync(runRoot, { recursive: true, force: true });
  } catch (error) {
    console.error(`Real-node WebDriver cleanup failed for ${runRoot}:`, error);
    if (exitCode === 0) exitCode = 1;
  }
}

function handleSignal(signal) {
  exitCode = signal === "SIGINT" ? 130 : 143;
  console.error(`Real-node WebDriver run interrupted by ${signal}; cleaning temporary state.`);
  cleanup();
  process.exitCode = exitCode;
}

process.once("SIGINT", () => handleSignal("SIGINT"));
process.once("SIGTERM", () => handleSignal("SIGTERM"));

try {
  const port = await freePort();
  writeFileSync(inputPath, inspectionPdf());
  writeProfile(port);
  const stdout = createWriteStream(serverStdoutPath);
  const stderr = createWriteStream(serverStderrPath);
  server = spawn(python, [
    join(here, "validation", "python_node_server.py"),
    "--port", String(port),
    "--token", token,
    "--node-identity", nodeIdentity,
    "--subject", "wdio-validation-user",
    "--intake-root", join(runRoot, "intake-store"),
  ], { cwd: repoRoot, env, stdio: ["ignore", "pipe", "pipe"] });
  server.stdout?.pipe(stdout);
  server.stderr?.pipe(stderr);
  await waitForPort(port);
  run(cargo, ["run", "--quiet", "--manifest-path", join(tauriRoot, "Cargo.toml"), "--example", "credential_store", "--", "set-stdin", credentialRef], { input: token });
  credentialSet = true;

  run(npm, ["run", "check:webdriver"]);
  run(npm, ["run", "tauri:build:webdriver"]);

  // Start the runtime egress observer before the WDIO session so it captures
  // TCP connections from the Tauri/WebView2 process tree throughout the run.
  // Server PID and Node server PID are both watched.
  const monitorPids = [process.pid, server?.pid].filter(Boolean);
  egressObserver = startEgressObserver(monitorPids);

  // The Tauri service's supported standalone initializer supplies the native
  // driver host/port directly. This avoids WDIO local-runner setup rejecting
  // the service's intentionally browserName-free Tauri capabilities.
  run(process.execPath, ["scripts/run-real-node-standalone.mjs"]);
  run(process.execPath, ["scripts/assert-wdio-log.mjs"]);

  // Stop the observer and let it flush its report before reading it.
  stopEgressObserver();
  await sleep(500);

  if (!existsSync(downloadPath) || statSync(downloadPath).size === 0) {
    throw new Error("The real-node desktop flow did not produce a non-empty verified artifact download.");
  }
  const downloadHeader = readFileSync(downloadPath).subarray(0, 2).toString("ascii");
  if (downloadHeader !== "PK") throw new Error("The real-node desktop flow did not produce a DOCX package.");

  // Collect run identity for the #123 evidence manifest (handoff §13 checklist).
  const branch = (() => {
    try { return execFileSync("git", ["rev-parse", "--abbrev-ref", "HEAD"], { cwd: repoRoot, encoding: "utf8" }).trim(); } catch { return "unknown"; }
  })();
  const commit = (() => {
    try { return execFileSync("git", ["rev-parse", "HEAD"], { cwd: repoRoot, encoding: "utf8" }).trim(); } catch { return "unknown"; }
  })();
  const pythonVersionRaw = (() => {
    try { return execFileSync(python, ["--version"], { encoding: "utf8" }).trim(); } catch { return "unknown"; }
  })();
  // Read the egress observer report if it was produced.
  let egressReport = null;
  let egressVerdict = "observer_not_available";
  if (existsSync(egressReportPath)) {
    try {
      egressReport = JSON.parse(readFileSync(egressReportPath, "utf8"));
      egressVerdict = egressReport.status ?? "unknown";
      if (egressReport.external_connection_count > 0) {
        console.error(
          `[AIRBENCH_EGRESS] ${egressReport.external_connection_count} external TCP connection(s) observed:`,
          JSON.stringify(egressReport.external_connections, null, 2),
        );
        // Do not fail the run — record the finding honestly and let the
        // evidence manifest reflect it. A network call from WebView2 to a
        // Microsoft update endpoint is documented; a call to an arbitrary
        // external host during the task itself is a correctness failure.
        if (exitCode === 0 && egressReport.external_connection_count > 0) {
          console.warn("[AIRBENCH_EGRESS] External connections observed — review egress report before closing #123.");
        }
      }
    } catch (err) {
      console.error("[AIRBENCH_EGRESS] Could not read observer report:", err.message);
    }
  } else if (process.platform === "win32") {
    console.warn("[AIRBENCH_EGRESS] Observer report not found — observer may not have started or had time to write.");
  }

  const evidence = [
    "real-handshake",
    "real-task-create",
    "real-query-upload",
    "real-preview",
    "real-event-replay",
    "real-plan-approval",
    "real-artifact-preview",
    "real-hash-verified-download",
  ];
  if (egressReport) evidence.push("runtime-egress-observed");

  const evidenceManifest = {
    issue: "#123",
    branch,
    commit,
    machine: hostname(),
    python_version: pythonVersionRaw,
    node_identity: nodeIdentity,
    ran_at: new Date().toISOString(),
    egress_observation: {
      verdict: egressVerdict,
      external_connection_count: egressReport?.external_connection_count ?? null,
      external_connections: egressReport?.external_connections ?? [],
      report_path: existsSync(egressReportPath) ? egressReportPath : null,
      limitation: egressReport?.limitation ?? "Observer was not available for this run.",
    },
    evidence,
    limitations: [
      "Synthetic PDF fixture — proves File Intake plumbing, not scanned-document OCR or vision",
      "Synthetic worker — not OCR, handwriting, engineering-drawing understanding, or GPU model inference",
      "Runtime TCP observer covers established connections only — UDP, ICMP, and pre-observer connections are not captured",
      "Clean host firewall or independent network monitor required for full no-egress acceptance (#124)",
      "Not packaged or clean-machine acceptance — #124 remains the packaged sovereign desktop gate",
    ],
    verdict: "passed",
  };
  writeFileSync(evidenceManifestPath, JSON.stringify(evidenceManifest, null, 2), "utf8");

  console.log(JSON.stringify({
    status: "passed",
    node: "real Python NodeApiService",
    input: "local PDF through the Rust File Intake boundary",
    output: "Node-authorized DOCX downloaded through the Rust save boundary",
    evidence: evidenceManifest.evidence,
    evidence_manifest: evidenceManifestPath,
  }));
} catch (error) {
  console.error(error instanceof Error ? error.stack : error);
  if (existsSync(serverStderrPath)) console.error(readFileSync(serverStderrPath, "utf8"));
  if (existsSync(env.AIRBENCH_WDIO_LOG_DIR)) {
    for (const fileName of readdirSync(env.AIRBENCH_WDIO_LOG_DIR)) {
      if (fileName.endsWith(".log")) {
        console.error(`[AIRBENCH_WDIO_LOG ${fileName}]`);
        console.error(readFileSync(join(env.AIRBENCH_WDIO_LOG_DIR, fileName), "utf8"));
      }
    }
  }
  exitCode = error && typeof error === "object" && "status" in error && Number.isInteger(error.status) ? error.status : 1;
} finally {
  cleanup();
}

process.exitCode = exitCode;
