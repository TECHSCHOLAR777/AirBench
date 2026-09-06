import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const sourceRoot = fileURLToPath(new URL("../src/", import.meta.url));
const forbidden = [
  /\bfetch\s*\(/,
  /\bWebSocket\s*\(/,
  /\bXMLHttpRequest\b/,
  /https?:\/\//,
  /wss?:\/\//,
  /@import\s+url/i,
];

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(path));
    else if (/\.(css|html|ts|tsx)$/.test(entry.name)) files.push(path);
  }
  return files;
}

const violations = [];
for (const file of await walk(sourceRoot)) {
  const contents = await readFile(file, "utf8");
  const patterns = /\.test\.(ts|tsx)$/.test(file)
    ? forbidden.filter((pattern) => pattern.source !== "https?:\\/\\/" && pattern.source !== "wss?:\\/\\/")
    : forbidden;
  for (const pattern of patterns) {
    if (pattern.test(contents)) violations.push(`${file}: ${pattern}`);
  }
}

if (violations.length) {
  console.error("Frontend source contains a forbidden egress surface:");
  console.error(violations.join("\n"));
  process.exit(1);
}

console.log("No network-capable APIs or external resource URLs found in frontend source.");
