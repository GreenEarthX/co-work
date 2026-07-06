/**
 * Source Resolver — given the canvas state (nodes + edges) and the plant form,
 * enumerate available source dictionaries / IDs / fields and resolve a numeric
 * value for a configured variable binding.
 */
import type { Node, Edge } from "@xyflow/react";
import {
  getEquipmentFieldDefs,
  getCarrierFieldDefs,
  getGateFieldDefs,
  type FieldDef,
} from "@/components/canvas/fieldDictionary";
import { DEFAULT_LIBRARY } from "@/engine/registry/defaultLibrary";

export type SourceKind =
  | "equipment"
  | "carrier"
  | "gate"
  | "plant"
  | "default_library"
  | "flow";

export const SOURCE_OPTIONS: Array<{ value: SourceKind; label: string; needsId: boolean }> = [
  { value: "equipment",       label: "Equipment",                needsId: true  },
  { value: "carrier",         label: "Carrier",                  needsId: true  },
  { value: "gate",            label: "Gate",                     needsId: true  },
  { value: "flow",            label: "Flow",                     needsId: true  },
  { value: "plant",           label: "Plant Form",               needsId: false },
  { value: "default_library", label: "Default Library",          needsId: false },
];

export interface VariableBinding {
  source: SourceKind | "";
  /** Equipment / Carrier / Gate node ID, or Edge ID for "flow" */
  refId?: string;
  /** Field name within the dictionary, or param key for default_library */
  field?: string;
  /** For default_library, the archetype ID to scope */
  archetypeId?: string;
}

export interface ResolverContext {
  nodes: Node[];
  edges: Edge[];
  /** Plant-level form values keyed by toKey(name) — typically availability/hours etc. */
  plantForm: Record<string, unknown>;
  /** Plant-level field defs (currently the same flat shape as availability/cost) */
  plantFieldDefs: FieldDef[];
}

/* ─────────────── Enumerators (for cascading selects) ─────────────── */

export function listIdsForSource(ctx: ResolverContext, source: SourceKind): Array<{ id: string; label: string }> {
  /** Append "#N" to labels that occur more than once so users can tell
   *  multiple instances of the same equipment apart (e.g. two Deoxidation
   *  Units → "Deoxidation Unit #1", "Deoxidation Unit #2"). Order is stable
   *  with respect to the input list. */
  const withInstanceSuffix = (
    items: Array<{ id: string; label: string }>,
  ): Array<{ id: string; label: string }> => {
    const counts = new Map<string, number>();
    for (const it of items) counts.set(it.label, (counts.get(it.label) ?? 0) + 1);
    const seen = new Map<string, number>();
    return items.map((it) => {
      if ((counts.get(it.label) ?? 0) <= 1) return it;
      const n = (seen.get(it.label) ?? 0) + 1;
      seen.set(it.label, n);
      return { id: it.id, label: `${it.label} #${n}` };
    });
  };

  switch (source) {
    case "equipment":
      return withInstanceSuffix(
        ctx.nodes
          .filter((n) => n.type === "equipment")
          .map((n) => ({ id: n.id, label: `${(n.data?.label as string) ?? n.id}` })),
      );
    case "carrier":
      return withInstanceSuffix(
        ctx.nodes
          .filter((n) => n.type === "carrier")
          .map((n) => ({ id: n.id, label: `${(n.data?.label as string) ?? n.id}` })),
      );
    case "gate":
      return withInstanceSuffix(
        ctx.nodes
          .filter((n) => n.type === "gate")
          .map((n) => ({ id: n.id, label: `${(n.data?.label as string) ?? n.id}` })),
      );
    case "flow": {
      const nodeLabel = (id: string) =>
        (ctx.nodes.find((n) => n.id === id)?.data?.label as string) ?? id;
      return ctx.edges.map((e) => ({
        id: e.id,
        label: `${nodeLabel(e.source)} → ${nodeLabel(e.target)}`,
      }));
    }
    default:
      return [];
  }
}

export function listFieldsForSource(
  ctx: ResolverContext,
  source: SourceKind,
  refId?: string,
): Array<{ key: string; label: string; unit?: string }> {
  if (source === "plant") {
    return ctx.plantFieldDefs.map((f) => ({ key: toKey(f.name), label: f.name, unit: f.unit }));
  }
  if (source === "default_library") {
    // Each archetype has a list of param keys; flatten as "{archetypeId} :: {paramKey}"
    return DEFAULT_LIBRARY.map((entry) => ({
      key: `${entry.archetypeId}::${entry.paramKey}`,
      label: `${entry.archetypeId}, ${entry.paramKey}`,
      unit: entry.unit,
    }));
  }
  if (source === "flow") {
    return [
      { key: "flowValue",   label: "Flow Value" },
      { key: "flowUnit",    label: "Flow Unit"  },
      { key: "carrierName", label: "Carrier"    },
    ];
  }
  if (!refId) return [];
  const node = ctx.nodes.find((n) => n.id === refId);
  if (!node) return [];
  const label = (node.data?.label as string) || "";
  const defs =
    source === "equipment" ? getEquipmentFieldDefs(label)
    : source === "carrier" ? getCarrierFieldDefs(label)
    : source === "gate"    ? getGateFieldDefs(label)
    : [];
  return defs.map((f) => ({ key: toKey(f.name), label: f.name, unit: f.unit }));
}

