/**
 * nodeIdSystem — Computes display IDs for canvas nodes:
 *   - Equipment → E1, E2, …
 *   - Carrier   → C1, C2, …
 *   - Gate      → G1, G2, …
 * Plus a per-label occurrence index (#1, #2, …) when the same label
 * appears more than once within its node type.
 *
 * Ordering is deterministic: nodes are sorted by their internal id so the
 * displayed numbers stay stable across renders regardless of selection or
 * drag order.
 */
import type { Node } from "@xyflow/react";

const TYPE_PREFIX: Record<string, string> = {
  equipment: "E",
  carrier: "C",
  gate: "G",
};

export interface NodeIdInfo {
  /** "E1" / "C2" / "G3" */
  displayId: string;
  /** Occurrence index of this label within its type (1-based). undefined if unique. */
  duplicateIndex?: number;
  /** Total occurrences of this label across the same type. */
  duplicateTotal: number;
}

/** Configurable rules for normalizing labels prior to duplicate counting. */
export interface LabelNormalizationOptions {
  /** Trim leading/trailing whitespace and collapse internal whitespace. Default: true. */
  trim?: boolean;
  /** Lower-case the label so "Pump" and "pump" count as the same. Default: true. */
  caseFold?: boolean;
  /** Strip diacritics ("Électrolyseur" → "electrolyseur"). Default: true. */
  stripDiacritics?: boolean;
  /** Strip a trailing " #n" / " (n)" / " - n" numeric suffix users add manually. Default: true. */
  stripNumericSuffix?: boolean;
  /** Case-insensitive placeholder labels treated as "no label". Default: ["", "untitled", "new", "n/a", "tbd", "todo", "?"] */
  placeholders?: string[];
}

const DEFAULT_PLACEHOLDERS = ["", "untitled", "new", "n/a", "na", "tbd", "todo", "?"];

const DEFAULT_OPTIONS: Required<LabelNormalizationOptions> = {
  trim: true,
  caseFold: true,
  stripDiacritics: true,
  stripNumericSuffix: true,
  placeholders: DEFAULT_PLACEHOLDERS,
};

/**
 * Normalize a raw label value into a comparison key, or `null` when the label
 * is missing / empty / a placeholder. Pure function — exported for tests and
 * for callers that need to mirror the duplicate-counting behavior.
 */
