// Screen: Menu/navigation config (no screen)
/**
 * GEX v6.1 — Universal Menu Architecture
 * File: src/config/menuArchitecture.ts
 *
 * Single source of truth for all navigation items.
 * Every item carries visibility rules: who sees it, based on
 * company_type + business_function + service_type.
 *
 * The TopBar reads this config and filters per UserRole context.
 */

// ── Role Types ──

export type CompanyType = 'PRODUCER' | 'OFFTAKER' | 'THIRD_PARTY';

export type ServiceType =
  | 'BANK' | 'INSURER' | 'CERTIFIER' | 'LOGISTICS'
  | 'ENGINEER' | 'EQUIPMENT' | 'LEGAL'
  | 'DFI'           // development finance institution / public investor (lender-class)
  | null;

export type BusinessFunction =
  | 'ENGINEERING' | 'FINANCE_TREASURY' | 'COMMERCIAL'
  | 'COMPLIANCE_LEGAL' | 'OPERATIONS' | 'EXECUTIVE';

// Prosumer capability — an entity can hold multiple (e.g. OFFTAKE + PRODUCE + SELL).
// FINANCE_REVIEW is a grantable permission that entitles a user to project-finance
// assessment screens (e.g. DSCR sensitivity) irrespective of their base function —
// e.g. an engineer or ops lead explicitly assigned finance-review duties.
export type TradeCapability = 'OFFTAKE' | 'PRODUCE' | 'SELL' | 'TRADE' | 'CERTIFY' | 'FINANCE' | 'INSURE' | 'FINANCE_REVIEW';

export interface UserRole {
  company_type: CompanyType;
  service_type: ServiceType;
  business_function: BusinessFunction;
  company_name: string;
  user_name: string;
  /** Prosumer capabilities — when present, used to expand visibility beyond company_type */
  capabilities?: TradeCapability[];
}

// ── Menu Item ──

export interface MenuItem {
  id: string;
  path: string;
  label: string;
  section: string;        // group header within dropdown
  visible_to: VisibilityRule[];
  /**
   * Roles for whom this screen is CONSULT-ONLY (analytics / truth they read,
   * not a verb they operate). Such roles keep full access — the screen stays
   * in `visible_to` and is reachable via the Project profile's "Analytics &
   * Truth" section — but it is NOT promoted in the global top-nav for them.
   * This separates navigation prominence from access (the two-layer model).
   * Prototype scope: Finance-Treasury producers and Banks only.
   */
  consult_for?: VisibilityRule[];
  icon?: string;          // lucide icon name
  tooltip?: string;       // from helpText.ts key
  /** Gate that must be ≥ threshold before this screen is actionable. Omit for always-accessible screens. */
  gate_prerequisite?: string;
}

export interface VisibilityRule {
  company_type: CompanyType | 'ALL';
  function?: BusinessFunction | 'ALL';
  service_type?: ServiceType | 'ALL';
  /**
   * Optional capability/permission gate. When set, the rule additionally
   * requires the user to hold this capability. Use with `company_type: 'ALL'`
   * to express "any user granted <capability>, regardless of base role" —
   * e.g. an engineer assigned FINANCE_REVIEW seeing DSCR sensitivity.
   */
  capability?: TradeCapability;
}

export interface MenuTab {
  id: string;
  label: string;
  items: MenuItem[];
}

// ── Capability → effective company_types mapping ──
// Prosumers with PRODUCE capability also see PRODUCER screens; OFFTAKE → OFFTAKER screens.

const CAPABILITY_TO_COMPANY_TYPE: Record<TradeCapability, CompanyType | null> = {
  OFFTAKE: 'OFFTAKER',
  PRODUCE: 'PRODUCER',
  SELL:     null,       // SELL doesn't map to a separate company_type
  TRADE:    null,
  CERTIFY:  'THIRD_PARTY',
  FINANCE:  'THIRD_PARTY',
  INSURE:   'THIRD_PARTY',
  FINANCE_REVIEW: null, // a permission, not a company-type expander (see matchesRule)
};

