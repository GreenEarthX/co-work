import { memo, useState, useMemo, useEffect } from "react";
import { Handle, Position, NodeProps, useReactFlow, useEdges, useNodes, type Edge } from "@xyflow/react";
import { Trash2, Pencil, Check } from "lucide-react";
import NodeValidationBadge from "./NodeValidationBadge";
import { gateIcons, defaultInputGateIcon, defaultOutputGateIcon } from "./iconRegistry";
import { ANCHOR_SIDES, anchorHandleId, type AnchorSide } from "./portSystem";
import { computeNodeIdMap, buildNodeIdTooltip } from "./nodeIdSystem";
import { useNodeIdVisible, useNodeIdDebug, useLabelNormalization } from "./nodeIdVisibility";
import NodeIdDebugOverlay, { nodeIdDebugRingClass } from "./NodeIdDebugOverlay";

/** Format a flow number concisely */
function fmtFlow(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  if (Math.abs(v) < 0.01 && v !== 0) return v.toExponential(1);
  return v % 1 === 0 ? String(v) : v.toFixed(2);
}

const SIDE_TO_POSITION: Record<AnchorSide, Position> = {
  top: Position.Top,
  right: Position.Right,
  bottom: Position.Bottom,
  left: Position.Left,
};

function getGateDisplayFlow(edges: Edge[], gateId: string, isInput: boolean) {
  const directionalEdges = edges.filter((edge) => (isInput ? edge.source === gateId : edge.target === gateId));
  const connectedEdges = directionalEdges.length > 0
    ? directionalEdges
    : edges.filter((edge) => edge.source === gateId || edge.target === gateId);

  let best: { value: number; unit: string } | null = null;
  for (const edge of connectedEdges) {
    const value = edge.data?.flowValue;
    const unit = typeof edge.data?.flowUnit === "string" ? edge.data.flowUnit : "";
    if (typeof value === "number" && Number.isFinite(value) && unit) {
      if (!best || value > best.value) {
        best = { value, unit };
      }
    }
  }
  return best;
}

