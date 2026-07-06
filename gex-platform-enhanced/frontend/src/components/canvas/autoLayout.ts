/**
 * Auto-layout engine — compact, square-ish process flow diagrams.
 *
 * Strategy:
 * 1. Topological layering (longest-path, left→right)
 * 2. Layer compaction — merge sparse adjacent layers to reduce width
 * 3. Carrier promotion — carriers sit between neighbor layers
 * 4. Multi-pass barycenter + transposition — minimizes edge crossings
 * 5. Straight-connection alignment — single-parent nodes align horizontally
 * 6. Vertical centering across layers
 * 7. Aggressive horizontal & vertical compaction
 * 8. Grid snapping for visual polish
 *
 * Never changes components, connections, or logic — only positions.
 */
import type { Node, Edge } from "@xyflow/react";

/* ── Layout constants ── */
const COMPACT_GAP_X = 60;       // horizontal gap between layer right-edge and next layer left-edge
const MIN_GAP_Y = 24;           // minimum vertical gap between nodes in same layer
const PADDING_X = 40;
const PADDING_Y = 40;
const BOUNDARY_MARGIN = 30;
const GRID_SNAP = 20;
const BARYCENTER_ITERATIONS = 8;
/** Max nodes per layer before we stop merging */

/* ── Node sizes ── */
function getNodeSize(node: Node): { w: number; h: number } {
  switch (node.type) {
    case "gate":      return { w: 170, h: 90 };
    case "carrier":   return { w: 82, h: 82 };
    case "equipment": return { w: 150, h: 90 };
    default:          return { w: 140, h: 80 };
  }
}

function snap(v: number): number {
  return Math.round(v / GRID_SNAP) * GRID_SNAP;
}

/* ── Adjacency ── */
interface AdjMap {
  downstream: Map<string, Set<string>>;
  upstream: Map<string, Set<string>>;
}

function buildAdjacency(edges: Edge[]): AdjMap {
  const downstream = new Map<string, Set<string>>();
  const upstream = new Map<string, Set<string>>();
  for (const e of edges) {
    if (!downstream.has(e.source)) downstream.set(e.source, new Set());
    downstream.get(e.source)!.add(e.target);
    if (!upstream.has(e.target)) upstream.set(e.target, new Set());
    upstream.get(e.target)!.add(e.source);
  }
  return { downstream, upstream };
}

/* ── Topological layering (longest-path) ── */
function assignLayers(nodes: Node[], adj: AdjMap): Map<string, number> {
  const layers = new Map<string, number>();
  const nodeIds = new Set(nodes.map((n) => n.id));

  const sources = nodes.filter((n) => {
    if (n.type === "boundary") return false;
    if (n.data.gateType === "input") return true;
    const ups = adj.upstream.get(n.id);
    return !ups || [...ups].filter((u) => nodeIds.has(u)).length === 0;
  });

  const queue: Array<{ id: string; depth: number }> = sources.map((n) => ({
    id: n.id, depth: 0,
  }));

  while (queue.length > 0) {
    const { id, depth } = queue.shift()!;
    const cur = layers.get(id) ?? -1;
    if (depth <= cur) continue;
    layers.set(id, depth);
    const downs = adj.downstream.get(id);
    if (downs) {
      for (const d of downs) {
        if (nodeIds.has(d)) queue.push({ id: d, depth: depth + 1 });
      }
    }
  }

  for (const n of nodes) {
    if (n.type !== "boundary" && !layers.has(n.id)) layers.set(n.id, 0);
  }

  return layers;
}

/**
 * Compact layers: pull nodes forward (toward layer 0) when possible
 * without violating upstream dependencies. This reduces the total
 * number of layers and makes the diagram shorter horizontally.
 */
function compactLayers(
  layerMap: Map<string, number>,
  nodes: Node[],
  adj: AdjMap,
): void {
  // Process nodes in reverse topological order (highest layer first)
  const sorted = [...nodes]
    .filter((n) => n.type !== "boundary")
    .sort((a, b) => (layerMap.get(b.id) ?? 0) - (layerMap.get(a.id) ?? 0));

  for (const n of sorted) {
    const currentLayer = layerMap.get(n.id) ?? 0;
    const ups = adj.upstream.get(n.id);
    if (!ups || ups.size === 0) continue;

    // Minimum layer = max upstream layer + 1
    let minLayer = 0;
    for (const u of ups) {
      const ul = layerMap.get(u);
      if (ul !== undefined) minLayer = Math.max(minLayer, ul + 1);
    }

    // Pull forward if possible
    if (minLayer < currentLayer) {
      layerMap.set(n.id, minLayer);
    }
  }
}

