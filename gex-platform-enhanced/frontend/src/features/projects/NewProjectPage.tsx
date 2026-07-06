// Screen: /projects/new — the on-ramp. First stop of the development-to-capital bridge.
/**
 * NewProjectPage — create a real project.
 *
 * This is where a new customer's project begins. It persists, server-side:
 *   • a project_id owned by the caller's company
 *   • the physical/financing PREMISE (power model · financing model · phase)
 *
 * The premise is not cosmetic: it scopes which bankability gates apply and
 * whether the lender gates are in play. We surface that consequence inline so
 * the choice is made with eyes open — not buried in a settings screen later.
 *
 * On success we go straight to the project profile, the next bridge stop.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Loader2, AlertTriangle } from "lucide-react";
import { projectsAPI, type ProjectCreateInput } from "@/api";
import { useUserRole } from "@/contexts/UserRoleContext";

type PowerModel = ProjectCreateInput["power_model"];
type FinancingModel = ProjectCreateInput["financing_model"];
type Phase = ProjectCreateInput["phase"];

const MOLECULES = ["H2", "NH3", "e-Methanol", "SAF", "e-NG", "e-Methane", "HVO"];

const POWER_MODELS: { value: PowerModel; label: string; consequence: string }[] = [
  {
    value: "OFF_GRID_BTM",
    label: "Off-grid · behind-the-meter",
    consequence: "Dedicated renewables, no grid import. Grid-connection and grid-PPA gates do not apply.",
  },
  {
    value: "GRID_CONNECTED",
    label: "Grid-connected",
    consequence: "Imports from the grid. Grid-connection agreement and a power-supply contract (PPA) become required evidence.",
  },
  {
    value: "HYBRID",
    label: "Hybrid (grid + dedicated)",
    consequence: "Both apply. Grid gates and dedicated-supply gates are evaluated together.",
  },
];

const FINANCING_MODELS: { value: FinancingModel; label: string; consequence: string }[] = [
  {
    value: "PROJECT_FINANCE",
    label: "Project finance (non-recourse)",
    consequence: "Lender gates apply (independent engineer, model audit, insurance, direct agreements). The full capital bridge.",
  },
  {
    value: "BALANCE_SHEET",
    label: "Balance sheet (corporate)",
    consequence: "Funded by the sponsor's balance sheet. Non-recourse lender gates are waived; corporate-FID evidence applies instead.",
  },
];

const PHASES: { value: Phase; label: string }[] = [
  { value: "development", label: "Development" },
  { value: "construction", label: "Construction" },
  { value: "commissioning", label: "Commissioning" },
  { value: "operating", label: "Operating" },
];

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-[var(--text-primary)]">{label}</span>
      {hint && <span className="mb-1 block text-[11px] text-[var(--text-muted)]">{hint}</span>}
      <div className="mt-1">{children}</div>
    </label>
  );
}

const inputClass =
  "w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2.5 py-[7px] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--brand)] focus:outline-none";

export function NewProjectPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { role, sessionTier } = useUserRole();

  const [name, setName] = useState("");
  const [molecule, setMolecule] = useState(MOLECULES[0]);
  const [location, setLocation] = useState("");
  const [country, setCountry] = useState("");
  const [capacity, setCapacity] = useState("");
  const [capex, setCapex] = useState("");
  const [powerModel, setPowerModel] = useState<PowerModel>("OFF_GRID_BTM");
  const [financingModel, setFinancingModel] = useState<FinancingModel>("PROJECT_FINANCE");
  const [phase, setPhase] = useState<Phase>("development");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = name.trim().length > 0 && sessionTier === "authenticated" && !submitting;

  const powerNote = POWER_MODELS.find((m) => m.value === powerModel)?.consequence;
  const financingNote = FINANCING_MODELS.find((m) => m.value === financingModel)?.consequence;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await projectsAPI.create({
        name: name.trim(),
        molecule,
        location: location.trim(),
        country: country.trim().toUpperCase(),
        capacity_mtpd: capacity ? Number(capacity) : 0,
        capex_eur: capex ? Number(capex) : 0,
        power_model: powerModel,
        financing_model: financingModel,
        phase,
      });
      await queryClient.invalidateQueries({ queryKey: ["projects", "visible"] });
      navigate(`/projects/${created.id}/edit`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the project");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4 animate-fade-in py-1">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-wider text-[var(--text-muted)]">
          On-ramp · Stop 1 of the capital bridge
        </p>
        <h1 className="font-display text-xl font-bold text-[var(--text-primary)]">New project</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Create the project and declare its premise. Everything downstream — gates, evidence,
          packages, finance, capital — operates on what you set here. Owned by{" "}
          <span className="font-semibold text-[var(--text-primary)]">{role.company_name}</span>.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* ── Identity ── */}
        <section className="gex-card space-y-3 p-4">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Identity</h2>
          <Field label="Project name">
            <input
              className={inputClass}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. North Sea e-Methanol"
              autoFocus
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Molecule">
              <select className="gex-select w-full" value={molecule} onChange={(e) => setMolecule(e.target.value)}>
                {MOLECULES.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Country" hint="ISO code, e.g. DE">
              <input
                className={inputClass}
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder="DE"
                maxLength={3}
              />
            </Field>
          </div>
          <Field label="Location">
            <input
              className={inputClass}
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="City / region"
            />
          </Field>
        </section>

        {/* ── Scale ── */}
        <section className="gex-card space-y-3 p-4">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Scale</h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Capacity" hint="tonnes/day of product">
              <input
                className={inputClass}
                type="number"
                min={0}
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                placeholder="0"
              />
            </Field>
            <Field label="CapEx" hint="EUR, total project">
              <input
                className={inputClass}
                type="number"
                min={0}
                value={capex}
                onChange={(e) => setCapex(e.target.value)}
                placeholder="0"
              />
            </Field>
          </div>
        </section>

        {/* ── Premise — this scopes the whole bridge ── */}
        <section className="gex-card space-y-3 p-4">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Premise</h2>
          <p className="-mt-1 text-[11px] text-[var(--text-muted)]">
            These two choices decide which bankability gates apply. You can change them later — it is
            audited.
          </p>
          <Field label="Power model">
            <select
              className="gex-select w-full"
              value={powerModel}
              onChange={(e) => setPowerModel(e.target.value as PowerModel)}
            >
              {POWER_MODELS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </Field>
          {powerNote && <p className="rounded bg-[var(--surface-muted)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">{powerNote}</p>}

          <Field label="Financing model">
            <select
              className="gex-select w-full"
              value={financingModel}
              onChange={(e) => setFinancingModel(e.target.value as FinancingModel)}
            >
              {FINANCING_MODELS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </Field>
          {financingNote && <p className="rounded bg-[var(--surface-muted)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">{financingNote}</p>}

          <Field label="Phase">
            <select className="gex-select w-full" value={phase} onChange={(e) => setPhase(e.target.value as Phase)}>
              {PHASES.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
        </section>

        {error && (
          <div className="flex items-start gap-2 rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => navigate("/projects")}
            className="rounded border border-[var(--border)] px-3 py-[7px] text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center gap-1.5 rounded bg-[var(--brand)] px-4 py-[7px] text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
            Create & open project
          </button>
        </div>
      </form>
    </div>
  );
}

export default NewProjectPage;
