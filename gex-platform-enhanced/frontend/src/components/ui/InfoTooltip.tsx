import React, { useState, useRef, useEffect } from 'react';
import { Info } from 'lucide-react';

interface InfoTooltipProps {
  text: string;
  side?: 'top' | 'bottom' | 'left' | 'right';
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
export function InfoTooltip({ text, side = 'top', maxWidth = 280 }: InfoTooltipProps) {
  const [show, setShow] = useState(false);
  const [adjustedSide, setAdjustedSide] = useState(side);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Auto-adjust if tooltip would overflow viewport
  useEffect(() => {
    if (show && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      if (side === 'top' && rect.top < 80) setAdjustedSide('bottom');
      else if (side === 'bottom' && rect.bottom > window.innerHeight - 80) setAdjustedSide('top');
      else if (side === 'right' && rect.right > window.innerWidth - maxWidth - 20) setAdjustedSide('left');
      else if (side === 'left' && rect.left < maxWidth + 20) setAdjustedSide('right');
      else setAdjustedSide(side);
    }
  }, [show, side, maxWidth]);

  const positionClass = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  }[adjustedSide];

  // Arrow direction (points toward trigger)
  const arrowClass = {
    top: 'top-full left-1/2 -translate-x-1/2 border-t-gray-900 border-l-transparent border-r-transparent border-b-transparent border-4',
    bottom: 'bottom-full left-1/2 -translate-x-1/2 border-b-gray-900 border-l-transparent border-r-transparent border-t-transparent border-4',
    left: 'left-full top-1/2 -translate-y-1/2 border-l-gray-900 border-t-transparent border-b-transparent border-r-transparent border-4',
    right: 'right-full top-1/2 -translate-y-1/2 border-r-gray-900 border-t-transparent border-b-transparent border-l-transparent border-4',
  }[adjustedSide];

  return (
    <span className="relative inline-flex items-center">
      <button
        ref={triggerRef}
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)}
        onBlur={() => setShow(false)}
        className="text-gray-500 hover:text-gray-300 transition-colors cursor-help p-0.5 rounded-full hover:bg-gray-800/50"
        aria-label="More information"
        tabIndex={0}
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      {show && (
        <span
          className={`absolute z-50 ${positionClass} px-3 py-2 text-xs
            leading-relaxed rounded-lg shadow-lg pointer-events-none
            bg-gray-900 border border-gray-700 text-gray-200`}
          style={{ width: `${maxWidth}px`, maxWidth: `${maxWidth}px` }}
          role="tooltip"
        >
          {text}
          <span className={`absolute ${arrowClass}`} />
        </span>
      )}
    </span>
  );
}

export default InfoTooltip;
