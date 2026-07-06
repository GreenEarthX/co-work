/**
 * Port System — minimal 4-anchor connection model.
 *
 * Every node exposes exactly 4 anchors at the midpoint of each side:
 *   a-top, a-right, a-bottom, a-left
 *
 * Each anchor renders as TWO React Flow handles overlapping at the same
 * coordinate — one of type "source" (suffix `-s`) and one of type "target"
 * (suffix `-t`) — so the user can drag a connection in either direction
 * from any side.
 *
 * Carrier-color helpers stay here because edges, legend, and overrides
 * still resolve stream color from the carrier label.
 */

import { getCarrierColorOverride } from "@/lib/carrierColorOverrides";

export type AnchorSide = "top" | "right" | "bottom" | "left";

/** All 4 anchor sides. */
export const ANCHOR_SIDES: readonly AnchorSide[] = ["top", "right", "bottom", "left"];

/** Build the React Flow handle ID for an anchor. */
export function anchorHandleId(side: AnchorSide, role: "source" | "target"): string {
  return `a-${side}-${role === "source" ? "s" : "t"}`;
}

/** Extract the side from an anchor handle ID; null if not an anchor handle. */
export function sideFromAnchorHandle(handleId: string | null | undefined): AnchorSide | null {
  if (!handleId) return null;
  if (handleId === "a-top-s" || handleId === "a-top-t") return "top";
  if (handleId === "a-right-s" || handleId === "a-right-t") return "right";
  if (handleId === "a-bottom-s" || handleId === "a-bottom-t") return "bottom";
  if (handleId === "a-left-s" || handleId === "a-left-t") return "left";
  return null;
}

/** ── Carrier color table (unchanged) ── */
const STREAM_PORT_ENTRIES: Array<{ color: string; id: string; resource: string }> = [
  { color: "hsl(45, 85%, 45%)",   id: "elec",  resource: "Electricity" },
  { color: "hsl(170, 70%, 40%)",  id: "sea",   resource: "Seawater" },
  { color: "hsl(220, 75%, 55%)",  id: "water", resource: "Water" },
  { color: "hsl(152, 50%, 42%)",  id: "h2",    resource: "Hydrogen" },
  { color: "hsl(199, 90%, 60%)",  id: "o2",    resource: "Oxygen" },
  { color: "hsl(0, 65%, 50%)",    id: "heat",  resource: "Heat" },
  { color: "hsl(25, 25%, 40%)",   id: "waste", resource: "Wastewater" },
  { color: "hsl(20, 90%, 55%)",   id: "co2",   resource: "CO₂" },
  { color: "hsl(270, 45%, 55%)",  id: "meoh",  resource: "Methanol" },
  { color: "hsl(215, 15%, 65%)",  id: "air",   resource: "Air" },
  { color: "hsl(185, 80%, 45%)",  id: "cool",  resource: "Cooling Water" },
  { color: "hsl(330, 75%, 55%)",  id: "n2",    resource: "Nitrogen" },
  { color: "hsl(45, 90%, 50%)",   id: "biogas", resource: "Biogas" },
];

const colorToPortMap = new Map(STREAM_PORT_ENTRIES.map((e) => [e.color, e]));
const idToColorMap = new Map(STREAM_PORT_ENTRIES.map((e) => [e.id, e.color]));
const resourceToColorMap = new Map(STREAM_PORT_ENTRIES.map((e) => [e.resource, e.color]));

function hashHue(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) % 360;
  return h;
}

export function getColorFromResource(resource: string): string {
  const override = getCarrierColorOverride(resource);
  if (override) return override;
  const known = resourceToColorMap.get(resource);
  if (known) return known;
  const hue = hashHue(resource);
  const generated = `hsl(${hue}, 55%, 50%)`;
  resourceToColorMap.set(resource, generated);
  return generated;
}

export function getPortIdFromColor(streamColor: string): string {
  return colorToPortMap.get(streamColor)?.id || "default";
}

export function getColorFromPortId(portId: string): string {
  return idToColorMap.get(portId) || "#888";
}

/**
 * Sane default handle pair for seed-data edges that don't know node positions.
 * Source exits the right side, target enters the left side.
 */
export function getEdgeHandles(
  _sourceId: string,
  _targetId: string,
  _streamColor: string,
): { sourceHandle: string; targetHandle: string } {
  return {
    sourceHandle: anchorHandleId("right", "source"),
    targetHandle: anchorHandleId("left", "target"),
  };
}

/**
 * Pick the side closest to the other node (used as a fallback when React
 * Flow gives us a connection without an explicit handle ID).
 */
