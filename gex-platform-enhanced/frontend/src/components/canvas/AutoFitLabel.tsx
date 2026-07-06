import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";

interface AutoFitLabelProps {
  text: string;
  /** Base (max) font size in px. Will scale down to `minSize` if needed. */
  maxSize?: number;
  /** Smallest allowed font size in px. */
  minSize?: number;
  /** Optional className for the wrapping element. */
  className?: string;
  /** Inline style overrides (e.g. color). */
  style?: CSSProperties;
  /** Fixed line-height multiplier. */
  lineHeight?: number;
}

/**
 * AutoFitLabel — renders a label that always fits inside its parent box.
 * Combines `break-words` + `hyphens: auto` for graceful wrapping with a
 * binary-search font-size shrink so long words never clip or overflow.
 */
export function AutoFitLabel({
  text,
  maxSize = 12,
  minSize = 8,
  className = "",
  style,
  lineHeight = 1.2,
}: AutoFitLabelProps) {
  const ref = useRef<HTMLParagraphElement>(null);
  const [size, setSize] = useState(maxSize);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const parent = el.parentElement;
    if (!parent) return;

    let lo = minSize;
    let hi = maxSize;
    let best = minSize;
    // Binary search for the largest font size that doesn't overflow.
    while (lo <= hi) {
      const mid = Math.floor((lo + hi) / 2);
      el.style.fontSize = `${mid}px`;
      const overflowsW = el.scrollWidth > parent.clientWidth;
      const overflowsH = el.scrollHeight > parent.clientHeight;
      if (overflowsW || overflowsH) {
        hi = mid - 1;
      } else {
        best = mid;
        lo = mid + 1;
      }
    }
    setSize(best);
    el.style.fontSize = "";
  }, [text, maxSize, minSize]);

  return (
    <p
      ref={ref}
      className={`text-center break-words [hyphens:auto] max-w-full ${className}`}
      style={{
        fontSize: `${size}px`,
        lineHeight,
        wordBreak: "break-word",
        overflowWrap: "anywhere",
        ...style,
      }}
    >
      {text}
    </p>
  );
}