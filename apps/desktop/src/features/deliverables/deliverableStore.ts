/**
 * Session store of everything the workspace has produced — answers, P&ID
 * exports, sandbox runs — so the Review tab can list and re-download them.
 * Deliberately in-memory: this is a working session record, not a durable
 * archive, and it is cleared when the app restarts.
 */

export type DeliverableKind = "markdown" | "json" | "graphml" | "code" | "text";

export interface Deliverable {
  id: string;
  title: string;
  kind: DeliverableKind;
  source: string;
  content: string;
  fileName: string;
  createdAt: string;
  routedModel?: string;
}

const MIME_BY_KIND: Record<DeliverableKind, string> = {
  markdown: "text/markdown",
  json: "application/json",
  graphml: "application/xml",
  code: "text/plain",
  text: "text/plain",
};

let deliverables: Deliverable[] = [];
const listeners = new Set<() => void>();

export function subscribeToDeliverables(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function listDeliverables(): Deliverable[] {
  return deliverables;
}

export function recordDeliverable(entry: Omit<Deliverable, "id" | "createdAt">): Deliverable {
  const deliverable: Deliverable = { ...entry, id: crypto.randomUUID(), createdAt: new Date().toISOString() };
  deliverables = [deliverable, ...deliverables];
  for (const listener of listeners) listener();
  return deliverable;
}

export function clearDeliverables(): void {
  deliverables = [];
  for (const listener of listeners) listener();
}

export function downloadDeliverable(deliverable: Deliverable): void {
  const blob = new Blob([deliverable.content], { type: MIME_BY_KIND[deliverable.kind] });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = deliverable.fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "deliverable";
}
