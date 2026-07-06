import { useCallback, useRef, useState } from "react";
import type { Node, Edge } from "@xyflow/react";

export interface CanvasSnapshot {
  nodes: Node[];
  edges: Edge[];
}

const MAX_HISTORY = 30;

/**
 * Simple undo stack for the plant canvas.
 * Call `pushSnapshot` before any mutating action to capture state.
 * Call `undo` to restore the most recent snapshot.
 */
export function useCanvasHistory() {
  const stack = useRef<CanvasSnapshot[]>([]);
  // Counter drives re-renders so canUndo reflects current stack size
  const [stackSize, setStackSize] = useState(0);

  const pushSnapshot = useCallback((nodes: Node[], edges: Edge[]) => {
    const snap: CanvasSnapshot = {
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    };
    stack.current.push(snap);
    if (stack.current.length > MAX_HISTORY) {
      stack.current.shift();
    }
    setStackSize(stack.current.length);
  }, []);

  const undo = useCallback((): CanvasSnapshot | null => {
    const snap = stack.current.pop() ?? null;
    setStackSize(stack.current.length);
    return snap;
  }, []);

  const canUndo = stackSize > 0;

  return { pushSnapshot, undo, canUndo };
}
