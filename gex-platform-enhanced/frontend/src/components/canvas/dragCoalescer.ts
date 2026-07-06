/**
 * Drag coalescer — collapses a burst of React-Flow `position` changes for the
 * same node into a single "latest-wins" update per animation frame.
 *
 * This is the same algorithm used inline in PlantCanvas's `onNodesChange`
 * handler, factored out so it can be unit-tested deterministically.
 */
export type PositionChange = {
  type: "position";
  id: string;
  position: { x: number; y: number };
  dragging?: boolean;
};

export type AnyChange =
  | PositionChange
  | { type: "select" | "remove" | "dimensions" | "add" | "reset"; id?: string; [k: string]: unknown };

export interface DragCoalescer {
  /** Push raw incoming changes; returns changes that must be applied synchronously now. */
  ingest(changes: AnyChange[]): AnyChange[];
  /** Force-flush any buffered drag positions (returns the merged batch). */
  flush(): PositionChange[];
  /** True if a flush is currently scheduled. */
  pending(): boolean;
  /** For tests: pending buffer size. */
  bufferSize(): number;
}

export function createDragCoalescer(scheduleFlush: (cb: () => void) => number,
                                    cancelFlush: (handle: number) => void): DragCoalescer {
  const buffer = new Map<string, PositionChange>();
  let handle: number | null = null;

  const doFlush = (): PositionChange[] => {
    handle = null;
    if (buffer.size === 0) return [];
    const out = Array.from(buffer.values());
    buffer.clear();
    return out;
  };

  return {
    ingest(changes) {
      const immediate: AnyChange[] = [];
      for (const c of changes) {
        if (c.type === "position" && (c as PositionChange).dragging === true && (c as PositionChange).position) {
          buffer.set((c as PositionChange).id, c as PositionChange);
        } else {
          immediate.push(c);
        }
      }
      if (buffer.size > 0 && handle == null) {
        handle = scheduleFlush(() => { doFlush(); });
      }
      // If we have immediate changes AND buffered drag positions, the caller
      // expects buffered ones first so the final state is consistent.
      if (immediate.length > 0 && buffer.size > 0) {
        if (handle != null) { cancelFlush(handle); handle = null; }
        const flushed = doFlush();
        return [...flushed, ...immediate];
      }
      return immediate;
    },
    flush() {
      if (handle != null) { cancelFlush(handle); handle = null; }
      return doFlush();
    },
    pending() { return handle != null; },
    bufferSize() { return buffer.size; },
  };
}