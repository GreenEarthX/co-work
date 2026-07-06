// Screen: Shared data module (no screen)
/**
 * Evidence catalog — DEV FALLBACK ONLY.
 *
 * The AUTHORITATIVE evidence policy (labels, sections, power-model
 * applicability, severity, escalation, owners, routes) lives server-side in
 * gex_pf_engine/backend/app/core/bankability_engine.py (EVIDENCE_META) and is
 * served by GET /api/v1/bankability/gates and embedded per-item in every
 * gate evaluation's evidence_detail.
 *
 * This mirror exists so the producer bankability view degrades gracefully
 * when the engine (port 8001) is down. It must stay in sync with the engine
 * registry — if they diverge, the engine wins.
 */

export type PowerModel = 'OFF_GRID_BTM' | 'GRID_CONNECTED' | 'HYBRID';
export type EvidenceSeverity = 'advisory' | 'warning' | 'deal_killer';

export interface EvidenceMeta {
  gate: string;            // gate number prefix, e.g. 'G1'
  label: string;
  section: string;         // 'A' … 'E'
  section_label: string;
  applies_to: (PowerModel | 'ALL')[];
  severity: EvidenceSeverity;          // base severity when missing
  escalates_at_construction: boolean;  // warning → deal_killer once capital at work
  owner_function: string;
  blocked_action?: string;
  route?: string;          // where the gap is worked; {project_id} is substituted
}

const G1 = 'G1';
const G0 = 'G0';

