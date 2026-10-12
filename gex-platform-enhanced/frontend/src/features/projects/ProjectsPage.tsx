// Screen: Projects screen (/projects)
//
// Phase and State come from one gate-engine readout per project (the same
// cached readout State & Blockers and Capital Eligibility read): Phase is the
// phase the project declared, State is what its evidence supports. Nothing here
// reads the customerProjects.ts `bankability` block any more; the BNK/E·G·C·B
// composite, the fixture capital columns and the typed "behind / on track"
// classification were removed 2026-09-30 (docs/master-reconciliation/06).
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, ChevronDown, AlertTriangle, LineChart, Pencil } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";
import { type CustomerProject, type RiskCategory } from "@/data/customerProjects";
import { useSelectedProject } from "@/contexts/ProjectContext";
import { type UserRole, useUserRole } from "@/contexts/UserRoleContext";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";
import { useRiskFlags } from "@/hooks/useRiskFlags";
import { useEngineReadouts, useVocabularyLabel } from "@/hooks/useEngineReadout";
import { resolveActionRoute, type RouteAction } from "@/lib/actionRouter";
import { isFinanceLike } from "@/data/evidenceCatalog";
import {
  blockingGates, decisionsGatedBy, gateName, gateShortId, humanise, type EngineReadout,
} from "@/lib/engineReadout";

// ─── Constants ────────────────────────────────────────────────────────────────

// 3-char molecule tickers — Bloomberg-style symbols, no color chips.
const MOL_TICK: Record<string, string> = {
  H2: "H2",
  NH3: "NH3",
  "e-Methanol": "MEO",
  SAF: "SAF",
  "e-NG": "ENG",
  "e-Methane": "ENG",
  "e-NH3": "NH3",
  HVO: "HVO",
  "e-Gasoline": "EGA",
  "e-LG": "ELG",
  "e-Naphtha": "ENA",
};

// 3-letter codes for the declared phase (project context) — dense column.
const PHASE_CODE: Record<string, string> = {
  development: "DEV",
  construction: "CON",
  commissioning: "CMS",
  operating: "OPS",
};

const PHASE_COLOR: Record<string, string> = {
  development: "text-amber-600 dark:text-amber-400",
  construction: "text-sky-600 dark:text-sky-400",
  commissioning: "text-violet-600 dark:text-violet-400",
  operating: "text-emerald-600 dark:text-emerald-400",
};

// Reference molecule prices (€/MT) — used for volume allocation estimates.
const MOLECULE_PRICE: Record<string, number> = {
  H2: 4500,
  NH3: 650,
  "e-Methanol": 850,
  SAF: 2200,
  "e-NG": 1100,
  "e-Methane": 1100,
  "e-NH3": 700,
  HVO: 1800,
  "e-Gasoline": 2000,
  "e-LG": 1600,
  "e-Naphtha": 900,
};

// The screen that shows a project's state and what blocks the next one.
const STATE_AND_BLOCKERS = "State & Blockers";

type Readout = UseQueryResult<EngineReadout>;
type LabelFn = (canonical: string | null | undefined) => string | null;

// ─── Derivation helpers ──────────────────────────────────────────────────────

const isCodStarted = (status: string) =>
  status === "operating" || status === "commissioning";

function volumeBreakdown(project: CustomerProject) {
  const price = MOLECULE_PRICE[project.molecule] ?? 1000;
  const annualOutput = project.capacity_mtpd * 365;
  const tokeniseShare = 0.8;
  const volumeToTokenise = Math.round(annualOutput * tokeniseShare);
  const plantLife = 20;
  const annualCapexCoverage = project.capex_eur / (price * plantLife);
  const volumeCapexCoverage = Math.round(annualCapexCoverage);
  const annualDepreciation = project.capex_eur / plantLife;
  const annualOpex = project.capex_eur * 0.04;
  const volumeForDeprecAndOpex = Math.round(
    (annualDepreciation + annualOpex) / price,
  );
  return {
    annualOutput: Math.round(annualOutput),
    volumeToTokenise,
    volumeCapexCoverage,
    volumeForDeprecAndOpex,
  };
}

