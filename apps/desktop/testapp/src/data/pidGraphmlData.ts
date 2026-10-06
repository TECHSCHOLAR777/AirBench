import { RAW_PID_GRAPHML } from './pidCorpusRaw';
import { PID_CORPUS_DRAWINGS, PidCorpusDrawing } from './pidCorpus';

export interface GraphmlNode {
  id: string;
  tag: string;
  spec?: string;
  subType?: string;
  label: 'crossing' | 'general' | 'connector' | 'instrumentation' | 'valve' | 'arrow' | 'background';
  categoryName: string;
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
  cx: number;
  cy: number;
}

export interface GraphmlEdge {
  source: string;
  target: string;
  edgeLabel: 'solid' | 'non-solid';
  spec?: string;
}

export interface ParsedPidGraph {
  nodes: GraphmlNode[];
  edges: GraphmlEdge[];
  nodeCount: number;
  edgeCount: number;
  drawingId: string;
  sourceType: 'corpus-xml' | 'uploaded-xml' | 'custom';
}

export const PID_COLOR_PALETTE = {
  general: {
    name: 'Equipment',
    color: '#bd5b38',
    border: '#bd5b38',
    bg: 'rgba(189, 91, 56, 0.15)',
    textColor: '#bd5b38',
    description: 'Columns, pumps, heat exchangers, vessels, tanks'
  },
  valve: {
    name: 'Valves',
    color: '#3ea877',
    border: '#3ea877',
    bg: 'rgba(62, 168, 119, 0.15)',
    textColor: '#3ea877',
    description: 'Control valves, check valves, manual gate valves, safety valves'
  },
  instrumentation: {
    name: 'Instruments',
    color: '#60a5fa',
    border: '#60a5fa',
    bg: 'rgba(96, 165, 250, 0.15)',
    textColor: '#60a5fa',
    description: 'Transmitters, indicators, controllers (PT, TT, FT, LIC)'
  },
  connector: {
    name: 'Piping & Connectors',
    color: '#d99c43',
    border: '#d99c43',
    bg: 'rgba(217, 156, 67, 0.15)',
    textColor: '#d99c43',
    description: 'Pipe junctions, flanges, tees, elbows'
  },
  crossing: {
    name: 'Crossings',
    color: '#9c978f',
    border: '#9c978f',
    bg: 'rgba(156, 151, 143, 0.15)',
    textColor: '#ede8dd',
    description: 'Non-intersecting pipe bridges & crossovers'
  },
  arrow: {
    name: 'Flow Arrows',
    color: '#ec4899',
    border: '#ec4899',
    bg: 'rgba(236, 72, 153, 0.15)',
    textColor: '#ec4899',
    description: 'Process stream flow arrows'
  },
  background: {
    name: 'Frame',
    color: '#64748b',
    border: '#64748b',
    bg: 'rgba(100, 116, 139, 0.15)',
    textColor: '#94a3b8',
    description: 'Drawing border and title block'
  }
} as const;

export type PidLegendKey = keyof typeof PID_COLOR_PALETTE;

export function normalizeDrawingId(rawId: string): string {
  if (!rawId) return '0';
  const clean = rawId.toLowerCase().trim();
  if (clean === 'pid-101' || clean === '0' || clean.includes('101')) return '0';
  if (clean === 'pid-102' || clean === '1' || clean.includes('102')) return '1';
  if (clean === 'pid-103' || clean === '2' || clean.includes('103')) return '2';
  if (clean === 'pid-104' || clean === '3' || clean.includes('104')) return '3';
  if (clean === 'pid-105' || clean === '4' || clean.includes('105')) return '4';
  return rawId;
}

// In-memory parsed graph cache for high performance
const PARSED_CACHE = new Map<string, ParsedPidGraph>();

/**
 * Parses raw GraphML XML string into spatial nodes and edges.
 * Cross-references key equipment from PID_CORPUS_DRAWINGS for authentic engineering tags.
 */
