/**
 * Staged demo answer for whatever the operator has typed in the composer.
 * Matches against the same hardcoded text fixtures the P&ID demo uses when
 * possible; otherwise falls back to a clearly-labeled generic answer. This
 * never calls a live model — it is a client-only preview shown alongside
 * (not instead of) the real Node task launch.
 */
import type { ProcessPhase } from "../../lib/processTheater";
import { loadFixtureManifest, matchTextFixture, resolveTextFixtureAnswer } from "../showcase_assistant/fixtures";

export function buildPromptPreviewPhases(routedModel: string): ProcessPhase[] {
  return [
    {
      id: "plan",
      label: "Planning",
      logs: [
        "Parsing task intent",
        `Selecting qualified worker: ${routedModel}`,
        "Preparing execution plan",
      ],
    },
    {
      id: "retrieve",
      label: "Retrieval",
      logs: [
        "Searching governed knowledge base",
        "Cross-referencing procedure library",
        "Assembling evidence set",
      ],
    },
    {
      id: "deliver",
      label: "Verification & delivery",
      logs: [
        "Verifying draft against policy",
        "Formatting deliverable",
        "Packaging artifact",
      ],
    },
  ];
}

export async function resolvePromptPreviewAnswer(promptText: string, outputLabel: string): Promise<string> {
  try {
    const manifest = await loadFixtureManifest();
    const fixture = matchTextFixture(manifest, promptText);
    if (fixture) return await resolveTextFixtureAnswer(fixture);
  } catch {
    // Fall through to the generic fallback below if the fixture manifest is unavailable.
  }
  return [
    `**Preview answer (demo)**`,
    "",
    `Based on the description provided, AirBench prepared a ${outputLabel.toLowerCase()} covering the requested outcome.`,
    "",
    `> "${promptText.trim().slice(0, 240)}"`,
    "",
    "_This is a hardcoded preview for demonstration and does not reflect a live model call. Launch the task to have the connected Node produce and verify an authoritative deliverable._",
  ].join("\n");
}
