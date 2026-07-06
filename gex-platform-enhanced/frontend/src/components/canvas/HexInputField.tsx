import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/Input";

interface HexInputFieldProps {
  value: string;
  onChange: (hex: string) => void;
}

const HEX_RE = /^#[0-9a-f]{6}$/;

function normalize(raw: string): string {
  let v = raw.trim().toLowerCase();
  if (!v.startsWith("#")) v = "#" + v;
  v = "#" + v.slice(1).replace(/[^0-9a-f]/g, "");
  return v.slice(0, 7);
}

export function HexInputField({ value, onChange }: HexInputFieldProps) {
  const [draft, setDraft] = useState(value);
  const focusedRef = useRef(false);

  useEffect(() => {
    if (!focusedRef.current) setDraft(value);
  }, [value]);

  return (
    <Input
      value={draft}
      spellCheck={false}
      aria-label="Hex color value"
      className="h-7 w-full font-mono text-[11px]"
      onFocus={() => { focusedRef.current = true; }}
      onBlur={() => {
        focusedRef.current = false;
        if (!HEX_RE.test(draft)) setDraft(value);
      }}
      onChange={(e) => {
        const next = normalize(e.target.value);
        setDraft(next);
        if (HEX_RE.test(next)) onChange(next);
      }}
    />
  );
}