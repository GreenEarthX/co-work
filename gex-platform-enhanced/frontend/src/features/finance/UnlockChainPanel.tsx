// Screen: Unlock chain panel (on the package register) — bridge Stop 6.
/**
 * UnlockChainPanel — makes the handoff legible: which capital tranche is gated
 * by which bankability gate, and which of the project's packages feed that gate.
 *
 * It joins two systems the customer has already touched:
 *   • bankability gates + capital unlocks (GET /bankability/evaluate)
 *   • development packages (passed in), matched to gates by gex_gate number
 *
 * No invented numbers — gate completion and unlock status come straight from
 * the engine; package→gate links are whatever the customer declared. A gate with
 * no feeding package is shown as a gap ("no package addresses this gate yet").
 */

import { useQuery } from "@tanstack/react-query";
import { Loader2, ArrowRight, AlertTriangle, Lock, Unlock } from "lucide-react";
import { bankabilityAPI } from "@/api";

interface GateEval { gate_id: string; gate_name: string; completion_pct: number; }
interface CapitalUnlock {
  capital_type: string;
  is_unlocked: boolean;
  financing_applicable: boolean;
  gating_gates: string[];
  best_progress_pct: number;
}
interface EvaluateResp {
  gate_evaluations: GateEval[];
  capital_unlocks: CapitalUnlock[];
}

export interface ChainPackage {
  package_id: string;
  package_name: string;
  gex_gate?: string | null;
  workflow_state: string;
}

const gateNum = (id?: string | null) => (id ? (id.match(/^G\d+/)?.[0] ?? id) : "");
const human = (s: string) => s.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());

export function UnlockChainPanel({ projectId, packages }: { projectId: string; packages: ChainPackage[] }) {
  const { data, isLoading, isError, error } = useQuery<EvaluateResp>({
    queryKey: ["bankability", "evaluate", projectId],
    queryFn: () => bankabilityAPI.evaluate(projectId),
    enabled: !!projectId && projectId !== "all",
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-[var(--text-muted)]">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading unlock chain…
      </div>
    );
  }
  if (isError) {
    return (
      <div className="flex items-start gap-2 rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <span>Could not load the unlock chain{error instanceof Error ? ` (${error.message})` : ""}.</span>
      </div>
    );
  }

  const gateById = new Map((data?.gate_evaluations ?? []).map((g) => [g.gate_id, g]));
  // Packages grouped by the gate number they feed.
  const pkgByGate = new Map<string, ChainPackage[]>();
  for (const p of packages) {
    const n = gateNum(p.gex_gate);
    if (!n) continue;
    if (!pkgByGate.has(n)) pkgByGate.set(n, []);
    pkgByGate.get(n)!.push(p);
  }

  const tranches = (data?.capital_unlocks ?? []).filter((c) => c.financing_applicable);
  const unlinked = packages.filter((p) => !gateNum(p.gex_gate));

  return (
    <div className="space-y-3">
      <p className="text-[12px] text-[var(--text-secondary)]">
        Each tranche of capital is gated by a bankability gate. A gate opens as its evidence is verified —
        and that evidence is what your packages produce. This is where package work moves the project bridge.
      </p>

      <div className="space-y-2">
        {tranches.map((c) => (
          <div key={c.capital_type} className="rounded border border-[var(--border)] bg-[var(--surface)] p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {c.is_unlocked ? <Unlock className="h-4 w-4 text-emerald-500" /> : <Lock className="h-4 w-4 text-[var(--text-muted)]" />}
                <span className="text-sm font-semibold text-[var(--text-primary)]">{human(c.capital_type)}</span>
              </div>
              <span className="font-mono text-[11px] text-[var(--text-muted)]">{c.best_progress_pct.toFixed(0)}% to unlock</span>
            </div>

            {c.gating_gates.map((gid) => {
              const n = gateNum(gid);
              const g = gateById.get(gid);
              const feeders = pkgByGate.get(n) ?? [];
              return (
                <div key={gid} className="mt-2 flex flex-wrap items-center gap-2 text-[12px]">
                  <span className="inline-flex items-center gap-1 text-[var(--text-muted)]">
                    <ArrowRight className="h-3 w-3" /> gated by
                  </span>
                  <span className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-primary)]">
                    {g ? g.gate_name?.replace(/_/g, " ") || gid : gid} · {g ? `${g.completion_pct.toFixed(0)}%` : "—"}
                  </span>
                  <span className="text-[var(--text-muted)]">·</span>
                  {feeders.length === 0 ? (
                    <span className="inline-flex items-center gap-1 text-amber-600">
                      <AlertTriangle className="h-3 w-3" /> no package addresses this gate yet
                    </span>
                  ) : (
                    <span className="flex flex-wrap gap-1">
                      {feeders.map((p) => (
                        <span key={p.package_id} className="rounded bg-[var(--brand)]/10 px-1.5 py-0.5 text-[11px] text-[var(--brand)]">
                          {p.package_name} <span className="font-mono text-[10px] opacity-70">({p.workflow_state})</span>
                        </span>
                      ))}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {unlinked.length > 0 && (
        <div className="rounded border border-dashed border-[var(--border)] p-3 text-[12px]">
          <div className="font-medium text-[var(--text-primary)]">Not yet linked to a gate</div>
          <p className="mt-0.5 text-[var(--text-muted)]">
            These packages don't declare which gate they feed — open a package and set "Feeds gate" so its
            work counts toward unlocking capital.
          </p>
          <div className="mt-1 flex flex-wrap gap-1">
            {unlinked.map((p) => (
              <span key={p.package_id} className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 text-[11px] text-[var(--text-secondary)]">{p.package_name}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default UnlockChainPanel;
