/**
 * FlowEdge — Custom React Flow edge with flow labels, selection, deletion, and context menu.
 * Labels are auto-offset to avoid overlapping with nodes.
 */
import { memo, useState, useCallback, useMemo, useRef, useEffect } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  getStraightPath,
  useStore,
  useReactFlow,
  type EdgeProps,
} from "@xyflow/react";
import { Check, X, Trash2 } from "lucide-react";
import { getColorFromResource } from "./portSystem";
import { useCarrierColorVersion } from "@/hooks/useCarrierColorVersion";
import { useStraightEdges } from "./nodeIdVisibility";
import { describeBatch, type BatchFlowConfig } from "./batchFlow";

/** Node bounding box dimensions by type */
function nodeBounds(type?: string): { w: number; h: number } {
  switch (type) {
    case "gate": return { w: 170, h: 100 };
    case "carrier": return { w: 82, h: 82 };
    case "equipment": return { w: 150, h: 100 };
    case "boundary": return { w: 0, h: 0 };
    default: return { w: 140, h: 80 };
  }
}

/** Minimum clearance between label center and node edge */
const LABEL_CLEARANCE = 24;
/** Maximum offset distance we allow */
const MAX_OFFSET = 60;

/**
 * Compute a label offset to avoid overlapping with nearby nodes.
 * Shifts label along the stream (toward source or target) if it sits
 * on top of a node bounding box.
 */
function computeLabelOffset(
  labelX: number,
  labelY: number,
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number,
  nodes: Array<{ id: string; position: { x: number; y: number }; type?: string }>,
  _sourceId?: string,
  _targetId?: string,
): { dx: number; dy: number } {
  // Approximate label size
  const LABEL_W = 70;
  const LABEL_H = 22;

  // Check if the label overlaps any node
  for (const node of nodes) {
    if (node.type === "boundary") continue;
    const { w, h } = nodeBounds(node.type);
    const nx = node.position.x;
    const ny = node.position.y;

    // Expand the node rect by clearance
    const left = nx - LABEL_CLEARANCE;
    const right = nx + w + LABEL_CLEARANCE;
    const top = ny - LABEL_CLEARANCE;
    const bottom = ny + h + LABEL_CLEARANCE;

    // Check overlap (label center ± half label size)
    const lLeft = labelX - LABEL_W / 2;
    const lRight = labelX + LABEL_W / 2;
    const lTop = labelY - LABEL_H / 2;
    const lBottom = labelY + LABEL_H / 2;

    if (lRight > left && lLeft < right && lBottom > top && lTop < bottom) {
      // Overlapping — shift label along the edge direction
      const dx = targetX - sourceX;
      const dy = targetY - sourceY;
      const len = Math.sqrt(dx * dx + dy * dy);
      if (len < 1) return { dx: 0, dy: -LABEL_CLEARANCE };

      // Find the direction perpendicular to the edge
      const perpX = -dy / len;
      const perpY = dx / len;

      // Try shifting perpendicular first (cleaner look)
      const shiftDist = Math.min(MAX_OFFSET, LABEL_CLEARANCE + LABEL_H);
      
      // Choose the perpendicular direction that moves away from the node center
      const nodeCx = nx + w / 2;
      const nodeCy = ny + h / 2;
      const toCenterX = nodeCx - labelX;
      const toCenterY = nodeCy - labelY;
      const dot = toCenterX * perpX + toCenterY * perpY;
      
      // Shift away from node center
      const sign = dot > 0 ? -1 : 1;
      return { dx: perpX * shiftDist * sign, dy: perpY * shiftDist * sign };
    }
  }

  return { dx: 0, dy: 0 };
}

