import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Trash2, ArrowLeftRight, Package, Activity } from "lucide-react";

interface EdgeContextMenuProps {
  x: number;
  y: number;
  flowMode?: "continuous" | "batch";
  onReverse: () => void;
  onDelete: () => void;
  onSwitchToBatch?: () => void;
  onSwitchToContinuous?: () => void;
  onEditBatch?: () => void;
  onClose: () => void;
}

export function EdgeContextMenu({
  x,
  y,
  flowMode = "continuous",
  onReverse,
  onDelete,
  onSwitchToBatch,
  onSwitchToContinuous,
  onEditBatch,
  onClose,
}: EdgeContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    window.addEventListener("wheel", onClose, { passive: true });
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("wheel", onClose);
    };
  }, [onClose]);

  // Clamp to viewport
  const left = Math.min(x, window.innerWidth - 220);
  const top = Math.min(y, window.innerHeight - 200);

  return createPortal(
    <div
      ref={ref}
      className="fixed z-[9999] min-w-[200px] rounded-md border border-border bg-popover text-popover-foreground shadow-lg py-1"
      style={{ left, top }}
      role="menu"
    >
      {flowMode === "continuous" && onSwitchToBatch && (
        <button
          type="button"
          onClick={() => { onSwitchToBatch(); onClose(); }}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent focus:bg-accent focus:outline-none"
          role="menuitem"
        >
          <Package className="h-3.5 w-3.5" />
          Switch to batch flow
        </button>
      )}
      {flowMode === "batch" && onEditBatch && (
        <button
          type="button"
          onClick={() => { onEditBatch(); onClose(); }}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent focus:bg-accent focus:outline-none"
          role="menuitem"
        >
          <Package className="h-3.5 w-3.5" />
          Edit batch details…
        </button>
      )}
      {flowMode === "batch" && onSwitchToContinuous && (
        <button
          type="button"
          onClick={() => { onSwitchToContinuous(); onClose(); }}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent focus:bg-accent focus:outline-none"
          role="menuitem"
        >
          <Activity className="h-3.5 w-3.5" />
          Switch to continuous flow
        </button>
      )}
      {(onSwitchToBatch || onSwitchToContinuous || onEditBatch) && (
        <div className="my-1 h-px bg-border mx-1" />
      )}
      <button
        type="button"
        autoFocus
        onClick={() => {
          onReverse();
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent focus:bg-accent focus:outline-none"
        role="menuitem"
      >
        <ArrowLeftRight className="h-3.5 w-3.5" />
        Reverse direction
      </button>
      <div className="my-1 h-px bg-border mx-1" />
      <button
        type="button"
        onClick={() => {
          onDelete();
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10 focus:bg-destructive/10 focus:outline-none"
        role="menuitem"
      >
        <Trash2 className="h-3.5 w-3.5" />
        Delete stream
      </button>
    </div>,
    document.body
  );
}