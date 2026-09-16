/**
 * Minimal, regex-based GraphML reader used only to turn the shipped P&ID
 * ground-truth topology files into a display-friendly JSON preview and a
 * trimmed GraphML snippet for the Home demo. Not a general XML parser —
 * it only understands the small node/edge shape these fixture files use.
 */

export interface TopologyNode {
  id: string;
  type: string;
  confidence: number;
}

export interface TopologyEdge {
  source: string;
  target: string;
  relation: string;
}

export interface ParsedTopology {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

function attr(body: string, key: string): string | null {
  const match = new RegExp(`key="${key}">([^<]*)<`).exec(body);
  return match ? match[1] : null;
}

export function parseGraphml(xml: string): ParsedTopology {
  const nodes: TopologyNode[] = [];
  const nodeRegex = /<node id="([^"]+)">([\s\S]*?)<\/node>/g;
  let match: RegExpExecArray | null;
  while ((match = nodeRegex.exec(xml))) {
    const body = match[2];
    nodes.push({
      id: match[1],
      type: attr(body, "type") ?? "unknown",
      confidence: Number.parseFloat(attr(body, "confidence") ?? "0") || 0,
    });
  }
  const edges: TopologyEdge[] = [];
  const edgeRegex = /<edge id="[^"]*" source="([^"]+)" target="([^"]+)">([\s\S]*?)<\/edge>/g;
  while ((match = edgeRegex.exec(xml))) {
    edges.push({
      source: match[1],
      target: match[2],
      relation: attr(match[3], "relation") ?? "process_flow_candidate",
    });
  }
  return { nodes, edges };
}

export function topologyToJsonPreview(topology: ParsedTopology): string {
  return JSON.stringify(
    {
      symbols: topology.nodes.map((node) => ({ tag: node.id, type: node.type, confidence: node.confidence })),
      edges: topology.edges.map((edge) => ({ from: edge.source, to: edge.target, relation: edge.relation })),
    },
    null,
    2,
  );
}
