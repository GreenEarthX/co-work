/**
 * procurementSync — single source of truth for equipment procurement.
 *
 * The equipment node on the plant canvas owns its procurement record under
 * `node.data.procurement`. Both the Plant Builder (SupplierPickerDialog) and
 * the Project Procurement page read/write through these helpers, keyed by
 * nodeId — never by label.
 *
 * Backwards compatible: legacy nodes that only carry the flat
 * `manufacturer`/`model`/… fields synthesize a procurement object on read.
 */
import type { Node } from "@xyflow/react";
import {
  getProcurementEntry,
  strategyLabels,
  type ProcurementStrategy,
} from "@/components/canvas/procurementDatabase";
import type { SupplierSelection } from "@/components/canvas/SupplierPickerDialog";

export interface NodeProcurement {
  manufacturer: string;
  model: string;
  country: string;
  priceEur: number;
  priceDisplay: string;
  efficiency: string;
  leadTimeMonths: number;
  trl: number;
  scaleThreshold?: string;
  /** Display label e.g. "Best Price" / "Best Efficiency" / "Scale Optimised" / "Custom" */
  strategy: string;
  plantScaleQty: number;
  source: "database" | "manual";
  updatedAt: string;
}

/** Strategy display label → DB key */
export function strategyKeyFromLabel(label: string | undefined): ProcurementStrategy {
  if (!label) return "bestPrice";
  for (const k of ["bestPrice", "bestEfficiency", "economiesOfScale"] as ProcurementStrategy[]) {
    if (strategyLabels[k].label === label) return k;
  }
  // Picker uses "Scale Optimised" — alias for economiesOfScale
  if (/scale/i.test(label)) return "economiesOfScale";
  if (/effic/i.test(label)) return "bestEfficiency";
  return "bestPrice";
}

/**
 * Read the procurement record off a node.
 * Returns null when the node has no procurement at all.
 */
export function getNodeProcurement(node: Node): NodeProcurement | null {
  const d = (node.data ?? {}) as Record<string, unknown>;
  const nested = d.procurement as Partial<NodeProcurement> | undefined;
  if (nested && nested.manufacturer && nested.model) {
    return {
      manufacturer: String(nested.manufacturer),
      model: String(nested.model),
      country: String(nested.country ?? ""),
      priceEur: Number(nested.priceEur ?? 0),
      priceDisplay: String(nested.priceDisplay ?? ""),
      efficiency: String(nested.efficiency ?? ""),
      leadTimeMonths: Number(nested.leadTimeMonths ?? 0),
      trl: Number(nested.trl ?? 0),
      scaleThreshold: nested.scaleThreshold ? String(nested.scaleThreshold) : undefined,
      strategy: String(nested.strategy ?? "Custom"),
      plantScaleQty: Number(nested.plantScaleQty ?? 1),
      source: (nested.source as "database" | "manual") ?? "manual",
      updatedAt: String(nested.updatedAt ?? new Date().toISOString()),
    };
  }

  // Legacy shim — flat fields written by older code paths.
  const manufacturer = (d.manufacturer as string) || "";
  const model = (d.model as string) || "";
  if (!manufacturer && !model) return null;

  const label = (d.label as string) || "";
  const entry = getProcurementEntry(label);
  const qty = entry?.plantScaleQty ?? 1;

  // Try to back-derive priceEur from a known DB entry matching the model.
  let priceEur = 0;
  if (entry) {
    for (const k of ["bestPrice", "bestEfficiency", "economiesOfScale"] as ProcurementStrategy[]) {
      if (entry[k].model === model || entry[k].manufacturer === manufacturer) {
        priceEur = entry[k].priceEur;
        break;
      }
    }
  }

  return {
    manufacturer,
    model,
    country: (d.country as string) || "",
    priceEur,
    priceDisplay: (d.priceDisplay as string) || "",
    efficiency: (d.efficiency as string) || "",
    leadTimeMonths: Number(d.leadTimeMonths ?? 0),
    trl: Number(d.trl ?? 0),
    strategy: (d.strategy as string) || "Custom",
    plantScaleQty: qty,
    source: "manual",
    updatedAt: new Date(0).toISOString(),
  };
}