const FlowEdge = memo(({
  id,
  sourceX, sourceY,
  targetX, targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd: _markerEnd,
  data,
  selected,
  source,
  target,
}: EdgeProps) => {
  // Subscribe ONLY to the two endpoint nodes. Subscribing to the entire
  // `s.nodes` array would re-render every edge on every drag tick (and the
  // `?? []` fallback would even allocate a fresh array each time, defeating
  // the equality check). `useShallow` makes the selector return-stable so
  // edges re-render only when one of their endpoints actually changes.
  // Cache the previous slice so the selector returns the same array reference
  // when nothing relevant changed → no re-render. This avoids importing
  // zustand/shallow (React Flow ships its own store).
  type EndpointNode = { id: string; position: { x: number; y: number }; type?: string; data?: unknown };
  const endpointCacheRef = useRef<EndpointNode[]>([]);
  const endpointNodes = useStore((s) => {
    const list = (s.nodes ?? []) as Array<{ id: string; position: { x: number; y: number }; type?: string; data?: unknown }>;
    const next: EndpointNode[] = [];
    for (const n of list) {
      if (n.id === source || n.id === target) {
        next.push({ id: n.id, position: n.position, type: n.type, data: n.data });
      }
    }
    const prev = endpointCacheRef.current;
    if (
      prev.length === next.length &&
      prev.every((p, i) => {
        const q = next[i];
        return p.id === q.id
          && p.type === q.type
          && p.position.x === q.position.x
          && p.position.y === q.position.y
          && (p.data as { label?: string } | undefined)?.label === (q.data as { label?: string } | undefined)?.label;
      })
    ) {
      return prev;
    }
    endpointCacheRef.current = next;
    return next;
  });
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [editUnit, setEditUnit] = useState("kg/h");
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);

  const edgeData = (data ?? {}) as {
    flowValue?: number;
    flowUnit?: string;
    imbalance?: number;
    isMotherFlow?: boolean;
    isElectricity?: boolean;
    flowMode?: "continuous" | "batch";
    batch?: BatchFlowConfig;
    labelOffsetX?: number;
    labelOffsetY?: number;
    bendOffsetX?: number;
    bendOffsetY?: number;
    onUpdateFlowValue?: (edgeId: string, flowValue: number | undefined, flowUnit: string) => void;
    onDeleteFlowValue?: (edgeId: string) => void;
    onDeleteStream?: (edgeId: string) => void;
    onUpdateEdgeRoute?: (edgeId: string, bendOffsetX: number, bendOffsetY: number) => void;
    onResetEdgeRoute?: (edgeId: string) => void;
    onOpenBatchDialog?: (edgeId: string) => void;
  };

  const flowValue = edgeData.flowValue;
  const flowUnit = edgeData.flowUnit || "kg/h";
  const hasFlow = flowValue !== undefined && flowValue !== null;
  const isMotherFlow = edgeData.isMotherFlow;
  const isElectricity = edgeData.isElectricity;
  const isBatch = edgeData.flowMode === "batch" && !!edgeData.batch;
  const batchConfig = edgeData.batch;
  const manualOffsetX = edgeData.labelOffsetX ?? 0;
  const manualOffsetY = edgeData.labelOffsetY ?? 0;
  const bendOffsetX = edgeData.bendOffsetX ?? 0;
  const bendOffsetY = edgeData.bendOffsetY ?? 0;
  const onUpdateFlowValue = edgeData.onUpdateFlowValue;
  const onDeleteFlowValue = edgeData.onDeleteFlowValue;
  const onDeleteStream = edgeData.onDeleteStream;
  const onUpdateEdgeRoute = edgeData.onUpdateEdgeRoute;
  const onResetEdgeRoute = edgeData.onResetEdgeRoute;
  const onOpenBatchDialog = edgeData.onOpenBatchDialog;

  const straight = useStraightEdges();
  const defaultCenterX = (sourceX + targetX) / 2;
  const defaultCenterY = (sourceY + targetY) / 2;
  const centerX = defaultCenterX + bendOffsetX;
  const centerY = defaultCenterY + bendOffsetY;
  const [edgePath, rawLabelX, rawLabelY] = straight
    ? (() => {
        if (bendOffsetX === 0 && bendOffsetY === 0) {
          return getStraightPath({ sourceX, sourceY, targetX, targetY });
        }
        // Manual bend → render as polyline source → bend → target.
        const d = `M ${sourceX} ${sourceY} L ${centerX} ${centerY} L ${targetX} ${targetY}`;
        return [d, centerX, centerY] as [string, number, number];
      })()
    : getSmoothStepPath({
        sourceX, sourceY, targetX, targetY,
        sourcePosition, targetPosition,
        borderRadius: 12,
        offset: 25,
        centerX,
        centerY,
      });

  // ── Hover-to-drag bend handle ─────────────────────────────────────────────
  const { screenToFlowPosition } = useReactFlow();
  const [hovered, setHovered] = useState(false);
  const draggingBendRef = useRef(false);
  const startBend = useCallback((e: React.PointerEvent) => {
    if (!onUpdateEdgeRoute) return;
    e.stopPropagation();
    e.preventDefault();
    draggingBendRef.current = true;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    const move = (ev: PointerEvent) => {
      if (!draggingBendRef.current) return;
      const flowPos = screenToFlowPosition({ x: ev.clientX, y: ev.clientY });
      onUpdateEdgeRoute(id, flowPos.x - defaultCenterX, flowPos.y - defaultCenterY);
    };
    const up = () => {
      draggingBendRef.current = false;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }, [id, onUpdateEdgeRoute, screenToFlowPosition, defaultCenterX, defaultCenterY]);
  useEffect(() => () => { draggingBendRef.current = false; }, []);
  const hasBend = bendOffsetX !== 0 || bendOffsetY !== 0;

  // Auto-offset labels to avoid node overlap
  const { dx: autoOffsetX, dy: autoOffsetY } = useMemo(
    () => computeLabelOffset(
      rawLabelX + manualOffsetX,
      rawLabelY + manualOffsetY,
      sourceX, sourceY, targetX, targetY,
      endpointNodes, source, target,
    ),
    [rawLabelX, rawLabelY, manualOffsetX, manualOffsetY, sourceX, sourceY, targetX, targetY, endpointNodes, source, target],
  );

  const labelX = rawLabelX + manualOffsetX + autoOffsetX;
  const labelY = rawLabelY + manualOffsetY + autoOffsetY;

  const handleDoubleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setEditValue(String(flowValue ?? ""));
    setEditUnit(flowUnit);
    setEditing(true);
  }, [flowValue, flowUnit]);

  const handleSave = useCallback(() => {
    const parsed = parseFloat(editValue);
    onUpdateFlowValue?.(id, isNaN(parsed) ? undefined : parsed, editUnit);
    setEditing(false);
  }, [id, editValue, editUnit, onUpdateFlowValue]);

  const handleDeleteFlow = useCallback(() => {
    onDeleteFlowValue?.(id);
    setEditing(false);
  }, [id, onDeleteFlowValue]);

  /** Delete the entire edge (stream) immediately */
  const handleDeleteStream = useCallback(() => {
    onDeleteStream?.(id);
    setContextMenu(null);
  }, [id, onDeleteStream]);

  /** Right-click context menu */
  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY });
  }, []);

  const closeContextMenu = useCallback(() => setContextMenu(null), []);

  // Bumps whenever a carrier color override changes — forces useMemo below
  // to re-resolve the stroke color so edges recolor live.
  const carrierColorVersion = useCarrierColorVersion();
  // Resolve color from connected carrier node's resource label, falling back to edge style
  const carrierColor = useMemo(() => {
    const carrierNode = endpointNodes.find(
      (n) => (n.id === source || n.id === target) && n.type === "carrier"
    );
    if (carrierNode) {
      const resource = (carrierNode.data as { label?: string })?.label;
      if (resource) {
        const resolved = getColorFromResource(resource);
        if (resolved) return resolved;
      }
    }
    return null;
  }, [endpointNodes, source, target, carrierColorVersion]);

  const streamColor = carrierColor || (style.stroke as string) || "hsl(174, 45%, 45%)";

  // Detect if this edge is connected to a gate node → dashed line
  const isGateConnected = useMemo(() => {
    return endpointNodes.some(
      (n) => (n.id === source || n.id === target) && n.type === "gate"
    );
  }, [endpointNodes, source, target]);

  const edgeStyle: React.CSSProperties = {
    ...style,
    stroke: streamColor,
    strokeWidth: isElectricity ? 1.9 : selected ? 3 : isMotherFlow ? 2.75 : Math.max(2, (style.strokeWidth as number) ?? 2),
    ...(isBatch
      ? { strokeDasharray: "2 4 8 4" }
      : isGateConnected && !isElectricity
      ? { strokeDasharray: "8 5" }
      : {}),
    ...(isBatch
      ? { animation: "batch-march 1.6s linear infinite" }
      : {}),
    ...(isElectricity
      ? {
          stroke: "hsl(38, 92%, 42%)",
          strokeDasharray: "5 3",
          opacity: 0.95,
        }
      : {}),
    ...(selected
      ? {
          stroke: streamColor,
          filter: `drop-shadow(0 0 8px ${streamColor}) drop-shadow(0 0 16px ${streamColor})`,
          opacity: 1,
        }
      : {}),
  };

  // Halo width sits just under the colored stroke so the carrier color reads
  // crisply on top while the halo provides background contrast on any theme.
  const haloWidth = (edgeStyle.strokeWidth as number) + 2.5;

  return (
    <>
      {/* Invisible wider path for easier click selection */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        className="react-flow__edge-interaction"
        onContextMenu={handleContextMenu}
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
      />
      {/* Background-colored halo, guarantees contrast against light or dark
          canvas backgrounds regardless of the carrier color. */}
      <path
        d={edgePath}
        fill="none"
        stroke="hsl(var(--background))"
        strokeWidth={haloWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.9}
        style={{ pointerEvents: "none", vectorEffect: "non-scaling-stroke" } as React.CSSProperties}
      />
      {/* Animated glow underlay for selected edge, uses carrier color */}
      {selected && !isElectricity && (
        <path
          d={edgePath}
          fill="none"
          stroke={streamColor}
          strokeWidth={6}
          strokeLinecap="round"
          opacity={0.18}
          className="selected-edge-glow"
          style={{ vectorEffect: "non-scaling-stroke" } as React.CSSProperties}
        />
      )}
      {/* Per-edge colored arrow marker so every stream has a directional arrow */}
      <defs>
        <marker
          id={`arrow-${id}`}
          viewBox="-2 -2 14 14"
          refX="9"
          refY="5"
          markerWidth={9}
          markerHeight={9}
          orient="auto-start-reverse"
        >
          {/* Background halo around the arrowhead so it reads on any theme */}
          <path
            d="M 0 0 L 10 5 L 0 10 z"
            fill="none"
            stroke="hsl(var(--background))"
            strokeWidth="2.5"
            strokeLinejoin="round"
          />
          <path d="M 0 0 L 10 5 L 0 10 z" fill={streamColor} />
        </marker>
      </defs>
      <BaseEdge
        path={edgePath}
        markerEnd={`url(#arrow-${id})`}
        style={{ ...edgeStyle, vectorEffect: "non-scaling-stroke" } as React.CSSProperties}
      />
      <EdgeLabelRenderer>
        {/* Hover/drag bend handle, appears when the edge or handle is hovered */}
        {onUpdateEdgeRoute && (
          <div
            className="nodrag nopan absolute"
            style={{
              transform: `translate(-50%, -50%) translate(${centerX}px, ${centerY}px)`,
              pointerEvents: "auto",
              opacity: hovered || hasBend || selected ? 1 : 0,
              transition: "opacity 120ms ease",
              cursor: "grab",
              zIndex: 1,
            }}
            onPointerEnter={() => setHovered(true)}
            onPointerLeave={() => setHovered(false)}
            onPointerDown={startBend}
            onDoubleClick={(e) => { e.stopPropagation(); onResetEdgeRoute?.(id); }}
            title="Drag to bend connection · double-click to reset"
          >
            <div
              className="rounded-full border-2 border-background shadow"
              style={{
                width: 12,
                height: 12,
                backgroundColor: streamColor,
              }}
            />
          </div>
        )}
        {/* Hover delete button, offset above the label */}
        <div
          className="nodrag nopan pointer-events-auto absolute opacity-0 hover:opacity-100 peer"
          style={{
            transform: `translate(-50%, -100%) translate(${labelX}px,${labelY - 14}px)`,
          }}
        >
          <button
            onClick={(e) => { e.stopPropagation(); handleDeleteStream(); }}
            className="h-5 w-5 rounded-full bg-destructive/90 border border-destructive text-destructive-foreground flex items-center justify-center shadow-md hover:scale-110 transition-all"
            title="Delete stream"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>

        {/* Flow label area */}
        <div
          className="nodrag nopan pointer-events-auto absolute group/label"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            zIndex: 10,
          }}
          onDoubleClick={handleDoubleClick}
          onContextMenu={handleContextMenu}
        >
          {/* Hover delete icon inline, appears on label hover, clears flow value only */}
          {!editing && hasFlow && (
            <button
              onClick={(e) => { e.stopPropagation(); handleDeleteFlow(); }}
              className="absolute -top-2.5 -right-2.5 h-4 w-4 rounded-full bg-muted text-muted-foreground flex items-center justify-center opacity-0 group-hover/label:opacity-100 transition-opacity shadow-sm hover:scale-110 z-10"
              title="Clear flow value"
            >
              <X className="h-2.5 w-2.5" />
            </button>
          )}

          {editing ? (
            <div className="flex items-center gap-1 bg-card border border-border rounded-md px-1.5 py-1 shadow-lg whitespace-nowrap z-50">
              <input
                autoFocus
                type="number"
                step="any"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") setEditing(false); }}
                className="w-16 text-[10px] bg-background border border-border rounded px-1.5 py-0.5 text-foreground focus:outline-none focus:ring-1 focus:ring-ring text-right [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                placeholder="Value"
              />
              <select
                value={editUnit}
                onChange={(e) => setEditUnit(e.target.value)}
                className="text-[10px] bg-background border border-border rounded px-1 py-0.5 text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {COMMON_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
              <button onClick={handleSave} className="text-success hover:text-success/80"><Check className="h-3.5 w-3.5" /></button>
              <button onClick={handleDeleteFlow} className="text-destructive hover:text-destructive/80"><Trash2 className="h-3 w-3" /></button>
              <button onClick={() => setEditing(false)} className="text-muted-foreground hover:text-foreground"><X className="h-3.5 w-3.5" /></button>
            </div>
          ) : isBatch && batchConfig ? (
            (() => {
              const desc = describeBatch(batchConfig);
              return (
                <div
                  className="cursor-pointer rounded-md px-2 py-1 shadow-sm border-[1.5px] bg-card transition-all hover:shadow-md flex flex-col items-center gap-0 leading-tight"
                  style={{
                    borderColor: streamColor,
                    backgroundColor: `${streamColor}1f`,
                  }}
                  title={`Batch flow · equivalent ≈ ${(flowValue ?? 0).toFixed(2)} ${flowUnit}`}
                  onClick={(e) => { e.stopPropagation(); onOpenBatchDialog?.(id); }}
                >
                  <div className="flex items-center gap-1">
                    <span className="text-[10px]">📦</span>
                    <span
                      className="text-[10px] font-semibold tabular-nums"
                      style={{ color: streamColor, fontFamily: "'Inter', system-ui, sans-serif" }}
                    >
                      {desc.line1}
                    </span>
                  </div>
                  <span className="text-[9px] text-muted-foreground tabular-nums">{desc.line2}</span>
                </div>
              );
            })()
          ) : hasFlow ? (
            <div
              className={`cursor-pointer rounded-full px-2 py-0.5 shadow-sm border bg-card transition-all hover:shadow-md flex items-center gap-1 ${isElectricity ? "opacity-50 scale-90" : ""}`}
              style={{
                borderColor: selected ? streamColor : undefined,
                boxShadow: selected ? `0 0 0 2px ${streamColor}40` : undefined,
              }}
              onClick={(e) => {
                e.stopPropagation();
                setEditValue(String(flowValue));
                setEditUnit(flowUnit);
                setEditing(true);
              }}
            >
              {isElectricity && <span className="text-[9px]">⚡</span>}
              <span className={`text-[10px] font-semibold tabular-nums ${isElectricity ? "text-[9px]" : ""}`} style={{ color: streamColor, fontFamily: "'Inter', system-ui, sans-serif" }}>{formatFlow(flowValue)}</span>
              <span className="text-[9px] text-muted-foreground">{flowUnit}</span>
            </div>
          ) : (
            <div
              className={`cursor-pointer rounded-full px-2 py-0.5 border border-dashed bg-card/50 transition-opacity ${
                selected ? "opacity-100" : "border-muted-foreground/20 opacity-0 hover:opacity-100"
              }`}
              style={selected ? { borderColor: streamColor } : undefined}
              onClick={(e) => {
                e.stopPropagation();
                setEditValue("");
                setEditUnit("kg/h");
                setEditing(true);
              }}
            >
              <span className="text-[8px] text-muted-foreground">+ flow</span>
            </div>
          )}
        </div>

        {/* Right-click context menu */}
        {contextMenu && (
          <>
            <div className="fixed inset-0 z-[100]" onClick={closeContextMenu} onContextMenu={(e) => { e.preventDefault(); closeContextMenu(); }} />
            <div
              className="fixed z-[101] bg-card border border-border rounded-lg shadow-xl py-1 min-w-[160px]"
              style={{ left: contextMenu.x, top: contextMenu.y }}
            >
              <button
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-accent transition-colors"
                onClick={() => {
                  setEditValue(String(flowValue ?? ""));
                  setEditUnit(flowUnit);
                  setEditing(true);
                  setContextMenu(null);
                }}
              >
                <Check className="h-3 w-3" />
                Edit Flow Value
              </button>
              <button
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10 transition-colors"
                onClick={() => { handleDeleteStream(); }}
              >
                <Trash2 className="h-3 w-3" />
                Delete Stream
              </button>
            </div>
          </>
        )}
      </EdgeLabelRenderer>
    </>
  );
});
FlowEdge.displayName = "FlowEdge";
export default FlowEdge;

/* ── Helpers ── */
function formatFlow(v: number): string {
  if (Math.abs(v) < 0.01 && v !== 0) return v.toExponential(1);
  return v % 1 === 0 ? String(v) : v.toFixed(2);
}

const COMMON_UNITS = [
  "MW", "kW", "GW", "kW/y", "kWh/y", "MWh/yr", "GWh/yr",
  "MW_th", "kW_th", "GJ/h",
  "kg/h", "t/h", "t/d", "kg/s", "kt/yr",
  "Nm³/h", "Nm³/d", "Nm³/y", "m³/h", "L/h", "L/min", "m³/d", "m³/y",
  "mol/s",
];
