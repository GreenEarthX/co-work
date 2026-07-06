import { useState } from "react";
import { ChevronDown, ChevronRight, Copy, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/label";
import { familiesForLabel } from "@/lib/procurement/technologyMap";
import type { EquipmentConstraints } from "@/lib/procurement/simulatorTypes";

interface Props {
  eq: EquipmentConstraints;
  matchCount: number;
  onChange: (patch: Partial<EquipmentConstraints>) => void;
  onCopyToAll: () => void;
}

const UNITS = ["MW", "kW", "Nm³/h", "kg/h", "t/h", "m³/h", "bar", "MWh"];

export default function EquipmentCard({ eq, matchCount, onChange, onCopyToAll }: Props) {
  const [open, setOpen] = useState(false);
  const allFamilies = familiesForLabel(eq.label);
  const noMatch = matchCount === 0;

  const toggleTech = (fam: string) => {
    const next = eq.technologies.includes(fam)
      ? eq.technologies.filter((t) => t !== fam)
      : [...eq.technologies, fam];
    onChange({ technologies: next });
  };

  return (
    <div
      className={`rounded-md border transition ${
        noMatch ? "border-warning/40 bg-warning/5" : "border-border bg-card hover:border-border/80"
      }`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left"
      >
        <div className="flex items-center gap-2 min-w-0">
          {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          <span className="text-xs font-medium truncate">{eq.label}</span>
          <span className="text-[10px] text-muted-foreground font-mono shrink-0 tabular-nums">{eq.nodeId.slice(0, 6)}</span>
        </div>
        <span
          className={`shrink-0 inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] uppercase tracking-[0.1em] tabular-nums border ${
            noMatch
              ? "border-destructive/30 bg-destructive/5 text-destructive"
              : "border-border bg-muted/40 text-muted-foreground"
          }`}
        >
          {noMatch && <AlertTriangle className="h-3 w-3" />}
          <span className="font-mono">{matchCount}</span>
          <span>{matchCount === 1 ? "match" : "matches"}</span>
        </span>
      </button>

      {open && (
        <div className="border-t border-border/60 bg-muted/20 p-3 space-y-3">
          {allFamilies.length > 0 && (
            <div>
              <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                Technology lock-in
              </Label>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {allFamilies.map((fam) => {
                  const on = eq.technologies.includes(fam);
                  return (
                    <button
                      key={fam}
                      type="button"
                      onClick={() => toggleTech(fam)}
                      className={`px-2.5 py-1 rounded-md text-xs border transition ${
                        on
                          ? "bg-primary/10 border-primary/40 text-primary"
                          : "bg-muted/40 border-border text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      {fam}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <Label className="text-xs uppercase tracking-wide text-muted-foreground">Capacity tolerance</Label>
            <div className="mt-2 grid grid-cols-4 gap-2">
              <Input
                placeholder="Min"
                type="number"
                value={eq.capacity.min ?? ""}
                onChange={(e) =>
                  onChange({
                    capacity: { ...eq.capacity, min: e.target.value ? Number(e.target.value) : undefined },
                  })
                }
              />
              <Input
                placeholder="Nominal"
                type="number"
                value={eq.capacity.nominal ?? ""}
                onChange={(e) =>
                  onChange({
                    capacity: { ...eq.capacity, nominal: e.target.value ? Number(e.target.value) : undefined },
                  })
                }
              />
              <Input
                placeholder="Max"
                type="number"
                value={eq.capacity.max ?? ""}
                onChange={(e) =>
                  onChange({
                    capacity: { ...eq.capacity, max: e.target.value ? Number(e.target.value) : undefined },
                  })
                }
              />
              <select
                value={eq.capacity.unit}
                onChange={(e) => onChange({ capacity: { ...eq.capacity, unit: e.target.value } })}
                className="h-9 rounded-md border border-border bg-card px-2 text-xs"
              >
                {UNITS.map((u) => (
                  <option key={u} value={u}>{u}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wide text-muted-foreground">
              Cost cap (per unit, EUR)
            </Label>
            <Input
              className="mt-2"
              type="number"
              placeholder="No cap"
              value={eq.costCapEur ?? ""}
              onChange={(e) =>
                onChange({ costCapEur: e.target.value ? Number(e.target.value) : undefined })
              }
            />
          </div>

          <div className="flex justify-end pt-1">
            <Button variant="secondary" size="sm" onClick={onCopyToAll}>
              <Copy className="h-3.5 w-3.5 mr-1.5" />
              Copy to all {eq.label}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}