export const STATIC_EVIDENCE_CATALOG: Record<string, EvidenceMeta> = {
  // ── G0 ──────────────────────────────────────────────────────────────────
  land_option_or_lease_executed: {
    gate: G0, label: 'Land Option or Lease Executed',
    section: 'A', section_label: 'Site Control',
    applies_to: ['ALL'], severity: 'deal_killer', escalates_at_construction: false,
    owner_function: 'LEGAL', blocked_action: 'Site control — no project without it',
    route: '/projects/{project_id}/edit',
  },
  zoning_compatibility_memo: {
    gate: G0, label: 'Zoning Compatibility Memo',
    section: 'A', section_label: 'Site Control',
    applies_to: ['ALL'], severity: 'warning', escalates_at_construction: true,
    owner_function: 'LEGAL', blocked_action: 'Planning permission pathway',
    route: '/projects/{project_id}/edit',
  },
  stakeholder_map_v1: {
    gate: G0, label: 'Stakeholder Map v1',
    section: 'B', section_label: 'Stakeholder & Community',
    applies_to: ['ALL'], severity: 'advisory', escalates_at_construction: false,
    owner_function: 'PROJECT', blocked_action: 'Social licence foundation',
    route: '/projects/{project_id}/edit',
  },
  // ── G1 — A. Power Access (grid-connected / hybrid) ──────────────────────
  grid_interconnection_study: {
    gate: G1, label: 'Grid Interconnection Study',
    section: 'A', section_label: 'Power Access',
    applies_to: ['GRID_CONNECTED', 'HYBRID'], severity: 'deal_killer', escalates_at_construction: false,
    owner_function: 'ENGINEERING', blocked_action: 'Connection feasibility confirmation',
    route: '/projects/{project_id}/edit',
  },
  queue_position_evidence: {
    gate: G1, label: 'Grid Queue Position / Capacity Reservation',
    section: 'A', section_label: 'Power Access',
    applies_to: ['GRID_CONNECTED', 'HYBRID'], severity: 'warning', escalates_at_construction: true,
    owner_function: 'ENGINEERING', blocked_action: 'COD timeline certainty',
    route: '/projects/{project_id}/edit',
  },
  grid_connection_cost_estimate: {
    gate: G1, label: 'Grid Connection Cost & Reinforcement Scope',
    section: 'A', section_label: 'Power Access',
    applies_to: ['GRID_CONNECTED', 'HYBRID'], severity: 'warning', escalates_at_construction: false,
    owner_function: 'ENGINEERING', blocked_action: 'CAPEX floor accuracy',
    route: '/finance-plant-builder',
  },
  connection_date_cod_compatibility_memo: {
    gate: G1, label: 'Connection Date vs COD Compatibility Memo',
    section: 'A', section_label: 'Power Access',
    applies_to: ['GRID_CONNECTED', 'HYBRID'], severity: 'warning', escalates_at_construction: true,
    owner_function: 'ENGINEERING', blocked_action: 'Schedule bankability',
    route: '/projects/{project_id}/edit',
  },
  // ── G1 — B. Renewable Power Procurement (grid-connected / hybrid) ───────
  ppa_register: {
    gate: G1, label: 'PPA Register (counterparty, MW, €/MWh, tenor)',
    section: 'B', section_label: 'Renewable Power Procurement',
    applies_to: ['GRID_CONNECTED', 'HYBRID'], severity: 'warning', escalates_at_construction: true,
    owner_function: 'SALES', blocked_action: 'RFNBO/45V additionality evidence; OPEX hedge',
    route: '/projects/{project_id}/edit',
  },
  ppa_signed_or_term_sheet_evidence: {
    gate: G1, label: 'Signed PPA / Term Sheet / LOI Evidence',
    section: 'B', section_label: 'Renewable Power Procurement',
    applies_to: ['GRID_CONNECTED', 'HYBRID'], severity: 'warning', escalates_at_construction: true,
    owner_function: 'SALES', blocked_action: 'Electricity price hedge — dominant OPEX of electrolysis',
    route: '/projects/{project_id}/edit',
  },
  ppa_volume_load_coverage_analysis: {
    gate: G1, label: 'PPA Volume vs Plant Load Coverage Analysis',
    section: 'B', section_label: 'Renewable Power Procurement',
    applies_to: ['GRID_CONNECTED', 'HYBRID'], severity: 'warning', escalates_at_construction: false,
    owner_function: 'ENGINEERING', blocked_action: 'Hourly renewable matching for RFNBO',
    route: '/projects/{project_id}/edit',
  },
  ppa_tenor_debt_comparison: {
    gate: G1, label: 'PPA Tenor vs Debt / Offtake Tenor Comparison',
    section: 'B', section_label: 'Renewable Power Procurement',
    applies_to: ['GRID_CONNECTED', 'HYBRID'], severity: 'advisory', escalates_at_construction: true,
    owner_function: 'FINANCE', blocked_action: 'Lender tenor mismatch risk',
    route: '/dscr-sensitivity',
  },
  // ── G1 — C. Curtailment & Dispatch (all power models) ───────────────────
  // Engineering evidence is worked on the project's technical premise (edit
  // page) — /dscr-sensitivity is a finance-restricted CONSEQUENCE screen.
  curtailment_assessment: {
    gate: G1, label: 'Curtailment Assessment (grid node congestion + load profile)',
    section: 'C', section_label: 'Curtailment & Dispatch',
    applies_to: ['ALL'], severity: 'warning', escalates_at_construction: false,
    owner_function: 'ENGINEERING', blocked_action: 'Availability factor; CFADS downside case',
    route: '/projects/{project_id}/edit',
  },
  dispatch_load_factor_production_impact: {
    gate: G1, label: 'Dispatch / Load Factor Impact on Production Volume',
    section: 'C', section_label: 'Curtailment & Dispatch',
    applies_to: ['ALL'], severity: 'warning', escalates_at_construction: false,
    owner_function: 'ENGINEERING', blocked_action: 'Production volume bankability; offtake delivery obligations',
    route: '/projects/{project_id}/edit',
  },
  // ── G1 — D. Water Supply & Permitting (all power models) ────────────────
  water_source_plan: {
    gate: G1, label: 'Water Source Plan (volume, cost, seasonal availability)',
    section: 'D', section_label: 'Water Supply',
    applies_to: ['ALL'], severity: 'deal_killer', escalates_at_construction: false,
    owner_function: 'ENGINEERING', blocked_action: 'Social licence; permitting pathway',
    route: '/projects/{project_id}/edit',
  },
  water_permit_pathway_memo: {
    gate: G1, label: 'Water Permit / Abstraction / Discharge Pathway',
    section: 'D', section_label: 'Water Supply',
    applies_to: ['ALL'], severity: 'warning', escalates_at_construction: true,
    owner_function: 'LEGAL', blocked_action: 'Construction permit; lender environmental covenant',
    route: '/projects/{project_id}/edit',
  },
  // ── G1 — E. BTM Generation (off-grid / hybrid) ──────────────────────────
  btm_generation_asset_evidence: {
    gate: G1, label: 'BTM Generation Asset Spec & CAPEX',
    section: 'E', section_label: 'BTM Generation',
    applies_to: ['OFF_GRID_BTM', 'HYBRID'], severity: 'deal_killer', escalates_at_construction: false,
    owner_function: 'ENGINEERING', blocked_action: 'Power supply premise — electricity is CAPEX for off-grid',
    route: '/finance-plant-builder',
  },
  generation_yield_study: {
    gate: G1, label: 'Generation Yield Study (P50/P90)',
    section: 'E', section_label: 'BTM Generation',
    applies_to: ['OFF_GRID_BTM', 'HYBRID'], severity: 'warning', escalates_at_construction: true,
    owner_function: 'ENGINEERING', blocked_action: 'Production volume bankability; lender P90 case',
    route: '/finance-plant-builder',
  },
  grid_independence_note: {
    gate: G1, label: 'Grid-Independence Design Note',
    section: 'E', section_label: 'BTM Generation',
    applies_to: ['OFF_GRID_BTM', 'HYBRID'], severity: 'warning', escalates_at_construction: false,
    owner_function: 'ENGINEERING', blocked_action: 'Evidence that no interconnect is required (or surplus-export scope)',
    route: '/projects/{project_id}/edit',
  },
  backup_construction_power_plan: {
    gate: G1, label: 'Backup / Construction Power Plan',
    section: 'E', section_label: 'BTM Generation',
    applies_to: ['OFF_GRID_BTM', 'HYBRID'], severity: 'warning', escalates_at_construction: true,
    owner_function: 'PROJECT', blocked_action: 'Construction schedule; commissioning power',
    route: '/projects/{project_id}/edit',
  },
};