/**
 * Promote carriers: place each carrier between its upstream and downstream layers.
 */
function promoteCarriers(nodes: Node[], layerMap: Map<string, number>, adj: AdjMap): void {
  for (const n of nodes) {
    if (n.type !== "carrier") continue;
    const ups = adj.upstream.get(n.id);
    const downs = adj.downstream.get(n.id);
    const upLayers = ups
      ? [...ups].map((id) => layerMap.get(id)).filter((l) => l !== undefined) as number[]
      : [];
    const downLayers = downs
      ? [...downs].map((id) => layerMap.get(id)).filter((l) => l !== undefined) as number[]
      : [];

    if (upLayers.length > 0 && downLayers.length > 0) {
      const maxUp = Math.max(...upLayers);
      const minDown = Math.min(...downLayers);
      if (minDown > maxUp) {
        layerMap.set(n.id, maxUp + 1);
      }
    }
  }
}

/* ── Type priority for initial ordering ── */
function typePriority(n: Node): number {
  if (n.type === "gate" && n.data.gateType === "input") return -2;
  if (n.type === "gate" && n.data.gateType === "output") return 2;
  if (n.type === "equipment") return 0;
  if (n.type === "carrier") return 1;
  return 3;
}

/* ── Barycenter with median ── */
function computeBarycenter(
  nodeId: string,
  adj: AdjMap,
  posMap: Map<string, number>,
): number {
  const neighbors = [
    ...(adj.upstream.get(nodeId) || []),
    ...(adj.downstream.get(nodeId) || []),
  ];
  const vals: number[] = [];
  for (const id of neighbors) {
    const v = posMap.get(id);
    if (v !== undefined) vals.push(v);
  }
  if (vals.length === 0) return Infinity;
  vals.sort((a, b) => a - b);
  const mid = Math.floor(vals.length / 2);
  return vals.length % 2 === 1
    ? vals[mid]
    : (vals[mid - 1] + vals[mid]) / 2;
}

/**
 * Count edge crossings between two adjacent layers.
 */
function countCrossings(
  leftOrder: string[],
  rightOrder: string[],
  adj: AdjMap,
): number {
  const leftIdx = new Map(leftOrder.map((id, i) => [id, i]));
  const rightIdx = new Map(rightOrder.map((id, i) => [id, i]));
  const pairs: Array<[number, number]> = [];

  for (const [src, targets] of adj.downstream) {
    const li = leftIdx.get(src);
    if (li === undefined) continue;
    for (const tgt of targets) {
      const ri = rightIdx.get(tgt);
      if (ri !== undefined) pairs.push([li, ri]);
    }
  }

  let crossings = 0;
  for (let i = 0; i < pairs.length; i++) {
    for (let j = i + 1; j < pairs.length; j++) {
      if ((pairs[i][0] - pairs[j][0]) * (pairs[i][1] - pairs[j][1]) < 0) {
        crossings++;
      }
    }
  }
  return crossings;
}

/**
 * Adjacent transposition: swap neighboring nodes if it reduces crossings.
 */
function transposeLayer(
  layerOrder: string[],
  prevOrder: string[] | null,
  nextOrder: string[] | null,
  adj: AdjMap,
): boolean {
  let improved = false;
  for (let i = 0; i < layerOrder.length - 1; i++) {
    let crossBefore = 0;
    let crossAfter = 0;

    if (prevOrder) {
      crossBefore += countCrossings(prevOrder, layerOrder, adj);
      const swapped = [...layerOrder];
      [swapped[i], swapped[i + 1]] = [swapped[i + 1], swapped[i]];
      crossAfter += countCrossings(prevOrder, swapped, adj);
    }
    if (nextOrder) {
      crossBefore += countCrossings(layerOrder, nextOrder, adj);
      const swapped = [...layerOrder];
      [swapped[i], swapped[i + 1]] = [swapped[i + 1], swapped[i]];
      crossAfter += countCrossings(swapped, nextOrder, adj);
    }

    if (crossAfter < crossBefore) {
      [layerOrder[i], layerOrder[i + 1]] = [layerOrder[i + 1], layerOrder[i]];
      improved = true;
    }
  }
  return improved;
}

