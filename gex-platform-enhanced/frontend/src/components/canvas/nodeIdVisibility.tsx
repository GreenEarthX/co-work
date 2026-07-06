/**
 * NodeIdVisibility — context for toggling the E/C/G identifier badges on
 * canvas nodes. Defaults to visible so behavior is unchanged when no
 * provider is mounted (e.g. tests, exports).
 */
import { createContext, useContext, type ReactNode } from "react";
import type { LabelNormalizationOptions } from "./nodeIdSystem";

const NodeIdVisibilityContext = createContext<boolean>(true);
const NodeIdDebugContext = createContext<boolean>(false);
const LabelNormalizationContext = createContext<LabelNormalizationOptions>({});
const CompactNodeContext = createContext<boolean>(false);
const StraightEdgesContext = createContext<boolean>(false);

export function NodeIdVisibilityProvider({ value, children }: { value: boolean; children: ReactNode }) {
  return (
    <NodeIdVisibilityContext.Provider value={value}>
      {children}
    </NodeIdVisibilityContext.Provider>
  );
}

export function useNodeIdVisible(): boolean {
  return useContext(NodeIdVisibilityContext);
}

/**
 * Debug overlay: when enabled, nodes render a colored ring + small chip
 * indicating whether the duplicate-counter is being computed (label has
 * a normalized key shared with peers), unique (key but no peers), or
 * suppressed (label empty/placeholder → key is null). Speeds up QA of
 * the label-normalization rules.
 */
export function NodeIdDebugProvider({ value, children }: { value: boolean; children: ReactNode }) {
  return (
    <NodeIdDebugContext.Provider value={value}>
      {children}
    </NodeIdDebugContext.Provider>
  );
}

export function useNodeIdDebug(): boolean {
  return useContext(NodeIdDebugContext);
}

/**
 * Provider for the label-normalization options used by the node-id system.
 * Lets users tune duplicate-detection rules from Plant Settings without
 * touching node code.
 */
export function LabelNormalizationProvider({
  value, children,
}: { value: LabelNormalizationOptions; children: ReactNode }) {
  return (
    <LabelNormalizationContext.Provider value={value}>
      {children}
    </LabelNormalizationContext.Provider>
  );
}

export function useLabelNormalization(): LabelNormalizationOptions {
  return useContext(LabelNormalizationContext);
}

/**
 * Compact-node mode: shrinks paddings, gaps and badge sizes on equipment
 * nodes while keeping the NAME label and ID badge legible. Toggle from
 * Plant Settings → Plant Display.
 */
export function CompactNodeProvider({ value, children }: { value: boolean; children: ReactNode }) {
  return (
    <CompactNodeContext.Provider value={value}>
      {children}
    </CompactNodeContext.Provider>
  );
}

export function useCompactNode(): boolean {
  return useContext(CompactNodeContext);
}

/**
 * Straight-edge mode: when enabled, FlowEdge renders edges as a single
 * straight line between source and target handles instead of a smooth-step
 * orthogonal path. Useful for compact P&ID-style layouts where users have
 * pre-aligned nodes and want minimum visual noise.
 */
export function StraightEdgesProvider({ value, children }: { value: boolean; children: ReactNode }) {
  return (
    <StraightEdgesContext.Provider value={value}>
      {children}
    </StraightEdgesContext.Provider>
  );
}

export function useStraightEdges(): boolean {
  return useContext(StraightEdgesContext);
}

export type NodeIdDebugState = "counted" | "unique" | "suppressed";

/** Classify a node's duplicate-counter state for the debug overlay. */
export function classifyNodeIdDebug(
  label: unknown,
  info: { duplicateTotal: number; duplicateIndex?: number } | undefined,
): NodeIdDebugState {
  // Suppressed = normalizeLabel returned null (empty / placeholder / missing).
  // We approximate that here by checking the trimmed string; the authoritative
  // signal is `duplicateTotal === 1 && no string label`.
  const hasLabel = typeof label === "string" && label.trim().length > 0;
  if (!hasLabel) return "suppressed";
  if (info && info.duplicateTotal > 1) return "counted";
  return "unique";
}

/** Tailwind-friendly visual tokens per debug state. */
export const NODE_ID_DEBUG_STYLES: Record<
  NodeIdDebugState,
  { ring: string; chipBg: string; chipText: string; label: string }
> = {
  counted: {
    ring: "ring-2 ring-emerald-500/70 ring-offset-1 ring-offset-background",
    chipBg: "bg-emerald-500 text-white",
    chipText: "text-emerald-700 dark:text-emerald-300",
    label: "DUP",
  },
  unique: {
    ring: "ring-2 ring-sky-400/60 ring-offset-1 ring-offset-background",
    chipBg: "bg-sky-500 text-white",
    chipText: "text-sky-700 dark:text-sky-300",
    label: "UNI",
  },
  suppressed: {
    ring: "ring-2 ring-amber-500/70 ring-offset-1 ring-offset-background",
    chipBg: "bg-amber-500 text-white",
    chipText: "text-amber-700 dark:text-amber-300",
    label: "–",
  },
};