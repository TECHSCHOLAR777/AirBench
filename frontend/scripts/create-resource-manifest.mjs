import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const distRoot = fileURLToPath(new URL("../dist/", import.meta.url));
const manifestName = "resource-manifest.json";
const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(path));
    else if (entry.name !== manifestName) files.push(path);
  }
  return files;
}

const files = [];
for (const file of await walk(distRoot)) {
  const contents = await readFile(file);
  files.push({
    path: relative(distRoot, file).replaceAll("\\", "/"),
    bytes: contents.byteLength,
    sha256: createHash("sha256").update(contents).digest("hex"),
  });
}

files.sort((left, right) => left.path.localeCompare(right.path));
const manifest = {
  manifestVersion: "1",
  application: "AirBench",
  applicationVersion: packageJson.version,
  generatedBy: "frontend/scripts/create-resource-manifest.mjs",
  assetCount: files.length,
  totalBytes: files.reduce((total, file) => total + file.bytes, 0),
  files,
};
await writeFile(join(distRoot, manifestName), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(`Wrote ${manifestName} with ${files.length} local assets.`);
