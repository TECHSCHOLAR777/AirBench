/**
 * Hardcoded fixture matching for the showcase assistant.
 *
 * Fixtures live in apps/desktop/public/demo-fixtures/ (see that folder's
 * README) and are fetched at runtime — nothing here is bundled at build
 * time, so drop new files in that folder and reload to pick them up.
 */

export type FixtureKind = "text" | "image";

export interface TextFixture {
  id: string;
  match: string[];
  title: string;
  output_file: string;
  route_label?: string;
}

export interface ImageFixture {
  id: string;
  match_filename: string[];
  title: string;
  output_image?: string;
  output_text?: string;
  route_label?: string;
}

export interface FixtureManifest {
  text_triggers: TextFixture[];
  image_triggers: ImageFixture[];
}

export interface FixtureMatchResult {
  kind: FixtureKind;
  fixture: TextFixture | ImageFixture;
  answerText: string;
  answerImageUrl?: string;
}

const MANIFEST_URL = "/demo-fixtures/manifest.json";
const FIXTURE_ROOT = "/demo-fixtures/";

let cachedManifest: FixtureManifest | null = null;

export async function loadFixtureManifest(): Promise<FixtureManifest> {
  if (cachedManifest) return cachedManifest;
  const response = await fetch(MANIFEST_URL, { cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load fixture manifest (${response.status}).`);
  const manifest = (await response.json()) as FixtureManifest;
  cachedManifest = {
    text_triggers: manifest.text_triggers ?? [],
    image_triggers: manifest.image_triggers ?? [],
  };
  return cachedManifest;
}

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

export function matchTextFixture(manifest: FixtureManifest, promptText: string): TextFixture | null {
  const normalizedPrompt = normalize(promptText);
  if (!normalizedPrompt) return null;
  for (const fixture of manifest.text_triggers) {
    if (fixture.match.some((trigger) => normalizedPrompt.includes(normalize(trigger)))) {
      return fixture;
    }
  }
  return null;
}

export function matchImageFixture(manifest: FixtureManifest, fileName: string): ImageFixture | null {
  const normalizedName = normalize(fileName);
  if (!normalizedName) return null;
  for (const fixture of manifest.image_triggers) {
    if (fixture.match_filename.some((trigger) => normalizedName.includes(normalize(trigger)))) {
      return fixture;
    }
  }
  return null;
}

export async function resolveTextFixtureAnswer(fixture: TextFixture): Promise<string> {
  const response = await fetch(`${FIXTURE_ROOT}${fixture.output_file}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load hardcoded output "${fixture.output_file}" (${response.status}).`);
  return await response.text();
}

export async function resolveImageFixtureAnswer(fixture: ImageFixture): Promise<{ text: string; imageUrl?: string }> {
  let text = "";
  if (fixture.output_text) {
    const response = await fetch(`${FIXTURE_ROOT}${fixture.output_text}`, { cache: "no-store" });
    if (response.ok) text = await response.text();
  }
  const imageUrl = fixture.output_image ? `${FIXTURE_ROOT}${fixture.output_image}` : undefined;
  return { text, imageUrl };
}