/* ── Overlap resolution ── */
interface PosEntry { node: Node; x: number; y: number }

function resolveVerticalOverlaps(positions: PosEntry[]): void {
  positions.sort((a, b) => a.y - b.y);
  for (let i = 1; i < positions.length; i++) {
    const prev = positions[i - 1];
    const curr = positions[i];
    const minY = prev.y + getNodeSize(prev.node).h + MIN_GAP_Y;
    if (curr.y < minY) curr.y = minY;
  }
}

/**
 * Align nodes with a single upstream parent to the same y-center.
 */
function alignStraightConnections(
  layerPositions: Map<number, PosEntry[]>,
  sortedLayers: number[],
  adj: AdjMap,
  yCenterMap: Map<string, number>,
): void {
  for (let li = 1; li < sortedLayers.length; li++) {
    const positions = layerPositions.get(sortedLayers[li])!;
    for (const p of positions) {
      const ups = adj.upstream.get(p.node.id);
      if (!ups || ups.size !== 1) continue;
      const parentId = [...ups][0];
      const parentCenter = yCenterMap.get(parentId);
      if (parentCenter === undefined) continue;
      const nodeH = getNodeSize(p.node).h;
      p.y = parentCenter - nodeH / 2;
    }
    resolveVerticalOverlaps(positions);
    for (const p of positions) {
      yCenterMap.set(p.node.id, p.y + getNodeSize(p.node).h / 2);
    }
  }
}

/**
 * Center layers vertically so the diagram is balanced.
 */
function centerLayersVertically(
  layerPositions: Map<number, PosEntry[]>,
  sortedLayers: number[],
): void {
  let globalMaxSpan = 0;
  for (const layer of sortedLayers) {
    const positions = layerPositions.get(layer)!;
    if (positions.length === 0) continue;
    const top = positions[0].y;
    const last = positions[positions.length - 1];
    const bottom = last.y + getNodeSize(last.node).h;
    globalMaxSpan = Math.max(globalMaxSpan, bottom - top);
  }

  for (const layer of sortedLayers) {
    const positions = layerPositions.get(layer)!;
    if (positions.length === 0) continue;
    const top = positions[0].y;
    const last = positions[positions.length - 1];
    const bottom = last.y + getNodeSize(last.node).h;
    const span = bottom - top;
    const offset = (globalMaxSpan - span) / 2;
    if (offset > 5) {
      for (const p of positions) p.y += offset;
    }
  }
}

/**
 * Aggressive horizontal compaction: close gaps to COMPACT_GAP_X.
 */
function compactHorizontal(
  layerPositions: Map<number, PosEntry[]>,
  sortedLayers: number[],
): void {
  for (let li = 1; li < sortedLayers.length; li++) {
    const prevPositions = layerPositions.get(sortedLayers[li - 1])!;
    const currPositions = layerPositions.get(sortedLayers[li])!;
    if (prevPositions.length === 0 || currPositions.length === 0) continue;

    let prevRightEdge = 0;
    for (const p of prevPositions) {
      prevRightEdge = Math.max(prevRightEdge, p.x + getNodeSize(p.node).w);
    }

    const currLeftEdge = Math.min(...currPositions.map((p) => p.x));
    const currentGap = currLeftEdge - prevRightEdge;
    const shift = currentGap - COMPACT_GAP_X;

    if (shift > GRID_SNAP) {
      for (const p of currPositions) p.x -= shift;
      for (let lj = li + 1; lj < sortedLayers.length; lj++) {
        for (const p of layerPositions.get(sortedLayers[lj])!) p.x -= shift;
      }
    }
  }
}

/**
 * Compact vertical: pull nodes upward, closing dead space.
 */