export function pickClosestAnchor(
  selfPos: { x: number; y: number },
  selfDims: { w: number; h: number },
  otherPos: { x: number; y: number },
  otherDims: { w: number; h: number },
): AnchorSide {
  const sc = { x: selfPos.x + selfDims.w / 2, y: selfPos.y + selfDims.h / 2 };
  const oc = { x: otherPos.x + otherDims.w / 2, y: otherPos.y + otherDims.h / 2 };
  const dx = oc.x - sc.x;
  const dy = oc.y - sc.y;
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? "right" : "left";
  return dy >= 0 ? "bottom" : "top";
}

function nodeDims(type?: string): { w: number; h: number } {
  if (type === "gate") return { w: 160, h: 80 };
  if (type === "carrier") return { w: 82, h: 82 };
  return { w: 140, h: 80 };
}

/**
 * Map a legacy handle ID (from saved plants pre-anchor-system) to its
 * new anchor equivalent. Read-time only — never written back.
 */
export function migrateLegacyHandle(
  h: string | null | undefined,
  role: "source" | "target",
): string | null {
  if (!h) return null;
  if (sideFromAnchorHandle(h)) return h;
  if (h.startsWith("top-") || h.startsWith("carrier-top")) return anchorHandleId("top", role);
  if (h.startsWith("bot-") || h.startsWith("carrier-bottom")) return anchorHandleId("bottom", role);
  if (h.startsWith("out-") || h.startsWith("right-") || h.startsWith("carrier-right")) return anchorHandleId("right", role);
  if (h.startsWith("in-") || h.startsWith("left-") || h.startsWith("carrier-left")) return anchorHandleId("left", role);
  if (h.startsWith("default-top")) return anchorHandleId("top", role);
  if (h.startsWith("default-bottom") || h.startsWith("default-bot")) return anchorHandleId("bottom", role);
  if (h.startsWith("default-out")) return anchorHandleId("right", role);
  if (h.startsWith("default-in")) return anchorHandleId("left", role);
  if (h.startsWith("default")) return anchorHandleId(role === "source" ? "right" : "left", role);
  // Reconnect drop-handle leftovers
  if (h.includes("reconnect")) return anchorHandleId(role === "source" ? "right" : "left", role);
  return null;
}

/**
 * Normalize a freshly-made connection:
 *   - Enforce drag direction (start node = source).
 *   - Keep the user-chosen anchor handles. Map legacy IDs through migration.
 *   - Fall back to the side closest to the counterpart node when missing.
 */
export function normalizeConnection(params: {
  rawSource: string | null | undefined;
  rawTarget: string | null | undefined;
  rawSourceHandle?: string | null | undefined;
  rawTargetHandle?: string | null | undefined;
  startNodeId: string | null | undefined;
  nodes: Array<{ id: string; type?: string; position: { x: number; y: number } }>;
}): {
  source: string;
  target: string;
  sourceHandle: string;
  targetHandle: string;
} | null {
  const { rawSource, rawTarget, startNodeId, nodes } = params;
  if (!rawSource || !rawTarget) return null;
  if (rawSource === rawTarget) return null;

  let source = rawSource;
  let target = rawTarget;
  let sourceHandleRaw = params.rawSourceHandle ?? null;
  let targetHandleRaw = params.rawTargetHandle ?? null;
  if (startNodeId && startNodeId === rawTarget && startNodeId !== rawSource) {
    source = rawTarget;
    target = rawSource;
    [sourceHandleRaw, targetHandleRaw] = [targetHandleRaw, sourceHandleRaw];
  }

  const sourceNode = nodes.find((n) => n.id === source);
  const targetNode = nodes.find((n) => n.id === target);
  if (!sourceNode || !targetNode) return null;

  let sourceHandle = migrateLegacyHandle(sourceHandleRaw, "source");
  let targetHandle = migrateLegacyHandle(targetHandleRaw, "target");

  if (!sourceHandle) {
    const sd = nodeDims(sourceNode.type);
    const td = nodeDims(targetNode.type);
    const side = pickClosestAnchor(sourceNode.position, sd, targetNode.position, td);
    sourceHandle = anchorHandleId(side, "source");
  }
  if (!targetHandle) {
    const sd = nodeDims(sourceNode.type);
    const td = nodeDims(targetNode.type);
    const side = pickClosestAnchor(targetNode.position, td, sourceNode.position, sd);
    targetHandle = anchorHandleId(side, "target");
  }

  // Endpoints may have been picked up via the invisible target overlay
  // that sits over each source dot. Coerce the role suffix so the edge
  // references handles that actually exist for that role — otherwise
  // React Flow can't resolve them and the edge silently fails to render.
  const srcSide = sideFromAnchorHandle(sourceHandle);
  const tgtSide = sideFromAnchorHandle(targetHandle);
  if (srcSide) sourceHandle = anchorHandleId(srcSide, "source");
  if (tgtSide) targetHandle = anchorHandleId(tgtSide, "target");

  return { source, target, sourceHandle, targetHandle };
}
