import { useCallback, useMemo, useRef, useState, type WheelEvent as ReactWheelEvent, type MouseEvent as ReactMouseEvent } from "react";
import { STRUCTURAL_KINDS, type PidGraph, type PidSymbolKind } from "../../lib/pidGraphml";

const KIND_STYLE: Record<PidSymbolKind, { color: string; radius: number; label: string }> = {
  general: { color: "#2f9e5c", radius: 20, label: "Equipment" },
  valve: { color: "#e08e1d", radius: 18, label: "Valve" },
  instrumentation: { color: "#2f7fe0", radius: 18, label: "Instrument" },
  arrow: { color: "#a855f7", radius: 16, label: "Flow arrow" },
  connector: { color: "#94a3b8", radius: 15, label: "Connector" },
  crossing: { color: "#c3cbd6", radius: 14, label: "Line crossing" },
  background: { color: "#d6dce4", radius: 13, label: "Sheet frame" },
  unknown: { color: "#94a3b8", radius: 15, label: "Unclassified" },
};

const MIN_NODE_RADIUS = 4;

const PADDING = 60;
const MIN_ZOOM = 1;
const MAX_ZOOM = 12;
const ZOOM_STEP = 1.35;

/**
 * Draws the reconstructed topology using each symbol's real bounding-box
 * centroid, so the graph keeps the spatial arrangement of the original
 * drawing instead of an arbitrary layout. Supports scroll-to-zoom and
 * drag-to-pan since real drawings pack hundreds of tightly spaced symbols.
 */
export function PidGraphCanvas({ graph }: { graph: PidGraph }) {
  const [showStructural, setShowStructural] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragState = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  const { nodes, edges, base, legend } = useMemo(() => {
    const visibleNodes = showStructural ? graph.nodes.filter((node) => node.kind !== "background") : graph.nodes.filter((node) => !STRUCTURAL_KINDS.has(node.kind));
    const visibleIds = new Set(visibleNodes.map((node) => node.id));
    const positions = new Map(graph.nodes.map((node) => [node.id, node]));
    const visibleEdges = graph.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));

    const { minX, minY, maxX, maxY } = graph.bounds;
    const width = Math.max(1, maxX - minX) + PADDING * 2;
    const height = Math.max(1, maxY - minY) + PADDING * 2;

    const kinds = new Map<PidSymbolKind, number>();
    for (const node of visibleNodes) kinds.set(node.kind, (kinds.get(node.kind) ?? 0) + 1);

    return {
      nodes: visibleNodes,
      edges: visibleEdges.map((edge) => ({ ...edge, from: positions.get(edge.source)!, to: positions.get(edge.target)! })),
      base: { x: minX - PADDING, y: minY - PADDING, width, height },
      legend: Array.from(kinds.entries()).sort((a, b) => b[1] - a[1]),
    };
  }, [graph, showStructural]);

  const clampPan = useCallback((next: { x: number; y: number }, z: number) => {
    const slack = { x: base.width * (1 - 1 / z) * 0.75, y: base.height * (1 - 1 / z) * 0.75 };
    return {
      x: Math.min(slack.x, Math.max(-slack.x, next.x)),
      y: Math.min(slack.y, Math.max(-slack.y, next.y)),
    };
  }, [base.width, base.height]);

  const zoomBy = useCallback((factor: number) => {
    setZoom((current) => {
      const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current * factor));
      setPan((currentPan) => clampPan(currentPan, next));
      return next;
    });
  }, [clampPan]);

  const resetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  const onWheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP);
  };

  const onPointerDown = (event: ReactMouseEvent<SVGSVGElement>) => {
    dragState.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
  };

  const onPointerMove = (event: ReactMouseEvent<SVGSVGElement>) => {
    if (!dragState.current || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const scale = (base.width / zoom) / rect.width;
    const dx = (event.clientX - dragState.current.x) * scale;
    const dy = (event.clientY - dragState.current.y) * scale;
    setPan(clampPan({ x: dragState.current.panX - dx, y: dragState.current.panY - dy }, zoom));
  };

  const endDrag = () => { dragState.current = null; };

  const viewW = base.width / zoom;
  const viewH = base.height / zoom;
  const viewX = base.x + (base.width - viewW) / 2 + pan.x;
  const viewY = base.y + (base.height - viewH) / 2 + pan.y;
  const viewBox = `${viewX} ${viewY} ${viewW} ${viewH}`;

  return <div className="pid-graph">
    <div className="pid-graph-toolbar">
      <div className="pid-graph-legend">
        {legend.map(([kind, count]) => <span key={kind} className="pid-graph-legend-item">
          <span className="pid-graph-swatch" style={{ background: KIND_STYLE[kind].color }} aria-hidden="true" />
          {KIND_STYLE[kind].label} <strong>{count}</strong>
        </span>)}
      </div>
      <div className="pid-graph-toolbar-controls">
        <label className="pid-graph-toggle">
          <input type="checkbox" checked={showStructural} onChange={(event) => setShowStructural(event.target.checked)} />
          Show line connectors
        </label>
        <div className="pid-graph-zoom">
          <button type="button" onClick={() => zoomBy(1 / ZOOM_STEP)} aria-label="Zoom out">−</button>
          <span>{Math.round(zoom * 100)}%</span>
          <button type="button" onClick={() => zoomBy(ZOOM_STEP)} aria-label="Zoom in">+</button>
          <button type="button" onClick={resetView} className="pid-graph-zoom-reset">Reset</button>
        </div>
      </div>
    </div>
    <svg
      ref={svgRef}
      className={`pid-graph-svg ${dragState.current ? "is-panning" : ""}`}
      viewBox={viewBox}
      role="img"
      aria-label="Reconstructed process topology"
      onWheel={onWheel}
      onMouseDown={onPointerDown}
      onMouseMove={onPointerMove}
      onMouseUp={endDrag}
      onMouseLeave={endDrag}
    >
      <g className="pid-graph-edges">
        {edges.map((edge, index) => <line key={index} x1={edge.from.x} y1={edge.from.y} x2={edge.to.x} y2={edge.to.y} />)}
      </g>
      <g className="pid-graph-nodes">
        {nodes.map((node) => <circle key={node.id} cx={node.x} cy={node.y} r={Math.max(MIN_NODE_RADIUS, KIND_STYLE[node.kind].radius / Math.sqrt(zoom))} fill={KIND_STYLE[node.kind].color}>
          <title>{`${node.id} · ${KIND_STYLE[node.kind].label}`}</title>
        </circle>)}
      </g>
    </svg>
  </div>;
}