function compactVertical(
  layerPositions: Map<number, PosEntry[]>,
  sortedLayers: number[],
): void {
  let globalMinY = Infinity;
  for (const layer of sortedLayers) {
    const positions = layerPositions.get(layer)!;
    if (positions.length > 0) globalMinY = Math.min(globalMinY, positions[0].y);
  }

  if (globalMinY > PADDING_Y + GRID_SNAP) {
    const pull = globalMinY - PADDING_Y;
    for (const layer of sortedLayers) {
      for (const p of layerPositions.get(layer)!) p.y -= pull;
    }
  }

  for (const layer of sortedLayers) {
    const positions = layerPositions.get(layer)!;
    if (positions.length < 2) continue;
    positions.sort((a, b) => a.y - b.y);
    for (let i = 1; i < positions.length; i++) {
      const prev = positions[i - 1];
      const curr = positions[i];
      const idealY = prev.y + getNodeSize(prev.node).h + MIN_GAP_Y;
      if (curr.y > idealY + GRID_SNAP) curr.y = idealY;
    }
  }
}

/**
 * Transpose all node positions (swap x ↔ y) for vertical layout mode.
 * Returns new node array with transposed positions and boundary dimensions.
 */
/**
 * Compute a proper vertical layout (top → bottom) from horizontal positions.
 * - Gates are placed OUTSIDE the boundary (inputs above, outputs below)
 * - Internal nodes are spaced vertically with no overlaps
 * - Boundary is wide enough for comfortable reading / PDF export
 */
export function transposeLayout(nodes: Node[]): Node[] {
  // boundary lookup skipped: // nodes.find((n) => n.type === "boundary");
  const gates = nodes.filter((n) => n.type === "gate");
  const internals = nodes.filter((n) => n.type !== "boundary" && n.type !== "gate");

  // Sort internals by horizontal position (x) — this gives us the process order
  const sorted = [...internals].sort((a, b) => a.position.x - b.position.x);

  // Compute vertical slot positions for internals
  const V_GAP = 120;           // vertical gap between rows
  const H_CENTER = 350;        // horizontal center for the main column
  const CARRIER_SIZE = 82;
  const EQUIP_W = 150;
  const GATE_W = 170;

  // Group by approximate horizontal position (layer) to detect side-by-side nodes
  const layers: Node[][] = [];
  let lastX = -Infinity;
  for (const n of sorted) {
    if (n.position.x - lastX > 80) {
      layers.push([n]);
    } else {
      layers[layers.length - 1].push(n);
    }
    lastX = n.position.x;
  }

  // Assign vertical positions
  const nodePositions = new Map<string, { x: number; y: number }>();
  const BOUNDARY_PAD_TOP = 40;
  let currentY = BOUNDARY_PAD_TOP + 160; // leave room for boundary header + INPUTS label

  for (const layer of layers) {
    const totalWidth = layer.reduce((sum, n) => {
      const w = n.type === "carrier" ? CARRIER_SIZE : EQUIP_W;
      return sum + w;
    }, 0);
    const layerGap = 60;
    const fullWidth = totalWidth + (layer.length - 1) * layerGap;
    let startX = H_CENTER - fullWidth / 2 + 100; // offset into boundary

    const maxH = Math.max(...layer.map((n) => n.type === "carrier" ? CARRIER_SIZE : 100));

    for (const n of layer) {
      const w = n.type === "carrier" ? CARRIER_SIZE : EQUIP_W;
      nodePositions.set(n.id, { x: startX, y: currentY });
      startX += w + layerGap;
    }
    currentY += maxH + V_GAP;
  }

  // Boundary dimensions — wide enough, tall enough to contain all internals
  const allPositions = [...nodePositions.values()];
  const minX = Math.min(...allPositions.map((p) => p.x)) - 80;
  const maxX = Math.max(...allPositions.map((p) => p.x)) + EQUIP_W + 80;
  const maxY = currentY;

  const bW = Math.max(700, maxX - minX);
  const bH = maxY + 40;
  const bX = minX;
  const bY = 120;

  // Gate positions — inputs above boundary, outputs below
  const inputGates = gates.filter((g) => g.data.gateType === "input");
  const outputGates = gates.filter((g) => g.data.gateType === "output");

  const inputSpacing = bW / (inputGates.length + 1);
  const outputSpacing = bW / (outputGates.length + 1);

  // Build the result
  return nodes.map((n) => {
    if (n.type === "boundary") {
      return {
        ...n,
        position: { x: bX, y: bY },
        data: { ...n.data, width: bW, height: bH, orientation: "vertical" },
        style: { ...(n.style || {}), width: bW, height: bH },
      };
    }
    if (n.type === "gate") {
      const isInput = n.data.gateType === "input";
      const gateList = isInput ? inputGates : outputGates;
      const idx = gateList.indexOf(n);
      const spacing = isInput ? inputSpacing : outputSpacing;
      return {
        ...n,
        position: {
          x: bX + spacing * (idx + 1) - GATE_W / 2,
          y: isInput ? 0 : bY + bH + 60,
        },
      };
    }
    const pos = nodePositions.get(n.id);
    if (pos) {
      return { ...n, position: { x: bX + pos.x, y: bY + pos.y } };
    }
    return { ...n, position: { x: n.position.y, y: n.position.x } };
  });
}

