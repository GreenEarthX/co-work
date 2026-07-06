import { memo, useState, useMemo, useEffect } from "react";
import { Handle, Position, NodeProps, useReactFlow, useEdges, useNodes } from "@xyflow/react";
import { Trash2, Pencil, Check, X, ArrowUpRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import NodeValidationBadge from "./NodeValidationBadge";
import { getCarrierIcon } from "./iconRegistry";
import { getColorFromResource, ANCHOR_SIDES, anchorHandleId, type AnchorSide } from "./portSystem";
import { getCarrierColorOverride, parseColor } from "@/lib/carrierColorOverrides";
import { useCarrierColorVersion } from "@/hooks/useCarrierColorVersion";
import { computeNodeIdMap, buildNodeIdTooltip } from "./nodeIdSystem";
import { useNodeIdVisible, useNodeIdDebug, useLabelNormalization } from "./nodeIdVisibility";
import NodeIdDebugOverlay, { nodeIdDebugRingClass } from "./NodeIdDebugOverlay";
import { AutoFitLabel } from "./AutoFitLabel";

// ── Every carrier type gets a card with a colored border + light tinted bg ──
// Built-in carrier chrome: vivid border + light tinted fill + brand icon.
// Label text always uses a single high-contrast color for legibility.
// `glow` is an rgba string used to render a soft outer halo around the bubble.
const carrierStyles: Record<string, { border: string; bg: string; iconColor: string; textColor: string; glow: string }> = {
  Electricity: { border: "border-amber-400",   bg: "bg-amber-50 dark:bg-amber-950/40",     iconColor: "text-amber-700",   textColor: "text-amber-800 dark:text-amber-200",     glow: "251,191,36" },
  Seawater:    { border: "border-teal-400",    bg: "bg-teal-50 dark:bg-teal-950/40",       iconColor: "text-teal-700",    textColor: "text-teal-800 dark:text-teal-200",       glow: "45,212,191" },
  Water:       { border: "border-blue-400",    bg: "bg-blue-50 dark:bg-blue-950/40",       iconColor: "text-blue-700",    textColor: "text-blue-800 dark:text-blue-200",       glow: "96,165,250" },
  Hydrogen:    { border: "border-emerald-400", bg: "bg-emerald-50 dark:bg-emerald-950/40", iconColor: "text-emerald-700", textColor: "text-emerald-800 dark:text-emerald-200", glow: "52,211,153" },
  Oxygen:      { border: "border-sky-400",     bg: "bg-sky-50 dark:bg-sky-950/40",         iconColor: "text-sky-700",     textColor: "text-sky-800 dark:text-sky-200",         glow: "56,189,248" },
  Nitrogen:    { border: "border-indigo-400",  bg: "bg-indigo-50 dark:bg-indigo-950/40",   iconColor: "text-indigo-700",  textColor: "text-indigo-800 dark:text-indigo-200",   glow: "129,140,248" },
  "CO₂":      { border: "border-orange-400",  bg: "bg-orange-50 dark:bg-orange-950/40",   iconColor: "text-orange-700",  textColor: "text-orange-800 dark:text-orange-200",   glow: "251,146,60" },
  Heat:        { border: "border-red-400",     bg: "bg-red-50 dark:bg-red-950/40",         iconColor: "text-red-700",     textColor: "text-red-800 dark:text-red-200",         glow: "248,113,113" },
  Methanol:    { border: "border-purple-400",  bg: "bg-purple-50 dark:bg-purple-950/40",   iconColor: "text-purple-700",  textColor: "text-purple-800 dark:text-purple-200",   glow: "192,132,252" },
  Wastewater:  { border: "border-stone-500",   bg: "bg-stone-100 dark:bg-stone-800/40",    iconColor: "text-stone-700",   textColor: "text-stone-800 dark:text-stone-200",     glow: "120,113,108" },
  Air:         { border: "border-slate-400",   bg: "bg-slate-50 dark:bg-slate-800/40",     iconColor: "text-slate-600",   textColor: "text-slate-700 dark:text-slate-200",     glow: "148,163,184" },
};

const defaultStyle = { border: "border-emerald-400", bg: "bg-emerald-50 dark:bg-emerald-950/40", iconColor: "text-emerald-700", textColor: "text-emerald-800 dark:text-emerald-200", glow: "52,211,153" };

const SIDE_TO_POSITION: Record<AnchorSide, Position> = {
  top: Position.Top,
  right: Position.Right,
  bottom: Position.Bottom,
  left: Position.Left,
};

const CarrierNode = memo(({ data, id }: NodeProps) => {
  const label = data.label as string;
  // Re-render whenever a carrier color override changes (live legend recolor).
  useCarrierColorVersion();
  const override = getCarrierColorOverride(label);
  // If the user explicitly recolored this carrier, treat it as custom-styled
  // so the override takes effect even on built-in carriers (Hydrogen, etc.).
  const style = override ? null : carrierStyles[label] || null;
  const Icon = getCarrierIcon(label);
  const isCustom = !style;
  const cfg = style || defaultStyle;
  const customColor = isCustom ? getColorFromResource(label) : undefined;
  // Build a translucent fill for the bubble that works for hex, rgb() AND
  // hsl() values (string-concatenating "66" only worked for hex, leaving
  // hsl-based carriers without any fill).
  // Build a vivid bubble for custom/overridden carriers: a light tinted fill
  // (~18% alpha so it stays soft) plus a saturated text color picked from
  // the brand color but darkened/lightened for contrast.
  // Use a much more saturated fill (~85% alpha) and pick pure black or white
  // text — this stays legible at canvas zoom-out where tinted brand text on
  // a pale wash becomes unreadable.
  const customStyle = useMemo(() => {
    if (!customColor) return { fill: undefined as string | undefined, border: undefined as string | undefined, text: undefined as string | undefined, glow: undefined as string | undefined };
    const rgb = parseColor(customColor);
    if (!rgb) return { fill: customColor, border: customColor, text: "#0b1220", glow: undefined };
    // Match the built-in carrier visual language (e.g. Heat / Hydrogen):
    //  - OPAQUE pale tint blended over white (like Tailwind ~50), so the
    //    bubble reads cleanly against any canvas background instead of
    //    going washed-out where 10%-alpha gets diluted by the dotted grid.
    //  - lightened border (mix toward white, like Tailwind ~400)
    //  - bold same-hue text (darkened ~40%, like Tailwind ~800)
    //  - soft same-hue glow
    const blend = (c: number, t: number) => Math.round(c + (255 - c) * t);
    const fillR = blend(rgb.r, 0.92);
    const fillG = blend(rgb.g, 0.92);
    const fillB = blend(rgb.b, 0.92);
    const fill = `rgb(${fillR}, ${fillG}, ${fillB})`;
    const border = `rgb(${blend(rgb.r, 0.25)}, ${blend(rgb.g, 0.25)}, ${blend(rgb.b, 0.25)})`;
    const darken = (c: number) => Math.round(c * 0.40);
    const text = `rgb(${darken(rgb.r)}, ${darken(rgb.g)}, ${darken(rgb.b)})`;
    const glow = `${rgb.r},${rgb.g},${rgb.b}`;
    return { fill, border, text, glow };
  }, [customColor]);
  const { setNodes, deleteElements } = useReactFlow();
  const edges = useEdges();
  const nodes = useNodes();
  const navigate = useNavigate();
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
  const labelOpts = useLabelNormalization();
  const idInfo = useMemo(() => computeNodeIdMap(nodes, labelOpts).get(id), [nodes, id, labelOpts]);
  const idTooltip = useMemo(() => buildNodeIdTooltip(id, label, idInfo), [id, label, idInfo]);
  const showIds = useNodeIdVisible();
  const debugIds = useNodeIdDebug();
  const debugRing = nodeIdDebugRingClass(label, idInfo, debugIds);

  // GAM eligibility: only if this carrier feeds directly into an "offtake" gate
  const isOfftakeCarrier = edges.some((e) => {
    if (e.source !== id) return false;
    const targetNode = nodes.find((n) => n.id === e.target);
    return targetNode?.type === "gate" &&
      typeof targetNode.data?.label === "string" &&
      targetNode.data.label.toLowerCase().includes("offtake");
  });

  // Compute total outgoing flow from this carrier for the GAM badge
  const outgoingFlow = edges
    .filter((e) => e.source === id && e.data?.flowValue != null)
    .reduce((sum, e) => sum + Number(e.data!.flowValue), 0);
  const outgoingUnit = edges.find((e) => e.source === id && e.data?.flowUnit)?.data?.flowUnit as string | undefined;

  const handleOpenGam = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigate("/green-assets");
  };


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
      <div className="absolute -top-3 left-1/2 -translate-x-1/2 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity z-10">
        {isOfftakeCarrier && (
          <button onClick={handleOpenGam} title="View in Project Commercial" className="h-5 w-5 rounded-full bg-primary/90 border border-primary flex items-center justify-center hover:bg-primary hover:scale-110 transition-all text-primary-foreground">
            <ArrowUpRight className="h-2.5 w-2.5" />
          </button>
        )}
        <button onClick={() => setEditing(true)} className="h-5 w-5 rounded-full bg-accent border border-border flex items-center justify-center hover:bg-primary hover:text-primary-foreground transition-colors">
          <Pencil className="h-2.5 w-2.5" />
        </button>
        <button onClick={handleDelete} className="h-5 w-5 rounded-full bg-accent border border-border flex items-center justify-center hover:bg-destructive hover:text-destructive-foreground transition-colors">
          <Trash2 className="h-2.5 w-2.5" />
        </button>
      </div>

      {/* GAM volume badge, shown for tradeable carriers */}
      {isOfftakeCarrier && outgoingFlow > 0 && (
        <button
          onClick={handleOpenGam}
          className="absolute -bottom-7 left-1/2 -translate-x-1/2 flex items-center gap-0.5 bg-primary/10 border border-primary/30 rounded-full px-1.5 py-0.5 text-[7px] font-semibold text-primary hover:bg-primary/20 transition-colors whitespace-nowrap z-10"
          title="Open in Project Commercial"
        >
          <span>{outgoingFlow.toLocaleString()} {outgoingUnit}</span>
          <ArrowUpRight className="h-2 w-2" />
        </button>
      )}

      <div
        title={idTooltip}
        className={`relative h-[78px] w-[78px] rounded-full border-2 flex flex-col items-center justify-center gap-0.5 px-2 transition-all group-hover:scale-[1.05] ${isCustom ? '' : `${cfg.border} ${cfg.bg}`} ${debugRing}`}
        style={{
          ...(isCustom ? { borderColor: customStyle.border, backgroundColor: customStyle.fill } : {}),
          boxShadow: (() => {
            const g = isCustom ? customStyle.glow : cfg.glow;
            if (!g) return undefined;
            return `0 0 0 1px rgba(${g}, 0.18), 0 0 6px 0 rgba(${g}, 0.22)`;
          })(),
        }}
      >
        <NodeIdDebugOverlay label={label} info={idInfo} />
        <Icon className={`h-4 w-4 shrink-0 ${isCustom ? '' : cfg.iconColor}`} style={isCustom ? { color: customStyle.border } : undefined} />
        {editing ? (
          <div className="absolute -bottom-7 left-1/2 -translate-x-1/2 flex items-center gap-0.5 bg-card border border-border rounded px-1 py-0.5 shadow-sm whitespace-nowrap z-20">
            <input
              autoFocus
              value={editLabel}
              onChange={(e) => setEditLabel(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") setEditing(false); }}
              className="w-20 text-[9px] text-center bg-background border border-border rounded px-1 py-0.5 text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <button onClick={handleSave} className="text-success"><Check className="h-3 w-3" /></button>
            <button onClick={() => setEditing(false)} className="text-muted-foreground"><X className="h-3 w-3" /></button>
          </div>
        ) : (
          <div className="w-[64px] flex items-center justify-center">
            <AutoFitLabel
              text={label}
              maxSize={11}
              minSize={8}
              lineHeight={1.1}
              className={`canvas-node-label font-extrabold text-center ${isCustom ? '' : cfg.textColor}`}
              style={isCustom ? { color: customStyle.text } : undefined}
            />
          </div>
        )}
        {!editing && showIds && (
          <div
            className={`canvas-node-id flex flex-col items-center gap-0 leading-none ${isCustom ? '' : cfg.textColor}`}
            style={isCustom ? { color: customStyle.text } : undefined}
          >
            <span className="text-[7px] font-bold tracking-wide">{idInfo?.displayId ?? "C?"}</span>
            {idInfo?.duplicateIndex !== undefined && (
              <span className="text-[6px] font-semibold opacity-80">#{idInfo.duplicateIndex}</span>
            )}
          </div>
        )}
      </div>

    </div>
  );
});
CarrierNode.displayName = "CarrierNode"; // v2

export default CarrierNode;