export function normalizeLabel(
  raw: unknown,
  options: LabelNormalizationOptions = {},
): string | null {
  if (typeof raw !== "string") return null;
  const opts = { ...DEFAULT_OPTIONS, ...options };

  let s = raw;
  if (opts.trim) s = s.replace(/\s+/g, " ").trim();
  if (s.length === 0) return null;
  if (opts.stripDiacritics) {
    // NFD splits combined chars into base + combining marks; strip the marks.
    s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }
  if (opts.caseFold) s = s.toLowerCase();
  if (opts.stripNumericSuffix) {
    s = s.replace(/\s*(?:[#(\-]?\s*\d+\)?\s*)$/u, "").trim();
  }
  if (s.length === 0) return null;

  const placeholderSet = new Set(opts.placeholders.map((p) => p.toLowerCase()));
  if (placeholderSet.has(s.toLowerCase())) return null;

  return s;
}

export function computeNodeIdMap(
  nodes: Node[],
  options: LabelNormalizationOptions = {},
  /**
   * Optional list of previously-assigned displayIds (e.g. "E2", "C5") that
   * have since been deleted from the canvas. These numbers are RESERVED so
   * future nodes never reuse them — preserves full traceability across
   * add/delete cycles ("E2 was the second pump we tried, never resurrect it").
   */
  reservedDisplayIds: readonly string[] = [],
): Map<string, NodeIdInfo> {
  const result = new Map<string, NodeIdInfo>();
  const byType: Record<string, Node[]> = { equipment: [], carrier: [], gate: [] };
  for (const n of nodes) {
    if (n.type && byType[n.type]) byType[n.type].push(n);
  }
  for (const type of Object.keys(byType)) {
    const prefix = TYPE_PREFIX[type];
    // Deterministic ordering: by internal id only, never by label (which can be
    // empty, missing, or change at runtime).
    const sorted = [...byType[type]].sort((a, b) => a.id.localeCompare(b.id));

    // Normalize labels via the configurable rules. Empty/missing/placeholder
    // labels are skipped so unlabelled nodes don't get spurious duplicate
    // indices grouped together.
    const normalize = (n: Node): string | null =>
      normalizeLabel((n.data as { label?: unknown })?.label, options);

    const labelCounts = new Map<string, number>();
    for (const n of sorted) {
      const key = normalize(n);
      if (key === null) continue;
      labelCounts.set(key, (labelCounts.get(key) ?? 0) + 1);
    }

    const labelSeen = new Map<string, number>();
    // Track which sequential numbers have already been claimed by pinned IDs
    // so newly-added nodes get the next free number rather than colliding.
    const claimed = new Set<number>();
    for (const n of sorted) {
      const pinned = (n.data as { displayId?: unknown })?.displayId;
      if (typeof pinned === "string" && pinned.startsWith(prefix)) {
        const num = Number.parseInt(pinned.slice(prefix.length), 10);
        if (Number.isFinite(num) && num > 0) claimed.add(num);
      }
    }
    // Reserve numbers from previously-deleted nodes so they're never reused.
    for (const r of reservedDisplayIds) {
      if (typeof r === "string" && r.startsWith(prefix)) {
        const num = Number.parseInt(r.slice(prefix.length), 10);
        if (Number.isFinite(num) && num > 0) claimed.add(num);
      }
    }
    let nextFree = 1;
    const allocate = (): number => {
      while (claimed.has(nextFree)) nextFree++;
      const v = nextFree;
      claimed.add(v);
      nextFree++;
      return v;
    };
    sorted.forEach((n) => {
      const key = normalize(n);
      const total = key !== null ? (labelCounts.get(key) ?? 1) : 1;
      let occurrence: number | undefined;
      if (key !== null && total > 1) {
        occurrence = (labelSeen.get(key) ?? 0) + 1;
        labelSeen.set(key, occurrence);
      }
      // Prefer a pinned displayId from node.data if present (persists across
      // reloads even when new nodes with smaller internal ids appear later).
      const pinned = (n.data as { displayId?: unknown })?.displayId;
      let displayNum: number;
      if (typeof pinned === "string" && pinned.startsWith(prefix)) {
        const parsed = Number.parseInt(pinned.slice(prefix.length), 10);
        displayNum = Number.isFinite(parsed) && parsed > 0 ? parsed : allocate();
      } else {
        displayNum = allocate();
      }
      result.set(n.id, {
        displayId: `${prefix}${displayNum}`,
        duplicateIndex: occurrence,
        duplicateTotal: total,
      });
    });
  }
  return result;
}

/** Convenience: read display info for a single node id given the full node list. */
export function getNodeIdInfo(nodes: Node[], nodeId: string): NodeIdInfo | undefined {
  return computeNodeIdMap(nodes).get(nodeId);
}

/** Build a human-readable tooltip explaining the node's identifier metadata. */
export function buildNodeIdTooltip(
  internalId: string,
  label: unknown,
  info: NodeIdInfo | undefined,
): string {
  const lines: string[] = [];
  lines.push(`Internal ID: ${internalId}`);
  lines.push(`Display ID: ${info?.displayId ?? "?"}`);
  const hasLabel = typeof label === "string" && label.trim().length > 0;
  if (info && info.duplicateTotal > 1 && info.duplicateIndex !== undefined) {
    lines.push(`Occurrence: #${info.duplicateIndex} of ${info.duplicateTotal} sharing this label`);
  } else if (!hasLabel) {
    lines.push(`Occurrence index suppressed: label is empty`);
  } else {
    lines.push(`Occurrence: unique label (no #n suffix)`);
  }
  return lines.join("\n");
}