function effectiveCompanyTypes(role: UserRole): CompanyType[] {
  const types = new Set<CompanyType>([role.company_type]);
  if (role.capabilities) {
    for (const cap of role.capabilities) {
      const ct = CAPABILITY_TO_COMPANY_TYPE[cap];
      if (ct) types.add(ct);
    }
  }
  return Array.from(types);
}

// ── Visibility helper ──

function matchesRule(rules: VisibilityRule[], role: UserRole): boolean {
  const companyTypes = effectiveCompanyTypes(role);
  return rules.some(rule => {
    const ctMatch = rule.company_type === 'ALL' || companyTypes.includes(rule.company_type);
    const fnMatch = !rule.function || rule.function === 'ALL' || rule.function === role.business_function;
    const stMatch = !rule.service_type || rule.service_type === 'ALL' ||
      (role.company_type === 'THIRD_PARTY' && rule.service_type === role.service_type);
    // Capability/permission gate (e.g. FINANCE_REVIEW) — when set, the user must hold it.
    const capMatch = !rule.capability || !!role.capabilities?.includes(rule.capability);
    return ctMatch && fnMatch && stMatch && capMatch;
  });
}

/** Full ACCESS check — may the role reach this screen at all? */
export function isVisible(item: MenuItem, role: UserRole): boolean {
  return matchesRule(item.visible_to, role);
}

/** Is this screen consult-only (read, not operate) for this role? */
export function isConsultOnly(item: MenuItem, role: UserRole): boolean {
  return !!item.consult_for && matchesRule(item.consult_for, role);
}

/**
 * NAV-PROMINENCE check — should this screen appear in the global top-nav for
 * this role? Visible AND not consult-only. Access (isVisible) is unchanged;
 * this only governs menu prominence (the two-layer model).
 */
export function isVisibleInNav(item: MenuItem, role: UserRole): boolean {
  return isVisible(item, role) && !isConsultOnly(item, role);
}

/** Consult-only screens for a role — surfaced on the Project profile. */
export function consultItemsForRole(role: UserRole): MenuItem[] {
  return MENU_TABS.flatMap(t => t.items).filter(i => isVisible(i, role) && isConsultOnly(i, role));
}

// ── Shorthand visibility constructors ──

const ALL: VisibilityRule = { company_type: 'ALL', function: 'ALL' };
const PROD = (fn?: BusinessFunction): VisibilityRule => ({ company_type: 'PRODUCER', function: fn || 'ALL' });
const OFT = (fn?: BusinessFunction): VisibilityRule => ({ company_type: 'OFFTAKER', function: fn || 'ALL' });
const TP = (svc: ServiceType, fn?: BusinessFunction): VisibilityRule => ({ company_type: 'THIRD_PARTY', service_type: svc, function: fn || 'ALL' });

// ────────────────────────────────────────────
// MENU DEFINITIONS
// ────────────────────────────────────────────

// ════════════════════════════════════════════════════════════════
// MENU DOCTRINE (v6.1 — de-aliased 2026-05-30)
//   • One screen → one canonical name → one canonical menu home.
//   • Duplicate entries removed; access preserved by unioning the roles of
//     the merged entries onto the survivor (no role loses a door) and, for
//     project-scoped screens, by the contextual DetailLinkRow on the Project
//     profile (Cost Basis, Plant Telemetry).
//   • Five false doors into /reports collapsed to ONE "Reports & Evidence" hub.
//   • is_new removed entirely; business state is derived from gate access at
//     render time (BLOCKED / READY / IC READY), never hard-coded.
//   • Finance sections use lender language and render as collapsible accordions.
//
//   • Pre-COD finance metrics are first-class GEX objects. DSCR sensitivity may
//     be projected, modelled, or scenario-based before COD. It is restricted
//     because it is sensitive, not because it is irrelevant before COD.
//     Entitlement to such metrics is by role/function (finance-function users +
//     lenders/insurers), never a generic company-type rule.
// ════════════════════════════════════════════════════════════════

