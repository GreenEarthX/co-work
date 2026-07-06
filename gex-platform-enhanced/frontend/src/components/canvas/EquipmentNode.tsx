import { memo, useState, useMemo, useEffect } from "react";
import { Handle, Position, NodeProps, useReactFlow, useEdges, useNodes } from "@xyflow/react";
import { Trash2, Pencil, Check, X, Zap } from "lucide-react";
import NodeValidationBadge from "./NodeValidationBadge";
import { ANCHOR_SIDES, anchorHandleId, type AnchorSide } from "./portSystem";
import { computeNodeIdMap, buildNodeIdTooltip } from "./nodeIdSystem";
import { useNodeIdVisible, useNodeIdDebug, useLabelNormalization, useCompactNode } from "./nodeIdVisibility";
import NodeIdDebugOverlay, { nodeIdDebugRingClass } from "./NodeIdDebugOverlay";
import { AutoFitLabel } from "./AutoFitLabel";
import { getNodeProcurement } from "@/lib/procurementSync";

// ── Category-based color accents ──
const equipColors: Record<string, { border: string; bg: string; icon: string }> = {
  "Mechanical Vapor Compression Distillation": { border: "border-blue-400/50", bg: "bg-blue-50 dark:bg-blue-950/30", icon: "text-blue-500" },
  "Multi Effect Distillation":                 { border: "border-blue-400/50", bg: "bg-blue-50 dark:bg-blue-950/30", icon: "text-blue-500" },
  "Multi Effect Humidification":               { border: "border-blue-400/50", bg: "bg-blue-50 dark:bg-blue-950/30", icon: "text-blue-500" },
  "Water Treatment": { border: "border-blue-400/50", bg: "bg-blue-50 dark:bg-blue-950/30", icon: "text-blue-500" },
  Electrolyzer:        { border: "border-teal-400/50", bg: "bg-teal-50 dark:bg-teal-950/30", icon: "text-teal-600" },
  "Electrolyzer 1":    { border: "border-teal-400/50", bg: "bg-teal-50 dark:bg-teal-950/30", icon: "text-teal-600" },
  "Electrolyzer 2":    { border: "border-teal-400/50", bg: "bg-teal-50 dark:bg-teal-950/30", icon: "text-teal-600" },
  "Deoxidation Unit":  { border: "border-indigo-400/50", bg: "bg-indigo-50 dark:bg-indigo-950/30", icon: "text-indigo-500" },
  "Dryer Unit":        { border: "border-indigo-400/50", bg: "bg-indigo-50 dark:bg-indigo-950/30", icon: "text-indigo-500" },
  "Deoxidation & Dryer Unit": { border: "border-indigo-400/50", bg: "bg-indigo-50 dark:bg-indigo-950/30", icon: "text-indigo-500" },
  Compressor:                { border: "border-amber-400/50", bg: "bg-amber-50 dark:bg-amber-950/30", icon: "text-amber-600" },
  "Hydrogen Compressor":     { border: "border-amber-400/50", bg: "bg-amber-50 dark:bg-amber-950/30", icon: "text-amber-600" },
  "H₂ Compressor":          { border: "border-amber-400/50", bg: "bg-amber-50 dark:bg-amber-950/30", icon: "text-amber-600" },
  Storage:                   { border: "border-emerald-400/50", bg: "bg-emerald-50 dark:bg-emerald-950/30", icon: "text-emerald-600" },
  "Hydrogen Storage Tank":   { border: "border-emerald-400/50", bg: "bg-emerald-50 dark:bg-emerald-950/30", icon: "text-emerald-600" },
  "Fuel Cell":               { border: "border-yellow-400/50", bg: "bg-yellow-50 dark:bg-yellow-950/30", icon: "text-yellow-600" },
  "H2 Motor":                { border: "border-yellow-400/50", bg: "bg-yellow-50 dark:bg-yellow-950/30", icon: "text-yellow-600" },
  "Hydrogen Motor":          { border: "border-yellow-400/50", bg: "bg-yellow-50 dark:bg-yellow-950/30", icon: "text-yellow-600" },
  "Re-Electrification Unit": { border: "border-yellow-400/50", bg: "bg-yellow-50 dark:bg-yellow-950/30", icon: "text-yellow-600" },
  "Methanol Synthesis Reactor": { border: "border-purple-400/50", bg: "bg-purple-50 dark:bg-purple-950/30", icon: "text-purple-600" },
  "Fischer Tropsch Reactor":    { border: "border-purple-400/50", bg: "bg-purple-50 dark:bg-purple-950/30", icon: "text-purple-600" },
  "Ammonia Synthesis Reactor":  { border: "border-purple-400/50", bg: "bg-purple-50 dark:bg-purple-950/30", icon: "text-purple-600" },
  "DAC Contactor":      { border: "border-orange-400/50", bg: "bg-orange-50 dark:bg-orange-950/30", icon: "text-orange-600" },
  "Direct Air Capture": { border: "border-orange-400/50", bg: "bg-orange-50 dark:bg-orange-950/30", icon: "text-orange-600" },
  "Gas Mixer":       { border: "border-pink-400/50", bg: "bg-pink-50 dark:bg-pink-950/30", icon: "text-pink-600" },
  "Liquid Mixer":    { border: "border-pink-400/50", bg: "bg-pink-50 dark:bg-pink-950/30", icon: "text-pink-600" },
  Valve:             { border: "border-slate-400/50", bg: "bg-slate-50 dark:bg-slate-800/30", icon: "text-slate-500" },
  Pump:              { border: "border-blue-400/50", bg: "bg-blue-50 dark:bg-blue-950/30", icon: "text-blue-500" },
  "Direct Ocean Capture": { border: "border-teal-400/50", bg: "bg-teal-50 dark:bg-teal-950/30", icon: "text-teal-600" },
};

