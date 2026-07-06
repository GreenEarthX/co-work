// Screen: UI primitive — used across all screens
import { useState, useRef, useEffect } from "react";
import { Info } from "lucide-react";
import { createPortal } from "react-dom";

interface InfoTooltipProps {
  text: string;
  side?: "top" | "bottom" | "left" | "right";
  maxWidth?: number;
}

/**
 * GEX Info Circle Tooltip (ⓘ)
 *
 * Place next to: page titles, metric labels, action buttons,
 * status badges, column headers, form input labels.
 *
 * Usage:
 *   <span className="flex items-center gap-1.5">
 *     <span>DSCR P50</span>
 *     <InfoTooltip text="Cash Flow Available for Debt Service ÷ Debt Service. Lenders require P50 ≥ 1.30x." />
 *   </span>
 */
export function InfoTooltip({
  text,
  side = "top",
  maxWidth = 280,
}: InfoTooltipProps) {
  const [show, setShow] = useState(false);
  const [adjustedSide, setAdjustedSide] = useState(side);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLSpanElement>(null);

  // Resolve side and viewport-safe anchor.
  useEffect(() => {
    if (show && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();

      let nextSide = side;
      if (side === "top" && rect.top < 80) nextSide = "bottom";
      else if (side === "bottom" && rect.bottom > window.innerHeight - 80)
        nextSide = "top";
      else if (side === "right" && rect.right > window.innerWidth - maxWidth - 20)
        nextSide = "left";
      else if (side === "left" && rect.left < maxWidth + 20)
        nextSide = "right";
      setAdjustedSide(nextSide);

      const gap = 12;
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const nextCoords = {
        top:
          nextSide === "top"
            ? rect.top - gap
            : nextSide === "bottom"
              ? rect.bottom + gap
              : centerY,
        left:
          nextSide === "left"
            ? rect.left - gap
            : nextSide === "right"
              ? rect.right + gap
              : centerX,
      };
      setCoords(nextCoords);
    }
  }, [show, side, maxWidth]);

  const positionClass = {
    top: "-translate-x-1/2 -translate-y-full",
    bottom: "-translate-x-1/2",
    left: "-translate-x-full -translate-y-1/2",
    right: "-translate-y-1/2",
  }[adjustedSide];

  // Arrow direction (points toward trigger)
  const arrowClass = {
    top: "top-full left-1/2 -translate-x-1/2 border-t-white border-l-transparent border-r-transparent border-b-transparent border-4",
    bottom:
      "bottom-full left-1/2 -translate-x-1/2 border-b-white border-l-transparent border-r-transparent border-t-transparent border-4",
    left: "left-full top-1/2 -translate-y-1/2 border-l-white border-t-transparent border-b-transparent border-r-transparent border-4",
    right:
      "right-full top-1/2 -translate-y-1/2 border-r-white border-t-transparent border-b-transparent border-l-transparent border-4",
  }[adjustedSide];

  return (
    <span className="relative inline-flex items-center">
      {/* Trigger is a focusable <span role="button"> rather than a real <button> so that
          InfoTooltip can be placed inside other interactive elements (e.g. collapsible
          header buttons) without a `validateDOMNesting: <button> in <button>` warning. */}
      <span
        ref={triggerRef}
        role="button"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)}
        onBlur={() => setShow(false)}
        className="inline-flex cursor-help rounded-full p-0.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        aria-label="More information"
        tabIndex={0}
      >
        <Info className="w-3.5 h-3.5" />
      </span>
      {show &&
        createPortal(
          <span
            className={`fixed z-[120] ${positionClass} rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs
              leading-relaxed text-black shadow-lg pointer-events-none normal-case`}
            style={{
              top: `${coords.top}px`,
              left: `${coords.left}px`,
              width: `${maxWidth}px`,
              maxWidth: `${maxWidth}px`,
            }}
            role="tooltip"
          >
            {text}
            <span className={`absolute ${arrowClass}`} />
          </span>,
          document.body,
        )}
    </span>
  );
}

export default InfoTooltip;