export const MENU_TABS: MenuTab[] = [

  // ───────────────────────────────────
  // 1. PROJECTS
  // ───────────────────────────────────
  {
    id: 'projects',
    label: 'Projects',
    items: [
      { id: 'my-projects', path: '/projects', label: 'Current Projects', section: '',
        visible_to: [ALL] },
      { id: 'project-overview', path: '/dashboard', label: 'Dashboard', section: '',
        visible_to: [ALL] },
      { id: 'task-flow', path: '/finance-dashboard', label: 'Task Flow', section: '',
        visible_to: [ALL] },
      { id: 'deal-killers', path: '/bankability-scores', label: 'Status & Blockers', section: '',
        visible_to: [ALL] },
      { id: 'adversarial-review', path: '/adversarial-review', label: 'Challenge Review', section: '',
        visible_to: [ALL] },
      // Cost Basis → canonical home is Finance; reachable contextually from the
      // Project profile (TECHNICAL → Cost Basis link).
      // Plant Telemetry → canonical home is Operations; reachable from Project
      // profile (TECHNICAL → Telemetry link).
      // Production Roadmap → canonical home is Operations (Construction Progress).
      // Evidence Upload → folded into the Reports & Evidence hub (Compliance).
    ],
  },

  // ───────────────────────────────────
  // 2. COMMERCIAL
  // ───────────────────────────────────
  {
    id: 'commercial',
    label: 'Commercial',
    items: [
      { id: 'market-discovery', path: '/marketplace', label: 'Commercial Overview', section: '',
        visible_to: [PROD('COMMERCIAL'), OFT('COMMERCIAL'), OFT('EXECUTIVE')] },
      { id: 'supply-offers', path: '/offtaker-supply', label: 'Purchase', section: '',
        visible_to: [OFT()] },
      { id: 'demand-pipeline', path: '/finance-demand', label: 'Sales', section: '',
        visible_to: [PROD('COMMERCIAL'), PROD('FINANCE_TREASURY'), TP('BANK')] },
      { id: 'offtake-quality', path: '/offtake-quality', label: 'Offtake Quality', section: '',
        visible_to: [PROD('COMMERCIAL'), PROD('FINANCE_TREASURY'), OFT('COMMERCIAL'), TP('BANK')],
        gate_prerequisite: 'G4' },

      { id: 'matching-engine', path: '/matching', label: 'Matching Engine', section: 'NEGOTIATION',
        visible_to: [PROD('COMMERCIAL'), OFT('COMMERCIAL')] },
      { id: 'rfq-management', path: '/trader-dashboard', label: 'RFQ Management', section: 'NEGOTIATION',
        visible_to: [PROD('COMMERCIAL'), OFT('COMMERCIAL'), OFT('FINANCE_TREASURY')] },
      { id: 'contracts', path: '/contracts', label: 'Contracts', section: 'NEGOTIATION',
        visible_to: [PROD('COMMERCIAL'), PROD('FINANCE_TREASURY'), OFT(), TP('BANK'), TP('LEGAL')] },
      { id: 'term-sheet', path: '/term-sheet', label: 'Term Sheet Tracker', section: 'NEGOTIATION',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('COMMERCIAL'), OFT('EXECUTIVE'), OFT('FINANCE_TREASURY'), TP('BANK'), TP('LEGAL')],
        gate_prerequisite: 'G4' },

      // Was labelled "Counterparties" but the screen is Delivery & Settlement —
      // a door must name what is behind it (Hidalgo). True counterparty/credit
      // management (static data, rating, exposure limits) does not exist yet and
      // is tracked as a CTRM gap by audit-menu.mjs, not faked with a door.
      { id: 'delivery-settlement', path: '/settlement', label: 'Delivery & Settlement', section: 'MARKET DATA',
        visible_to: [PROD('COMMERCIAL'), OFT('COMMERCIAL')] },
      // GreenMesh is the canonical home for /capacity (commercial aggregation /
      // netting). Logistics & Shipping (Operations) was the duplicate door —
      // its roles (TP LOGISTICS, OFT/PROD OPERATIONS) are unioned in here.
      { id: 'greenmesh-netting', path: '/capacity', label: 'GreenMesh (Capacity & Logistics)', section: 'MARKET DATA',
        visible_to: [PROD('COMMERCIAL'), PROD('OPERATIONS'), OFT('OPERATIONS'), TP('LOGISTICS')] },
    ],
  },

  // ───────────────────────────────────
  // 3. FINANCE  (sections render as collapsible accordions)
  // ───────────────────────────────────
  {
    id: 'finance',
    label: 'Finance',
    items: [
      // ── Credit Assessment (always-open core) ──
      { id: 'project-readiness', path: '/finance/bankability', label: 'Project Readiness', section: '',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), TP('BANK')] },
      { id: 'capital-stack', path: '/capital-stack', label: 'Capital Stack', section: '',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), TP('BANK')],
        gate_prerequisite: 'G5' },
      { id: 'covenants', path: '/covenants', label: 'Covenants', section: '',
        visible_to: [PROD('FINANCE_TREASURY'), TP('BANK')] },

      // ── Deal Structuring ──
      // CONSULT (analytics/truth) — demoted from Finance & Bank top-nav,
      // reachable via the Project profile's "Analytics & Truth" section.
      // DSCR sensitivity is a FIRST-CLASS PRE-COD bankability instrument:
      // projected / modelled / scenario-based DSCR determines whether a project
      // can reach financial close. It is restricted because it is SENSITIVE
      // (reveals debt fragility), NOT because it is irrelevant before COD.
      //
      // Entitlement is by ROLE/FUNCTION, not generic company type: any
      // finance-function user across company types, plus lenders/insurers who
      // underwrite the risk. Prosumer finance/exec are covered automatically via
      // capability expansion (effectiveCompanyTypes → PRODUCER/OFFTAKER).
      { id: 'dscr-sensitivity', path: '/dscr-sensitivity', label: 'Sensitivity Analysis', section: 'DEAL STRUCTURING',
        visible_to: [
          PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'),   // producer / prosumer finance + exec
          OFT('FINANCE_TREASURY'), OFT('EXECUTIVE'),     // offtaker / prosumer finance + exec (supplier reliability)
          TP('BANK'), TP('INSURER'), TP('DFI'),          // lenders, insurers, DFIs underwriting the risk
          // DEV-ONLY menu affordance: a global FINANCE_REVIEW capability surfaces the
          // entry in dev. The AUTHORITATIVE per-project control is the FinanceRouteGuard
          // (frontend) + require_finance_entitlement (backend 403). Project-scoped grants
          // are enforced there, not here — menu visibility ≠ data access.
          { company_type: 'ALL', capability: 'FINANCE_REVIEW' },
        ],
        consult_for: [PROD('FINANCE_TREASURY'), TP('BANK')] },
      // Gabillon decomposition = model-facing, RESTRICTED (same entitlement set as DSCR).
      // Broad commercial-facing "Price Explanation" is a separate, deferred view.
      // Frontend route is FinanceRouteGuard-wrapped; backend /decomposition is 403-protected.
      { id: 'pricing-lineage', path: '/pricing-lineage', label: 'Price Decomposition (Gabillon)', section: 'DEAL STRUCTURING',
        visible_to: [
          PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'),
          OFT('FINANCE_TREASURY'), OFT('EXECUTIVE'),
          TP('BANK'), TP('INSURER'), TP('DFI'),
          { company_type: 'ALL', capability: 'FINANCE_REVIEW' }, // dev-only menu affordance (see DSCR note)
        ],
        consult_for: [PROD('FINANCE_TREASURY'), TP('BANK')] },
      { id: 'cost-basis', path: '/finance-plant-builder', label: 'Cost Basis (CAPEX / LCOF)', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), PROD('ENGINEERING'), TP('BANK'), TP('ENGINEER'), TP('EQUIPMENT')],
        consult_for: [PROD('FINANCE_TREASURY'), TP('BANK')],  // engineers still OPERATE it → stays in their nav
        tooltip: 'Equipment-level CAPEX build-up, BoP breakdown, LCOF vs market, and certification premium stack' },
      { id: 'instrument-catalog', path: '/finance-instruments', label: 'Instrument Catalog', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), TP('BANK')], consult_for: [PROD('FINANCE_TREASURY'), TP('BANK')] },
      { id: 'instrument-compatibility', path: '/instrument-compatibility', label: 'Instrument Compatibility', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('COMMERCIAL'), OFT('FINANCE_TREASURY'), TP('BANK'), TP('INSURER')],
        consult_for: [PROD('FINANCE_TREASURY'), TP('BANK')] },
      { id: 'structuring-timeline', path: '/finance-structuring-timeline', label: 'Structuring Timeline', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), TP('BANK')], consult_for: [PROD('FINANCE_TREASURY'), TP('BANK')] },
      { id: 'spend-wave', path: '/finance/spend-wave', label: 'Spend Wave (Pre-FID)', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), TP('BANK')], consult_for: [PROD('FINANCE_TREASURY'), TP('BANK')] },
      // Move 2 — surfaces engine-computed CFADS/waterfall/DSRA with a governance
      // stamp. Honest "Debt Cashflow & Waterfall", NOT "Debt Sizing" (LLCR/PLCR
      // /S&U not yet computed — shown as explicit gaps).
      { id: 'debt-waterfall', path: '/finance/debt-waterfall', label: 'Debt Cashflow & Waterfall', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), TP('BANK'), TP('DFI')], consult_for: [PROD('FINANCE_TREASURY'), TP('BANK')] },
      { id: 'dfi-dashboard', path: '/finance/dfi-dashboard', label: 'DFI Dashboard', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), TP('BANK')], consult_for: [PROD('FINANCE_TREASURY'), TP('BANK')] },
      { id: 'info-lineage', path: '/finance/lineage', label: 'Evidence Lineage', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), TP('BANK')], consult_for: [PROD('FINANCE_TREASURY'), TP('BANK')] },

      // OPERATE — verbs the finance/bank user performs (stay in top-nav)
      { id: 'gap-analysis', path: '/finance-gaps', label: 'Gap Analysis', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), TP('BANK')],
        gate_prerequisite: 'G5' },
      { id: 'package-builder', path: '/finance-package', label: 'Development Packages', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), TP('BANK')] },
      { id: 'risk-allocation', path: '/finance-risk-matrix', label: 'Risk Allocation', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), TP('BANK'), TP('INSURER')] },
      { id: 'drawdown-timeline', path: '/finance/drawdown-timeline', label: 'Drawdown Timeline', section: 'DEAL STRUCTURING',
        visible_to: [PROD('FINANCE_TREASURY'), TP('BANK')],
        gate_prerequisite: 'G10' },

      // ── Conditions Precedent (CPs) ──
      { id: 'insurance-schedule', path: '/insurance-schedule', label: 'Insurance Schedule', section: 'CONDITIONS PRECEDENT',
        visible_to: [PROD('FINANCE_TREASURY'), TP('BANK'), TP('INSURER')],
        gate_prerequisite: 'G7' },
      { id: 'insurer-coverage-lines', path: '/insurance-coverage', label: 'Coverage Lines (CAR/EAR/DSU/BI)', section: 'CONDITIONS PRECEDENT',
        visible_to: [TP('INSURER'), PROD('FINANCE_TREASURY')],
        gate_prerequisite: 'G7' },
      { id: 'insurer-asset-register', path: '/insurance-assets', label: 'Asset & Exposure Register', section: 'CONDITIONS PRECEDENT',
        visible_to: [TP('INSURER'), PROD('FINANCE_TREASURY')] },

      // ── IC & Diligence ──
      { id: 'banker-snapshot', path: '/bankability-snapshot', label: "Banker's Snapshot", section: 'IC & DILIGENCE',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), TP('BANK')],
        gate_prerequisite: 'G8' },
      { id: 'ic-pack', path: '/ic-pack', label: 'IC Pack Builder', section: 'IC & DILIGENCE',
        visible_to: [PROD('FINANCE_TREASURY'), TP('BANK')],
        gate_prerequisite: 'G10' },
      { id: 'transfer-readiness', path: '/transfer-readiness', label: 'Transfer Readiness', section: 'IC & DILIGENCE',
        visible_to: [PROD('FINANCE_TREASURY'), TP('BANK')] },
      { id: 'data-room', path: '/data-room', label: 'Data Room', section: 'IC & DILIGENCE',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('COMPLIANCE_LEGAL'), OFT('COMMERCIAL'), TP('BANK'), TP('INSURER'), TP('LEGAL'), TP('CERTIFIER')],
        gate_prerequisite: 'G10' },

      // ── Financial Close ──
      { id: 'approval-queue', path: '/approval-queue', label: 'Approval Queue', section: 'FINANCIAL CLOSE',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), OFT('EXECUTIVE'), TP('BANK')],
        gate_prerequisite: 'G10' },
      { id: 'commitment-signing', path: '/commitment-signing', label: 'Commitment Signing', section: 'FINANCIAL CLOSE',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('COMMERCIAL'), OFT('COMMERCIAL'), OFT('FINANCE_TREASURY'), OFT('EXECUTIVE'), TP('BANK')],
        gate_prerequisite: 'G10' },
      { id: 'commitment-verifier', path: '/commitment-verifier', label: 'Commitment Verifier', section: 'FINANCIAL CLOSE',
        visible_to: [ALL] },
    ],
  },

  // ───────────────────────────────────
  // 4. COMPLIANCE
  // ───────────────────────────────────
  {
    id: 'compliance',
    label: 'Compliance',
    items: [
      // Certification Readiness — merged with the former "Certification Distance"
      // (same /cert-readiness screen); roles unioned.
      { id: 'cert-readiness', path: '/cert-readiness', label: 'Certification Readiness', section: '',
        visible_to: [PROD('COMPLIANCE_LEGAL'), PROD('ENGINEERING'), TP('CERTIFIER'), OFT('COMPLIANCE_LEGAL'), OFT('COMMERCIAL')] },
      { id: 'evidence-hierarchy', path: '/evidence-hierarchy', label: 'Evidence Hierarchy', section: '',
        visible_to: [ALL] },
      { id: 'verification-status', path: '/stage-gates', label: 'Verification Status', section: '',
        visible_to: [TP('CERTIFIER'), TP('BANK'), PROD('COMPLIANCE_LEGAL')] },
      { id: 'regulatory-registry', path: '/regulator-dashboard', label: 'Regulatory Registry', section: 'REGULATORY',
        visible_to: [PROD('COMPLIANCE_LEGAL'), { company_type: 'THIRD_PARTY', service_type: 'LEGAL' }] },
      // Reports & Evidence — single hub replacing the five /reports false doors
      // (Evidence Upload, Decision Twin, Audit Trail, ESG, Performance Matrix).
      { id: 'reports-hub', path: '/reports', label: 'Reports & Evidence', section: 'REGULATORY',
        visible_to: [ALL] },
    ],
  },

  // ───────────────────────────────────
  // 5. OPERATIONS
  // ───────────────────────────────────
  {
    id: 'operations',
    label: 'Operations',
    items: [
      // Project Timeline — merged with the former "Milestones & Drawdown"
      // (same /finance-timeline screen); ALL roles retained.
      { id: 'project-timeline', path: '/finance-timeline', label: 'Project Timeline & Milestones', section: '',
        visible_to: [ALL] },
      { id: 'construction-progress', path: '/producer-bankability', label: 'Construction Progress', section: '',
        visible_to: [PROD('ENGINEERING'), PROD('OPERATIONS'), TP('ENGINEER')] },
      { id: 'cfo-report', path: '/cfo-report', label: 'CEO Report', section: 'PORTFOLIO',
        visible_to: [PROD('FINANCE_TREASURY'), PROD('EXECUTIVE'), PROD('OPERATIONS')] },

      { id: 'ops-plant-telemetry', path: '/plant-data', label: 'Plant Telemetry', section: 'PLANT',
        visible_to: [PROD('OPERATIONS'), PROD('ENGINEERING'), TP('ENGINEER')] },
      { id: 'ot-gateways', path: '/ciso-gateways', label: 'OT Gateway Status', section: 'PLANT',
        visible_to: [PROD('OPERATIONS')] },
      // Logistics & Shipping → canonical home is Commercial (GreenMesh).
      // Performance Matrix → folded into the Reports & Evidence hub.
    ],
  },
];

