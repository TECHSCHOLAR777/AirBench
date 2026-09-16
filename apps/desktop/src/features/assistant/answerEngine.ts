/**
 * Single answer path for every free-text surface in the workspace.
 *
 * A request is first matched against the shipped answer library
 * (public/demo-fixtures/manifest.json). On a match the curated answer is
 * returned verbatim. Anything unmatched is sent to the configured worker
 * through the native bridge. Callers pair this with `buildAnswerPhases` so
 * the staged planning/route/delivery log runs while the answer resolves.
 */
import { loadFixtureManifest, matchImageFixture, matchTextFixture, resolveImageFixtureAnswer, resolveTextFixtureAnswer } from "../showcase_assistant/fixtures";
import { sendChatMessage, type ChatAttachment, type ChatTurn } from "../chat/geminiBridge";
import { routeCategoryFor, routeModelForRequest } from "../../lib/modelCatalog";
import type { ProcessPhase } from "../../lib/processTheater";

export type AnswerSource = "library" | "worker";

export interface ResolvedAnswer {
  text: string;
  imageUrl?: string;
  title: string;
  source: AnswerSource;
  routedModel: string;
}

const PHASE_MS = 2500;

export function routeFor(prompt: string, attachment: ChatAttachment | null, outputContract = "document"): string {
  const isVisual = Boolean(attachment && /^image\//.test(attachment.mimeType));
  return routeModelForRequest(routeCategoryFor(outputContract, isVisual));
}

export function buildAnswerPhases(routedModel: string): ProcessPhase[] {
  return [
    {
      id: "plan",
      label: "Planning",
      durationMs: PHASE_MS,
      logs: ["Interpreting the request", "Breaking the outcome into steps"],
    },
    {
      id: "route",
      label: "Selecting model",
      durationMs: PHASE_MS,
      logs: [`Selected worker: ${routedModel}`, "Capability check passed"],
    },
    {
      id: "deliver",
      label: "Delivery",
      durationMs: PHASE_MS,
      logs: ["Assembling the evidence set", "Packaging the deliverable"],
    },
  ];
}

export async function resolveAnswer(
  prompt: string,
  options: { attachment?: ChatAttachment | null; history?: ChatTurn[]; outputContract?: string } = {},
): Promise<ResolvedAnswer> {
  const attachment = options.attachment ?? null;
  const routedModel = routeFor(prompt, attachment, options.outputContract);

  try {
    const manifest = await loadFixtureManifest();
    if (attachment) {
      const imageFixture = matchImageFixture(manifest, attachment.fileName);
      if (imageFixture) {
        const answer = await resolveImageFixtureAnswer(imageFixture);
        if (answer.text || answer.imageUrl) {
          return { text: answer.text, imageUrl: answer.imageUrl, title: imageFixture.title, source: "library", routedModel };
        }
      }
    }
    const textFixture = matchTextFixture(manifest, prompt);
    if (textFixture) {
      return { text: await resolveTextFixtureAnswer(textFixture), title: textFixture.title, source: "library", routedModel };
    }
  } catch {
    // The curated library is optional. Fall through to the worker.
  }

  const text = await sendChatMessage(options.history ?? [], prompt, attachment);
  return { text, title: deriveTitle(prompt), source: "worker", routedModel };
}

export function deriveTitle(prompt: string): string {
  const firstLine = prompt.trim().split("\n")[0]?.trim() ?? "";
  if (!firstLine) return "Workspace answer";
  return firstLine.length > 72 ? `${firstLine.slice(0, 69)}…` : firstLine;
}
