/**
 * EurNumberInput — Numeric input that displays thousand-separated digits
 * while typing/blurring but stores raw `number` values upstream. EUR symbol
 * appears as a leading adornment so users see "€ 1,234,000" instead of
 * "1234000".
 */
import { useEffect, useId, useState } from "react";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/utils";

interface Props {
  id?: string;
  value: number;
  onChange: (val: number) => void;
  className?: string;
  inputClassName?: string;
  ariaDescribedBy?: string;
  ariaLabel?: string;
  /** Hide the leading € adornment (e.g. when used for hectares or %) */
  noSymbol?: boolean;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
}

function formatGrouped(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(n);
}

function parseGrouped(s: string): number {
  const cleaned = s.replace(/[^0-9.-]/g, "");
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : 0;
}

export default function EurNumberInput({
  id, value, onChange, className, inputClassName, ariaDescribedBy, ariaLabel,
  noSymbol = false, min = 0, max, step, placeholder,
}: Props) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const [text, setText] = useState<string>(() => formatGrouped(value));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setText(formatGrouped(value));
  }, [value, focused]);

  return (
    <div className={cn("relative", className)}>
      {!noSymbol && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground"
        >
          €
        </span>
      )}
      <Input
        id={inputId}
        inputMode="numeric"
        type="text"
        autoComplete="off"
        aria-describedby={ariaDescribedBy}
        aria-label={ariaLabel}
        className={cn(noSymbol ? "" : "pl-6", "tabular-nums", inputClassName)}
        value={text}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          const n = parseGrouped(text);
          const bounded = Math.max(min, max != null ? Math.min(max, n) : n);
          onChange(bounded);
          setText(formatGrouped(bounded));
        }}
        onChange={(e) => {
          const next = e.target.value;
          setText(next);
          // Live-propagate raw number so totals/auto-save update as user types.
          onChange(parseGrouped(next));
        }}
      />
    </div>
  );
}