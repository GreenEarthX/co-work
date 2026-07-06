import { useEffect, useRef, useState } from "react";
import { HexColorPicker } from "react-colorful";

interface PrecisionColorPickerProps {
  color: string;
  onChange: (c: string) => void;
}

/**
 * Wraps react-colorful's HexColorPicker and adds a "precision mode":
 * while a drag is active, holding Shift scales pointer movement by 0.25,
 * so the saturation/hue bubble moves in smaller increments for fine tuning.
 *
 * Implementation: intercepts pointermove in the capture phase. Real
 * (isTrusted) events are halted while Shift is held, and a synthetic
 * pointermove with scaled coordinates is dispatched in their place so
 * react-colorful still updates.
 */
export function PrecisionColorPicker({ color, onChange }: PrecisionColorPickerProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [shiftHeld, setShiftHeld] = useState(false);
  const [dragging, setDragging] = useState(false);

  const stateRef = useRef({
    active: false,
    lastX: 0,
    lastY: 0,
    virtX: 0,
    virtY: 0,
    pointerId: 0,
  });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;

    const SCALE = 0.25;

    const onDown = (e: PointerEvent) => {
      stateRef.current = {
        active: true,
        lastX: e.clientX,
        lastY: e.clientY,
        virtX: e.clientX,
        virtY: e.clientY,
        pointerId: e.pointerId,
      };
      setDragging(true);
    };

    const onMoveCapture = (e: PointerEvent) => {
      if (!stateRef.current.active) return;
      if (!e.isTrusted) return; // ignore our own synthetic events

      const dx = e.clientX - stateRef.current.lastX;
      const dy = e.clientY - stateRef.current.lastY;
      stateRef.current.lastX = e.clientX;
      stateRef.current.lastY = e.clientY;

      if (!e.shiftKey) {
        // Normal mode: let the original event through, keep virt synced.
        stateRef.current.virtX = e.clientX;
        stateRef.current.virtY = e.clientY;
        return;
      }

      // Shift held — block real event, dispatch a scaled synthetic one.
      stateRef.current.virtX += dx * SCALE;
      stateRef.current.virtY += dy * SCALE;

      e.stopImmediatePropagation();
      e.preventDefault();

      const fake = new PointerEvent("pointermove", {
        clientX: stateRef.current.virtX,
        clientY: stateRef.current.virtY,
        pointerId: stateRef.current.pointerId,
        bubbles: true,
        cancelable: true,
        pointerType: e.pointerType,
        isPrimary: true,
      });
      document.dispatchEvent(fake);
    };

    const onUp = () => {
      if (stateRef.current.active) {
        stateRef.current.active = false;
        setDragging(false);
      }
    };

    const onKey = (e: KeyboardEvent) => setShiftHeld(e.shiftKey);

    el.addEventListener("pointerdown", onDown);
    document.addEventListener("pointermove", onMoveCapture, { capture: true });
    document.addEventListener("pointerup", onUp, { capture: true });
    document.addEventListener("pointercancel", onUp, { capture: true });
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onKey);

    return () => {
      el.removeEventListener("pointerdown", onDown);
      document.removeEventListener("pointermove", onMoveCapture, { capture: true } as EventListenerOptions);
      document.removeEventListener("pointerup", onUp, { capture: true } as EventListenerOptions);
      document.removeEventListener("pointercancel", onUp, { capture: true } as EventListenerOptions);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keyup", onKey);
    };
  }, []);

  const showActive = dragging && shiftHeld;

  return (
    <div className="space-y-1.5">
      <div ref={wrapRef} className={showActive ? "ring-2 ring-primary/60 rounded" : undefined}>
        <HexColorPicker color={color} onChange={onChange} />
      </div>
      <p className="text-[10px] text-muted-foreground leading-tight">
        Hold{" "}
        <kbd className={`px-1 py-px rounded border text-[9px] font-mono ${showActive ? "bg-primary text-primary-foreground border-primary" : "bg-muted border-border"}`}>
          Shift
        </kbd>{" "}
        while dragging for precise adjustments.
      </p>
    </div>
  );
}
