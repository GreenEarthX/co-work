import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Pencil, Settings2, Trash2, Copy } from "lucide-react";

interface NodeContextMenuProps {
  x: number;
  y: number;
  nodeType: string;
  onRename: () => void;
  onEditDetails: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onClose: () => void;
}

export function NodeContextMenu({
  x,
  y,
  nodeType,
  onRename,
  onEditDetails,
  onDuplicate,
  onDelete,
  onClose,
}: NodeContextMenuProps) {
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

  const left = Math.min(x, window.innerWidth - 220);
  const top = Math.min(y, window.innerHeight - 140);

  // Carriers and gates don't have a rich detail dialog like equipment, but
  // double-click still opens whatever the canvas wires up — so we show the
  // option for all node types.
  const showEditDetails = nodeType !== "boundary";

  return createPortal(
    <div
      ref={ref}
      className="fixed z-[9999] min-w-[200px] rounded-md border border-border bg-popover text-popover-foreground shadow-lg py-1"
      style={{ left, top }}
      role="menu"
    >
      <button
        type="button"
        autoFocus
        onClick={() => {
          onRename();
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent focus:bg-accent focus:outline-none"
        role="menuitem"
      >
        <Pencil className="h-3.5 w-3.5" />
        Rename
        <span className="ml-auto text-[10px] text-muted-foreground">name only</span>
      </button>
      {showEditDetails && (
        <button
          type="button"
          onClick={() => {
            onEditDetails();
            onClose();
          }}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent focus:bg-accent focus:outline-none"
          role="menuitem"
        >
          <Settings2 className="h-3.5 w-3.5" />
          Edit details
          <span className="ml-auto text-[10px] text-muted-foreground">all properties</span>
        </button>
      )}
      <button
        type="button"
        onClick={() => {
          onDuplicate();
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent focus:bg-accent focus:outline-none"
        role="menuitem"
      >
        <Copy className="h-3.5 w-3.5" />
        Duplicate
        <span className="ml-auto text-[10px] text-muted-foreground">copy</span>
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
        Delete
      </button>
    </div>,
    document.body
  );
}
