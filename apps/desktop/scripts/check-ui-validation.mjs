import { readFile, readdir, stat } from "node:fs/promises";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = fileURLToPath(new URL(".", import.meta.url));
const frontendRoot = join(scriptDirectory, "..");
const sourceRoot = join(frontendRoot, "src");
const baselinePath = join(frontendRoot, "validation", "ui-baseline.json");
const indexPath = join(frontendRoot, "index.html");
const stylesPath = join(sourceRoot, "app", "styles.css");
const distRoot = join(frontendRoot, "dist");

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(path));
    else files.push(path);
  }
  return files;
}

async function readIfFile(path) {
  try {
    if (!(await stat(path)).isFile()) return null;
    return await readFile(path, "utf8");
  } catch {
    return null;
  }
}

const baseline = JSON.parse(await readFile(baselinePath, "utf8"));
const sourceFiles = (await walk(sourceRoot)).filter((path) => /\.(css|ts|tsx)$/.test(path));
const sourceEntries = await Promise.all(sourceFiles.map(async (path) => [path, await readFile(path, "utf8")]));
const sourceText = sourceEntries.map(([, contents]) => contents).join("\n");
const styles = await readFile(stylesPath, "utf8");
const index = await readFile(indexPath, "utf8");
const failures = [];

for (const theme of baseline.themes) {
  const selector = `.app-shell[data-theme="${theme}"]`;
  if (!styles.includes(selector)) failures.push(`Missing declared theme selector: ${selector}`);
}

for (const contract of baseline.requiredCssContracts) {
  if (!styles.includes(contract)) failures.push(`Missing CSS accessibility or policy contract: ${contract}`);
}

for (const contract of baseline.requiredLocalResourceContracts) {
  const tauriConfig = await readFile(join(frontendRoot, "src-tauri", "tauri.conf.json"), "utf8");
  if (!tauriConfig.includes(contract)) failures.push(`Missing local-resource policy contract: ${contract}`);
}

for (const surface of baseline.surfaces) {
  for (const marker of surface.markers) {
    if (!sourceText.includes(marker)) failures.push(`Surface ${surface.id} is missing marker: ${marker}`);
  }
}

const authoredFiles = sourceEntries.filter(([path]) => !/\.test\.(ts|tsx)$/.test(path) && !path.includes(`${join("src", "generated")}`));
const forbiddenRuntimePatterns = [
  /\bfetch\s*\(/,
  /\bWebSocket\s*\(/,
  /\bXMLHttpRequest\b/,
  /\bEventSource\s*\(/,
  /\bnavigator\.sendBeacon\s*\(/,
  /https?:\/\//,
  /wss?:\/\//,
];
for (const [path, contents] of authoredFiles) {
  for (const pattern of forbiddenRuntimePatterns) {
    if (pattern.test(contents)) failures.push(`Authored frontend egress surface in ${relative(frontendRoot, path)}: ${pattern}`);
  }
}

const localResourcePatterns = [
  /<[^>]+(?:src|href)=["'](?:https?:|\/\/)/i,
  /@import\s+(?:url\()?\s*["']?(?:https?:|\/\/)/i,
  /url\(\s*["']?(?:https?:|\/\/)/i,
];
for (const [path, contents] of [[indexPath, index], [stylesPath, styles]]) {
  for (const pattern of localResourcePatterns) {
    if (pattern.test(contents)) failures.push(`External resource reference in ${relative(frontendRoot, path)}: ${pattern}`);
  }
}

const builtFiles = await readIfFile(join(distRoot, "index.html"));
if (builtFiles !== null) {
  for (const pattern of localResourcePatterns) {
    if (pattern.test(builtFiles)) failures.push(`External resource reference in built index.html: ${pattern}`);
  }
  for (const path of (await walk(join(distRoot, "assets"))).filter((candidate) => /\.(css|html)$/.test(candidate))) {
    const contents = await readFile(path, "utf8");
    for (const pattern of localResourcePatterns.slice(1)) {
      if (pattern.test(contents)) failures.push(`External resource reference in built asset ${relative(frontendRoot, path)}: ${pattern}`);
    }
  }
}

if (failures.length > 0) {
  console.error("AirBench frontend validation preflight failed:");
  console.error(failures.join("\n"));
  process.exit(1);
}

console.log(`AirBench frontend validation preflight passed: ${baseline.surfaces.length} semantic surfaces, ${baseline.themes.length} themes, local-resource checks, and authored-source egress checks.`);
