import { readFile } from "node:fs/promises";

const config = JSON.parse(await readFile(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8"));
const failures = [];
const windows = config.bundle?.windows;
const csp = config.app?.security?.csp ?? "";

if (windows?.webviewInstallMode?.type !== "offlineInstaller") {
  failures.push("Windows WebView2 mode must be offlineInstaller.");
}
if (config.bundle?.createUpdaterArtifacts) failures.push("Updater artifacts must remain disabled for FE-VAL-1.");
if (!String(csp).includes("connect-src 'none'")) failures.push("FE-VAL-1 CSP must deny all connections before the Node transport is implemented.");
if (!String(csp).includes("default-src 'self'")) failures.push("CSP must have a self-only default source.");
if (config.build?.devUrl !== "http://127.0.0.1:1420") failures.push("Development URL must remain loopback-only.");

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}

console.log("Tauri FE-VAL-1 configuration checks passed.");
