/**
 * ConstraintPanel — Step 1 of the Procurement Simulator.
 *
 * Global filters (TRL, geography, vendors, cost/lead caps) + per-equipment
 * refinement cards. No scoring weights, no configuration-count picker — the
 * engine uses fixed institutional defaults.
 */
import { useState } from "react";
import { Input } from "@/components/ui/Input";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/Badge";
import { X } from "lucide-react";
import EquipmentCard from "./EquipmentCard";
import {
  REGION_OPTIONS,
  type GlobalPreferences,
  type RegionKey,
  type EquipmentConstraints,
} from "@/lib/procurement/simulatorTypes";

interface Props {
  globals: GlobalPreferences;
  setGlobals: (g: GlobalPreferences) => void;
  equipment: EquipmentConstraints[];
  matchCounts: Record<string, number>;
  onEquipmentChange: (nodeId: string, patch: Partial<EquipmentConstraints>) => void;
  onCopyToAll: (nodeId: string, label: string) => void;
  totalSlotMatches: number;
  totalSlotPool: number;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-medium">
      {children}
    </div>
  );
}

export default function ConstraintPanel({
  globals,
  setGlobals,
  equipment,
  matchCounts,
  onEquipmentChange,
  onCopyToAll,
  totalSlotMatches,
  totalSlotPool,
}: Props) {
  const [vendorInput, setVendorInput] = useState("");
  const [excludedInput, setExcludedInput] = useState("");

  const toggleRegion = (r: RegionKey) => {
    const next = globals.regions.includes(r)
      ? globals.regions.filter((x) => x !== r)
      : [...globals.regions, r];
    setGlobals({ ...globals, regions: next });
  };

  const addChip = (
    field: "preferredManufacturers" | "excludedManufacturers",
    value: string,
    setter: (v: string) => void,
  ) => {
    const v = value.trim();
    if (!v || globals[field].includes(v)) return;
    setGlobals({ ...globals, [field]: [...globals[field], v] });
    setter("");
  };

  const removeChip = (
    field: "preferredManufacturers" | "excludedManufacturers",
    value: string,
  ) => {
    setGlobals({ ...globals, [field]: globals[field].filter((x) => x !== value) });
  };

  return (
    <div className="flex flex-col">
      <div className="p-5 space-y-6">
        {/* Global filters */}
        <section className="space-y-5">
          <div className="flex items-baseline justify-between border-b border-border/60 pb-2">
            <SectionLabel>Global Filters</SectionLabel>
            <span className="text-[11px] text-muted-foreground tabular-nums">
              {totalSlotMatches.toLocaleString()} / {totalSlotPool.toLocaleString()} relevant suppliers match
            </span>
          </div>

          {/* TRL */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <SectionLabel>Technology Readiness Level minimum</SectionLabel>
              <span className="text-xs font-mono text-foreground">{globals.trlMin}</span>
            </div>
            <Slider
              value={[globals.trlMin]}
              onValueChange={(v) => setGlobals({ ...globals, trlMin: v[0] })}
              min={1}
              max={9}
              step={1}
            />
          </div>

          {/* Geography */}
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <SectionLabel>Geography — Regions</SectionLabel>
              <span className="text-[10px] text-muted-foreground">
                {globals.regions.length === 0 ? "All regions" : `${globals.regions.length} selected`}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {REGION_OPTIONS.map((r) => {
                const on = globals.regions.includes(r);
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => toggleRegion(r)}
                    className={`px-2.5 py-1 rounded-md text-[11px] border transition ${
                      on
                        ? "bg-primary/10 border-primary/40 text-primary"
                        : "bg-card border-border text-muted-foreground hover:border-border/80 hover:text-foreground"
                    }`}
                  >
                    {r}
                  </button>
                );
              })}
            </div>
            <p className="text-[10px] text-muted-foreground">
              Select one or more regions to scope suppliers. Leave empty to include all regions.
            </p>
          </div>

          {/* Vendors */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <SectionLabel>Preferred Manufacturers</SectionLabel>
              <Input
                placeholder="Type and press Enter"
                value={vendorInput}
                onChange={(e) => setVendorInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addChip("preferredManufacturers", vendorInput, setVendorInput);
                  }
                }}
                className="h-9 text-xs"
              />
              {globals.preferredManufacturers.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {globals.preferredManufacturers.map((m) => (
                    <Badge key={m} variant="default" className="gap-1 font-normal">
                      {m}
                      <button onClick={() => removeChip("preferredManufacturers", m)} type="button">
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <SectionLabel>Excluded Manufacturers</SectionLabel>
              <Input
                placeholder="Type and press Enter"
                value={excludedInput}
                onChange={(e) => setExcludedInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addChip("excludedManufacturers", excludedInput, setExcludedInput);
                  }
                }}
                className="h-9 text-xs"
              />
              {globals.excludedManufacturers.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {globals.excludedManufacturers.map((m) => (
                    <Badge key={m} variant="danger" className="gap-1 font-normal">
                      {m}
                      <button onClick={() => removeChip("excludedManufacturers", m)} type="button">
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Cost & lead time */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <SectionLabel>Total CAPEX cap (EUR)</SectionLabel>
              <Input
                type="number"
                placeholder="Optional"
                value={globals.totalCapexCapEur ?? ""}
                onChange={(e) =>
                  setGlobals({
                    ...globals,
                    totalCapexCapEur: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                className="h-9 text-xs"
              />
            </div>
            <div className="space-y-2">
              <SectionLabel>Max lead time (months)</SectionLabel>
              <Input
                type="number"
                placeholder="Optional"
                value={globals.maxLeadTimeMonths ?? ""}
                onChange={(e) =>
                  setGlobals({
                    ...globals,
                    maxLeadTimeMonths: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                className="h-9 text-xs"
              />
            </div>
          </div>
        </section>

        {/* Equipment */}
        <section className="space-y-3">
          <div className="flex items-baseline justify-between border-b border-border/60 pb-2">
            <SectionLabel>Per-Equipment Refinement</SectionLabel>
            <span className="text-[11px] text-muted-foreground tabular-nums">
              {equipment.length} equipment item{equipment.length === 1 ? "" : "s"}
            </span>
          </div>
          <div className="space-y-2">
            {equipment.map((eq) => (
              <EquipmentCard
                key={eq.nodeId}
                eq={eq}
                matchCount={matchCounts[eq.nodeId] ?? 0}
                onChange={(patch) => onEquipmentChange(eq.nodeId, patch)}
                onCopyToAll={() => onCopyToAll(eq.nodeId, eq.label)}
              />
            ))}
            {equipment.length === 0 && (
              <div className="rounded-md border border-dashed border-border bg-muted/20 p-8 text-center text-xs text-muted-foreground">
                No equipment found on this plant canvas yet.
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}