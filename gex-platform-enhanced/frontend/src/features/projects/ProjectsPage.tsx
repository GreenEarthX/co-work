// Screen: Projects screen (/projects)
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, ChevronDown, AlertTriangle, Pencil } from "lucide-react";
import { type CustomerProject, type CommitmentStatus, type RiskCategory } from "@/data/customerProjects";
import { useSelectedProject } from "@/contexts/ProjectContext";
import { type UserRole, useUserRole } from "@/contexts/UserRoleContext";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";
import { useRiskFlags } from "@/hooks/useRiskFlags";
import { resolveActionRoute, type RouteAction } from "@/lib/actionRouter";

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

// 3-letter phase codes — dense column.
const STATUS_CODE: Record<string, string> = {
  development: "DEV",
  construction: "CON",
  commissioning: "CMS",
  operating: "OPS",
};

const STATUS_COLOR: Record<string, string> = {
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

const COMMITMENT_ORDER: Record<CommitmentStatus, number> = {
  NONE: 0,
  INDICATIVE: 1,
  TERM_SHEET: 2,
  CREDIT_APPROVED: 3,
  LEGAL_COMPLETE: 4,
  DRAWN: 5,
};

const COMMITMENT_LABELS: Record<CommitmentStatus, string> = {
  NONE: "no engagement",
  INDICATIVE: "indicative",
  TERM_SHEET: "term sheet",
  CREDIT_APPROVED: "credit approved",
  LEGAL_COMPLETE: "legal complete",
  DRAWN: "drawn",
};

function commitmentColor(status: CommitmentStatus): string {
  if (status === "DRAWN" || status === "LEGAL_COMPLETE")
    return "text-emerald-600 dark:text-emerald-400";
  if (status === "CREDIT_APPROVED" || status === "TERM_SHEET")
    return "text-brand-600 dark:text-brand-400";
  if (status === "INDICATIVE") return "text-amber-600 dark:text-amber-400";
  return "text-[var(--text-muted)]";
}

// ─── Derivation helpers (kept intact for progressive disclosure) ─────────────

const isCodStarted = (status: string) =>
  status === "operating" || status === "commissioning";

function capexFinancingPct(project: CustomerProject): number {
  // capex_eur 0 = CAPEX not publicly disclosed (public-source seeds) — avoid NaN%
  if (!project.capex_eur) return 0;
  let funded = 0;
  for (const c of project.bankability.capital_status) {
    const amt = parseFloat(c.amount.replace(/[^0-9.]/g, "")) * 1_000_000;
    if ((COMMITMENT_ORDER[c.commitment_status] ?? 0) >= 2) funded += amt;
  }
  return Math.min(100, Math.round((funded / project.capex_eur) * 100));
}

function opexCoveragePct(project: CustomerProject): number {
  if (!project.capex_eur) return 0;
  const annualOpex = project.capex_eur * 0.04;
  const monthlyOpex = annualOpex / 12;
  const price = MOLECULE_PRICE[project.molecule] ?? 1000;
  const utilizationFactor = 0.85;
  const monthlyVolumeSold = project.capacity_mtpd * 30.4 * utilizationFactor;
  const monthlyRevenue = monthlyVolumeSold * price;
  return Math.round((monthlyRevenue / monthlyOpex) * 100);
}

interface BankabilityAxes {
  evidence_pct: number;
  gates_pct: number;
  capital_pct: number;
  blockers_pct: number;
}

function bankabilityAxes(project: CustomerProject): BankabilityAxes {
  const gates = project.bankability.gates;
  const capitals = project.bankability.capital_status;

  const totalEvidence = gates.reduce((s, g) => s + g.total_evidence, 0);
  const verifiedEvidence = gates.reduce((s, g) => s + g.verified_count, 0);
  const evidence_pct =
    totalEvidence > 0 ? Math.round((verifiedEvidence / totalEvidence) * 100) : 0;

  const gates_pct =
    gates.length > 0
      ? Math.round((gates.filter((g) => g.is_complete).length / gates.length) * 100)
      : 0;

  let committedAmt = 0;
  let totalAmt = 0;
  for (const c of capitals) {
    const amt = parseFloat(c.amount.replace(/[^0-9.]/g, "")) || 0;
    totalAmt += amt;
    if (COMMITMENT_ORDER[c.commitment_status] >= 2) committedAmt += amt;
  }
  const capital_pct =
    totalAmt > 0 ? Math.round((committedAmt / totalAmt) * 100) : 0;

  const openBlockers = gates.reduce((s, g) => s + g.blocking_items.length, 0);
  const alerts = project.bankability.risk_alerts.length;
  const blockers_pct = Math.max(0, 100 - openBlockers * 8 - alerts * 5);

  return { evidence_pct, gates_pct, capital_pct, blockers_pct };
}

type ProjectState = "needs_action" | "on_track" | "behind";

function classifyProjectState(project: CustomerProject): ProjectState {
  const bPct = project.bankability.overall_completion;
  const alerts = project.bankability.risk_alerts.length;
  const openBlockers = project.bankability.gates.reduce(
    (s, g) => s + g.blocking_items.length,
    0,
  );
  if (project.status === "development" && bPct < 50) return "behind";
  if (alerts > 0 || openBlockers > 0) return "needs_action";
  return "on_track";
}

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
  kind:
    | "molecule"
    | "phase"
    | "capacity"
    | "status"
    | "targetCod"
    | "capexFinancing",
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
    case "capacity":
      return "/capacity";
    case "status":
      if (business_function === "COMPLIANCE_LEGAL" || service_type === "CERTIFIER")
        return "/stage-gates";
      if (business_function === "ENGINEERING" || business_function === "OPERATIONS")
        return "/producer-bankability";
      return "/bankability-scores";
    case "targetCod":
      if (business_function === "ENGINEERING" || business_function === "OPERATIONS")
        return "/producer-bankability";
      return "/finance-timeline";
    case "capexFinancing":
      if (business_function === "COMMERCIAL" && company_type === "OFFTAKER")
        return "/offtake-quality";
      if (business_function === "COMPLIANCE_LEGAL") return "/stage-gates";
      return "/capital-stack";
    default:
      return "/dashboard";
  }
}

