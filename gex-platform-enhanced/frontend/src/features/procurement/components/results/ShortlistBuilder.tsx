import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Check, RotateCcw } from "lucide-react";
import { formatEur } from "./formatHelpers";
import type { Configuration } from "@/lib/procurement/simulatorTypes";
import type { CatalogEntry } from "@/lib/equipmentCatalog";

interface Props {
  configurations: Configuration[];
  onCommit: (config: Configuration) => void;
}

export default function ShortlistBuilder({ configurations, onCommit }: Props) {
  const top = configurations[0];
  const [picks, setPicks] = useState<Record<string, CatalogEntry | null>>(() => {
    const o: Record<string, CatalogEntry | null> = {};
    top?.slots.forEach((s) => { o[s.nodeId] = s.pick; });
    return o;
  });

  const totals = useMemo(() => {
    const items = Object.values(picks).filter(Boolean) as CatalogEntry[];
    return {
      capex: items.reduce((s, i) => s + i.priceEur, 0),
      maxLead: items.length ? Math.max(...items.map((i) => i.leadTimeMonths)) : 0,
      minTrl: items.length ? Math.min(...items.map((i) => i.trl)) : 0,
    };
  }, [picks]);

  if (!top) {
    return <div className="rounded-lg border border-dashed border-border bg-muted/20 p-12 text-center text-sm text-muted-foreground">Run the simulation first.</div>;
  }

  const reset = () => {
    const o: Record<string, CatalogEntry | null> = {};
    top.slots.forEach((s) => { o[s.nodeId] = s.pick; });
    setPicks(o);
  };

  const commit = () => {
    onCommit({ ...top, slots: top.slots.map((s) => ({ ...s, pick: picks[s.nodeId] ?? null })) });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
      <div className="space-y-2">
        {top.slots.map((s) => (
          <div key={s.nodeId} className="rounded-lg border border-border bg-card p-3">
            <div className="text-sm font-medium mb-2">{s.label}</div>
            <div className="space-y-1">
              {s.candidates.slice(0, 5).map((cand, i) => {
                const sel = picks[s.nodeId]?.manufacturer === cand.manufacturer && picks[s.nodeId]?.model === cand.model;
                return (
                  <button key={i} type="button" onClick={() => setPicks({ ...picks, [s.nodeId]: cand })}
                    className={`w-full text-left px-2 py-1.5 rounded text-xs flex items-center justify-between gap-2 border transition ${sel ? "border-primary bg-primary/10" : "border-transparent hover:bg-muted/50"}`}>
                    <div className="min-w-0">
                      <div className="font-medium truncate">{cand.manufacturer} · {cand.model}</div>
                      <div className="text-muted-foreground">{cand.country} · TRL {cand.trl} · {cand.leadTimeMonths}mo</div>
                    </div>
                    <div className="font-mono shrink-0">{cand.priceDisplay}</div>
                  </button>
                );
              })}
              {s.candidates.length === 0 && <div className="text-xs text-destructive px-2">No matches.</div>}
            </div>
          </div>
        ))}
      </div>
      <div className="space-y-2 lg:sticky lg:top-4 lg:self-start">
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <div className="text-sm font-semibold">Running totals</div>
          <div className="space-y-1.5 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">CAPEX</span><span className="font-mono font-semibold">{formatEur(totals.capex)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Max lead time</span><span className="font-mono font-semibold">{totals.maxLead} mo</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Min TRL</span><span className="font-mono font-semibold">{totals.minTrl || "—"}</span></div>
          </div>
          <div className="space-y-2 pt-2 border-t border-border">
            <Button onClick={commit} className="w-full" size="sm"><Check className="h-3.5 w-3.5 mr-1.5" /> Commit selection</Button>
            <Button onClick={reset} variant="secondary" className="w-full" size="sm"><RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Reset to top-ranked</Button>
          </div>
        </div>
      </div>
    </div>
  );
}