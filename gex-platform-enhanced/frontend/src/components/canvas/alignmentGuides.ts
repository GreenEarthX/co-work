/**
 * alignmentGuides — magnetic-snap helpers for node dragging.
 *
 * While the user drags a node, we compare its candidate position against
 * every other node's edges + centers on both axes. When a candidate line
 * is within `THRESHOLD` (in canvas pixels), we snap the dragged node to
 * that line and emit a guide so the canvas can render a thin overlay
 * spanning the involved nodes.
 */

export const SNAP_THRESHOLD = 6;

export interface NodeRect {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface AlignmentGuide {
  /** "v" = vertical line (constant x), "h" = horizontal line (constant y). */
  orientation: "v" | "h";
  /** Canvas coordinate of the line. */
  position: number;
  /** Min/max along the perpendicular axis — used to size the overlay. */
  start: number;
  end: number;
}

export function nodeDimsByType(type?: string): { w: number; h: number } {
  if (type === "gate") return { w: 170, h: 100 };
  if (type === "carrier") return { w: 82, h: 82 };
  if (type === "boundary") return { w: 0, h: 0 };
  return { w: 150, h: 100 };
}

/**
 * Compute the snapped position + active guides for a single dragged node.
 * Returns the candidate unchanged (and no guides) if nothing is near.
 */
export function computeSnap(
  draggedId: string,
  candidate: { x: number; y: number },
  draggedDims: { w: number; h: number },
  others: NodeRect[],
  threshold: number = SNAP_THRESHOLD,
): { position: { x: number; y: number }; guides: AlignmentGuide[] } {
  const dW = draggedDims.w;
  const dH = draggedDims.h;

  // Candidate edge/center lines on each axis for the dragged node.
  const dxLines = [candidate.x, candidate.x + dW / 2, candidate.x + dW];
  const dyLines = [candidate.y, candidate.y + dH / 2, candidate.y + dH];

  let bestX: { delta: number; line: number } | null = null;
  let bestY: { delta: number; line: number } | null = null;
  const xMatches: Array<{ line: number; other: NodeRect }> = [];
  const yMatches: Array<{ line: number; other: NodeRect }> = [];

  for (const o of others) {
    if (o.id === draggedId || o.w === 0) continue;
    const oxLines = [o.x, o.x + o.w / 2, o.x + o.w];
    const oyLines = [o.y, o.y + o.h / 2, o.y + o.h];

    for (let i = 0; i < dxLines.length; i++) {
      for (const ox of oxLines) {
        const diff = ox - dxLines[i];
        if (Math.abs(diff) <= threshold) {
          if (!bestX || Math.abs(diff) < Math.abs(bestX.delta)) {
            bestX = { delta: diff, line: ox };
          }
          if (Math.abs(ox - (bestX?.line ?? ox)) < 0.5) xMatches.push({ line: ox, other: o });
        }
      }
    }
    for (let i = 0; i < dyLines.length; i++) {
      for (const oy of oyLines) {
        const diff = oy - dyLines[i];
        if (Math.abs(diff) <= threshold) {
          if (!bestY || Math.abs(diff) < Math.abs(bestY.delta)) {
            bestY = { delta: diff, line: oy };
          }
          if (Math.abs(oy - (bestY?.line ?? oy)) < 0.5) yMatches.push({ line: oy, other: o });
        }
      }
    }
  }

  const position = {
    x: bestX ? candidate.x + bestX.delta : candidate.x,
    y: bestY ? candidate.y + bestY.delta : candidate.y,
  };

  const guides: AlignmentGuide[] = [];
  if (bestX) {
    const involved = xMatches.filter((m) => Math.abs(m.line - bestX!.line) < 0.5).map((m) => m.other);
    const ys = involved.flatMap((o) => [o.y, o.y + o.h]);
    ys.push(position.y, position.y + dH);
    guides.push({
      orientation: "v",
      position: bestX.line,
      start: Math.min(...ys) - 8,
      end: Math.max(...ys) + 8,
    });
  }
  if (bestY) {
    const involved = yMatches.filter((m) => Math.abs(m.line - bestY!.line) < 0.5).map((m) => m.other);
    const xs = involved.flatMap((o) => [o.x, o.x + o.w]);
    xs.push(position.x, position.x + dW);
    guides.push({
      orientation: "h",
      position: bestY.line,
      start: Math.min(...xs) - 8,
      end: Math.max(...xs) + 8,
    });
  }

  return { position, guides };
}