// ─── Role-aware next-action derivation ───────────────────────────────────────
// Returns a short, action-verb-led string scoped to what THIS user should do.
// Falls back to project.bankability.next_milestone when no role-specific action applies.

function roleNextActionText(project: CustomerProject, role: UserRole): string {
  const { business_function, company_type, service_type } = role;
  const openBlockers = project.bankability.gates.filter(
    (g) => !g.is_complete && g.blocking_items.length > 0,
  );
  const alerts = project.bankability.risk_alerts;
  const topBlocker = openBlockers[0];
  const topAlert = alerts[0];

  // Finance / Bank — capital commitment actions
  if (
    business_function === "FINANCE_TREASURY" ||
    service_type === "BANK"
  ) {
    const uncommitted = project.bankability.capital_status.find(
      (c) =>
        COMMITMENT_ORDER[c.commitment_status] >= 1 &&
        COMMITMENT_ORDER[c.commitment_status] < 3,
    );
    if (uncommitted)
      return `Advance ${uncommitted.name} to credit approval`;
    if (topAlert) return `Review risk alert: ${topAlert.replace(/_/g, " ")}`;
    return project.bankability.next_milestone;
  }

  // Engineering / Operations — blocker resolution
  if (
    business_function === "ENGINEERING" ||
    business_function === "OPERATIONS" ||
    service_type === "ENGINEER"
  ) {
    if (topBlocker) {
      const item = topBlocker.blocking_items[0].replace(/_/g, " ");
      return `Resolve ${topBlocker.id.split("_")[0]}: ${item}`;
    }
    return project.bankability.next_milestone;
  }

  // Compliance / Legal / Certifier — gate completion
  if (
    business_function === "COMPLIANCE_LEGAL" ||
    service_type === "CERTIFIER" ||
    service_type === "LEGAL"
  ) {
    const incompleteGate = project.bankability.gates.find((g) => !g.is_complete);
    if (incompleteGate)
      return `Clear stage gate: ${incompleteGate.id.replace(/_/g, " ")}`;
    return project.bankability.next_milestone;
  }

  // Commercial / Offtaker — offtake or term sheet actions
  if (
    business_function === "COMMERCIAL" ||
    company_type === "OFFTAKER"
  ) {
    const tsReady = project.bankability.capital_status.find(
      (c) => c.commitment_status === "INDICATIVE",
    );
    if (tsReady) return `Progress ${tsReady.name} to term sheet`;
    return project.bankability.next_milestone;
  }

  // Executive — high-level milestone
  if (business_function === "EXECUTIVE") {
    if (project.bankability.overall_completion < 50 && project.status === "development")
      return `Escalate: bankability ${project.bankability.overall_completion}% — below threshold`;
    if (topAlert) return `Assess alert: ${topAlert.replace(/_/g, " ")}`;
    return project.bankability.next_milestone;
  }

  return project.bankability.next_milestone;
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
    return { kind: "next:finance", preferred_route: "/capital-stack", owner_function: "FINANCE_TREASURY", fallback_route: "/bankability-scores", fallback_label: "Bankability", label: "Capital Stack" };
  if (business_function === "ENGINEERING" || business_function === "OPERATIONS" || service_type === "ENGINEER")
    return { kind: "next:engineering", preferred_route: "/producer-bankability", owner_function: "ENGINEERING", label: "Gate Evidence" };
  if (business_function === "COMPLIANCE_LEGAL" || service_type === "CERTIFIER" || service_type === "LEGAL")
    return { kind: "next:compliance", preferred_route: "/stage-gates", owner_function: "COMPLIANCE_LEGAL", label: "Stage Gates" };
  if (business_function === "COMMERCIAL" || company_type === "OFFTAKER")
    return { kind: "next:commercial", preferred_route: "/offtake-quality", owner_function: "COMMERCIAL", fallback_route: "/bankability-scores", fallback_label: "Bankability", label: "Offtake Quality" };
  if (business_function === "EXECUTIVE")
    return { kind: "next:executive", preferred_route: "/finance-timeline", owner_function: "EXECUTIVE", label: "Finance Timeline" };
  return { kind: "next:default", preferred_route: "/bankability-scores", owner_function: "EXECUTIVE", label: "Bankability" };
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

/** Capital tranches a gate blocks — the causal consequence. */
function gateUnlocks(project: CustomerProject, gateId: string): string | null {
  const gated = project.bankability.capital_status.filter(
    (c) => !c.is_unlocked && c.gating_gates.includes(gateId),
  );
  if (gated.length === 0) return null;
  return gated.map((c) => `${c.amount} ${c.name}`).join(" · ");
}

/** LEGACY risk-alert string → an ACTION (keyword heuristic for projects not yet
 *  migrated to structured risk_flags). Owner-surface alerts (offtake/financing)
 *  carry a fallback so the resolver routes non-owners off the locked screen. */
function riskAlertAction(project: CustomerProject, alert: string): LabelledAction {
  const a = alert.toLowerCase();
  const pid = encodeURIComponent(project.id);
  if (/capacity|overstat|discrepan|public source/.test(a))
    return { kind: "alert:capacity", preferred_route: `/adversarial-review?project=${pid}`, owner_function: "EXECUTIVE", label: "Challenge Review" };
  if (/45v|rfnbo|red.?iii|temporal|certif|ghg|iso.?14064/.test(a))
    return { kind: "alert:cert", preferred_route: "/cert-readiness", owner_function: "COMPLIANCE_LEGAL", label: "Cert Readiness" };
  if (/offtake|related.?party|take.?or.?pay|tenor|term sheet|loi\b/.test(a))
    return { kind: "alert:offtake", preferred_route: "/offtake-quality", owner_function: "COMMERCIAL", fallback_route: `/producer-bankability?project=${pid}&gate=G4`, fallback_label: "Gate Evidence", label: "Offtake Quality" };
  if (/lender|debt|equity|capital|wacc|insur|drawdown/.test(a))
    return { kind: "alert:financing", preferred_route: "/capital-stack", owner_function: "FINANCE_TREASURY", fallback_route: "/bankability-scores", fallback_label: "Bankability", label: "Capital Stack" };
  if (/grid|permit|eia|environmental|water|land|interconnect|ppa/.test(a))
    return { kind: "alert:site", preferred_route: "/producer-bankability", owner_function: "ENGINEERING", label: "Gate Evidence" };
  return { kind: "alert:other", preferred_route: "/bankability-scores", owner_function: "EXECUTIVE", label: "Bankability" };
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
        fallback_route: "/bankability-scores", fallback_label: "Bankability",
        label: "Capital Stack",
      };
    case "insurance":
      return { kind: "risk:insurance", preferred_route: "/insurance", owner_function: "FINANCE_TREASURY", label: "Insurance Schedule" };
    case "site_permits":
      return { kind: "risk:site_permits", preferred_route: "/producer-bankability", owner_function: "ENGINEERING", label: "Gate Evidence" };
    default:
      return { kind: "risk:other", preferred_route: "/bankability-scores", owner_function: "EXECUTIVE", label: "Bankability" };
  }
}

