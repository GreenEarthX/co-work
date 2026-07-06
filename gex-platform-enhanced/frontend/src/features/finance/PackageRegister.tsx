// Screen: /finance-package — Development Package Register (bridge Stop 2).
/**
 * PackageRegister — the project's development packages, and the form to add one.
 *
 * The Development Package is the bridge unit: every cost line is a named package
 * that removes a stated risk and becomes eligible for a capital source. This
 * screen is bound to the SELECTED project (not a hard-coded demo) and shows only
 * what the server computes — package counts, P50 CAPEX, maturity by state. No
 * fabricated DSCR/WACC: pre-COD finance is a package-definition problem, not an
 * operating-ratio one.
 *
 * GET  /api/v1/packages/project/{id}          → the register
 * GET  /api/v1/packages/project/{id}/summary  → honest aggregates
 * POST /api/v1/packages                        → create (≥1 risk_removed enforced)
 */

import { useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { Plus, Loader2, AlertTriangle, PackageOpen } from "lucide-react";
import { packagesAPI, type PackageCreateInput } from "@/api";
import { useSelectedProject } from "@/contexts/ProjectContext";
import { useUserRole } from "@/contexts/UserRoleContext";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";
import { PackageDetailDrawer, type PackageDetail } from "./PackageDetailDrawer";
import { UnlockChainPanel } from "./UnlockChainPanel";
import { Link2 } from "lucide-react";

const PACKAGE_TYPES = [
  "DEVEX", "PRE_FEED", "FEED", "DIRECT_CAPEX", "INDIRECT_CAPEX", "OWNER_COST",
  "CONTINGENCY", "RESERVE", "INSURANCE", "LEGAL", "LOGISTICS", "CERTIFICATION",
];
const PHASES = ["FEL_1", "FEL_2", "FEED", "FID", "CONSTRUCTION", "COD"];
const ESTIMATE_CLASSES = ["CLASS_5", "CLASS_4", "CLASS_3", "CLASS_2", "CLASS_1"];
const RISK_CATEGORIES = [
  "TECHNICAL", "PERMITTING", "COST", "SCHEDULE", "REVENUE", "CERTIFICATION",
  "EXECUTION", "SOVEREIGN", "LEGAL", "FINANCIAL", "INSURABILITY", "LOGISTICS",
];
// SENIOR_DEBT is intentionally excluded pre-FID — the server rejects it for
// FEL/FEED phases, so we don't tempt the user with an invalid choice.
const CAPITAL_SOURCES = [
  "EQUITY", "GRANT", "BRIDGE", "VENDOR_FINANCE", "CONCESSIONAL", "ECA",
  "DSRA", "INSURANCE_BACKED",
];
const DRAWDOWN_METHODS = [
  "MILESTONE", "CERTIFICATE", "PERMIT", "DATE", "PROGRESS", "AWARD",
  "REIMBURSEMENT", "RESERVE",
];

const PRE_FID_PHASES = new Set(["FEL_1", "FEL_2", "FEED"]);

interface PackageRow {
  package_id: string;
  package_name: string;
  package_type: string;
  phase_required: string;
  cost_amount: number;
  cost_p10?: number | null;
  cost_p90?: number | null;
  currency?: string;
  estimate_class: string;
  risk_removed: string[];
  capital_eligible: string[];
  workflow_state: string;
  capital_status: string;
  gex_gate?: string | null;
  downstream_effect?: string[];
  unlock_condition?: string[];
  aace_class_history?: { class: string; date: string }[];
  version: number;
}

interface Summary {
  total_packages: number;
  total_capex_p50_eur: number;
  by_phase: Record<string, number>;
  by_state: Record<string, number>;
  fid_readiness_pct: number;
}

const fmtEur = (n: number) =>
  n >= 1_000_000 ? `€${(n / 1_000_000).toFixed(1)}M` : `€${(n / 1_000).toFixed(0)}k`;

function Chip({ children, tone = "muted" }: { children: React.ReactNode; tone?: "muted" | "brand" | "amber" }) {
  const tones: Record<string, string> = {
    muted: "bg-[var(--surface-muted)] text-[var(--text-secondary)]",
    brand: "bg-[var(--brand)]/10 text-[var(--brand)]",
    amber: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
  };
  return <span className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-mono ${tones[tone]}`}>{children}</span>;
}

const inputClass =
  "w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2.5 py-[7px] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--brand)] focus:outline-none";

export function PackageRegister() {
  const { selectedProjectId } = useSelectedProject();
  const { role, authSession } = useUserRole();
  const { projects } = useVisibleProjects();
  const queryClient = useQueryClient();
  const projectId = selectedProjectId;
  const projectName = projects.find((p) => p.id === projectId)?.name ?? projectId;

  const changedBy = authSession?.email ?? role.user_name;
  const actorType = role.company_type;

  const [formOpen, setFormOpen] = useState(false);
  const [openPackage, setOpenPackage] = useState<PackageDetail | null>(null);
  const [chainOpen, setChainOpen] = useState(false);

  const refreshPackages = () =>
    queryClient.invalidateQueries({ queryKey: ["packages", projectId] });

  const validProject = !!projectId && projectId !== "all";

  const { data: packages = [], isLoading, isError, error, refetch } = useQuery<PackageRow[]>({
    queryKey: ["packages", projectId],
    queryFn: () => packagesAPI.listForProject(projectId),
    enabled: validProject,
    retry: 1,
  });
  const { data: summary } = useQuery<Summary>({
    queryKey: ["packages", projectId, "summary"],
    queryFn: () => packagesAPI.summary(projectId),
    enabled: validProject,
  });

  if (!validProject) {
    return (
      <div className="p-6 text-sm text-[var(--text-muted)]">
        Select a single project to see its development packages.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 animate-fade-in py-1">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-wider text-[var(--text-muted)]">
            Stop 2 · the spend that buys evidence
          </p>
          <h1 className="font-display text-xl font-bold text-[var(--text-primary)]">
            Development packages
          </h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            {projectName} — each package removes a stated risk and becomes eligible for a capital source.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setChainOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded border border-[var(--border)] px-3 py-[7px] text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
          >
            <Link2 className="h-4 w-4" /> {chainOpen ? "Hide" : "Show"} unlock chain
          </button>
          <button
            type="button"
            onClick={() => setFormOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded bg-[var(--brand)] px-3 py-[7px] text-sm font-semibold text-white hover:opacity-90"
          >
            <Plus className="h-4 w-4" /> New package
          </button>
        </div>
      </div>

      {chainOpen && (
        <div className="gex-card p-4">
          <h2 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
            Unlock chain — what your packages unlock
          </h2>
          <UnlockChainPanel projectId={projectId} packages={packages} />
        </div>
      )}

      {/* Honest summary — server aggregates only */}
      {summary && summary.total_packages > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <SummaryStat label="Packages" value={String(summary.total_packages)} />
          <SummaryStat label="CAPEX (P50)" value={fmtEur(summary.total_capex_p50_eur)} />
          <SummaryStat label="FID-ready cost" value={`${summary.fid_readiness_pct.toFixed(0)}%`} />
          <SummaryStat
            label="States"
            value={Object.entries(summary.by_state).map(([s, n]) => `${n}·${s}`).join("  ") || "—"}
          />
        </div>
      )}

      {formOpen && (
        <NewPackageForm
          projectId={projectId}
          defaultOwner={role.company_name}
          onCancel={() => setFormOpen(false)}
          onCreated={() => {
            setFormOpen(false);
            refreshPackages();
          }}
        />
      )}

      {/* Register */}
      {isLoading ? (
        <div className="flex items-center gap-2 p-6 text-sm text-[var(--text-muted)]">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading register…
        </div>
      ) : isError ? (
        <div className="gex-card flex flex-col items-start gap-2 p-4 text-sm">
          <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
            <AlertTriangle className="h-4 w-4" />
            <span className="font-semibold">Could not load the package register</span>
          </div>
          <p className="text-[13px] text-[var(--text-secondary)]">
            The list could not be read — this is a load error, not an empty register.
            {error instanceof Error ? ` (${error.message})` : ""}
          </p>
          <button type="button" onClick={() => refetch()}
            className="mt-1 rounded border border-[var(--border)] px-3 py-[6px] text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">
            Retry
          </button>
        </div>
      ) : packages.length === 0 ? (
        <div className="gex-card flex flex-col items-center gap-2 p-8 text-center">
          <PackageOpen className="h-7 w-7 text-[var(--text-muted)]" />
          <p className="text-sm font-semibold text-[var(--text-primary)]">No packages yet</p>
          <p className="max-w-sm text-[13px] text-[var(--text-secondary)]">
            The first package is usually <span className="font-mono">DEVEX</span> — owner's engineer and
            site diligence. Create it to begin the spend → evidence → capital loop.
          </p>
          {!formOpen && (
            <button
              type="button"
              onClick={() => setFormOpen(true)}
              className="mt-1 inline-flex items-center gap-1.5 rounded bg-[var(--brand)] px-3 py-[7px] text-sm font-semibold text-white hover:opacity-90"
            >
              <Plus className="h-4 w-4" /> Create first package
            </button>
          )}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-[var(--border)] bg-[var(--surface)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-left font-mono text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
                <th className="px-3 py-2">Package <span className="font-normal normal-case text-[var(--text-muted)]">· click a row to mature it</span></th>
                <th className="px-3 py-2">Phase</th>
                <th className="px-3 py-2 text-right">Cost</th>
                <th className="px-3 py-2">Removes risk</th>
                <th className="px-3 py-2">Capital</th>
                <th className="px-3 py-2">State</th>
              </tr>
            </thead>
            <tbody>
              {packages.map((p) => (
                <tr key={p.package_id} onClick={() => setOpenPackage(p as PackageDetail)}
                  className="cursor-pointer border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-hover)]">
                  <td className="px-3 py-2">
                    <div className="font-medium text-[var(--text-primary)]">{p.package_name}</div>
                    <div className="mt-0.5 flex gap-1">
                      <Chip tone="brand">{p.package_type}</Chip>
                      <Chip>{p.estimate_class.replace("CLASS_", "Class ")}</Chip>
                    </div>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-[var(--text-secondary)]">{p.phase_required}</td>
                  <td className="px-3 py-2 text-right font-mono text-[var(--text-primary)]">{fmtEur(p.cost_amount)}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {p.risk_removed.length === 0 ? <span className="text-xs text-rose-500">none</span>
                        : p.risk_removed.map((r) => <Chip key={r}>{r}</Chip>)}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {p.capital_eligible.length === 0 ? <span className="text-xs text-[var(--text-muted)]">—</span>
                        : p.capital_eligible.map((c) => <Chip key={c} tone="amber">{c}</Chip>)}
                    </div>
                  </td>
                  <td className="px-3 py-2"><Chip>{p.workflow_state}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openPackage && (
        <PackageDetailDrawer
          pkg={openPackage}
          changedBy={changedBy}
          actorType={actorType}
          onClose={() => setOpenPackage(null)}
          onChanged={() => {
            refreshPackages();
            // Re-sync the open drawer with the freshly-fetched row.
            packagesAPI.listForProject(projectId).then((list: PackageDetail[]) => {
              const fresh = list.find((x) => x.package_id === openPackage.package_id);
              if (fresh) setOpenPackage(fresh);
            }).catch(() => {});
          }}
        />
      )}
    </div>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="gex-card px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--text-muted)]">{label}</div>
      <div className="mt-0.5 truncate font-mono text-sm font-semibold text-[var(--text-primary)]">{value}</div>
    </div>
  );
}

function NewPackageForm({
  projectId,
  defaultOwner,
  onCancel,
  onCreated,
}: {
  projectId: string;
  defaultOwner: string;
  onCancel: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState("DEVEX");
  const [phase, setPhase] = useState("FEL_1");
  const [cost, setCost] = useState("");
  const [estimateClass, setEstimateClass] = useState("CLASS_5");
  const [risks, setRisks] = useState<string[]>([]);
  const [capital, setCapital] = useState<string[]>([]);
  const [drawdown, setDrawdown] = useState("MILESTONE");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (body: PackageCreateInput) => packagesAPI.create(body),
    onSuccess: onCreated,
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Could not create package"),
  });

  const toggle = (arr: string[], v: string, set: (x: string[]) => void) =>
    set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  const canSubmit =
    name.trim().length >= 3 && Number(cost) > 0 && risks.length >= 1 && !mutation.isPending;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!canSubmit) {
      setError("Name (≥3 chars), a positive cost, and at least one risk removed are required.");
      return;
    }
    mutation.mutate({
      project_id: projectId,
      package_name: name.trim(),
      package_type: type,
      phase_required: phase,
      discipline_owner: defaultOwner,
      cost_amount: Number(cost),
      estimate_class: estimateClass,
      risk_removed: risks,
      capital_eligible: capital,
      drawdown_method: drawdown,
    });
  }

  return (
    <form onSubmit={submit} className="gex-card space-y-3 p-4">
      <h2 className="text-sm font-semibold text-[var(--text-primary)]">New development package</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block sm:col-span-2">
          <span className="text-xs font-semibold text-[var(--text-primary)]">Package name</span>
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Owner's Engineer & Site Diligence" />
        </label>
        <label className="block">
          <span className="text-xs font-semibold text-[var(--text-primary)]">Type</span>
          <select className="gex-select w-full" value={type} onChange={(e) => setType(e.target.value)}>
            {PACKAGE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-xs font-semibold text-[var(--text-primary)]">Phase required</span>
          <select className="gex-select w-full" value={phase} onChange={(e) => setPhase(e.target.value)}>
            {PHASES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-xs font-semibold text-[var(--text-primary)]">Cost (P50, EUR)</span>
          <input className={inputClass} type="number" min={0} value={cost} onChange={(e) => setCost(e.target.value)} placeholder="0" />
        </label>
        <label className="block">
          <span className="text-xs font-semibold text-[var(--text-primary)]">Estimate class</span>
          <select className="gex-select w-full" value={estimateClass} onChange={(e) => setEstimateClass(e.target.value)}>
            {ESTIMATE_CLASSES.map((c) => <option key={c} value={c}>{c.replace("CLASS_", "Class ")}</option>)}
          </select>
        </label>
      </div>

      <div>
        <span className="text-xs font-semibold text-[var(--text-primary)]">
          Risk removed <span className="text-rose-500">*</span>
          <span className="ml-1 font-normal text-[var(--text-muted)]">— a package that removes no risk is an orphaned cost line</span>
        </span>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {RISK_CATEGORIES.map((r) => (
            <button key={r} type="button" onClick={() => toggle(risks, r, setRisks)}
              className={`rounded px-2 py-1 text-[11px] font-mono ${risks.includes(r) ? "bg-[var(--brand)] text-white" : "bg-[var(--surface-muted)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"}`}>
              {r}
            </button>
          ))}
        </div>
      </div>

      <div>
        <span className="text-xs font-semibold text-[var(--text-primary)]">
          Capital eligible
          {PRE_FID_PHASES.has(phase) && <span className="ml-1 font-normal text-[var(--text-muted)]">— senior debt not eligible pre-FID</span>}
        </span>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {CAPITAL_SOURCES.map((c) => (
            <button key={c} type="button" onClick={() => toggle(capital, c, setCapital)}
              className={`rounded px-2 py-1 text-[11px] font-mono ${capital.includes(c) ? "bg-amber-500 text-white" : "bg-[var(--surface-muted)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"}`}>
              {c}
            </button>
          ))}
        </div>
      </div>

      <label className="block max-w-xs">
        <span className="text-xs font-semibold text-[var(--text-primary)]">Drawdown trigger</span>
        <select className="gex-select w-full" value={drawdown} onChange={(e) => setDrawdown(e.target.value)}>
          {DRAWDOWN_METHODS.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </label>

      {error && (
        <div className="flex items-start gap-2 rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> <span>{error}</span>
        </div>
      )}

      <div className="flex items-center justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded border border-[var(--border)] px-3 py-[7px] text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">
          Cancel
        </button>
        <button type="submit" disabled={!canSubmit}
          className="inline-flex items-center gap-1.5 rounded bg-[var(--brand)] px-4 py-[7px] text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">
          {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Create package
        </button>
      </div>
    </form>
  );
}

export default PackageRegister;