/* ─────────────── Resolver (binding → numeric value) ─────────────── */

export function resolveBinding(
  ctx: ResolverContext,
  binding: VariableBinding,
): { value: number | null; raw: unknown; unit?: string; status: "ok" | "missing" | "non_numeric" } {
  if (!binding.source) return { value: null, raw: null, status: "missing" };

  if (binding.source === "plant") {
    if (!binding.field) return { value: null, raw: null, status: "missing" };
    const raw = ctx.plantForm[binding.field];
    return numeric(raw);
  }

  if (binding.source === "default_library") {
    if (!binding.field) return { value: null, raw: null, status: "missing" };
    const [archetypeId, paramKey] = binding.field.split("::");
    const entry = DEFAULT_LIBRARY.find(
      (e) => e.archetypeId === archetypeId && e.paramKey === paramKey,
    );
    if (!entry) return { value: null, raw: null, status: "missing" };
    return { value: entry.defaultValue, raw: entry.defaultValue, unit: entry.unit, status: "ok" };
  }

  if (binding.source === "flow") {
    if (!binding.refId || !binding.field) return { value: null, raw: null, status: "missing" };
    const edge = ctx.edges.find((e) => e.id === binding.refId);
    if (!edge) return { value: null, raw: null, status: "missing" };
    const data = (edge.data ?? {}) as Record<string, unknown>;
    const raw = data[binding.field];
    return numeric(raw);
  }

  // equipment / carrier / gate
  if (!binding.refId || !binding.field) return { value: null, raw: null, status: "missing" };
  const node = ctx.nodes.find((n) => n.id === binding.refId);
  if (!node) return { value: null, raw: null, status: "missing" };
  const raw = (node.data as Record<string, unknown> | undefined)?.[binding.field];
  return numeric(raw);
}

function numeric(raw: unknown): { value: number | null; raw: unknown; status: "ok" | "missing" | "non_numeric" } {
  if (raw === undefined || raw === null || raw === "") return { value: null, raw, status: "missing" };
  const n = typeof raw === "number" ? raw : parseFloat(String(raw));
  if (Number.isFinite(n)) return { value: n, raw, status: "ok" };
  return { value: null, raw, status: "non_numeric" };
}

/* ─────────────── Expression evaluator ─────────────── */

/**
 * Evaluate an equation expression like "W_dc_out = W_ac_in * eta_rectifier".
 * Substitutes resolved values for each input variable and computes the RHS.
 * Returns null if any input is missing or expression unsafe.
 */
export function evaluateExpression(
  expression: string,
  values: Record<string, number | null>,
): { value: number | null; rhs: string; error?: string } {
  const eqIdx = expression.indexOf("=");
  const rhs = eqIdx >= 0 ? expression.slice(eqIdx + 1).trim() : expression.trim();

  // Substitute identifiers with their values
  const identRegex = /[A-Za-z_][A-Za-z0-9_]*/g;
  let missing = false;
  const substituted = rhs.replace(identRegex, (id) => {
    if (id in values) {
      const v = values[id];
      if (v === null || v === undefined || !Number.isFinite(v)) {
        missing = true;
        return "NaN";
      }
      return `(${v})`;
    }
    // Allow standard math functions
    if (["min", "max", "abs", "sqrt", "log", "exp", "pow"].includes(id)) {
      return `Math.${id}`;
    }
    missing = true;
    return "NaN";
  });

  if (missing) return { value: null, rhs, error: "Missing inputs" };

  // Safety: only allow numbers, operators, parens, dots, Math, whitespace
  if (!/^[\d\s+\-*/().,Math]*$/.test(substituted.replace(/Math\.\w+/g, ""))) {
    return { value: null, rhs, error: "Unsafe expression" };
  }

  try {
    // eslint-disable-next-line @typescript-eslint/no-implied-eval, no-new-func
    const fn = new Function(`return (${substituted});`);
    const v = fn();
    if (typeof v !== "number" || !Number.isFinite(v)) {
      return { value: null, rhs, error: "Non-numeric result" };
    }
    return { value: v, rhs };
  } catch (e) {
    return { value: null, rhs, error: (e as Error).message };
  }
}

/* ─────────────── Local copy of toKey (matches ComponentDetailDialog) ─────────────── */
function toKey(name: string): string {
  return name
    .replace(/[₂₃⁺⁻]/g, "")
    .replace(/[^a-zA-Z0-9 ]/g, "")
    .split(" ")
    .map((w, i) => (i === 0 ? w.toLowerCase() : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()))
    .join("");
}