/**
 * Reroute edge handles after transposing layout.
 * Uses always-present default handles (default-top, default-bottom,
 * carrier-top, carrier-bottom) so edges connect immediately without
 * waiting for port-specific handles to render.
 */
export function transposeEdgeHandles(
  edges: Edge[],
  nodes: Node[],
  targetOrientation: "horizontal" | "vertical",
): Edge[] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const isVertical = targetOrientation === "vertical";

  return edges.map((e) => {
    const srcNode = nodeMap.get(e.source);
    const tgtNode = nodeMap.get(e.target);

    let sourceHandle: string | undefined;
    let targetHandle: string | undefined;

    if (isVertical) {
      // Vertical: flow goes top → bottom
      sourceHandle = srcNode?.type === "carrier" ? "carrier-bottom" : "default-bottom";
      targetHandle = tgtNode?.type === "carrier" ? "carrier-top" : "default-top";
    } else {
      // Horizontal: flow goes left → right
      sourceHandle = srcNode?.type === "carrier" ? "carrier-right" : "default-out";
      targetHandle = tgtNode?.type === "carrier" ? "carrier-left" : "default-in";
    }

    return {
      ...e,
      sourceHandle,
      targetHandle,
    };
  });
}

/* ── Main entry point ── */
export function autoLayoutNodes(nodes: Node[], edges: Edge[]): Node[] {
  const nonBoundary = nodes.filter((n) => n.type !== "boundary");
  const boundary = nodes.find((n) => n.type === "boundary");

  if (nonBoundary.length === 0) return nodes;

  const adj = buildAdjacency(edges);
  const layerMap = assignLayers(nonBoundary, adj);

  // ── Layer compaction: pull nodes forward to minimize total layers ──
  compactLayers(layerMap, nonBoundary, adj);

  // Promote carriers between their neighbors
  promoteCarriers(nonBoundary, layerMap, adj);

  // Group nodes by layer
  const layerGroups = new Map<number, Node[]>();
  for (const n of nonBoundary) {
    const layer = layerMap.get(n.id) ?? 0;
    if (!layerGroups.has(layer)) layerGroups.set(layer, []);
    layerGroups.get(layer)!.push(n);
  }

  const sortedLayers = [...layerGroups.keys()].sort((a, b) => a - b);

  // Initial sort by type priority
  for (const layer of sortedLayers) {
    layerGroups.get(layer)!.sort((a, b) => typePriority(a) - typePriority(b));
  }

  // Per-layer max widths
  const layerWidths = sortedLayers.map((layer) => {
    const group = layerGroups.get(layer)!;
    return Math.max(...group.map((n) => getNodeSize(n).w));
  });

  // First pass: initial placement with compact horizontal spacing
  const yCenterMap = new Map<string, number>();
  const layerPositions = new Map<number, PosEntry[]>();

  let cumulativeX = PADDING_X;
  for (let li = 0; li < sortedLayers.length; li++) {
    const layer = sortedLayers[li];
    const group = layerGroups.get(layer)!;
    const x = snap(cumulativeX);
    const positions: PosEntry[] = [];

    let y = PADDING_Y;
    for (const node of group) {
      positions.push({ node, x, y: snap(y) });
      yCenterMap.set(node.id, y + getNodeSize(node).h / 2);
      y += getNodeSize(node).h + MIN_GAP_Y;
    }

    layerPositions.set(layer, positions);
    cumulativeX += layerWidths[li] + COMPACT_GAP_X;
  }

  // ── Multi-pass barycenter with median + transposition ──
  const layerOrders = new Map<number, string[]>();
  for (const layer of sortedLayers) {
    layerOrders.set(layer, layerGroups.get(layer)!.map((n) => n.id));
  }

  for (let iter = 0; iter < BARYCENTER_ITERATIONS; iter++) {
    const sweep = iter % 2 === 0 ? sortedLayers : [...sortedLayers].reverse();

    for (const layer of sweep) {
      const order = layerOrders.get(layer)!;
      const group = layerGroups.get(layer)!;

      const bary = new Map<string, number>();
      for (const id of order) {
        bary.set(id, computeBarycenter(id, adj, yCenterMap));
      }
      order.sort((a, b) => {
        const ba = bary.get(a) ?? 0;
        const bb = bary.get(b) ?? 0;
        if (Math.abs(ba - bb) > 0.5) return ba - bb;
        const na = group.find((n) => n.id === a)!;
        const nb = group.find((n) => n.id === b)!;
        return typePriority(na) - typePriority(nb);
      });

      const nodeMap = new Map(group.map((n) => [n.id, n]));
      for (let i = 0; i < order.length; i++) {
        group[i] = nodeMap.get(order[i])!;
      }

      const positions = layerPositions.get(layer)!;
      let y = PADDING_Y;
      for (let ni = 0; ni < group.length; ni++) {
        positions[ni] = { node: group[ni], x: positions[0].x, y: snap(y) };
        y += getNodeSize(group[ni]).h + MIN_GAP_Y;
      }

      resolveVerticalOverlaps(positions);
      for (const p of positions) {
        yCenterMap.set(p.node.id, p.y + getNodeSize(p.node).h / 2);
      }
    }

    // Transposition pass
    for (let li = 0; li < sortedLayers.length; li++) {
      const layer = sortedLayers[li];
      const order = layerOrders.get(layer)!;
      const prevOrder = li > 0 ? layerOrders.get(sortedLayers[li - 1])! : null;
      const nextOrder =
        li < sortedLayers.length - 1
          ? layerOrders.get(sortedLayers[li + 1])!
          : null;

      if (transposeLayer(order, prevOrder, nextOrder, adj)) {
        const group = layerGroups.get(layer)!;
        const nodeMap = new Map(group.map((n) => [n.id, n]));
        for (let i = 0; i < order.length; i++) {
          group[i] = nodeMap.get(order[i])!;
        }
        const positions = layerPositions.get(layer)!;
        let y = PADDING_Y;
        for (let ni = 0; ni < group.length; ni++) {
          positions[ni] = { node: group[ni], x: positions[0].x, y: snap(y) };
          y += getNodeSize(group[ni]).h + MIN_GAP_Y;
        }
        resolveVerticalOverlaps(positions);
        for (const p of positions) {
          yCenterMap.set(p.node.id, p.y + getNodeSize(p.node).h / 2);
        }
      }
    }
  }

  // Straight-connection alignment
  alignStraightConnections(layerPositions, sortedLayers, adj, yCenterMap);

  // Vertical centering
  centerLayersVertically(layerPositions, sortedLayers);

  // Aggressive compaction
  compactHorizontal(layerPositions, sortedLayers);
  compactVertical(layerPositions, sortedLayers);

  // Final overlap checks — within layers AND across all nodes globally
  for (const layer of sortedLayers) {
    resolveVerticalOverlaps(layerPositions.get(layer)!);
  }

  // Global overlap check: ensure no two nodes from ANY layers overlap
  {
    const allPositions: PosEntry[] = [];
    for (const layer of sortedLayers) {
      allPositions.push(...layerPositions.get(layer)!);
    }
    // Check all pairs for overlap
    for (let i = 0; i < allPositions.length; i++) {
      const a = allPositions[i];
      const as = getNodeSize(a.node);
      for (let j = i + 1; j < allPositions.length; j++) {
        const b = allPositions[j];
        const bs = getNodeSize(b.node);
        // Check if rectangles overlap
        const overlapX = a.x < b.x + bs.w + 10 && a.x + as.w + 10 > b.x;
        const overlapY = a.y < b.y + bs.h + 10 && a.y + as.h + 10 > b.y;
        if (overlapX && overlapY) {
          // Push the lower node down
          if (b.y <= a.y + as.h) {
            b.y = a.y + as.h + MIN_GAP_Y;
          }
        }
      }
    }
  }

  // Snap all final positions
  for (const layer of sortedLayers) {
    for (const p of layerPositions.get(layer)!) {
      p.x = snap(p.x);
      p.y = snap(p.y);
    }
  }

  // Normalize: shift so top-left starts near origin
  let globalMinX = Infinity;
  let globalMinY = Infinity;
  for (const layer of sortedLayers) {
    for (const p of layerPositions.get(layer)!) {
      globalMinX = Math.min(globalMinX, p.x);
      globalMinY = Math.min(globalMinY, p.y);
    }
  }
  const shiftX = globalMinX - PADDING_X;
  const shiftY = globalMinY - PADDING_Y;
  if (shiftX > 0 || shiftY > 0) {
    for (const layer of sortedLayers) {
      for (const p of layerPositions.get(layer)!) {
        if (shiftX > 0) p.x -= shiftX;
        if (shiftY > 0) p.y -= shiftY;
      }
    }
  }

  // Collect final positions and bounds
  const newPositions = new Map<string, { x: number; y: number }>();
  let maxX = 0;
  let maxY = 0;

  for (const layer of sortedLayers) {
    for (const p of layerPositions.get(layer)!) {
      newPositions.set(p.node.id, { x: p.x, y: p.y });
      const size = getNodeSize(p.node);
      maxX = Math.max(maxX, p.x + size.w);
      maxY = Math.max(maxY, p.y + size.h);
    }
  }

  return nodes.map((n) => {
    if (n.type === "boundary" && boundary) {
      const bx = snap(PADDING_X - BOUNDARY_MARGIN);
      const by = snap(PADDING_Y - BOUNDARY_MARGIN);
      return {
        ...n,
        position: { x: bx, y: by },
        style: {
          ...((n.style as Record<string, unknown>) || {}),
          width: snap(maxX - bx + BOUNDARY_MARGIN),
          height: snap(maxY - by + BOUNDARY_MARGIN),
        },
      };
    }
    const pos = newPositions.get(n.id);
    if (!pos) return n;
    return { ...n, position: pos };
  });
}

