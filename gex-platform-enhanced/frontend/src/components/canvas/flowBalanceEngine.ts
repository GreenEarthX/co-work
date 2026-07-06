/**
 * Flow Balance Engine — validates that mother flow = sum of child flows at every node.
 *
 * Concepts:
 * - Mother flow: the incoming edge(s) to a node carrying a specific carrier type
 * - Child flows: the outgoing edge(s) from that node
 * - At each node: sum(inputs) should equal sum(outputs) for matching units
 * - Imbalance = sum(inputs) - sum(outputs); positive = flow lost, negative = flow gained
 */
import type { Node, Edge } from "@xyflow/react";

export interface FlowImbalance {
  nodeId: string;
  nodeLabel: string;
  unit: string;
  totalIn: number;
  totalOut: number;
  /** Positive means flow is lost/unaccounted, negative means extra flow appearing */
  loss: number;
  lossPercent: number;
}

export interface BalanceReport {
  balanced: boolean;
  imbalances: FlowImbalance[];
  /** Edges annotated with isMotherFlow and imbalance data */
  annotatedEdges: Edge[];
}

/**
 * Run the balance engine across the entire graph.
 * Groups edges by unit at each node and checks conservation.
 */
export function runFlowBalance(nodes: Node[], edges: Edge[]): BalanceReport {
  const imbalances: FlowImbalance[] = [];

  // For each node, group incoming/outgoing edges by unit
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // Build adjacency: nodeId → { inEdges, outEdges }
  const adj = new Map<string, { inEdges: Edge[]; outEdges: Edge[] }>();
  for (const n of nodes) {
    adj.set(n.id, { inEdges: [], outEdges: [] });
  }
  for (const e of edges) {
    adj.get(e.source)?.outEdges.push(e);
    adj.get(e.target)?.inEdges.push(e);
  }

  // Identify mother flows: an edge is a "mother" if its source node has only that
  // one incoming edge with flow, and multiple outgoing edges (fan-out)
  const motherEdgeIds = new Set<string>();

  // Check balance at each non-gate, non-boundary node
  for (const [nodeId, { inEdges, outEdges }] of adj) {
    const node = nodeMap.get(nodeId);
    if (!node) continue;
    // Skip gate nodes (they are terminals) and boundary nodes
    if (node.type === "gate" || node.type === "boundary") continue;

    // Group edges by unit
    const inByUnit = groupByUnit(inEdges);
    const outByUnit = groupByUnit(outEdges);

    // Get all units present
    const allUnits = new Set([...inByUnit.keys(), ...outByUnit.keys()]);

    for (const unit of allUnits) {
      const totalIn = sumFlows(inByUnit.get(unit) || []);
      const totalOut = sumFlows(outByUnit.get(unit) || []);

      if (totalIn === 0 && totalOut === 0) continue;

      const loss = totalIn - totalOut;
      const lossPercent = totalIn > 0 ? (loss / totalIn) * 100 : 0;

      // Tolerance: < 0.1% is considered balanced
      if (Math.abs(lossPercent) > 0.1) {
        imbalances.push({
          nodeId,
          nodeLabel: (node.data?.label as string) || nodeId,
          unit,
          totalIn,
          totalOut,
          loss,
          lossPercent,
        });
      }

      // Mark mother flows: if a node has 1 input edge and multiple output edges for same unit
      const inEdgesForUnit = (inByUnit.get(unit) || []).filter(hasFlowData);
      const outEdgesForUnit = (outByUnit.get(unit) || []).filter(hasFlowData);
      if (inEdgesForUnit.length === 1 && outEdgesForUnit.length > 1) {
        motherEdgeIds.add(inEdgesForUnit[0].id);
      }
    }
  }

  // Build annotated edges
  const imbalanceByEdge = new Map<string, number>();

  // For edges leaving an imbalanced node, tag with imbalance info
  for (const imb of imbalances) {
    const { outEdges } = adj.get(imb.nodeId) || { outEdges: [] };
    for (const e of outEdges) {
      const eUnit = (e.data?.flowUnit as string) || "";
      if (eUnit === imb.unit) {
        imbalanceByEdge.set(e.id, imb.loss);
      }
    }
  }

  const annotatedEdges = edges.map((e) => ({
    ...e,
    data: {
      ...e.data,
      isMotherFlow: motherEdgeIds.has(e.id),
      imbalance: imbalanceByEdge.get(e.id) ?? undefined,
    },
  }));

  return {
    balanced: imbalances.length === 0,
    imbalances,
    annotatedEdges,
  };
}

/* ── Helpers ── */

function groupByUnit(edges: Edge[]): Map<string, Edge[]> {
  const map = new Map<string, Edge[]>();
  for (const e of edges) {
    if (!hasFlowData(e)) continue;
    const unit = (e.data?.flowUnit as string) || "unknown";
    if (!map.has(unit)) map.set(unit, []);
    map.get(unit)!.push(e);
  }
  return map;
}

function sumFlows(edges: Edge[]): number {
  return edges.reduce((sum, e) => {
    const v = e.data?.flowValue as number | undefined;
    return sum + (v ?? 0);
  }, 0);
}

function hasFlowData(e: Edge): boolean {
  return e.data?.flowValue !== undefined && e.data?.flowValue !== null;
}
