import { readFile, readdir } from "node:fs/promises";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const scriptDirectory = fileURLToPath(new URL(".", import.meta.url));
const frontendRoot = join(scriptDirectory, "..");
const sourceRoot = join(frontendRoot, "src");
const failures = [];

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

function attribute(openingElement, name) {
  return openingElement.attributes.properties.find((property) =>
    ts.isJsxAttribute(property) && property.name.text === name
  );
}

function attributeValue(openingElement, name) {
  const found = attribute(openingElement, name);
  if (!found) return null;
  if (!found.initializer) return "";
  if (ts.isStringLiteral(found.initializer)) return found.initializer.text;
  if (ts.isJsxExpression(found.initializer)) return found.initializer.expression?.getText() ?? "";
  return found.initializer.getText();
}

function hasAccessibleContent(element) {
  if (!ts.isJsxElement(element)) return false;
  return element.children.some((child) => {
    if (ts.isJsxText(child)) return child.text.trim().length > 0;
    if (ts.isJsxExpression(child)) return child.expression !== undefined;
    if (ts.isJsxElement(child)) return hasAccessibleContent(child);
    return false;
  });
}

function hasAccessibleName(openingElement, element, ancestors) {
  if (attributeValue(openingElement, "aria-label") || attributeValue(openingElement, "aria-labelledby")) return true;
  if (hasAccessibleContent(element)) return true;
  return ancestors.some((ancestor) => ts.isJsxElement(ancestor) && ancestor.openingElement.tagName.getText() === "label");
}

function checkElement(element, sourceFile, ancestors) {
  const openingElement = ts.isJsxElement(element) ? element.openingElement : element;
  const tagName = openingElement.tagName.getText(sourceFile);
  const location = sourceFile.getLineAndCharacterOfPosition(openingElement.getStart(sourceFile));
  const where = `${relative(frontendRoot, sourceFile.fileName)}:${location.line + 1}`;

  if (tagName === "button" && attribute(openingElement, "type") === undefined) {
    failures.push(`${where}: button must declare an explicit type`);
  }

  if (["input", "textarea", "select"].includes(tagName) && !hasAccessibleName(openingElement, element, ancestors)) {
    failures.push(`${where}: ${tagName} must have an accessible name`);
  }

  if (attributeValue(openingElement, "role") === "dialog") {
    if (attributeValue(openingElement, "aria-modal") !== "true") failures.push(`${where}: dialog must declare aria-modal="true"`);
    if (!attributeValue(openingElement, "aria-label") && !attributeValue(openingElement, "aria-labelledby")) {
      failures.push(`${where}: dialog must declare aria-label or aria-labelledby`);
    }
  }
}

const files = (await walk(sourceRoot)).filter((path) => path.endsWith(".tsx") && !path.includes(".test."));
for (const path of files) {
  const source = await readFile(path, "utf8");
  const sourceFile = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

  function visit(node, ancestors = []) {
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) checkElement(node, sourceFile, ancestors);
    const nextAncestors = ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node) ? [...ancestors, node] : ancestors;
    ts.forEachChild(node, (child) => visit(child, nextAncestors));
  }

  visit(sourceFile);
}

if (failures.length > 0) {
  console.error("AirBench frontend accessibility contract check failed:");
  console.error(failures.join("\n"));
  process.exit(1);
}

console.log(`AirBench frontend accessibility contract check passed: ${files.length} authored TSX files scanned.`);