function resolveProjectDetailPath(
  kind: "molecule" | "phase" | "state" | "capacity" | "targetCod",
  role: UserRole,
): string {
  const { business_function, company_type, service_type } = role;
  switch (kind) {
    case "molecule":
      if (business_function === "COMPLIANCE_LEGAL" || service_type === "CERTIFIER")
        return "/cert-readiness";
      if (business_function === "COMMERCIAL" || company_type === "OFFTAKER")
        return "/offtake-quality";
      if (business_function === "FINANCE_TREASURY" || service_type === "BANK")
        return "/pricing-lineage";
      return "/offtake-quality";
    case "phase":
      if (business_function === "ENGINEERING" || business_function === "OPERATIONS")
        return "/producer-bankability";
      if (business_function === "EXECUTIVE") return "/finance-timeline";
      return "/bankability-scores";
    case "state":
      if (business_function === "COMPLIANCE_LEGAL" || service_type === "CERTIFIER")
        return "/stage-gates";
      if (business_function === "ENGINEERING" || business_function === "OPERATIONS")
        return "/producer-bankability";
      return "/bankability-scores";
    case "capacity":
      return "/capacity";
    case "targetCod":
      if (business_function === "ENGINEERING" || business_function === "OPERATIONS")
        return "/producer-bankability";
      return "/finance-timeline";
    default:
      return "/dashboard";
  }
}

// ─── Next step, from the engine ──────────────────────────────────────────────
// The same sentence for every role: the next state and what it waits on. The
// role decides only where the "Your next action" button goes (roleNextAction).

function engineNextStep(readout: Readout, stateLabel: LabelFn): string {
  if (readout.isLoading) return "…";
  const r = readout.data;
  if (!r) return "Gate engine unavailable";
  if (!r.next_state) return "No further state";
  const gates = blockingGates(r).map((g) => gateName(r, g.gate_id));
  const waits = gates.length > 0
    ? gates
    : (r.commitments_blocking_next_state ?? []).map((s) => s.message);
  return `Reach ${stateLabel(r.next_state)}: ${waits.join(", ") || "the gates it needs are satisfied"}`;
}

// ─── Causal "ways" — no claim without a route to act on it ──────────────────
// Sung: a number/claim must trace to the screen where it is SET, not dead-end
// on prose. Each helper returns the screen where the stated problem is worked.

/** The role-scoped next action as a RouteAction: the role picks its own home
 *  surface (preferred); the resolver confirms the viewer can act there and
 *  falls back to the open scoreboard for owner surfaces that don't fit. */
type LabelledAction = RouteAction & { label: string; fallback_label?: string };

function roleNextAction(role: UserRole): LabelledAction {
  const { business_function, company_type, service_type } = role;
  if (business_function === "FINANCE_TREASURY" || service_type === "BANK")
    return { kind: "next:finance", preferred_route: "/capital-stack", owner_function: "FINANCE_TREASURY", fallback_route: "/bankability-scores", fallback_label: STATE_AND_BLOCKERS, label: "Capital Stack" };
  if (business_function === "ENGINEERING" || business_function === "OPERATIONS" || service_type === "ENGINEER")
    return { kind: "next:engineering", preferred_route: "/producer-bankability", owner_function: "ENGINEERING", label: "Gate Evidence" };
  if (business_function === "COMPLIANCE_LEGAL" || service_type === "CERTIFIER" || service_type === "LEGAL")
    return { kind: "next:compliance", preferred_route: "/stage-gates", owner_function: "COMPLIANCE_LEGAL", label: "Gates & Evidence" };
  if (business_function === "COMMERCIAL" || company_type === "OFFTAKER")
    return { kind: "next:commercial", preferred_route: "/offtake-quality", owner_function: "COMMERCIAL", fallback_route: "/bankability-scores", fallback_label: STATE_AND_BLOCKERS, label: "Offtake Quality" };
  if (business_function === "EXECUTIVE")
    return { kind: "next:executive", preferred_route: "/finance-timeline", owner_function: "EXECUTIVE", label: "Finance Timeline" };
  return { kind: "next:default", preferred_route: "/bankability-scores", owner_function: "EXECUTIVE", label: STATE_AND_BLOCKERS };
}

/** A blocking gate → the gate-evidence deep-link. The route is open (the
 *  persona-scoped view self-explains a gate not in the viewer's persona — the
 *  F2 banner), so this resolves "allowed"; routing it through the resolver
 *  keeps the decision out of the screen and visible to the linter. */
