/**
 * The five ground-truth P&ID drawings shipped with the workspace.
 *
 * Raster derivatives live in public/pid-corpus/ (built from demo_showcase/PID
 * by scripts/prepare_pid_corpus.py). The matching GraphML ground truth lives
 * in src/assets/pid-corpus/ and is pulled in lazily as raw text, so opening a
 * drawing loads only that drawing's topology.
 */
import type { ProcessPhase } from "../../lib/processTheater";

export interface PidDrawing {
  id: string;
  tag: string;
  title: string;
  unit: string;
  thumb: string;
  display: string;
  width: number;
  height: number;
  nodeCount: number;
  edgeCount: number;
}

export const PID_DRAWINGS: PidDrawing[] = [
  { id: "0", tag: "PID-101", title: "Crude feed and preheat train", unit: "Unit 100 · Crude distillation", thumb: "/pid-corpus/0-thumb.jpg", display: "/pid-corpus/0-display.jpg", width: 7168, height: 4562, nodeCount: 452, edgeCount: 496 },
  { id: "1", tag: "PID-102", title: "Atmospheric column overhead", unit: "Unit 100 · Crude distillation", thumb: "/pid-corpus/1-thumb.jpg", display: "/pid-corpus/1-display.jpg", width: 7168, height: 4562, nodeCount: 450, edgeCount: 500 },
  { id: "2", tag: "PID-103", title: "Debutanizer reflux loop", unit: "Unit 200 · Light ends recovery", thumb: "/pid-corpus/2-thumb.jpg", display: "/pid-corpus/2-display.jpg", width: 7168, height: 4562, nodeCount: 434, edgeCount: 477 },
  { id: "3", tag: "PID-104", title: "Hydrotreater reactor loop", unit: "Unit 300 · Distillate hydrotreating", thumb: "/pid-corpus/3-thumb.jpg", display: "/pid-corpus/3-display.jpg", width: 7168, height: 4562, nodeCount: 629, edgeCount: 688 },
  { id: "4", tag: "PID-105", title: "Product rundown and storage", unit: "Unit 400 · Rundown and tankage", thumb: "/pid-corpus/4-thumb.jpg", display: "/pid-corpus/4-display.jpg", width: 7168, height: 4562, nodeCount: 556, edgeCount: 605 },
];

/** Drawings shown before the operator adds any of their own. */
export const DEFAULT_PID_DRAWINGS: PidDrawing[] = PID_DRAWINGS.slice(0, 2);

/**
 * Resolve a file the operator picked back to its corpus entry. Accepts the
 * raster derivative names (`3-display.jpg`, `3-thumb.jpg`), the topology name
 * (`3.graphml`), or the drawing tag (`PID-104.jpg`).
 */
export function matchPidDrawing(fileName: string): PidDrawing | null {
  const stem = fileName.replace(/\.[^.]+$/, "").toLowerCase();
  const normalized = stem.replace(/[^a-z0-9]/g, "");
  return PID_DRAWINGS.find((drawing) => {
    if (stem === drawing.id || stem === `${drawing.id}-display` || stem === `${drawing.id}-thumb`) return true;
    return normalized === drawing.tag.toLowerCase().replace(/[^a-z0-9]/g, "");
  }) ?? null;
}

const graphmlModules = import.meta.glob("../../assets/pid-corpus/*.graphml", { query: "?raw", import: "default" }) as Record<string, () => Promise<string>>;

export async function loadPidGraphml(drawing: PidDrawing): Promise<string> {
  const entry = Object.entries(graphmlModules).find(([path]) => path.endsWith(`/${drawing.id}.graphml`));
  if (!entry) throw new Error(`No topology is bundled for ${drawing.tag}.`);
  return await entry[1]();
}

export function buildPidPhases(drawing: PidDrawing): ProcessPhase[] {
  const stem = drawing.tag.toLowerCase();
  return [
    {
      id: "ingest",
      label: "Stage 1 · Symbol & component detection",
      durationMs: 2800,
      logs: [
        `Processing P&ID image: ${drawing.tag} (ID: ${stem}) — ${drawing.width}×${drawing.height} raster`,
        "[SymbolDetector] Loading YOLO model from models/weights/pid/best.pt...",
        `[SymbolDetector] Processing image ${drawing.width}x${drawing.height} across sliding-window patches...`,
      ],
    },
    {
      id: "detect",
      label: "Stage 2 · Classification & taxonomy",
      durationMs: 2600,
      logs: [
        `[SymbolDetector] Finished detection: ${drawing.nodeCount} candidate symbol regions extracted.`,
        "--- [Stage 2] Classifying Component Categories & Taxonomy ---",
        `[SymbolClassifier] Finished classification: ${drawing.nodeCount} components categorized (active legend: Refinery_PSU_Taxonomy_v1).`,
      ],
    },
    {
      id: "ocr",
      label: "Stage 3 · Text localization & OCR",
      durationMs: 2200,
      logs: [
        "--- [Stage 3] Running Text Localization & OCR ---",
        "[TextOCR] Extracted tag and label text entities via EasyOCR",
      ],
    },
    {
      id: "topology",
      label: "Stage 4-5 · Line tracing & topology assembly",
      durationMs: 3200,
      logs: [
        "[LineDetector] Tracing topology edges via mode='skeleton_walk'...",
        `[LineDetector] Traced ${drawing.edgeCount} total edges connecting symbols, connectors, and crossings.`,
        `[TopologyBuilder] Built topology with ${drawing.nodeCount} symbols and ${drawing.edgeCount} edges.`,
      ],
    },
    {
      id: "verify",
      label: "Stage 6 · Export & verification",
      durationMs: 2600,
      logs: [
        `[Exporter] Successfully exported GraphML to ${stem}_generated.graphml`,
        `[Exporter] Successfully exported JSON graph to ${stem}_graph.json`,
        "Topology accepted as untrusted evidence — exports ready for review",
      ],
    },
  ];
}
