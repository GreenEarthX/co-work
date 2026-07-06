import type { Node } from "@xyflow/react";

export const BOUNDARY_PADDING = 60;
export const BOUNDARY_TOP_PADDING = 50;

export interface BoundaryRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ManualPadding {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/** Compute the minimum rect that wraps all equipment + carrier nodes, plus padding. */
export function computeBoundaryRect(
  nodes: Node[],
  manualPadding: ManualPadding = { left: 0, right: 0, top: 0, bottom: 0 },
): BoundaryRect | null {
  const inner = nodes.filter((n) => n.type === "equipment" || n.type === "carrier");
  if (inner.length === 0) return null;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of inner) {
    const nw = n.type === "carrier" ? 72 : 140;
    const nh = n.type === "carrier" ? 72 : 80;
    minX = Math.min(minX, n.position.x);
    minY = Math.min(minY, n.position.y);
    maxX = Math.max(maxX, n.position.x + nw);
    maxY = Math.max(maxY, n.position.y + nh);
  }
  return {
    x: minX - BOUNDARY_PADDING - manualPadding.left,
    y: minY - BOUNDARY_PADDING - BOUNDARY_TOP_PADDING - manualPadding.top,
    w: maxX - minX + BOUNDARY_PADDING * 2 + manualPadding.left + manualPadding.right,
    h: maxY - minY + BOUNDARY_PADDING * 2 + BOUNDARY_TOP_PADDING + manualPadding.top + manualPadding.bottom,
  };
}

/** Synthesize a boundary node from a rect. Used when no boundary exists yet. */
export function makeBoundaryNode(rect: BoundaryRect): Node {
  return {
    id: "b-system",
    type: "boundary",
    position: { x: rect.x, y: rect.y },
    data: { width: rect.w, height: rect.h, orientation: "horizontal" },
    draggable: false,
    selectable: false,
    zIndex: -1,
  };
}

/** Returns the next nodes array after adding `newNode`, auto-creating a boundary
 *  in the same update if the new node is the first equipment/carrier. */
export function addNodeWithBoundary(
  current: Node[],
  newNode: Node,
  manualPadding?: ManualPadding,
): Node[] {
  const next = [...current, newNode];
  const isInner = newNode.type === "equipment" || newNode.type === "carrier";
  const hasBoundary = current.some((n) => n.type === "boundary");
  if (!isInner || hasBoundary) return next;
  const rect = computeBoundaryRect(next, manualPadding);
  if (!rect) return next;
  return [makeBoundaryNode(rect), ...next];
}