/**
 * After layout, reroute edge handles so that:
 * - Vertically aligned nodes use top/bottom ports
 * - Horizontally aligned nodes use left/right ports
 * - Diagonal connections pick the dominant axis
 */
export function rerouteEdgesAfterLayout(
  nodes: Node[],
  edges: Edge[],
): Edge[] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  function getCenter(n: Node): { cx: number; cy: number } {
    const size = getNodeSize(n);
    return {
      cx: n.position.x + size.w / 2,
      cy: n.position.y + size.h / 2,
    };
  }

  return edges.map((edge) => {
    const srcNode = nodeMap.get(edge.source);
    const tgtNode = nodeMap.get(edge.target);
    if (!srcNode || !tgtNode) return edge;

    const existingSource = edge.sourceHandle || "";
    const existingTarget = edge.targetHandle || "";

    if (existingSource.startsWith("default") || existingTarget.startsWith("default")) return edge;

    if (srcNode.type === "carrier" || tgtNode.type === "carrier") {
      return rerouteCarrierEdge(edge, srcNode, tgtNode);
    }

    const srcParts = existingSource.split("-");
    const tgtParts = existingTarget.split("-");
    const srcPortId = srcParts.length > 1 ? srcParts.slice(1).join("-") : "";
    const tgtPortId = tgtParts.length > 1 ? tgtParts.slice(1).join("-") : "";
    if (!srcPortId || !tgtPortId) return edge;

    const sc = getCenter(srcNode);
    const tc = getCenter(tgtNode);
    const dx = tc.cx - sc.cx;
    const dy = tc.cy - sc.cy;
    const absDx = Math.abs(dx);
    const absDy = Math.abs(dy);

    const ALIGN_THRESH = 80; // wider threshold for compact layout

    // CONSTRAINT: source can only use "out" (right) or "bot" (bottom)
    //             target can only use "in" (left) or "top" (top)
    let srcPrefix: string;
    let tgtPrefix: string;

    // Vertically aligned → source exits bottom, target enters top
    if (absDx < ALIGN_THRESH && absDy > 30 && dy > 0) {
      srcPrefix = "bot";
      tgtPrefix = "top";
    }
    // Vertically aligned but target is ABOVE → can't use top as source, use right/left
    else if (absDx < ALIGN_THRESH && absDy > 30 && dy < 0) {
      srcPrefix = "out";
      tgtPrefix = "in";
    }
    // Horizontally aligned or dominant horizontal (target to the right)
    else if (dx > 0) {
      srcPrefix = "out";
      tgtPrefix = "in";
    }
    // Target is to the left — source exits right, target enters left (flow wraps)
    else if (dx <= 0 && absDx >= absDy) {
      srcPrefix = "out";
      tgtPrefix = "in";
    }
    // Target is below-left — source exits bottom, target enters top
    else if (dy > 0) {
      srcPrefix = "bot";
      tgtPrefix = "top";
    }
    // Fallback
    else {
      srcPrefix = "out";
      tgtPrefix = "in";
    }

    return {
      ...edge,
      sourceHandle: `${srcPrefix}-${srcPortId}`,
      targetHandle: `${tgtPrefix}-${tgtPortId}`,
    };
  });
}