/**
 * Write a SupplierSelection into a node's `data.procurement`. Mirrors
 * `manufacturer`/`model` at the top of `data` so existing UI (status dot,
 * legacy reads) keeps working.
 */
export function applyProcurementToNode(node: Node, selection: SupplierSelection): Node {
  const label = (node.data?.label as string) || "";
  const entry = getProcurementEntry(label);
  const strategyKey = strategyKeyFromLabel(selection.strategy);
  const priceEur = entry?.[strategyKey]?.priceEur ?? 0;
  const plantScaleQty = entry?.plantScaleQty ?? 1;

  const procurement: NodeProcurement = {
    manufacturer: selection.manufacturer,
    model: selection.model,
    country: selection.country,
    priceEur,
    priceDisplay: selection.priceDisplay,
    efficiency: selection.efficiency,
    leadTimeMonths: selection.leadTimeMonths,
    trl: selection.trl,
    scaleThreshold: selection.scaleThreshold,
    strategy: selection.strategy,
    plantScaleQty,
    source: "database",
    updatedAt: new Date().toISOString(),
  };

  return {
    ...node,
    data: {
      ...(node.data ?? {}),
      procurement,
      // Mirrored fields for legacy consumers (status dot, old reads).
      manufacturer: procurement.manufacturer,
      model: procurement.model,
      country: procurement.country,
      priceDisplay: procurement.priceDisplay,
      efficiency: procurement.efficiency,
      leadTimeMonths: procurement.leadTimeMonths,
      trl: procurement.trl,
      strategy: procurement.strategy,
    },
  };
}

export function clearNodeProcurement(node: Node): Node {
  const data = { ...(node.data ?? {}) } as Record<string, unknown>;
  delete data.procurement;
  delete data.manufacturer;
  delete data.model;
  delete data.country;
  delete data.priceDisplay;
  delete data.efficiency;
  delete data.leadTimeMonths;
  delete data.trl;
  delete data.strategy;
  return { ...node, data };
}

export interface DerivedProcurementLine {
  nodeId: string;
  equipment: string;
  manufacturer: string;
  model: string;
  country: string;
  priceEur: number;
  scaledPriceEur: number;
  priceDisplay: string;
  efficiency: string;
  leadTimeMonths: number;
  trl: number;
  plantScaleQty: number;
  strategy: ProcurementStrategy;
}

export interface DerivedProcurementSnapshot {
  lineItems: DerivedProcurementLine[];
  totalCapexEur: number;
}

/**
 * Build a procurement snapshot directly from canvas equipment nodes.
 * Replaces the old localStorage `procurement:{plantId}` blob as the
 * source of truth.
 */
export function buildProcurementSnapshot(nodes: Node[]): DerivedProcurementSnapshot {
  const lineItems: DerivedProcurementLine[] = [];
  let total = 0;
  for (const node of nodes) {
    if (node.type !== "equipment") continue;
    const proc = getNodeProcurement(node);
    if (!proc) continue;
    const scaled = proc.priceEur * proc.plantScaleQty;
    total += scaled;
    lineItems.push({
      nodeId: node.id,
      equipment: (node.data?.label as string) || "",
      manufacturer: proc.manufacturer,
      model: proc.model,
      country: proc.country,
      priceEur: proc.priceEur,
      scaledPriceEur: scaled,
      priceDisplay: proc.priceDisplay,
      efficiency: proc.efficiency,
      leadTimeMonths: proc.leadTimeMonths,
      trl: proc.trl,
      plantScaleQty: proc.plantScaleQty,
      strategy: strategyKeyFromLabel(proc.strategy),
    });
  }
  return { lineItems, totalCapexEur: total };
}