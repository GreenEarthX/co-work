import { Button } from "@/components/ui/Button";
import { Download, Check } from "lucide-react";
import { formatEur } from "./formatHelpers";
import type { Configuration } from "@/lib/procurement/simulatorTypes";

interface Props {
  configurations: Configuration[];
  onCommit: (config: Configuration) => void;
}

export default function ComparisonMatrix({ configurations, onCommit }: Props) {
  if (configurations.length === 0) {
    return <div className="rounded-lg border border-dashed border-border bg-muted/20 p-12 text-center text-sm text-muted-foreground">Run the simulation to compare configurations.</div>;
  }
  const slots = configurations[0].slots;
  const downloadCsv = () => {
    const header = ["Equipment", ...configurations.map((c) => `Config #${c.rank}`)].join(",");
    const rows = slots.map((s, i) => {
      return [escapeCsv(s.label), ...configurations.map((c) => {
        const slot = c.slots[i];
        return slot.pick ? escapeCsv(`${slot.pick.manufacturer} ${slot.pick.model} (${slot.pick.priceDisplay})`) : "—";
      })].join(",");
    });
    const totals = ["TOTAL CAPEX", ...configurations.map((c) => formatEur(c.totals.capexEur))].join(",");
    const csv = [header, ...rows, totals].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "procurement-comparison.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button variant="secondary" size="sm" onClick={downloadCsv}><Download className="h-3.5 w-3.5 mr-1.5" /> Export CSV</Button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-xs border-collapse">
          <thead className="bg-muted/40">
            <tr>
              <th className="text-left p-2 border-b border-border sticky left-0 bg-muted/40 z-10">Equipment</th>
              {configurations.map((c) => (
                <th key={c.id} className="text-left p-2 border-b border-l border-border min-w-[180px]">
                  <div className="font-mono">Config #{c.rank}</div>
                  <div className="text-muted-foreground font-normal">Score {c.score.total.toFixed(0)}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slots.map((s, i) => (
              <tr key={s.nodeId} className="hover:bg-muted/20">
                <td className="p-2 border-b border-border font-medium sticky left-0 bg-card z-10">{s.label}</td>
                {configurations.map((c) => {
                  const slot = c.slots[i];
                  return (
                    <td key={c.id} className="p-2 border-b border-l border-border align-top">
                      {slot.pick ? (
                        <>
                          <div className="font-medium truncate">{slot.pick.manufacturer}</div>
                          <div className="text-muted-foreground truncate">{slot.pick.model}</div>
                          <div className="font-mono mt-0.5">{slot.pick.priceDisplay} · {slot.pick.country}</div>
                        </>
                      ) : (
                        <span className="text-destructive">No match</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr className="bg-muted/30 font-semibold">
              <td className="p-2 sticky left-0 bg-muted/30 z-10">TOTAL CAPEX</td>
              {configurations.map((c) => (
                <td key={c.id} className="p-2 border-l border-border font-mono">{formatEur(c.totals.capexEur)}</td>
              ))}
            </tr>
            <tr className="bg-muted/30">
              <td className="p-2 sticky left-0 bg-muted/30 z-10">Max lead time</td>
              {configurations.map((c) => (
                <td key={c.id} className="p-2 border-l border-border">{c.totals.maxLeadTimeMonths} mo</td>
              ))}
            </tr>
            <tr className="bg-muted/30">
              <td className="p-2 sticky left-0 bg-muted/30 z-10">Min TRL</td>
              {configurations.map((c) => (
                <td key={c.id} className="p-2 border-l border-border">{c.totals.minTrl || "—"}</td>
              ))}
            </tr>
            <tr>
              <td className="p-2"></td>
              {configurations.map((c) => (
                <td key={c.id} className="p-2 border-l border-border">
                  <Button size="sm" className="w-full" onClick={() => onCommit(c)}>
                    <Check className="h-3 w-3 mr-1" /> Commit
                  </Button>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function escapeCsv(s: string): string {
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}