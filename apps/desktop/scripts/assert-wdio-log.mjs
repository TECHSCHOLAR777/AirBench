import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const logDir = process.env.AIRBENCH_WDIO_LOG_DIR
  ? path.resolve(process.env.AIRBENCH_WDIO_LOG_DIR)
  : path.resolve(here, "../logs");
const marker = "frontend log capture marker";

let entries;
try {
  entries = await readdir(logDir, { withFileTypes: true });
} catch (error) {
  if (error?.code === "ENOENT") {
    throw new Error(`No WebDriver log directory was created at ${logDir}`);
  }
  throw error;
}

const candidates = entries
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

const captured = await Promise.all(files.map(async ({ file }) => ({
  file,
  content: await readFile(file, "utf8"),
})));
const matching = captured.find(({ content }) => content.includes(marker));
if (!matching) {
  throw new Error(`WebDriver log marker was not captured in ${logDir}`);
}

console.log(`WebDriver frontend log capture verified in ${matching.file}`);