const defaultColors = { border: "border-primary/30", bg: "bg-card", icon: "text-primary" };

function getEquipColors(label: string) {
  if (equipColors[label]) return equipColors[label];
  // For merged equipment ("A & B"), try to match the first component's color
  if (label.includes(" & ")) {
    const first = label.split(" & ")[0].trim();
    if (equipColors[first]) return equipColors[first];
  }
  return defaultColors;
}

const SIDE_TO_POSITION: Record<AnchorSide, Position> = {
  top: Position.Top,
  right: Position.Right,
  bottom: Position.Bottom,
  left: Position.Left,
};

const EquipmentNode = memo(({ data, id }: NodeProps) => {
  const label = data.label as string;
  const subtitle = data.subtitle as string | undefined;
  const colors = getEquipColors(label);
  const { setNodes, deleteElements } = useReactFlow();
  const edges = useEdges();
  const allNodes = useNodes();
  const labelOpts = useLabelNormalization();
  const idInfo = useMemo(() => computeNodeIdMap(allNodes, labelOpts).get(id), [allNodes, id, labelOpts]);
  const idTooltip = useMemo(() => buildNodeIdTooltip(id, label, idInfo), [id, label, idInfo]);
  const showIds = useNodeIdVisible();
  const debugIds = useNodeIdDebug();
  const compact = useCompactNode();
  const debugRing = nodeIdDebugRingClass(label, idInfo, debugIds);
  const [editing, setEditing] = useState(false);
  const [editLabel, setEditLabel] = useState(label);
  const [editSubtitle, setEditSubtitle] = useState(subtitle ?? "");

  // Listen for "rename" requests dispatched by the canvas right-click menu.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ id: string }>).detail;
      if (detail?.id !== id) return;
      setEditLabel(label);
      setEditSubtitle(subtitle ?? "");
      setEditing(true);
    };
    window.addEventListener("canvas:node-rename", handler);
    return () => window.removeEventListener("canvas:node-rename", handler);
  }, [id, label, subtitle]);

  // Detect electricity-consumption purely from edges (drives the ⚡ badge).
  const consumesElectricity = useMemo(() => {
    for (const e of edges) {
      if ((e.source === id || e.target === id) && (e.data as Record<string, unknown>)?.isElectricity) {
        return true;
      }
    }
    return false;
  }, [edges, id]);

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteElements({ nodes: [{ id }] });
  };

  const handleSave = () => {
    setNodes((nds) => nds.map((n) => n.id === id ? { ...n, data: { ...n.data, label: editLabel, subtitle: editSubtitle || undefined } } : n));
    setEditing(false);
  };

  const procurement = getNodeProcurement({ id, data, type: "equipment", position: { x: 0, y: 0 } } as any);
  const hasManufacturer = !!procurement;

  return (
    <div className="relative group">
      <NodeValidationBadge nodeId={id} />

      {/* ── 4 anchor connection points (top/right/bottom/left midpoints) ──
           Each side renders a stacked source + target handle so the user
           can drag a connection in either direction from any anchor. */}
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

      <div title={idTooltip} className={`${compact ? "w-[130px] min-h-[64px] gap-0.5 px-2 py-2" : "w-[150px] min-h-[78px] gap-1 px-2.5 py-2.5"} relative rounded-lg border bg-card ${(data.isCriticalPath as boolean) ? "border-amber-500 ring-1 ring-amber-400/40" : colors.border} flex flex-col items-center justify-center shadow-sm transition-all group-hover:shadow-md group-hover:scale-[1.02] ${(data.criticalPathMode as boolean) ? "cursor-pointer ring-2 ring-amber-400/60" : ""} ${debugRing}`}>
        <NodeIdDebugOverlay label={label} info={idInfo} />
        {/* Critical path badge */}
        {(data.isCriticalPath as boolean) && (
          <div className="absolute -top-2 left-1/2 -translate-x-1/2 bg-amber-500 text-white text-[8px] font-bold px-1.5 py-0.5 rounded-full uppercase tracking-wider z-10">
            Critical
          </div>
        )}
        {/* Procurement status dot */}
        <div className={`absolute top-1.5 left-1.5 h-2 w-2 rounded-full ${hasManufacturer ? "bg-success" : "bg-warning animate-pulse"}`} title={hasManufacturer ? `Manufacturer: ${data.manufacturer}` : "Missing manufacturer"} />

        {/* ⚡ Electricity consumption badge */}
        {consumesElectricity && (
          <div
            className="absolute -top-1.5 -left-1.5 h-4 w-4 rounded-full bg-amber-100 dark:bg-amber-900/60 border border-amber-300 dark:border-amber-600 flex items-center justify-center z-10"
            title="Consumes electricity"
          >
            <Zap className="h-2.5 w-2.5 text-amber-500" />
          </div>
        )}

        {/* Action buttons */}
        <div className="absolute -top-2 -right-2 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity z-10">
          <button onClick={() => { setEditLabel(label); setEditSubtitle(subtitle ?? ""); setEditing(true); }} className="h-5 w-5 rounded-full bg-accent border border-border flex items-center justify-center hover:bg-primary hover:text-primary-foreground transition-colors">
            <Pencil className="h-2.5 w-2.5" />
          </button>
          <button onClick={handleDelete} className="h-5 w-5 rounded-full bg-accent border border-border flex items-center justify-center hover:bg-destructive hover:text-destructive-foreground transition-colors">
            <Trash2 className="h-2.5 w-2.5" />
          </button>
        </div>

        {editing ? (
          <div className="flex flex-col items-center gap-1">
            <input
              autoFocus
              value={editLabel}
              onChange={(e) => setEditLabel(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") setEditing(false); }}
              className="w-24 text-[9px] text-center bg-background border border-border rounded px-1 py-0.5 text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              placeholder="Name"
            />
            <input
              value={editSubtitle}
              onChange={(e) => setEditSubtitle(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") setEditing(false); }}
              className="w-24 text-[9px] text-center bg-background border border-border rounded px-1 py-0.5 text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              placeholder="e.g. 30 bar"
            />
            <div className="flex gap-0.5">
              <button onClick={handleSave} className="text-success"><Check className="h-3 w-3" /></button>
              <button onClick={() => setEditing(false)} className="text-muted-foreground"><X className="h-3 w-3" /></button>
            </div>
          </div>
        ) : (
          <div className={`w-full flex flex-col items-center text-center ${compact ? "gap-0.5" : "gap-1.5"}`}>
            {/* Always-visible name label */}
            <div className="w-full px-1 max-w-full overflow-hidden">
              <AutoFitLabel
                text={label}
                maxSize={compact ? 12 : 14}
                minSize={compact ? 9 : 10}
                lineHeight={1.2}
                className="canvas-node-label canvas-node-label--boost font-extrabold text-card-foreground"
              />
            </div>
            {showIds && (
              <div className="flex flex-row items-baseline gap-1 justify-center leading-[1.1]">
                <span className={`canvas-node-id ${compact ? "text-[9px]" : "text-[10px]"} font-bold tracking-wide leading-[1.1] ${colors.icon}`} style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
                  {idInfo?.displayId ?? "E?"}
                </span>
                {idInfo?.duplicateIndex !== undefined && (
                  <span className="text-[7px] font-semibold text-muted-foreground leading-[1.1]">#{idInfo.duplicateIndex}</span>
                )}
              </div>
            )}
            {subtitle && (
              <p className="text-[10px] font-medium text-muted-foreground leading-[1.2]">{subtitle}</p>
            )}
            {(data.isCriticalPath as boolean) && (data.operatingHours as number) && (
              <p className="text-[8px] font-mono text-amber-600 dark:text-amber-400 leading-[1.2]">
                {(data.operatingHours as number).toLocaleString()} h/yr
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
});
EquipmentNode.displayName = "EquipmentNode";

export default EquipmentNode;