function blockerAction(project: CustomerProject, gateId: string): LabelledAction {
  return {
    kind: `blocker:${gateId}`,
    preferred_route: `/producer-bankability?project=${encodeURIComponent(project.id)}&gate=${encodeURIComponent(gateId)}`,
    label: "Gate Evidence",
  };
}

/** Structured flags carry a semantic category → an ACTION (preferred owner
 *  surface + owner + universal fallback). The route decision is no longer made
 *  here: resolveActionRoute decides whether THIS viewer gets the owner surface
 *  or the fallback (the F3 fix, now centralized). The screen only describes;
 *  the resolver routes. No (category × role) matrix lives here. */
function riskFlagAction(project: CustomerProject, category: RiskCategory): LabelledAction {
  const pid = encodeURIComponent(project.id);
  switch (category) {
    case "capacity_claim":
      return { kind: "risk:capacity_claim", preferred_route: `/adversarial-review?project=${pid}`, owner_function: "EXECUTIVE", label: "Challenge Review" };
    case "certification":
    case "policy":
      return { kind: "risk:certification", preferred_route: "/cert-readiness", owner_function: "COMPLIANCE_LEGAL", label: "Cert Readiness" };
    case "offtake":
    case "supply_chain":
      // Commercial/offtaker own offtake-quality; everyone else is routed by the
      // resolver to the governing gate evidence (G4), never the locked screen.
      return {
        kind: "risk:offtake", preferred_route: "/offtake-quality", owner_function: "COMMERCIAL",
        fallback_route: `/producer-bankability?project=${pid}&gate=G4`, fallback_label: "Gate Evidence",
        label: "Offtake Quality",
      };
    case "financing":
      // Finance own the capital stack; others fall back to the open scoreboard.
      return {
        kind: "risk:financing", preferred_route: "/capital-stack", owner_function: "FINANCE_TREASURY",
        fallback_route: "/bankability-scores", fallback_label: STATE_AND_BLOCKERS,
        label: "Capital Stack",
      };
    case "insurance":
      return { kind: "risk:insurance", preferred_route: "/insurance", owner_function: "FINANCE_TREASURY", label: "Insurance Schedule" };
    case "site_permits":
      return { kind: "risk:site_permits", preferred_route: "/producer-bankability", owner_function: "ENGINEERING", label: "Gate Evidence" };
    default:
      return { kind: "risk:other", preferred_route: "/bankability-scores", owner_function: "EXECUTIVE", label: STATE_AND_BLOCKERS };
  }
}

// ─── Tiny display helpers ────────────────────────────────────────────────────

