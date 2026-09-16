/**
 * Reader for the ground-truth P&ID GraphML files shipped in
 * src/assets/pid-corpus/. Those files declare their attributes indirectly
 * (`<key id="d0" attr.name="label">` … `<data key="d0">valve</data>`) and
 * carry each symbol's bounding box in original drawing pixel space, so the
 * parsed graph can be drawn as a real spatial topology rather than an
 * arbitrary force layout.
 */

export type PidSymbolKind = "valve" | "instrumentation" | "general" | "connector" | "crossing" | "arrow" | "background" | "unknown";

export interface PidNode {
  id: string;
  kind: PidSymbolKind;
  x: number;
  y: number;
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
}

export interface PidEdge {
  source: string;
  target: string;
  label: string | null;
}

export interface PidGraph {
  nodes: PidNode[];
  edges: PidEdge[];
  bounds: { minX: number; minY: number; maxX: number; maxY: number };
  counts: Record<string, number>;
}

/** Symbol kinds that represent drawing furniture rather than process equipment. */
export const STRUCTURAL_KINDS: ReadonlySet<PidSymbolKind> = new Set(["connector", "crossing", "background"]);

function toKind(value: string): PidSymbolKind {
  switch (value) {
    case "valve":
    case "instrumentation":
    case "general":
    case "connector":
    case "crossing":
    case "arrow":
    case "background":
      return value;
    default:
      return "unknown";
  }
}

function numberOr(value: string | undefined, fallback: number): number {
  if (value === undefined) return fallback;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function parsePidGraphml(xml: string): PidGraph {
  const document = new DOMParser().parseFromString(xml, "application/xml");
  if (document.querySelector("parsererror")) throw new Error("The topology file could not be read.");

  const attributeNames = new Map<string, string>();
  for (const key of Array.from(document.getElementsByTagName("key"))) {
    const id = key.getAttribute("id");
    const name = key.getAttribute("attr.name");
    if (id && name) attributeNames.set(id, name);
  }

  const readData = (element: Element): Record<string, string> => {
    const values: Record<string, string> = {};
    for (const data of Array.from(element.getElementsByTagName("data"))) {
      const key = data.getAttribute("key");
      const name = key ? attributeNames.get(key) : null;
      if (name) values[name] = data.textContent ?? "";
    }
    return values;
  };

  const nodes: PidNode[] = [];
  const counts: Record<string, number> = {};
  for (const element of Array.from(document.getElementsByTagName("node"))) {
    const id = element.getAttribute("id");
    if (!id) continue;
    const values = readData(element);
    const kind = toKind(values.label ?? "");
    const rawXmin = numberOr(values.xmin, 0);
    const rawYmin = numberOr(values.ymin, 0);
    // A few sheet-frame boxes in the ground truth store their corners
    // inverted, so normalise rather than trusting min/max by name.
    const xmin = Math.min(rawXmin, numberOr(values.xmax, rawXmin));
    const xmax = Math.max(rawXmin, numberOr(values.xmax, rawXmin));
    const ymin = Math.min(rawYmin, numberOr(values.ymax, rawYmin));
    const ymax = Math.max(rawYmin, numberOr(values.ymax, rawYmin));
    counts[kind] = (counts[kind] ?? 0) + 1;
    nodes.push({ id, kind, xmin, ymin, xmax, ymax, x: (xmin + xmax) / 2, y: (ymin + ymax) / 2 });
  }

  const edges: PidEdge[] = [];
  for (const element of Array.from(document.getElementsByTagName("edge"))) {
    const source = element.getAttribute("source");
    const target = element.getAttribute("target");
    if (!source || !target) continue;
    const values = readData(element);
    edges.push({ source, target, label: values.edge_label?.trim() || null });
  }

  // "background" nodes are the drawing frame and would swamp the extent, so
  // the visible bounds come from the symbols that actually carry process meaning.
  const measured = nodes.filter((node) => node.kind !== "background");
  const source = measured.length > 0 ? measured : nodes;
  const bounds = source.reduce(
    (accumulator, node) => ({
      minX: Math.min(accumulator.minX, node.xmin),
      minY: Math.min(accumulator.minY, node.ymin),
      maxX: Math.max(accumulator.maxX, node.xmax),
      maxY: Math.max(accumulator.maxY, node.ymax),
    }),
    { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity },
  );

  return { nodes, edges, bounds, counts };
}

/** Equipment-only view used for the symbols export and the summary counts. */
export function processSymbols(graph: PidGraph): PidNode[] {
  return graph.nodes.filter((node) => !STRUCTURAL_KINDS.has(node.kind));
}

export function pidSymbolsJson(graph: PidGraph, meta: { tag: string; title: string; width: number; height: number }): string {
  const symbols = processSymbols(graph);
  return JSON.stringify(
    {
      drawing: { tag: meta.tag, title: meta.title, pixel_width: meta.width, pixel_height: meta.height },
      summary: {
        symbols_detected: symbols.length,
        connections: graph.edges.length,
        by_kind: graph.counts,
      },
      symbols: symbols.map((node) => ({
        id: node.id,
        kind: node.kind,
        bbox: { xmin: node.xmin, ymin: node.ymin, xmax: node.xmax, ymax: node.ymax },
        centroid: { x: Math.round(node.x), y: Math.round(node.y) },
      })),
      connections: graph.edges.map((edge) => ({ from: edge.source, to: edge.target, label: edge.label })),
    },
    null,
    2,
  );
}