const ESCALATION_PHASES = new Set(['construction', 'commissioning', 'operating']);

/** Fallback meta for keys the catalog does not know. */
export function evidenceMetaFallback(key: string, gatePrefix?: string): EvidenceMeta {
  return (
    STATIC_EVIDENCE_CATALOG[key] ?? {
      gate: gatePrefix ?? 'G?',
      label: key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()),
      section: 'Z', section_label: 'Other',
      applies_to: ['ALL'], severity: 'warning', escalates_at_construction: false,
      owner_function: 'PROJECT',
    }
  );
}

export function appliesToModel(applies_to: string[], powerModel: PowerModel | null | undefined): boolean {
  if (applies_to.includes('ALL')) return true;
  if (!powerModel) return true; // unknown — show everything
  return applies_to.includes(powerModel);
}

/** Phase-aware severity — mirrors engine _effective_severity. */
export function effectiveSeverity(meta: Pick<EvidenceMeta, 'severity' | 'escalates_at_construction'>, projectStatus: string | null | undefined): EvidenceSeverity {
  if (
    meta.severity === 'warning' &&
    meta.escalates_at_construction &&
    projectStatus && ESCALATION_PHASES.has(projectStatus)
  ) {
    return 'deal_killer';
  }
  return meta.severity;
}

/** Substitute {project_id} in a catalog route. */
export function resolveEvidenceRoute(route: string | undefined, projectId: string): string | undefined {
  return route?.replace('{project_id}', encodeURIComponent(projectId));
}

/**
 * canEnterRoute — the single permission primitive: may THIS viewer meaningfully
 * act on THIS route? Two restriction classes (everything else is open):
 *  • FINANCE_GUARDED_ROUTES — hard FinanceRouteGuard in App.tsx (finance/exec/
 *    bank/DFI/insurer only); a non-finance viewer is physically blocked.
 *  • OWNER_SURFACES — workflow-locked analysis screens (GateLock) that belong
 *    to one function. Anyone may navigate there, but only the owner acts; the
 *    resolver routes non-owners to a universal fallback instead (the F3 fix),
 *    rather than dumping them on a screen that is locked or not their work.
 */
const FINANCE_GUARDED_ROUTES = new Set(['/dscr-sensitivity', '/pricing-lineage']);

const OWNER_SURFACES: Record<string, 'FINANCE' | 'COMMERCIAL'> = {
  '/capital-stack': 'FINANCE',
  '/offtake-quality': 'COMMERCIAL',
};

type RoleLike = { business_function: string; service_type?: string | null; company_type?: string };

const isFinanceLike = (r: RoleLike) =>
  r.business_function === 'FINANCE_TREASURY' ||
  r.business_function === 'EXECUTIVE' ||
  ['BANK', 'DFI', 'INSURER'].includes(r.service_type ?? '');

const isCommercialLike = (r: RoleLike) =>
  r.business_function === 'COMMERCIAL' ||
  r.business_function === 'EXECUTIVE' ||
  r.company_type === 'OFFTAKER';

export function canEnterRoute(route: string | undefined, role: RoleLike): boolean {
  if (!route) return false;
  const path = route.split('?')[0];
  if (FINANCE_GUARDED_ROUTES.has(path)) return isFinanceLike(role);
  const owner = OWNER_SURFACES[path];
  if (owner === 'FINANCE') return isFinanceLike(role);
  if (owner === 'COMMERCIAL') return isCommercialLike(role);
  return true;
}
