import { memo, useCallback, useRef, useEffect } from "react";
import { NodeProps } from "@xyflow/react";
import { Building2 } from "lucide-react";

type ResizeSide = "left" | "right" | "top" | "bottom";
type ResizeHandle = ResizeSide | "top-left" | "top-right" | "bottom-left" | "bottom-right";

const HANDLE_THICKNESS = 14;
const CORNER_SIZE = 18;

/** Map a corner/side handle to the individual sides it affects */
function sidesFor(handle: ResizeHandle): ResizeSide[] {
  switch (handle) {
    case "top-left": return ["top", "left"];
    case "top-right": return ["top", "right"];
    case "bottom-left": return ["bottom", "left"];
    case "bottom-right": return ["bottom", "right"];
    default: return [handle];
  }
}

const BoundaryNode = memo(({ data }: NodeProps) => {
  const w = (data.width as number) || 1000;
  const h = (data.height as number) || 400;
  const orientation = (data.orientation as string) || "horizontal";
  const isVertical = orientation === "vertical";
  const onOpenInfrastructure = data.onOpenInfrastructure as (() => void) | undefined;

  const onResizeDragRef = useRef(data.onResizeDrag as ((side: ResizeSide, dx: number, dy: number) => void) | undefined);
  const onResizeEndRef = useRef(data.onResizeEnd as (() => void) | undefined);
  useEffect(() => {
    onResizeDragRef.current = data.onResizeDrag as ((side: ResizeSide, dx: number, dy: number) => void) | undefined;
    onResizeEndRef.current = data.onResizeEnd as (() => void) | undefined;
  }, [data.onResizeDrag, data.onResizeEnd]);

  const startRef = useRef<{ handle: ResizeHandle; startX: number; startY: number } | null>(null);

  const handlePointerDown = useCallback((handle: ResizeHandle, e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation();
    e.preventDefault();
    const target = e.currentTarget;
    target.setPointerCapture(e.pointerId);
    startRef.current = { handle, startX: e.clientX, startY: e.clientY };

    const handleMove = (ev: PointerEvent) => {
      if (!startRef.current) return;
      ev.preventDefault();
      ev.stopPropagation();
      const dx = ev.clientX - startRef.current.startX;
      const dy = ev.clientY - startRef.current.startY;
      startRef.current.startX = ev.clientX;
      startRef.current.startY = ev.clientY;
      const sides = sidesFor(startRef.current.handle);
      for (const side of sides) {
        onResizeDragRef.current?.(side, dx, dy);
      }
    };

    const handleUp = (ev: PointerEvent) => {
      ev.preventDefault();
      startRef.current = null;
      target.releasePointerCapture(ev.pointerId);
      onResizeEndRef.current?.();
      target.removeEventListener("pointermove", handleMove);
      target.removeEventListener("pointerup", handleUp);
    };

    target.addEventListener("pointermove", handleMove);
    target.addEventListener("pointerup", handleUp);
  }, []);

  const edgeHandles: { handle: ResizeSide; style: React.CSSProperties }[] = [
    {
      handle: "left",
      style: {
        position: "absolute", left: 0, top: CORNER_SIZE, width: HANDLE_THICKNESS, height: `calc(100% - ${CORNER_SIZE * 2}px)`,
        cursor: "ew-resize", zIndex: 100,
      },
    },
    {
      handle: "right",
      style: {
        position: "absolute", right: 0, top: CORNER_SIZE, width: HANDLE_THICKNESS, height: `calc(100% - ${CORNER_SIZE * 2}px)`,
        cursor: "ew-resize", zIndex: 100,
      },
    },
    {
      handle: "top",
      style: {
        position: "absolute", top: 0, left: CORNER_SIZE, height: HANDLE_THICKNESS, width: `calc(100% - ${CORNER_SIZE * 2}px)`,
        cursor: "ns-resize", zIndex: 100,
      },
    },
    {
      handle: "bottom",
      style: {
        position: "absolute", bottom: 0, left: CORNER_SIZE, height: HANDLE_THICKNESS, width: `calc(100% - ${CORNER_SIZE * 2}px)`,
        cursor: "ns-resize", zIndex: 100,
      },
    },
  ];

  const cornerHandles: { handle: ResizeHandle; style: React.CSSProperties; cursor: string }[] = [
    { handle: "top-left", cursor: "nwse-resize", style: { position: "absolute", top: 0, left: 0, width: CORNER_SIZE, height: CORNER_SIZE, zIndex: 110 } },
    { handle: "top-right", cursor: "nesw-resize", style: { position: "absolute", top: 0, right: 0, width: CORNER_SIZE, height: CORNER_SIZE, zIndex: 110 } },
    { handle: "bottom-left", cursor: "nesw-resize", style: { position: "absolute", bottom: 0, left: 0, width: CORNER_SIZE, height: CORNER_SIZE, zIndex: 110 } },
    { handle: "bottom-right", cursor: "nwse-resize", style: { position: "absolute", bottom: 0, right: 0, width: CORNER_SIZE, height: CORNER_SIZE, zIndex: 110 } },
  ];

  return (
    <div
      style={{ width: w, height: h, position: "relative" }}
      className="rounded-2xl border-[3px] border-dashed border-primary/40 bg-primary/[0.04] pointer-events-none shadow-[inset_0_0_60px_rgba(0,0,0,0.03)]"
    >
      {/* Site Infrastructure shortcut — sits just outside the top-right corner */}
      {onOpenInfrastructure && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onOpenInfrastructure(); }}
          className="nodrag nopan pointer-events-auto absolute -top-3 right-3 z-[120] flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-card border border-primary/30 text-[11px] font-medium text-primary shadow-sm hover:bg-primary/10 hover:border-primary/60 transition-colors"
          title="Open Site Infrastructure (non-process equipment, construction & site costs)"
        >
          <Building2 className="h-3 w-3" />
          Site Infrastructure
        </button>
      )}

      {/* Edge handles */}
      {edgeHandles.map(({ handle, style }) => (
        <div
          key={handle}
          onPointerDown={(e) => handlePointerDown(handle, e)}
          style={style}
          className="group nodrag nopan pointer-events-auto"
        >
          <div className="absolute inset-0 bg-primary/0 group-hover:bg-primary/15 transition-colors duration-150" />
        </div>
      ))}

      {/* Corner handles */}
      {cornerHandles.map(({ handle, style, cursor }) => (
        <div
          key={handle}
          onPointerDown={(e) => handlePointerDown(handle, e)}
          style={{ ...style, cursor }}
          className="group nodrag nopan pointer-events-auto"
        >
          <div className="absolute inset-0 bg-primary/0 group-hover:bg-primary/20 rounded-lg transition-colors duration-150" />
          {/* Diagonal arrow icon */}
          <svg
            className="absolute inset-0 m-auto opacity-0 group-hover:opacity-60 transition-opacity duration-150 text-primary"
            width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
          >
            {handle === "top-left" && <><line x1="8" y1="2" x2="2" y2="8" /><polyline points="2,2 8,2" /><polyline points="2,8 2,2" /></>}
            {handle === "top-right" && <><line x1="2" y1="2" x2="8" y2="8" /><polyline points="2,2 8,2" /><polyline points="8,2 8,8" /></>}
            {handle === "bottom-left" && <><line x1="8" y1="8" x2="2" y2="2" /><polyline points="2,2 2,8" /><polyline points="2,8 8,8" /></>}
            {handle === "bottom-right" && <><line x1="2" y1="8" x2="8" y2="2" /><polyline points="8,2 8,8" /><polyline points="2,8 8,8" /></>}
          </svg>
        </div>
      ))}

      {isVertical ? (
        <>
          <div className="absolute top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-primary/10 border border-primary/20 pointer-events-none">
            <span className="text-[11px] font-bold text-primary/60 uppercase tracking-widest">System Boundary</span>
          </div>
          <div className="absolute top-10 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-sky-500/10 border border-sky-400/20 pointer-events-none">
            <span className="text-sm font-bold text-sky-600 dark:text-sky-400">↑ UPSTREAM</span>
          </div>
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-amber-500/10 border border-amber-400/20 pointer-events-none">
            <span className="text-sm font-bold text-amber-600 dark:text-amber-400">DOWNSTREAM ↓</span>
          </div>
        </>
      ) : (
        <>
          <div className="absolute top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-primary/10 border border-primary/20 pointer-events-none">
            <span className="text-[11px] font-bold text-primary/60 uppercase tracking-widest">System Boundary</span>
          </div>
          <div className="absolute bottom-4 left-5 px-3 py-1 rounded-md bg-sky-500/10 border border-sky-400/20 pointer-events-none">
            <span className="text-sm font-bold text-sky-600 dark:text-sky-400">UPSTREAM →</span>
          </div>
          <div className="absolute bottom-4 right-5 px-3 py-1 rounded-md bg-amber-500/10 border border-amber-400/20 pointer-events-none">
            <span className="text-sm font-bold text-amber-600 dark:text-amber-400">DOWNSTREAM →</span>
          </div>
        </>
      )}
    </div>
  );
});
BoundaryNode.displayName = "BoundaryNode";

export default BoundaryNode;