// ───────────────────────────────────
// CISO ADMIN (separate, password-gated)
// ───────────────────────────────────

export const CISO_ITEMS: MenuItem[] = [
  // ── Security & Access ──
  { id: 'ciso-overview',  path: '/ciso-dashboard',      label: 'Security Overview',      section: 'SECURITY',  visible_to: [ALL] },
  { id: 'ciso-access',    path: '/ciso-access-monitor',  label: 'Access Monitor',         section: 'SECURITY',  visible_to: [ALL] },
  { id: 'ciso-identity',  path: '/ciso-identity',        label: 'Identity & Access (ABAC)',section: 'SECURITY', visible_to: [ALL] },
  { id: 'ciso-barriers',  path: '/ciso-barriers',        label: 'Information Barriers',   section: 'SECURITY',  visible_to: [ALL] },
  { id: 'ciso-residency', path: '/ciso-residency',       label: 'Data Residency',         section: 'SECURITY',  visible_to: [ALL] },
  { id: 'ciso-gateways',  path: '/ciso-gateways',        label: 'OT Gateways',            section: 'SECURITY',  visible_to: [ALL] },
  { id: 'ciso-comms',     path: '/ciso-communications',  label: 'Communications Monitor', section: 'SECURITY',  visible_to: [ALL] },
  { id: 'ciso-gantt',     path: '/ciso-gantt-config',    label: 'Gantt Visibility',       section: 'SECURITY',  visible_to: [ALL] },
  { id: 'ciso-policy',    path: '/ciso-policy',          label: 'Policy Matrix',          section: 'SECURITY',  visible_to: [ALL] },
  { id: 'ciso-compliance',path: '/ciso-compliance',      label: 'Compliance (ISO 27001)', section: 'SECURITY',  visible_to: [ALL] },
  // Event Bus Monitor merged into Security Overview (same /ciso-dashboard screen).
  // ── Webmaster / Orchestrator ──
  { id: 'pricing-admin',  path: '/ciso-pricing',         label: 'Pricing Curves (Gabillon)', section: 'WEBMASTER', visible_to: [ALL] },
  { id: 'pricing-curves-view', path: '/pricing-curves',  label: 'Forward Curves (Project view)', section: 'WEBMASTER', visible_to: [ALL] },
];

// ── Count helper (for dev) ──

export function countVisibleItems(role: UserRole): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const tab of MENU_TABS) {
    counts[tab.id] = tab.items.filter(item => isVisible(item, role)).length;
  }
  return counts;
}