/**
 * Reroute edges involving carrier nodes.
 *
 * CRITICAL: Carrier handles have fixed types:
 *   - carrier-left, carrier-top → type="target" only
 *   - carrier-right, carrier-bottom → type="source" only
 *
 * So when a carrier is the SOURCE of an edge, only right/bottom are valid.
 * When a carrier is the TARGET, only left/top are valid.
 */
function rerouteCarrierEdge(edge: Edge, srcNode: Node, tgtNode: Node): Edge {
  function getCenter(n: Node) {
    const s = getNodeSize(n);
    return { cx: n.position.x + s.w / 2, cy: n.position.y + s.h / 2 };
  }

  const sc = getCenter(srcNode);
  const tc = getCenter(tgtNode);
  const dx = tc.cx - sc.cx;
  const dy = tc.cy - sc.cy;
  const absDx = Math.abs(dx);
  const absDy = Math.abs(dy);

  const THRESH = 60;

  // Determine ideal direction pair
  let isVertical = false;
  let isPositive = true; // true = down/right, false = up/left

  if (absDx < THRESH && absDy > 30) {
    isVertical = true;
    isPositive = dy > 0;
  } else if (absDy < THRESH && absDx > 30) {
    isVertical = false;
    isPositive = dx > 0;
  } else if (absDx >= absDy) {
    isVertical = false;
    isPositive = dx > 0;
  } else {
    isVertical = true;
    isPositive = dy > 0;
  }

  const newEdge = { ...edge };

  // Source carrier: can only use right (source) or bottom (source)
  if (srcNode.type === "carrier") {
    if (isVertical && isPositive) {
      newEdge.sourceHandle = "carrier-bottom"; // going down
    } else if (isVertical && !isPositive) {
      // Going up — but carrier-top is target-only, so use carrier-right as fallback
      newEdge.sourceHandle = "carrier-right";
    } else {
      newEdge.sourceHandle = isPositive ? "carrier-right" : "carrier-right"; // left is target-only
    }
  } else {
    // Equipment/gate source — ONLY "out" (right) or "bot" (bottom)
    const parts = (edge.sourceHandle || "").split("-");
    const portId = parts.length > 1 ? parts.slice(1).join("-") : "";
    if (portId) {
      const srcPrefix = (isVertical && isPositive) ? "bot" : "out";
      newEdge.sourceHandle = `${srcPrefix}-${portId}`;
    }
  }

  // Target carrier: can only use left (target) or top (target)
  if (tgtNode.type === "carrier") {
    if (isVertical && isPositive) {
      newEdge.targetHandle = "carrier-top"; // coming from above
    } else {
      newEdge.targetHandle = "carrier-left";
    }
  } else {
    // Equipment/gate target — ONLY "in" (left) or "top" (top)
    const parts = (edge.targetHandle || "").split("-");
    const portId = parts.length > 1 ? parts.slice(1).join("-") : "";
    if (portId) {
      const tgtPrefix = (isVertical && isPositive) ? "top" : "in";
      newEdge.targetHandle = `${tgtPrefix}-${portId}`;
    }
  }

  return newEdge;
}
