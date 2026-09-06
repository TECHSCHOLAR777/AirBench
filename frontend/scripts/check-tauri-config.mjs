import { readFile } from "node:fs/promises";

const config = JSON.parse(await readFile(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8"));
const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
const cargoToml = await readFile(new URL("../src-tauri/Cargo.toml", import.meta.url), "utf8");
const failures = [];
const windows = config.bundle?.windows;
const csp = config.app?.security?.csp ?? "";
const browserArgs = config.app?.windows?.[0]?.additionalBrowserArgs ?? "";
const cargoVersion = cargoToml.match(/^version\s*=\s*"([^"]+)"/m)?.[1];
if (config.version !== packageJson.version) failures.push(`Tauri version ${config.version} does not match package version ${packageJson.version}.`);
if (cargoVersion !== packageJson.version) failures.push(`Cargo version ${cargoVersion ?? "<missing>"} does not match package version ${packageJson.version}.`);
if (config.identifier !== "org.airbench.desktop") failures.push("The desktop identifier must remain the approved AirBench identifier.");
if (!config.bundle?.targets?.includes("nsis")) failures.push("The supported Windows bundle must include the NSIS target.");

if (windows?.webviewInstallMode?.type !== "offlineInstaller") {
  failures.push("Windows WebView2 mode must be offlineInstaller.");
}
if (config.bundle?.createUpdaterArtifacts) failures.push("Updater artifacts must remain disabled for FE-VAL-1.");
if (!String(csp).includes("connect-src 'none'")) failures.push("FE-VAL-1 CSP must deny all connections before the Node transport is implemented.");
if (!String(csp).includes("default-src 'self'")) failures.push("CSP must have a self-only default source.");
if (config.build?.devUrl !== "http://127.0.0.1:1420") failures.push("Development URL must remain loopback-only.");
for (const flag of ["--disable-background-networking", "--disable-component-update", "--disable-domain-reliability", "--disable-sync", "--disable-crash-reporter", "--disable-breakpad", "--disable-quic", "--host-resolver-rules=MAP * 0.0.0.0"]) {
  if (!String(browserArgs).includes(flag)) failures.push(`WebView2 must include the offline startup flag ${flag}.`);
}
for (const flag of ["--proxy-server=127.0.0.1:9", "--proxy-bypass-list=127.0.0.1;localhost;[::1]"]) {
  if (!String(browserArgs).includes(flag)) failures.push(`WebView2 must include the local-only proxy policy ${flag}.`);
}
if (!String(browserArgs).includes("--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection")) {
  failures.push("WebView2 must retain Tauri's default disabled feature set while adding offline flags.");
}
if (config.app?.windows?.[0]?.dataDirectory !== "airbench-webview2") failures.push("The production WebView2 profile must use an AirBench-owned data directory.");
if (config.app?.windows?.[0]?.proxyUrl !== "http://127.0.0.1:9") failures.push("The production WebView2 window must use the non-listening loopback proxy.");

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}

console.log("Tauri FE-VAL-1 configuration checks passed.");