const GateNode = memo(({ data, id }: NodeProps) => {
  const isInput = data.gateType === "input";
  const isSnapped = data.isSnapped === true;
  const label = data.label as string;
  const Icon = gateIcons[label] || (isInput ? defaultInputGateIcon : defaultOutputGateIcon);
  const { setNodes, deleteElements } = useReactFlow();
  const edges = useEdges();
  const allNodes = useNodes();
  const labelOpts = useLabelNormalization();
  const idInfo = useMemo(() => computeNodeIdMap(allNodes, labelOpts).get(id), [allNodes, id, labelOpts]);
  const idTooltip = useMemo(() => buildNodeIdTooltip(id, label, idInfo), [id, label, idInfo]);
  const showIds = useNodeIdVisible();
  const debugIds = useNodeIdDebug();
  const debugRing = nodeIdDebugRingClass(label, idInfo, debugIds);
  const [editing, setEditing] = useState(false);
  const [editLabel, setEditLabel] = useState(label);

  // Listen for "rename" requests dispatched by the canvas right-click menu.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ id: string }>).detail;
      if (detail?.id !== id) return;
      setEditLabel(label);
      setEditing(true);
    };
    window.addEventListener("canvas:node-rename", handler);
    return () => window.removeEventListener("canvas:node-rename", handler);
  }, [id, label]);

  // Mirror the gate's primary stream value instead of summing every attached edge
  const flowSummary = useMemo(() => {
    return getGateDisplayFlow(edges, id, isInput);
  }, [edges, id, isInput]);

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteElements({ nodes: [{ id }] });
  };

  const handleSave = () => {
    setNodes((nds) => nds.map((n) => n.id === id ? { ...n, data: { ...n.data, label: editLabel } } : n));
    setEditing(false);
  };

  return (
    <div className="relative group">
      {/* Snap indicator, pulses when gate hits boundary edge */}
      {isSnapped && (
        <div className="absolute -inset-2 rounded-2xl border-2 border-primary/60 animate-ping pointer-events-none" />
      )}
      {isSnapped && (
        <div className="absolute -inset-2 rounded-2xl border-2 border-primary/50 pointer-events-none" />
      )}
      <NodeValidationBadge nodeId={id} />

      {/* ── 4 anchor connection points ── */}
      {ANCHOR_SIDES.map((side) => (
        <div key={side}>
          <Handle
            id={anchorHandleId(side, "source")}
            type="source"
            position={SIDE_TO_POSITION[side]}
            className="anchor-dot"
          />
          <Handle
            id={anchorHandleId(side, "target")}
            type="target"
            position={SIDE_TO_POSITION[side]}
            className="anchor-dot-target"
          />
        </div>
      ))}

      {/* Action buttons */}
      <div className="absolute -top-3 -right-3 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity z-10">
        <button onClick={() => setEditing(true)} className="h-6 w-6 rounded-full bg-accent border border-border flex items-center justify-center hover:bg-primary hover:text-primary-foreground transition-colors">
          <Pencil className="h-3 w-3" />
        </button>
        <button onClick={handleDelete} className="h-6 w-6 rounded-full bg-accent border border-border flex items-center justify-center hover:bg-destructive hover:text-destructive-foreground transition-colors">
          <Trash2 className="h-3 w-3" />
        </button>
      </div>

      <div title={idTooltip} className={`w-[160px] min-h-[80px] rounded-xl border-[3px] flex flex-col items-center justify-center shadow-lg transition-all group-hover:shadow-xl group-hover:scale-[1.03] ${debugRing} ${
        isInput
          ? "border-sky-400 bg-sky-50 dark:bg-sky-950/60 shadow-sky-400/20 group-hover:shadow-sky-400/40"
          : "border-amber-400 bg-amber-50 dark:bg-amber-950/60 shadow-amber-400/20 group-hover:shadow-amber-400/40"
      }`}>
        <NodeIdDebugOverlay label={label} info={idInfo} />
        {/* Direction badge */}
        <div className={`absolute -top-3 left-1/2 -translate-x-1/2 px-2.5 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-widest ${
          isInput ? "bg-sky-500 text-white" : "bg-amber-500 text-white"
        }`}>
          {isInput ? "▸ Input" : "◂ Output"}
        </div>

        <Icon className={`h-5 w-5 mb-0.5 ${isInput ? "text-sky-600 dark:text-sky-400" : "text-amber-600 dark:text-amber-400"}`} />
        {/* Identifier badge, ID on one line, occurrence on another */}
        {showIds && (
          <div className="flex flex-col items-center leading-none">
            <span className={`text-[11px] font-extrabold tracking-wider ${
              isInput ? "text-sky-700 dark:text-sky-300" : "text-amber-700 dark:text-amber-300"
            }`}>
              {idInfo?.displayId ?? "G?"}
            </span>
            {idInfo?.duplicateIndex !== undefined && (
              <span className="text-[8px] font-semibold text-muted-foreground mt-0.5">#{idInfo.duplicateIndex}</span>
            )}
          </div>
        )}

        {editing ? (
          <div className="flex items-center gap-0.5">
            <input
              autoFocus
              value={editLabel}
              onChange={(e) => setEditLabel(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") setEditing(false); }}
              className="w-24 text-[10px] text-center bg-background border border-border rounded px-1 py-0.5 text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <button onClick={handleSave} className="text-success"><Check className="h-3.5 w-3.5" /></button>
          </div>
        ) : (
          <>
            <p className={`text-[12px] font-extrabold leading-tight text-center ${
              isInput ? "text-sky-800 dark:text-sky-200" : "text-amber-800 dark:text-amber-200"
            }`}>{label}</p>
            {flowSummary && (
              <div className={`mt-1 px-2 py-0.5 rounded-md text-center ${
                isInput ? "bg-sky-200/60 dark:bg-sky-800/40" : "bg-amber-200/60 dark:bg-amber-800/40"
              }`}>
                <span className={`text-[13px] font-mono font-black ${
                  isInput ? "text-sky-700 dark:text-sky-300" : "text-amber-700 dark:text-amber-300"
                }`}>{fmtFlow(flowSummary.value)}</span>
                <span className={`text-[10px] ml-1 font-semibold ${
                  isInput ? "text-sky-600/80 dark:text-sky-400/80" : "text-amber-600/80 dark:text-amber-400/80"
                }`}>{flowSummary.unit}</span>
              </div>
            )}
          </>
        )}
      </div>

    </div>
  );
});
GateNode.displayName = "GateNode";

export default GateNode;
