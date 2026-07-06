/**
 * EquationMiniMap — a tiny, read-only canvas thumbnail used inside the
 * equation editor's ID dropdowns. Renders the SAME ReactFlow nodes/edges
 * as the main canvas (identical shapes, colors, routing) so the user gets a
 * faithful preview. Pan/zoom/interaction are disabled; one node or edge can
 * be highlighted via an overlay.
 */
import { useMemo, useRef, useEffect, useState, memo } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import CarrierNode from "./CarrierNode";
import GateNode from "./GateNode";
import EquipmentNode from "./EquipmentNode";
import BoundaryNode from "./BoundaryNode";
import FlowEdge from "./FlowEdge";

interface Props {
  nodes: Node[];
  edges: Edge[];
  /** Highlighted node id (equipment / carrier / gate) */
  highlightNodeId?: string;
  /** Highlighted edge id (flow) */
  highlightEdgeId?: string;
  /** Width — number (px) or any CSS length (e.g. "100%"). Defaults to "100%". */
  width?: number | string;
  /** Height — number (px) or any CSS length. If omitted, derived from the
   *  canvas content's natural aspect ratio so node/edge layout matches the
   *  main canvas at any dropdown size. */
  height?: number | string;
  /** Minimum height (px) when auto-deriving from aspect ratio. */
  minHeight?: number;
  /** Maximum height (px) when auto-deriving from aspect ratio. */
  maxHeight?: number;
}

const nodeTypes = {
  carrier: CarrierNode,
  gate: GateNode,
  equipment: EquipmentNode,
  boundary: BoundaryNode,
};

const edgeTypes = { flowEdge: FlowEdge };

// Static stylesheet — hoisted out so it isn't recreated on every render.
// Disables the canvas node hover effects inside the read-only mini-map.
const MINI_MAP_STYLE = `
  .equation-mini-map .group:hover { transform: none !important; }
  .equation-mini-map .group * { transition: none !important; }
  .equation-mini-map .group:hover .group-hover\\:scale-\\[1\\.02\\] { transform: none !important; }
  .equation-mini-map .group:hover .group-hover\\:shadow-md { box-shadow: none !important; }
  .equation-mini-map .group:hover .group-hover\\:opacity-100 { opacity: 0 !important; }
  .equation-mini-map { pointer-events: none; }
`;

/** Imperatively re-fit the viewport when the highlighted node/edge changes,
 *  so we don't have to remount the entire ReactFlow instance. */
function FitOnHighlight({ token }: { token: string }) {
  const rf = useReactFlow();
  useEffect(() => {
    // Defer to next frame so node measurements are up-to-date.
    const id = requestAnimationFrame(() => {
      try {
        rf.fitView({ padding: 0.15, includeHiddenNodes: true, duration: 200 });
      } catch {
        /* ignore — RF not ready yet */
      }
    });
    return () => cancelAnimationFrame(id);
  }, [rf, token]);
  return null;
}

function EquationMiniMapImpl({
  nodes,
  edges,
  highlightNodeId,
  highlightEdgeId,
  width = "100%",
  height,
  minHeight = 120,
  maxHeight = 320,
}: Props) {
  // Measure the rendered width so we can compute a height that matches the
  // main canvas's natural aspect ratio (responsive sizing).
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [measuredWidth, setMeasuredWidth] = useState<number>(
    typeof width === "number" ? width : 300,
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && Math.abs(w - measuredWidth) > 0.5) setMeasuredWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [measuredWidth]);

  // Compute the natural aspect ratio of the underlying canvas content from
  // node positions + sizes. This ensures the mini-map's proportions mirror
  // the main canvas regardless of dropdown width.
  const aspectRatio = useMemo(() => {
    if (nodes.length === 0) return 16 / 9;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodes) {
      const x = n.position?.x ?? 0;
      const y = n.position?.y ?? 0;
      const w = (n.width as number | undefined) ?? 140;
      const h = (n.height as number | undefined) ?? 80;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x + w > maxX) maxX = x + w;
      if (y + h > maxY) maxY = y + h;
    }
    const w = Math.max(1, maxX - minX);
    const h = Math.max(1, maxY - minY);
    return w / h;
  }, [nodes]);

  // Derive height: caller-supplied wins; otherwise compute from width/AR
  // and clamp to sensible bounds so it never collapses or dominates the UI.
  const resolvedHeight = useMemo(() => {
    if (height !== undefined) return height;
    const h = measuredWidth / aspectRatio;
    return Math.min(maxHeight, Math.max(minHeight, h));
  }, [height, measuredWidth, aspectRatio, minHeight, maxHeight]);

  // Match the main canvas exactly: only flag the focused element with
  // `selected` so ReactFlow's standard `.react-flow__node.selected` /
  // `.react-flow__edge.selected` outline applies. No custom dimming or
  // opacity changes — those don't exist on the main canvas.
  const decoratedNodes = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        selected: n.id === highlightNodeId,
        draggable: false,
        selectable: false,
      })),
    [nodes, highlightNodeId],
  );

  const decoratedEdges = useMemo(
    () =>
      edges.map((e) => ({
        ...e,
        selected: e.id === highlightEdgeId,
      })),
    [edges, highlightEdgeId],
  );

  if (nodes.length === 0) {
    return (
      <div
        ref={containerRef}
        className="rounded-md border border-dashed border-border bg-muted/30 flex items-center justify-center text-[10px] text-muted-foreground"
        style={{ width, height: resolvedHeight }}
      >
        Empty canvas
      </div>
    );
  }

  // Token used by the inner FitOnHighlight helper to re-run `fitView` without
  // remounting the ReactFlow tree.
  const fitToken = `${highlightNodeId ?? ""}::${highlightEdgeId ?? ""}`;

  return (
    <div
      ref={containerRef}
      className="relative rounded-md border border-border bg-background overflow-hidden equation-mini-map"
      style={{ width, height: resolvedHeight }}
    >
      {/* Disable hover scale/shadow effects from canvas node components inside the mini-map preview */}
      <style>{MINI_MAP_STYLE}</style>
      <ReactFlowProvider>
        <ReactFlow
          nodes={decoratedNodes}
          edges={decoratedEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.15, includeHiddenNodes: true }}
          minZoom={0.05}
          maxZoom={2}
          panOnDrag={false}
          panOnScroll={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
          preventScrolling={false}
        />
        <FitOnHighlight token={fitToken} />
      </ReactFlowProvider>
    </div>
  );
}

const EquationMiniMap = memo(EquationMiniMapImpl);
EquationMiniMap.displayName = "EquationMiniMap";
export default EquationMiniMap;