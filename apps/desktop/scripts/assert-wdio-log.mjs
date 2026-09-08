import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const logDir = path.resolve(here, "../logs");
const marker = "frontend log capture marker";

const candidates = (await readdir(logDir, { withFileTypes: true }))
  .filter((entry) => entry.isFile() && entry.name.endsWith(".log"))
  .map(async (entry) => {
    const file = path.join(logDir, entry.name);
    return { file, modifiedAt: (await stat(file)).mtimeMs };
  });

const files = await Promise.all(candidates);
files.sort((left, right) => right.modifiedAt - left.modifiedAt);

if (files.length === 0) {
  throw new Error(`No WebDriver log was captured in ${logDir}`);
}

const latest = files[0].file;
const content = await readFile(latest, "utf8");
if (!content.includes(marker)) {
  throw new Error(`WebDriver log marker was not captured in ${latest}`);
}

console.log(`WebDriver frontend log capture verified in ${latest}`);
