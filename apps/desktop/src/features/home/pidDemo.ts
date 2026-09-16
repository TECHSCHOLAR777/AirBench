/**
 * Hardcoded P&ID demo walkthrough for Home: four shipped ground-truth
 * drawings, each replayed as input image -> planning/retrieval log ->
 * symbol JSON -> topology GraphML -> reconstructed output image. The
 * JSON/GraphML shown are the real fixture topology files (see
 * apps/desktop/public/demo-fixtures/pid/), only the pacing and log lines
 * around them are staged. Nothing here calls a live model.
 */
import type { ProcessPhase } from "../../lib/processTheater";
import { parseGraphml, topologyToJsonPreview, type ParsedTopology } from "../../lib/graphmlPreview";

export interface PidDemoSample {
  id: string;
  label: string;
  sourceImage: string;
  outputImage: string;
  graphmlUrl: string;
  assetCount: number;
  edgeCount: number;
}

const ROOT = "/demo-fixtures/pid/";

export const PID_DEMO_SAMPLES: PidDemoSample[] = [
  { id: "pid-sd-001", label: "PID-SD-001 · Feed transfer train", sourceImage: `${ROOT}pid-sd-001-source.png`, outputImage: `${ROOT}pid-sd-001-output.png`, graphmlUrl: `${ROOT}pid-sd-001-topology.graphml`, assetCount: 11, edgeCount: 8 },
  { id: "pid-sd-002", label: "PID-SD-002 · Vessel let-down loop", sourceImage: `${ROOT}pid-sd-002-source.png`, outputImage: `${ROOT}pid-sd-002-output.png`, graphmlUrl: `${ROOT}pid-sd-002-topology.graphml`, assetCount: 12, edgeCount: 8 },
  { id: "pid-sd-003", label: "PID-SD-003 · Booster pump train", sourceImage: `${ROOT}pid-sd-003-source.png`, outputImage: `${ROOT}pid-sd-003-output.png`, graphmlUrl: `${ROOT}pid-sd-003-topology.graphml`, assetCount: 13, edgeCount: 12 },
  { id: "pid-sd-004", label: "PID-SD-004 · Relief and blowdown header", sourceImage: `${ROOT}pid-sd-004-source.png`, outputImage: `${ROOT}pid-sd-004-output.png`, graphmlUrl: `${ROOT}pid-sd-004-topology.graphml`, assetCount: 12, edgeCount: 8 },
];

export function buildPidDemoPhases(sample: PidDemoSample): ProcessPhase[] {
  return [
    {
      id: "plan",
      label: "Planning & retrieval",
      logs: [
        `Registering P&ID extraction task for ${sample.label}`,
        "Retrieving qualified vision worker: airbench-qwen25-vl-7b",
        "Loading domain P&ID symbol library",
      ],
    },
    {
      id: "extract",
      label: "Symbol extraction",
      logs: [
        "Running vision detector across drawing regions",
        `Detected ${sample.assetCount} candidate symbols`,
        "Writing symbols.json",
      ],
    },
    {
      id: "topology",
      label: "Topology reconstruction",
      logs: [
        "Converting detections to topology graph (GraphML)",
        `Resolving ${sample.edgeCount} process-flow edges`,
        "Rendering reviewed reconstruction overlay",
      ],
    },
  ];
}

export async function fetchPidTopology(sample: PidDemoSample): Promise<{ topology: ParsedTopology; jsonPreview: string; graphmlText: string }> {
  const response = await fetch(sample.graphmlUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load topology for ${sample.label} (${response.status}).`);
  const graphmlText = await response.text();
  const topology = parseGraphml(graphmlText);
  return { topology, jsonPreview: topologyToJsonPreview(topology), graphmlText };
}

export function buildPidReportMarkdown(sample: PidDemoSample, topology: ParsedTopology): string {
  const symbolLines = topology.nodes.map((node) => `- \`${node.id}\` (${node.type}, ${Math.round(node.confidence * 100)}% confidence)`).join("\n");
  return [
    `**${sample.label} — digitized topology**`,
    "",
    `Detected ${topology.nodes.length} symbols and ${topology.edges.length} process-flow edges.`,
    "",
    "**Symbols**",
    symbolLines,
  ].join("\n");
}