export function parseGraphmlXml(xmlContent: string, drawingId?: string): ParsedPidGraph {
  const normId = drawingId ? normalizeDrawingId(drawingId) : '0';
  const corpusDrawing = PID_CORPUS_DRAWINGS.find(d => d.id === normId) || PID_CORPUS_DRAWINGS[0];
  const keyEquipmentList = corpusDrawing?.keyEquipment || [];

  const nodes: GraphmlNode[] = [];
  const edges: GraphmlEdge[] = [];

  const nodeRegex = /<node\s+id="([^"]+)">([\s\S]*?)<\/node>/g;
  let match: RegExpExecArray | null;
  
  let vCounter = 1;
  let iCounter = 1;
  let eCounter = 1;
  const claimedKeyEquipment = new Set<string>();

  while ((match = nodeRegex.exec(xmlContent)) !== null) {
    const id = match[1];
    const body = match[2];

    const dataMap: Record<string, string> = {};
    const dataRegex = /<data\s+key="([^"]+)">([\s\S]*?)<\/data>/g;
    let dMatch: RegExpExecArray | null;
    while ((dMatch = dataRegex.exec(body)) !== null) {
      dataMap[dMatch[1]] = dMatch[2].trim();
    }

    const rawLabel = (dataMap['d0'] || 'connector').toLowerCase() as GraphmlNode['label'];
    const label: GraphmlNode['label'] = 
      ['crossing', 'general', 'connector', 'instrumentation', 'valve', 'arrow', 'background'].includes(rawLabel)
        ? rawLabel
        : 'connector';

    // Parse coordinates checking long (d1..d4) and double (d5..d8)
    const xmin = dataMap['d1'] !== undefined 
      ? parseFloat(dataMap['d1']) 
      : (dataMap['d5'] !== undefined ? parseFloat(dataMap['d5']) : 100);

    const ymin = dataMap['d2'] !== undefined 
      ? parseFloat(dataMap['d2']) 
      : (dataMap['d6'] !== undefined ? parseFloat(dataMap['d6']) : 100);

    const xmax = dataMap['d3'] !== undefined 
      ? parseFloat(dataMap['d3']) 
      : (dataMap['d7'] !== undefined ? parseFloat(dataMap['d7']) : xmin + 40);

    const ymax = dataMap['d4'] !== undefined 
      ? parseFloat(dataMap['d4']) 
      : (dataMap['d8'] !== undefined ? parseFloat(dataMap['d8']) : ymin + 40);

    const cx = Math.round((xmin + xmax) / 2);
    const cy = Math.round((ymin + ymax) / 2);

    let tag = id;
    let subType: string = PID_COLOR_PALETTE[label]?.name || label;
    let spec = '';

    // Match closest key equipment of matching class if within proximity threshold
    if (label === 'general' || label === 'valve' || label === 'instrumentation') {
      let closestEq: typeof keyEquipmentList[0] | null = null;
      let minDistance = 1200; // Search radius in coordinate units

      for (const eq of keyEquipmentList) {
        if (claimedKeyEquipment.has(eq.tag)) continue;

        const isMatchClass = 
          (label === 'valve' && (eq.type.includes('Valve') || eq.tag.includes('V-') || eq.tag.includes('FCV') || eq.tag.includes('PSV') || eq.tag.includes('TCV') || eq.tag.includes('PCV'))) ||
          (label === 'instrumentation' && (eq.type.includes('Transmitter') || eq.type.includes('Indicator') || eq.tag.startsWith('P') || eq.tag.startsWith('T') || eq.tag.startsWith('F'))) ||
          (label === 'general' && (eq.type.includes('Pump') || eq.type.includes('Exchanger') || eq.type.includes('Column') || eq.type.includes('Condenser') || eq.type.includes('Vessel') || eq.type.includes('Tank') || eq.type.includes('Reactor') || eq.type.includes('Heater') || eq.type.includes('Compressor')));

        if (isMatchClass) {
          const dist = Math.hypot(cx - eq.x, cy - eq.y);
          if (dist < minDistance) {
            minDistance = dist;
            closestEq = eq;
          }
        }
      }

      if (closestEq) {
        tag = closestEq.tag;
        subType = closestEq.type;
        spec = closestEq.specs;
        claimedKeyEquipment.add(closestEq.tag);
      } else {
        if (label === 'valve') {
          tag = `V-${vCounter++}`;
          subType = 'Process Isolation Valve';
          spec = 'Class 150 RF Flanged Gate Valve';
        } else if (label === 'instrumentation') {
          tag = `PT/TI-${iCounter++}`;
          subType = 'In-line Process Transmitter';
          spec = '4-20mA HART isolated signal lead';
        } else if (label === 'general') {
          tag = `EQ-${eCounter++}`;
          subType = 'Process Equipment Module';
          spec = 'ASME Sec VIII Div 1 CS Shell';
        }
      }
    } else if (label === 'crossing') {
      tag = `CR-${id.replace('crossing', '')}`;
      subType = 'Topological Pipe Bridge';
      spec = 'Non-intersecting process line overlap';
    } else if (label === 'connector') {
      tag = `J-${id.replace('connector', '')}`;
      subType = 'Piping Header Branch';
      spec = 'Welded Schedule 40 Tee / Reducer';
    } else if (label === 'arrow') {
      tag = `FLOW-${id.replace('arrow', '')}`;
      subType = 'Process Stream Flow Direction';
      spec = 'Process fluid vector heading';
    }

    nodes.push({
      id,
      tag,
      label,
      categoryName: PID_COLOR_PALETTE[label]?.name || label,
      subType,
      spec,
      xmin,
      ymin,
      xmax,
      ymax,
      cx,
      cy
    });
  }

  const edgeRegex = /<edge\s+source="([^"]+)"\s+target="([^"]+)">([\s\S]*?)<\/edge>/g;
  while ((match = edgeRegex.exec(xmlContent)) !== null) {
    const source = match[1];
    const target = match[2];
    const body = match[3];
    const d9Match = body.match(/<data\s+key="d9">([^<]+)<\/data>/);
    const edgeLabel = (d9Match && d9Match[1].trim() === 'non-solid') ? 'non-solid' : 'solid';

    const spec = edgeLabel === 'solid' ? '8"-Process-Run' : 'Instrument-Lead';

    edges.push({
      source,
      target,
      edgeLabel,
      spec
    });
  }

  return {
    nodes,
    edges,
    nodeCount: nodes.length,
    edgeCount: edges.length,
    drawingId: normId,
    sourceType: drawingId && RAW_PID_GRAPHML[normId] ? 'corpus-xml' : 'uploaded-xml'
  };
}

/**
 * Gets the raw GraphML XML string for any drawing (Corpus 0..4 or custom)
 */
export function getRawGraphmlXml(drawingId: string): string {
  const normId = normalizeDrawingId(drawingId);
  if (RAW_PID_GRAPHML[normId]) {
    return RAW_PID_GRAPHML[normId];
  }
  // Fallback: generate GraphML from parsed data
  const drawing = PID_CORPUS_DRAWINGS.find(d => d.id === normId) || PID_CORPUS_DRAWINGS[0];
  return generateGraphmlXml(drawing.id, drawing.tag, drawing.title);
}

/**
 * Loads and caches the topological graph for a drawing ID or custom XML string
 */
export function loadPidGraphml(drawingIdOrXml: string, customXml?: string): ParsedPidGraph {
  const isXml = customXml || (drawingIdOrXml.includes('<graphml') ? drawingIdOrXml : null);
  
  if (isXml) {
    return parseGraphmlXml(isXml);
  }

  const normId = normalizeDrawingId(drawingIdOrXml);
  if (PARSED_CACHE.has(normId)) {
    return PARSED_CACHE.get(normId)!;
  }

  const rawXml = RAW_PID_GRAPHML[normId] || RAW_PID_GRAPHML['0'];
  const parsed = parseGraphmlXml(rawXml, normId);
  PARSED_CACHE.set(normId, parsed);
  return parsed;
}

/**
 * Returns structured JSON representation of the P&ID graph suitable for display and download
 */
export function getPidJsonData(drawingId: string, customGraph?: ParsedPidGraph) {
  const normId = normalizeDrawingId(drawingId);
  const drawing = PID_CORPUS_DRAWINGS.find(d => d.id === normId) || PID_CORPUS_DRAWINGS[0];
  const graph = customGraph || loadPidGraphml(normId);

  // Group connections by node
  const connectionsMap = new Map<string, string[]>();
  graph.edges.forEach(e => {
    if (!connectionsMap.has(e.source)) connectionsMap.set(e.source, []);
    if (!connectionsMap.has(e.target)) connectionsMap.set(e.target, []);
    connectionsMap.get(e.source)!.push(e.target);
    connectionsMap.get(e.target)!.push(e.source);
  });

  // Calculate category statistics
  const categoryCounts: Record<string, number> = {};
  graph.nodes.forEach(n => {
    categoryCounts[n.label] = (categoryCounts[n.label] || 0) + 1;
  });

  return {
    schemaVersion: "1.0.0",
    generatedAt: new Date().toISOString(),
    drawing: {
      id: drawing.id,
      tag: drawing.tag,
      title: drawing.title,
      unit: drawing.unit,
      dwgNumber: drawing.dwgNumber,
      revision: drawing.revision,
      sheet: drawing.sheet,
      description: drawing.description,
      canvasDimensions: {
        width: drawing.width || 7168,
        height: drawing.height || 4562,
        coordinateSystem: "Upper-Left Origin (0,0) to (7168, 4562)"
      }
    },
    topologySummary: {
      totalNodes: graph.nodeCount,
      totalEdges: graph.edgeCount,
      categoryBreakdown: categoryCounts,
      keyEquipmentCount: drawing.keyEquipment?.length || 0
    },
    keyEquipmentManifest: drawing.keyEquipment || [],
    nodes: graph.nodes.map(n => ({
      id: n.id,
      tag: n.tag,
      category: n.label,
      categoryName: n.categoryName,
      subType: n.subType || n.label,
      spec: n.spec || undefined,
      boundingBox: {
        xmin: n.xmin,
        ymin: n.ymin,
        xmax: n.xmax,
        ymax: n.ymax,
        width: n.xmax - n.xmin,
        height: n.ymax - n.ymin
      },
      centerCoordinates: {
        x: n.cx,
        y: n.cy
      },
      connectedNodes: connectionsMap.get(n.id) || []
    })),
    edges: graph.edges.map((e, idx) => ({
      edgeId: `edge-${idx + 1}`,
      source: e.source,
      target: e.target,
      edgeType: e.edgeLabel,
      spec: e.spec || '8"-CR-Line'
    }))
  };
}

/**
 * Regenerates clean GraphML XML from any graph state
 */
export function generateGraphmlXml(drawingId: string, tag: string, title: string): string {
  const normId = normalizeDrawingId(drawingId);
  if (RAW_PID_GRAPHML[normId]) {
    return RAW_PID_GRAPHML[normId];
  }

  const data = loadPidGraphml(drawingId);
  let xml = `<?xml version='1.0' encoding='utf-8'?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">
  <!-- AirBench Sovereign Spatial GraphML -->
  <!-- Target Drawing: ${tag} (${title}) -->
  <!-- Canvas Resolution: 7168x4562 -->
  <key id="d0" for="node" attr.name="label" attr.type="string" />
  <key id="d1" for="node" attr.name="xmin" attr.type="long" />
  <key id="d2" for="node" attr.name="ymin" attr.type="long" />
  <key id="d3" for="node" attr.name="xmax" attr.type="long" />
  <key id="d4" for="node" attr.name="ymax" attr.type="long" />
  <key id="d5" for="node" attr.name="tag" attr.type="string" />
  <key id="d9" for="edge" attr.name="edge_label" attr.type="string" />
  <graph edgedefault="undirected" id="${tag}">
`;

  data.nodes.forEach(n => {
    xml += `    <node id="${n.id}">
      <data key="d0">${n.label}</data>
      <data key="d1">${n.xmin}</data>
      <data key="d2">${n.ymin}</data>
      <data key="d3">${n.xmax}</data>
      <data key="d4">${n.ymax}</data>
      <data key="d5">${n.tag || n.id}</data>
    </node>\n`;
  });

  data.edges.forEach(e => {
    xml += `    <edge source="${e.source}" target="${e.target}">
      <data key="d9">${e.edgeLabel}</data>
    </edge>\n`;
  });

  xml += `  </graph>
</graphml>`;
  return xml;
}