function fmtShort(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** Target COD as declared: MMM-YY for a date, "—" when none is recorded, and
 *  anything else (e.g. "2027-Q3") exactly as entered. `new Date("")` used to
 *  render "INVALID DATE-aN" for every project created without a date. */
export function fmtCod(date: string | null | undefined): string {
  if (!date) return "—";
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return date;
  const month = d.toLocaleString("en-GB", { month: "short", timeZone: "UTC" }).toUpperCase();
  return `${month}-${String(d.getUTCFullYear()).slice(-2)}`;
}

// ─── Phase and State cells ────────────────────────────────────────────────────

function PhaseCell({ readout, phaseLabel }: { readout: Readout; phaseLabel: LabelFn }) {
  if (readout.isLoading) return <span className="text-center text-[var(--text-muted)]">…</span>;
  const phase = readout.data?.project_phase;
  if (!phase) {
    return (
      <span className="text-center font-mono text-[11px] text-[var(--text-muted)]" title="No phase recorded in the project context">
        —
      </span>
    );
  }
  return (
    <span
      className={`text-center font-mono text-[11px] font-bold ${PHASE_COLOR[phase] ?? "text-[var(--text-muted)]"}`}
      title={`Declared phase: ${phaseLabel(phase)}`}
    >
      {PHASE_CODE[phase] ?? phase.slice(0, 3).toUpperCase()}
    </span>
  );
}

function StateCell({ readout, stateLabel }: { readout: Readout; stateLabel: LabelFn }) {
  if (readout.isLoading) return <span className="text-right text-[var(--text-muted)]">…</span>;
  const r = readout.data;
  if (!r) {
    return (
      <span className="text-right font-mono text-[11px] text-[var(--text-muted)]" title="Gate engine unavailable">
        —
      </span>
    );
  }
  return (
    <span className="flex min-w-0 flex-col items-end leading-tight" title={r.state_label ?? undefined}>
      <span className="max-w-full truncate text-[11px] font-semibold text-[var(--text-primary)]">
        {stateLabel(r.current_state)}
      </span>
      <span className="font-mono text-[10px] tabular-nums text-[var(--text-muted)]">
        {r.total_verified}/{r.total_evidence} verified
      </span>
    </span>
  );
}

// ─── Expand-in-place panel ────────────────────────────────────────────────────
// Opens inline below the clicked row. Contains:
//   (1) Next action, gates blocking the next state, risk flags
//   (2) Capacity derivation (volumeBreakdown)
//   (3) Persona deep-links

function ExpandPanel({
  project,
  role,
  readout,
  onNav,
}: {
  project: CustomerProject;
  role: UserRole;
  readout: Readout;
  onNav: (path: string) => void;
}) {
  const phaseLabel = useVocabularyLabel("project_phase");
  const stateLabel = useVocabularyLabel("readiness");
  const vb = volumeBreakdown(project);
  const ops = isCodStarted(project.status);
  const r = readout.data;
  const openGates = r ? blockingGates(r) : [];
  const nextStep = engineNextStep(readout, stateLabel);
  // Server-filtered structured flags (ABAC: classification × stakeholding).
  const { flags: riskFlags } = useRiskFlags(project.id);

  const links: Array<{ label: string; value: string; kind: Parameters<typeof resolveProjectDetailPath>[0] }> = [
    { label: "Molecule", value: project.molecule, kind: "molecule" },
    { label: "Phase", value: phaseLabel(r?.project_phase) ?? "not recorded", kind: "phase" },
    { label: "State", value: r ? stateLabel(r.current_state) ?? r.current_state : "—", kind: "state" },
    { label: "Capacity", value: `${project.capacity_mtpd} MTPD`, kind: "capacity" },
    { label: "Target COD", value: fmtCod(project.completion_date), kind: "targetCod" },
  ];

  return (
    <div className="border-t border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3">
      <div className="grid grid-cols-12 gap-4 text-[11px]">
        {/* Your action — role-scoped, leads the panel.
            Sung structure per row: THOUGHT (the claim) → CONSEQUENCE (what it
            blocks) → WAY (the screen where it is worked). Nothing here
            is allowed to dead-end on prose. */}
        <div className="col-span-12 lg:col-span-7 space-y-2">
          <SectionLabel>Your next action</SectionLabel>
          {(() => {
            const action = roleNextAction(role);
            const resolved = resolveActionRoute(role, action, project.id);
            const label = resolved.status === "fallback" ? (action.fallback_label ?? action.label) : action.label;
            return (
              <button
                onClick={() => resolved.route && onNav(resolved.route)}
                disabled={!resolved.route}
                className="block w-full rounded border border-amber-400/40 bg-amber-50/10 px-2 py-1.5 text-left text-[11px] font-semibold leading-snug text-[var(--text-primary)] transition-colors hover:bg-amber-50/30 disabled:cursor-default"
                title={resolved.route ? `Work this in ${label}` : undefined}
              >
                {nextStep}
                <span className="mt-0.5 block font-mono text-[10px] font-normal uppercase tracking-[0.06em] text-[var(--brand,#0ea5a0)]">
                  → {label}
                </span>
              </button>
            );
          })()}
          <div className="font-mono text-[10px] text-[var(--text-muted)]">
            {project.location}
            <span>
              {" · "}
              {project.lat.toFixed(2)}N,{Math.abs(project.lng).toFixed(2)}
              {project.lng >= 0 ? "E" : "W"}
            </span>
          </div>
          {r && openGates.length > 0 && (
            <>
              <div className="text-[var(--text-muted)] pt-1">Blocking the next state</div>
              <ul className="space-y-0.5">
                {openGates.slice(0, 4).map((g) => {
                  const neededFor = decisionsGatedBy(r, g.gate_id).map((c) => c.label ?? humanise(c.capital_type));
                  // The resolver owns the decision; the gate-evidence view is
                  // persona-scoped and self-explains a gate outside the viewer's
                  // persona (F2 banner), so this never dead-ends generically.
                  const resolved = resolveActionRoute(role, blockerAction(project, g.gate_id), project.id);
                  return (
                    <li key={g.gate_id}>
                      <button
                        onClick={() => resolved.route && onNav(resolved.route)}
                        className="flex w-full items-start gap-1 text-left text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                        title={`Open ${gateShortId(g.gate_id)} evidence detail`}
                      >
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
                        <span className="min-w-0">
                          <span className="block truncate">
                            {gateName(r, g.gate_id)} · {g.verified_count}/{g.total_evidence} verified
                          </span>
                          {neededFor.length > 0 && (
                            <span className="block truncate font-mono text-[10px] text-[var(--text-muted)]">
                              needed for {neededFor.join(" · ")}
                            </span>
                          )}
                          <span className="block font-mono text-[10px] uppercase tracking-[0.06em] text-[var(--brand,#0ea5a0)]">
                            → Gate Evidence
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
          {riskFlags.length > 0 && (
            <>
              <div className="text-[var(--text-muted)] pt-1">Risk flags</div>
              <ul className="space-y-1">
                {riskFlags.slice(0, 4).map((f) => {
                  const action = riskFlagAction(project, f.category);
                  const resolved = resolveActionRoute(role, action, project.id);
                  const label = resolved.status === "fallback" ? (action.fallback_label ?? "Gate Evidence") : action.label;
                  return (
                    <li key={f.id}>
                      <button
                        onClick={() => resolved.route && onNav(resolved.route)}
                        disabled={!resolved.route}
                        className="flex w-full items-start gap-1 text-left text-[10px] text-rose-500 hover:text-rose-400 disabled:cursor-default disabled:text-[var(--text-muted)]"
                        title={`${f.severity} severity · ${f.confidence} confidence · sources: ${f.source_ids.join(", ")}`}
                      >
                        <span className="mt-0.5 shrink-0">▲</span>
                        <span className="min-w-0">
                          <span className="block">{f.claim}</span>
                          <span className="block font-mono text-[9px] uppercase tracking-[0.06em] text-[var(--text-muted)]">
                            {f.severity} · conf {f.confidence} · {f.status.toLowerCase()} · owner {f.owner_function.replace(/_/g, " ")} ·{" "}
                            {f.source_ids.length} src
                          </span>
                          {resolved.route ? (
                            <span className="block font-mono uppercase tracking-[0.06em] text-[var(--brand,#0ea5a0)]">
                              → {label}
                            </span>
                          ) : (
                            <span className="block font-mono uppercase tracking-[0.06em] text-[var(--text-muted)]">
                              worked by {resolved.owner_function?.replace(/_/g, " ")}
                            </span>
                          )}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>

        {/* Capacity derivation */}
        <div className="col-span-12 lg:col-span-5 space-y-1">
          <SectionLabel>Capacity derivation</SectionLabel>
          <KV label="Nameplate" value={`${project.capacity_mtpd} MTPD`} />
          <KV label="Annual output" value={`${fmtShort(vb.annualOutput)} MT/y`} />
          <KV label="To tokenise (80%)" value={`${fmtShort(vb.volumeToTokenise)} MT/y`} />
          {!ops && (
            <KV
              label="Volume to cover CAPEX"
              value={`${fmtShort(vb.volumeCapexCoverage)} MT/y`}
            />
          )}
          {ops && (
            <KV
              label="Cover deprec + OPEX"
              value={`${fmtShort(vb.volumeForDeprecAndOpex)} MT/y`}
            />
          )}
          <KV
            label="CAPEX"
            value={`€${fmtShort(project.capex_eur)}`}
          />
        </div>
      </div>

      {/* Persona deep-links — role-aware jump bar */}
      <div className="mt-3 flex flex-wrap items-center gap-1 border-t border-[var(--border)] pt-2">
        <button
          onClick={() => onNav(`/projects/${project.id}/edit`)}
          className="group inline-flex items-center gap-1.5 rounded border border-brand-400/60 bg-brand-50/10 px-2.5 py-[3px] text-[10px] font-mono uppercase tracking-wider text-brand-700 dark:text-brand-300 hover:bg-brand-100/20 transition-colors"
        >
          <Pencil className="h-3 w-3" />
          Edit Profile
        </button>
        {/* Techno-economic assessment. Shown to the viewer class the finance
            guard admits — the server gate (require_finance_entitlement) is the
            real control, so this only avoids offering a door that answers "no
            access". The screen itself says when no approved base case exists. */}
        {isFinanceLike(role) && (
          <button
            onClick={() => onNav(`/economics/${project.id}`)}
            className="group inline-flex items-center gap-1.5 rounded border border-brand-400/60 bg-brand-50/10 px-2.5 py-[3px] text-[10px] font-mono uppercase tracking-wider text-brand-700 dark:text-brand-300 hover:bg-brand-100/20 transition-colors"
          >
            <LineChart className="h-3 w-3" />
            Economics (TEA)
          </button>
        )}
        <span className="mx-1 h-3 w-px bg-[var(--border)]" />
        {links.map((l) => (
          <button
            key={l.kind}
            onClick={() => onNav(resolveProjectDetailPath(l.kind, role))}
            className="group inline-flex items-center gap-1 rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-[3px] text-[10px] font-mono uppercase tracking-wider text-[var(--text-secondary)] hover:border-brand-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
          >
            <span className="text-[var(--text-muted)] group-hover:text-brand-600 dark:group-hover:text-brand-400">
              {l.label}
            </span>
            <span className="text-[var(--text-primary)] group-hover:text-brand-600 dark:group-hover:text-brand-400">
              {l.value}
            </span>
            <ChevronRight className="h-3 w-3" />
          </button>
        ))}
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="text-[9px] font-bold uppercase tracking-[0.15em] text-[var(--text-muted)]">
      {children}
    </div>
  );
}

function KV({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div className="grid grid-cols-[auto_1fr_auto] items-center gap-1">
      <span className="text-[var(--text-muted)] whitespace-nowrap">{label}</span>
      <span className="border-b border-dotted border-[var(--border)] min-w-[8px]" />
      <span
        className={`font-mono text-right whitespace-nowrap ${
          emphasis
            ? "font-bold text-[var(--text-primary)]"
            : "font-semibold text-[var(--text-primary)]"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

const ROW_GRID =
  "grid-cols-[24px_minmax(180px,2fr)_40px_40px_130px_minmax(200px,2fr)_68px_28px]";

export function ProjectsPage() {
  const navigate = useNavigate();
  const { setSelectedProjectId } = useSelectedProject();
  const { role } = useUserRole();
  const { projects: visibleProjects } = useVisibleProjects();
  const stateLabel = useVocabularyLabel("readiness");
  const phaseLabel = useVocabularyLabel("project_phase");

  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  // One engine readout per visible project — the same cached reads the
  // State & Blockers and Capital Eligibility screens use.
  const readoutList = useEngineReadouts(visibleProjects.map((p) => p.id));
  const readoutById = new Map(visibleProjects.map((p, i) => [p.id, readoutList[i]]));

  const filtered = useMemo(
    () =>
      visibleProjects.filter((p) => {
        const matchMol = filter === "all" || p.molecule === filter;
        const matchStr =
          search === "" ||
          p.name.toLowerCase().includes(search.toLowerCase()) ||
          p.location.toLowerCase().includes(search.toLowerCase());
        return matchMol && matchStr;
      }),
    [visibleProjects, filter, search],
  );

  const jump = (project: CustomerProject, path: string) => {
    setSelectedProjectId(project.id);
    setExpanded(null);
    navigate(path);
  };

  const roleSuffix = (() => {
    if (role.service_type) return role.service_type;
    return role.business_function.replace("_", " ");
  })();

  return (
    <div className="space-y-3 animate-fade-in">
      {/* ── Header ── */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-xl font-bold text-[var(--text-primary)]">
            Projects & Assets
            <span className="ml-3">{role.company_name}</span>
          </h1>
          <div className="mt-0.5 flex items-center gap-3 font-mono text-[11px] text-[var(--text-muted)]">
            <span>
              <span className="text-[var(--text-primary)] font-semibold">
                {visibleProjects.length}
              </span>{" "}
              projects
            </span>
            <span className="text-[var(--text-muted)]">
              {role.user_name} · {roleSuffix}
            </span>
          </div>
        </div>

        {/* Filters — inline, compact */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => navigate("/projects/new")}
            className="rounded bg-[var(--brand)] px-3 py-[6px] text-xs font-mono font-semibold text-white hover:opacity-90"
          >
            + New Project
          </button>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="gex-select text-xs font-mono"
          >
            <option value="all">ALL MOL</option>
            <option value="H2">H2</option>
            <option value="NH3">NH3</option>
            <option value="e-Methanol">MEO</option>
            <option value="SAF">SAF</option>
            <option value="e-NG">ENG</option>
          </select>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="w-48 rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-[5px] text-xs font-mono text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--brand)] focus:outline-none"
          />
        </div>
      </div>

      {/* ── Dense table ── */}
      <div className="overflow-hidden rounded border border-[var(--border)] bg-[var(--surface)]">
        {/* Header row */}
        <div className={`grid ${ROW_GRID} items-center gap-2 border-b border-[var(--border)] bg-[var(--surface-muted)] px-3 py-1.5 text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]`}>
          <span />
          <span>Project</span>
          <span className="text-center">Mol</span>
          <span className="text-center" title="Phase declared in the project context">Phase</span>
          <span className="text-right" title="State the evidence supports, from the gate engine">State</span>
          <span title="What the next state needs, from the gate engine">Next step</span>
          <span className="text-center">COD</span>
          <span />
        </div>

        {/* Data rows */}
        {filtered.length === 0 && (
          <div className="px-3 py-8 text-center text-xs font-mono text-[var(--text-muted)]">
            No projects match current filter.
          </div>
        )}
        {filtered.map((project) => {
          const readout = readoutById.get(project.id)!;
          const isOpen = expanded === project.id;
          const tick = MOL_TICK[project.molecule] ?? project.molecule;
          const nextStep = engineNextStep(readout, stateLabel);

          return (
            <div
              key={project.id}
              className={`border-b border-[var(--border)] last:border-b-0 ${
                isOpen ? "bg-[var(--surface-muted)]/40" : ""
              }`}
            >
              <button
                type="button"
                onClick={() => setExpanded((cur) => (cur === project.id ? null : project.id))}
                className={`grid w-full ${ROW_GRID} items-center gap-2 px-3 py-2 text-left hover:bg-[var(--surface-hover)] transition-colors`}
              >
                {/* Expand chevron */}
                <span className="text-[var(--text-muted)]">
                  {isOpen ? (
                    <ChevronDown className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" />
                  )}
                </span>
                {/* Name + location */}
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-semibold text-[var(--text-primary)]">
                    {project.name}
                  </span>
                  <span className="block truncate font-mono text-[10px] text-[var(--text-muted)]">
                    {project.location}
                  </span>
                </span>
                {/* Molecule ticker */}
                <span className="text-center font-mono text-[11px] font-bold text-[var(--text-primary)]">
                  {tick}
                </span>
                {/* Declared phase | evidenced state — read against each other */}
                <PhaseCell readout={readout} phaseLabel={phaseLabel} />
                <StateCell readout={readout} stateLabel={stateLabel} />
                {/* Next step — from the engine, single line */}
                <span className="truncate text-[11px] text-[var(--text-secondary)]" title={nextStep}>
                  {nextStep}
                </span>
                {/* COD */}
                <span className="text-center font-mono text-[11px] text-[var(--text-secondary)]">
                  {fmtCod(project.completion_date)}
                </span>
                {/* Jump to the gate evidence */}
                <span
                  role="button"
                  tabIndex={0}
                  aria-label={`Open gate evidence for ${project.name}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    jump(project, "/producer-bankability");
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      jump(project, "/producer-bankability");
                    }
                  }}
                  className="inline-flex h-5 w-5 cursor-pointer items-center justify-center rounded border border-[var(--border)] text-[var(--text-muted)] hover:border-brand-400 hover:text-brand-600 dark:hover:text-brand-400"
                >
                  <ChevronRight className="h-3 w-3" />
                </span>
              </button>

              {/* Expand-in-place */}
              {isOpen && (
                <ExpandPanel
                  project={project}
                  role={role}
                  readout={readout}
                  onNav={(path) => jump(project, path)}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Footer legend */}
      <div className="flex flex-wrap items-center gap-4 font-mono text-[10px] text-[var(--text-muted)]">
        <span>
          <span className="font-bold text-[var(--text-secondary)]">Phase</span> = declared in the project context
        </span>
        <span>
          <span className="font-bold text-[var(--text-secondary)]">State</span> = what the evidence supports, from the gate engine
        </span>
        <span>n/m = applicable evidence items verified</span>
      </div>
    </div>
  );
}