// ─── Tiny display helpers ────────────────────────────────────────────────────

function fmtShort(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function fmtCod(date: string): string {
  const d = new Date(date);
  return `${d.toLocaleString("en-GB", { month: "short" }).toUpperCase()}-${String(
    d.getFullYear(),
  ).slice(-2)}`;
}

// Single-letter state marker. Bloomberg uses a narrow colored glyph in
// the leftmost column rather than a badge.
function stateMarker(state: ProjectState): { char: string; color: string; label: string } {
  if (state === "behind")
    return { char: "●", color: "text-rose-500", label: "Behind plan" };
  if (state === "needs_action")
    return { char: "●", color: "text-amber-500", label: "Needs action" };
  return { char: "●", color: "text-emerald-500", label: "On track" };
}

// ─── Four-segment inline microbar ────────────────────────────────────────────
// Evidence · Gates · Capital · Blockers-clear — each rendered as a quarter
// slice. Widths within a slice encode that axis's %. Hover reveals the number.
// This is the progressive-disclosure primitive: the headline BNK% (left)
// decomposes into four sub-capabilities inline, without expanding the row.

function FourSegmentBar({ axes }: { axes: BankabilityAxes }) {
  const segs: Array<{ key: string; label: string; pct: number }> = [
    { key: "E", label: "Evidence", pct: axes.evidence_pct },
    { key: "G", label: "Gates", pct: axes.gates_pct },
    { key: "C", label: "Capital", pct: axes.capital_pct },
    { key: "B", label: "Blockers clear", pct: axes.blockers_pct },
  ];
  return (
    <div className="flex h-1.5 w-full gap-px">
      {segs.map((s) => (
        <div
          key={s.key}
          className="relative flex-1 bg-[var(--border)]/40 overflow-hidden"
          title={`${s.label}: ${s.pct}%`}
        >
          <div
            className={segColor(s.pct)}
            style={{ width: `${s.pct}%`, height: "100%" }}
          />
        </div>
      ))}
    </div>
  );
}

function segColor(pct: number): string {
  if (pct >= 85) return "h-full bg-emerald-500";
  if (pct >= 55) return "h-full bg-amber-400";
  if (pct >= 25) return "h-full bg-brand-500";
  return "h-full bg-rose-500";
}

function bnkColor(pct: number): string {
  if (pct >= 85) return "text-emerald-600 dark:text-emerald-400";
  if (pct >= 55) return "text-amber-600 dark:text-amber-400";
  if (pct >= 25) return "text-brand-600 dark:text-brand-400";
  return "text-rose-600 dark:text-rose-400";
}

// ─── Expand-in-place panel ────────────────────────────────────────────────────
// Replaces the old modal. Opens inline below the clicked row. Contains:
//   (1) Context — phase, next action, open blockers
//   (2) Capacity derivation (volumeBreakdown)
//   (3) Capital stack (tranche → amount → commitment stage)
//   (4) Persona deep-links (6 entry points that were the ProjectDetail modal)
// Progressive disclosure: the row's numbers are re-stated AND their inputs
// are shown — the user sees *how the number was derived*.

function ExpandPanel({
  project,
  role,
  onNav,
}: {
  project: CustomerProject;
  role: UserRole;
  onNav: (path: string) => void;
}) {
  const vb = volumeBreakdown(project);
  const ops = isCodStarted(project.status);
  const cpx = capexFinancingPct(project);
  const opx = opexCoveragePct(project);
  const openGates = project.bankability.gates.filter(
    (g) => !g.is_complete && g.blocking_items.length > 0,
  );
  const myNextAction = roleNextActionText(project, role);
  // Server-filtered structured flags (ABAC: classification × stakeholding).
  // Falls back to the static copy in dev; legacy string alerts render for
  // projects not yet migrated to risk_flags.
  const { flags: riskFlags } = useRiskFlags(project.id);

  const links: Array<{ label: string; value: string; kind: Parameters<typeof resolveProjectDetailPath>[0] }> = [
    { label: "Molecule", value: project.molecule, kind: "molecule" },
    { label: "Phase", value: project.phase, kind: "phase" },
    { label: "Capacity", value: `${project.capacity_mtpd} MTPD`, kind: "capacity" },
    { label: "Status", value: STATUS_CODE[project.status] ?? "—", kind: "status" },
    { label: "Target COD", value: fmtCod(project.completion_date), kind: "targetCod" },
    { label: ops ? "OPEX cov." : "CAPEX fin.", value: `${ops ? opx : cpx}%`, kind: "capexFinancing" },
  ];

  return (
    <div className="border-t border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3">
      <div className="grid grid-cols-12 gap-4 text-[11px]">
        {/* Your action — role-scoped, leads the panel.
            Sung structure per row: THOUGHT (the claim) → CONSEQUENCE (what it
            blocks) → WAY (the screen where it is worked). Nothing here
            is allowed to dead-end on prose. */}
        <div className="col-span-12 lg:col-span-4 space-y-2">
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
                {myNextAction}
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
            {" · "}
            {project.phase}
          </div>
          {openGates.length > 0 && (
            <>
              <div className="text-[var(--text-muted)] pt-1">Open blockers</div>
              <ul className="space-y-0.5">
                {openGates.slice(0, 4).map((g) => {
                  const unlocks = gateUnlocks(project, g.id);
                  // The resolver owns the decision; the gate-evidence view is
                  // persona-scoped and self-explains a gate outside the viewer's
                  // persona (F2 banner), so this never dead-ends generically.
                  const resolved = resolveActionRoute(role, blockerAction(project, g.id), project.id);
                  return (
                    <li key={g.id}>
                      <button
                        onClick={() => resolved.route && onNav(resolved.route)}
                        className="flex w-full items-start gap-1 text-left text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                        title={`Open ${g.id} evidence detail`}
                      >
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
                        <span className="min-w-0">
                          <span className="block truncate">
                            <span className="font-mono font-semibold">{g.id.split("_")[0]}</span>{" "}
                            {g.blocking_items[0].replace(/_/g, " ")}
                            {g.blocking_items.length > 1
                              ? ` +${g.blocking_items.length - 1}`
                              : ""}
                          </span>
                          {unlocks && (
                            <span className="block truncate font-mono text-[10px] text-[var(--text-muted)]">
                              blocks {unlocks}
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
          {riskFlags.length > 0 ? (
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
          ) : project.bankability.risk_alerts.length > 0 && (
            <>
              <div className="text-[var(--text-muted)] pt-1">Risk alerts</div>
              <ul className="space-y-0.5">
                {project.bankability.risk_alerts.slice(0, 3).map((a) => {
                  const action = riskAlertAction(project, a);
                  const resolved = resolveActionRoute(role, action, project.id);
                  const label = resolved.status === "fallback" ? (action.fallback_label ?? action.label) : action.label;
                  return (
                    <li key={a}>
                      <button
                        onClick={() => resolved.route && onNav(resolved.route)}
                        disabled={!resolved.route}
                        className="flex w-full items-start gap-1 text-left text-[10px] text-rose-500 hover:text-rose-400 disabled:cursor-default disabled:text-[var(--text-muted)]"
                        title={resolved.route ? `Work this risk in ${label}` : undefined}
                      >
                        <span className="mt-0.5 shrink-0">▲</span>
                        <span className="min-w-0">
                          <span className="block">{a.replace(/_/g, " ")}</span>
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
        <div className="col-span-12 lg:col-span-4 space-y-1">
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
          <KV
            label={ops ? "OPEX coverage" : "CAPEX financed"}
            value={`${ops ? opx : cpx}%`}
            emphasis
          />
        </div>

        {/* Capital stack */}
        <div className="col-span-12 lg:col-span-4 space-y-1">
          <SectionLabel>Capital stack</SectionLabel>
          {project.bankability.capital_status.map((c) => (
            <div
              key={c.type}
              className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-1"
            >
              <span className="whitespace-nowrap text-[var(--text-secondary)]">{c.name}</span>
              <span className="border-b border-dotted border-[var(--border)] min-w-[8px]" />
              <span className="font-mono font-semibold text-[var(--text-primary)] whitespace-nowrap">
                {c.amount}
              </span>
              <span
                className={`font-mono text-[10px] uppercase tracking-wider whitespace-nowrap ${commitmentColor(
                  c.commitment_status,
                )}`}
              >
                {COMMITMENT_LABELS[c.commitment_status]}
              </span>
            </div>
          ))}
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

function SectionLabel({ children }: { children: React.ReactNode }) {
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

export function ProjectsPage() {
  const navigate = useNavigate();
  const { setSelectedProjectId } = useSelectedProject();
  const { role } = useUserRole();
  const { projects: visibleProjects } = useVisibleProjects();

  const [filter, setFilter] = useState<string>("all");
  const [stateFilter, setStateFilter] = useState<"all" | ProjectState>("all");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const filtered = useMemo(
    () =>
      visibleProjects.filter((p) => {
        const matchMol = filter === "all" || p.molecule === filter;
        const matchState =
          stateFilter === "all" || classifyProjectState(p) === stateFilter;
        const matchStr =
          search === "" ||
          p.name.toLowerCase().includes(search.toLowerCase()) ||
          p.location.toLowerCase().includes(search.toLowerCase());
        return matchMol && matchState && matchStr;
      }),
    [visibleProjects, filter, stateFilter, search],
  );

  const stateCounts = useMemo(() => {
    const c = { needs_action: 0, on_track: 0, behind: 0 };
    for (const p of visibleProjects) c[classifyProjectState(p)]++;
    return c;
  }, [visibleProjects]);

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
      {/* ── Header + counts strip ── */}
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
            <span className="text-[var(--border)]">|</span>
            <span className="text-rose-500">
              ● {stateCounts.behind} behind
            </span>
            <span className="text-amber-500">
              ● {stateCounts.needs_action} needs action
            </span>
            <span className="text-emerald-500">
              ● {stateCounts.on_track} on track
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
          <select
            value={stateFilter}
            onChange={(e) =>
              setStateFilter(e.target.value as typeof stateFilter)
            }
            className="gex-select text-xs font-mono"
          >
            <option value="all">ALL STATES</option>
            <option value="needs_action">NEEDS ACTION</option>
            <option value="on_track">ON TRACK</option>
            <option value="behind">BEHIND</option>
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
        <div className="grid grid-cols-[24px_16px_minmax(180px,2fr)_40px_40px_110px_minmax(200px,2fr)_64px_68px_28px] items-center gap-2 border-b border-[var(--border)] bg-[var(--surface-muted)] px-3 py-1.5 text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          <span />
          <span />
          <span>Project</span>
          <span className="text-center">Mol</span>
          <span className="text-center">Stat</span>
          <span className="text-right">Bnk · E·G·C·B</span>
          <span title="Role-scoped action for your function">Your next action</span>
          <span className="text-right" title="Operating: OPEX coverage %; Development/Construction: CAPEX financed %">Cpx/Opx%</span>
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
          const axes = bankabilityAxes(project);
          const bPct = project.bankability.overall_completion;
          const state = classifyProjectState(project);
          const mark = stateMarker(state);
          const ops = isCodStarted(project.status);
          const cpx = ops ? opexCoveragePct(project) : capexFinancingPct(project);
          const isOpen = expanded === project.id;
          const tick = MOL_TICK[project.molecule] ?? project.molecule;
          const statusCode = STATUS_CODE[project.status] ?? "—";
          const statusColor = STATUS_COLOR[project.status] ?? "text-[var(--text-muted)]";
          const nextAction = roleNextActionText(project, role);

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
                className="grid w-full grid-cols-[24px_16px_minmax(180px,2fr)_40px_40px_110px_minmax(200px,2fr)_64px_68px_28px] items-center gap-2 px-3 py-2 text-left hover:bg-[var(--surface-hover)] transition-colors"
              >
                {/* Expand chevron */}
                <span className="text-[var(--text-muted)]">
                  {isOpen ? (
                    <ChevronDown className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" />
                  )}
                </span>
                {/* State dot */}
                <span className={mark.color} title={mark.label}>
                  {mark.char}
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
                {/* Status code */}
                <span
                  className={`text-center font-mono text-[11px] font-bold ${statusColor}`}
                >
                  {statusCode}
                </span>
                {/* BNK headline + inline 4-segment microbar */}
                <span className="flex flex-col items-end gap-1">
                  <span
                    className={`font-mono text-[12px] font-bold tabular-nums ${bnkColor(bPct)}`}
                  >
                    {String(bPct).padStart(2, " ")}%
                  </span>
                  <span className="w-full">
                    <FourSegmentBar axes={axes} />
                  </span>
                </span>
                {/* Next action — role-scoped, single line */}
                <span className="truncate text-[11px] text-[var(--text-secondary)]" title={nextAction}>
                  {nextAction}
                </span>
                {/* Cpx / Opx % */}
                <span className="text-right font-mono text-[12px] font-semibold tabular-nums text-[var(--text-primary)]">
                  {cpx}%
                </span>
                {/* COD */}
                <span className="text-center font-mono text-[11px] text-[var(--text-secondary)]">
                  {fmtCod(project.completion_date)}
                </span>
                {/* Jump-to-bankability */}
                <span
                  role="button"
                  tabIndex={0}
                  aria-label={`Open bankability for ${project.name}`}
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
          <span className="font-bold text-[var(--text-secondary)]">BNK</span>{" "}
          decomposes into E·G·C·B:
        </span>
        <span>E = evidence verified / total</span>
        <span>G = gates cleared / total</span>
        <span>C = capital committed (TS+) / total</span>
        <span>B = 100 − blockers · alerts</span>
      </div>
    </div>
  );
}
