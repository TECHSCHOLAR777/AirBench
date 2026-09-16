/**
 * Hardcoded, demo-stable roster of the models this AirBench Node build
 * ships with. These IDs match the qualification records shipped at
 * qualifications/records/*.json in the repo root. This list is intentionally
 * static (not fetched) so the desktop shell always has something coherent to
 * show on Home and in Settings, independent of whether a live qualification
 * measurement has completed on the connected Node.
 */

export type ModelRole = "reasoning" | "vision_worker" | "lead_worker" | "embedding" | "reranker";

export interface CatalogModel {
  id: string;
  roles: ModelRole[];
  summary: string;
}

export const MODEL_CATALOG: CatalogModel[] = [
  { id: "airbench-gemma-4-12b", roles: ["lead_worker", "reasoning"], summary: "Lead reasoning worker" },
  { id: "airbench-gemma-4-e2b", roles: ["reasoning"], summary: "Compact reasoning worker" },
  { id: "airbench-qwen25-vl-7b", roles: ["vision_worker"], summary: "Vision / P&ID intake" },
  { id: "airbench-qwen3-8b", roles: ["reasoning"], summary: "Code & tool-calling worker" },
  { id: "bge-m3", roles: ["embedding"], summary: "Embedding model" },
  { id: "bge-reranker-v2-m3", roles: ["reranker"], summary: "Reranker" },
];

export type RouteCategory = "text_or_document" | "code" | "image_or_pid";

/** Reasoning workers eligible for plain text/document requests. Qwen is reserved for code. */
const TEXT_OR_DOCUMENT_WORKERS = ["airbench-gemma-4-12b", "airbench-gemma-4-e2b"];

/**
 * Extends the old showcase-assistant image/text split with a third lane for
 * code deliverables. This is a hardcoded routing *display* used on Home to
 * show which qualified worker a request would land on — it does not call
 * any model directly. The real Node decides actual routing.
 *
 * Text/document requests are randomized across the eligible reasoning
 * workers on every call so the display doesn't always show the same model.
 */
export function routeModelForRequest(category: RouteCategory): string {
  if (category === "image_or_pid") return "airbench-qwen25-vl-7b";
  if (category === "code") return "airbench-qwen3-8b";
  return TEXT_OR_DOCUMENT_WORKERS[Math.floor(Math.random() * TEXT_OR_DOCUMENT_WORKERS.length)];
}

export function routeCategoryFor(outputContract: string, hasImageOrPid: boolean): RouteCategory {
  if (hasImageOrPid) return "image_or_pid";
  if (outputContract === "code") return "code";
  return "text_or_document";
}
