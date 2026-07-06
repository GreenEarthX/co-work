import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { AlertTriangle, ChevronDown, ChevronRight, Check } from "lucide-react";
import { formatEur } from "./formatHelpers";
import type { Configuration } from "@/lib/procurement/simulatorTypes";

interface Props {
  configurations: Configuration[];
  onCommit: (config: Configuration) => void;
  committingId?: string | null;
}

export default function ConfigCards({ configurations, onCommit, committingId }: Props) {
  if (configurations.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-muted/20 p-12 text-center text-sm text-muted-foreground">
        No configurations to show. Run the simulation, or relax the constraints.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {configurations.map((c) => (
        <ConfigCard key={c.id} c={c} total={configurations.length} isTop={c.rank === 1} onCommit={() => onCommit(c)} committing={committingId === c.id} />
      ))}
    </div>
  );
}

function ConfigCard({ c, total, isTop, onCommit, committing }: { c: Configuration; total: number; isTop: boolean; onCommit: () => void; committing: boolean }) {
  const [open, setOpen] = useState(false);
  const rankLabel = `${String(c.rank).padStart(2, "0")} / ${String(total).padStart(2, "0")}`;
  return (
    <div
      className={`rounded-lg border bg-card overflow-hidden transition ${
        isTop ? "border-primary/40" : "border-border hover:border-border/80"
      }`}
    >
      <div className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono tabular-nums uppercase tracking-[0.14em] text-muted-foreground">
              {rankLabel}
            </span>
            {isTop && (
              <span className="text-[10px] uppercase tracking-[0.12em] text-primary font-medium">
                Top
              </span>
            )}
            {c.warnings.length > 0 && (
              <span className="inline-flex items-center gap-1 text-[10px] text-warning border border-warning/40 px-1.5 py-0.5 rounded">
                <AlertTriangle className="h-3 w-3" /> {c.warnings.length}
              </span>
            )}
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Score</div>
            <div className="font-mono text-lg font-semibold tabular-nums">{c.score.total.toFixed(0)}</div>
          </div>
        </div>
        <div className="grid grid-cols-4 gap-2 text-xs">
          <Metric label="CAPEX" value={formatEur(c.totals.capexEur)} />
          <Metric label="Avg eff" value={`${c.totals.avgEfficiencyScore.toFixed(0)}%`} />
          <Metric label="Lead time" value={`${c.totals.maxLeadTimeMonths}mo`} />
          <Metric label="Min TRL" value={String(c.totals.minTrl || "—")} />
        </div>
        <button type="button" onClick={() => setOpen(o => !o)} className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition">
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {open ? "Hide" : "Drill in"} ({c.slots.length} equipment)
        </button>
        {open && (
          <div className="rounded-md border border-border bg-muted/20 divide-y divide-border text-xs">
            {c.slots.map((s) => (
              <div key={s.nodeId} className="p-2 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-medium truncate">{s.label}</div>
                  {s.pick ? (
                    <div className="text-muted-foreground truncate">{s.pick.manufacturer} · {s.pick.model}</div>
                  ) : (
                    <div className="text-destructive">No match</div>
                  )}
                </div>
                {s.pick && (
                  <div className="text-right shrink-0">
                    <div className="font-mono">{s.pick.priceDisplay}</div>
                    <div className="text-muted-foreground">{s.pick.country}</div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {c.warnings.length > 0 && (
          <div className="rounded-md border border-warning/30 bg-warning/5 p-2 text-xs space-y-0.5">
            {c.warnings.map((w, i) => (
              <div key={i} className="flex gap-1.5">
                <AlertTriangle className="h-3 w-3 text-warning shrink-0 mt-0.5" />
                <span>{w.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="border-t border-border/60 px-3 py-2 bg-card flex justify-end">
        <Button onClick={onCommit} disabled={committing} variant="secondary" size="sm">
          {committing ? "Committing…" : (<><Check className="h-3.5 w-3.5 mr-1.5" /> Commit to plant</>)}
        </Button>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border/60 bg-muted/20 p-2">
      <div className="text-[10px] uppercase text-muted-foreground tracking-[0.12em]">{label}</div>
      <div className="font-mono font-semibold tabular-nums">{value}</div>
    </div>
  );
}