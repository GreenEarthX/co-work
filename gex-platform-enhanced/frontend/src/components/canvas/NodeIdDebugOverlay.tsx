/**
 * NodeIdDebugOverlay — small absolute-positioned chip rendered on top of a
 * canvas node when debug mode is on. Color-codes whether the duplicate
 * counter is being computed (DUP), the label is unique (UNI), or counting
 * was suppressed because the label normalized to null (—).
 */
import { useNodeIdDebug, classifyNodeIdDebug, NODE_ID_DEBUG_STYLES } from "./nodeIdVisibility";
import type { NodeIdInfo } from "./nodeIdSystem";

interface Props {
  label: unknown;
  info: NodeIdInfo | undefined;
}

export default function NodeIdDebugOverlay({ label, info }: Props) {
  const enabled = useNodeIdDebug();
  if (!enabled) return null;
  const state = classifyNodeIdDebug(label, info);
  const s = NODE_ID_DEBUG_STYLES[state];
  const tip =
    state === "counted"
      ? `Duplicate counter ACTIVE, #${info?.duplicateIndex} of ${info?.duplicateTotal}`
      : state === "unique"
        ? "Duplicate counter inactive, label is unique among its type"
        : "Duplicate counter SUPPRESSED, label is empty / placeholder";
  return (
    <div
      title={tip}
      className={`pointer-events-none absolute -top-2 -left-2 z-20 flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[8px] font-bold tracking-wider shadow-md ${s.chipBg}`}
    >
      {s.label}
      {state === "counted" && info?.duplicateIndex !== undefined && (
        <span className="opacity-90">{info.duplicateIndex}/{info.duplicateTotal}</span>
      )}
    </div>
  );
}

/** Convenience: classNames for the debug ring to add to the node's main shape. */
export function nodeIdDebugRingClass(label: unknown, info: NodeIdInfo | undefined, enabled: boolean): string {
  if (!enabled) return "";
  const state = classifyNodeIdDebug(label, info);
  return NODE_ID_DEBUG_STYLES[state].ring;
}