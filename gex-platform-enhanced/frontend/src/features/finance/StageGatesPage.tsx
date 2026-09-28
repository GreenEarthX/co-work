// Screen: Stage gates screen (/stage-gates, /finance/stage-gates)
import { type ChangeEvent, useState, useEffect, useCallback } from "react";
import {
  RefreshCw,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Upload,
  XCircle,
  Eye,
  Lock,
  Unlock,
  FileText,
  ExternalLink,
  MinusCircle,
  FileSignature,
} from "lucide-react";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { HELP, TAB_DESCRIPTIONS } from "@/config/helpText";
import { bankabilityAPI } from "@/lib/api";
import { useSelectedProject } from "@/contexts/ProjectContext";
import { useUserRole } from "@/contexts/UserRoleContext";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";

// ═══════════════════════════════════════════════════════════════
// TYPES (match engine output models)
// ═══════════════════════════════════════════════════════════════

interface EvidenceItem {
  key: string;
  status:
    | "NOT_STARTED"
    | "IN_PROGRESS"
    | "SUBMITTED"
    | "UNDER_REVIEW"
    | "VERIFIED"
    | "REJECTED"
    | "EXPIRED"
    | "NOT_APPLICABLE";
  submitted_by?: string;
  verified_by?: string;
  submitted_at?: string;
  verified_at?: string;
  document_hash?: string;
  document_url?: string;
  document_ref?: string;
  document_name?: string;
  notes?: string;
  label?: string;
  // Evidence rules 3.0.0 — maturity is a separate axis from verification.
  // A VERIFIED item counts only when its declared maturity meets the
  // requirement; undeclared maturity fails closed.
  required_maturity?: Maturity | null;
  declared_maturity?: Maturity | null;
  maturity_status?: "NOT_REQUIRED" | "MET" | "BELOW_REQUIRED" | "NOT_DECLARED";
  // Assignment (migration 055) — the named person who must produce the item.
  // Added by the platform, not the engine; absent means nobody is assigned.
  assignee_user_id?: string | null;
  assignee_name?: string | null;
  assignee_function?: string | null;
  due_date?: string | null;
  request_note?: string | null;
  // Commitment (migration 057): assignment creates a request, the assignee
  // accepts it by committing to a date. Derived server-side at read time.
  committed_at?: string | null;
  // NOT_REQUIRED: a request exists but the item does not apply to the project.
  commitment?: "UNASSIGNED" | "NOT_COMMITTED" | "COMMITTED" | "OVERDUE" | "DONE" | "NOT_REQUIRED";
  days_overdue?: number;
  can_commit?: boolean; // the caller is the assignee
  can_assign?: boolean; // the caller's company owns the project (or GEX admin)
  can_withdraw?: boolean; // owner may take back a request on a not-applicable item
  // Evidence rules 4.0.0. Financing scope is per item: PROJECT_FINANCE items
  // protect lenders and are not asked of a balance-sheet project. Lenses say
  // which parties rely on the item — views, never separate scores.
  applicable?: boolean;
  scope?: "ALL" | "PROJECT_FINANCE";
  lenses?: Lens[];
  not_applicable_reason?: "POWER_MODEL" | "FINANCING_MODEL" | null;
}

type Lens = "PRODUCER" | "OFFTAKER" | "CAPITAL" | "CERTIFIER";

// Offtake O0–O7 / EPC E0–E6, derived by the engine from evidence maturity and
// the commitment cards. `reasons` say why the level is not higher.
interface CommitmentLevel {
  level: string;
  reasons: string[];
  effective?: boolean;
  form?: string | null;
  contracting_model?: string | null;
}

interface CommitmentCheck {
  kind: "offtake" | "epc";
  required: string;
  actual: string;
  met: boolean;
  reasons: string[];
}

// PASS / FAIL decide (a FAIL blocks the gate). NOT_EVALUABLE means a card
// lacks the data — shown so the gap is visible, never counted as coherent.
interface CoherenceCheck {
  id: string;
  gate: string;
  title: string;
  lenses: Lens[];
  status: "PASS" | "FAIL" | "NOT_EVALUABLE" | "NOT_APPLICABLE";
  detail: string;
  documents: string[];
  missing: string[];
}

interface RegressionTrigger {
  id: string;
  title: string;
  card: string;
  field: string;
  gates: string[];
  detail: string;
}

interface CommitmentShortfall {
  kind: string;
  gate: string;
  required: string;
  actual: string;
  message: string;
}

interface LensReadout {
  applicable: number;
  verified: number;
  blocking: string[];
}

// The subset of GET /bankability/rules this screen reads. Definitions come
// from the engine so the wording cannot drift from the rules that score.
interface EngineRules {
  rules_version?: string;
  lens_definitions?: Record<string, string>;
  offtake_level_definitions?: Record<string, string>;
  epc_level_definitions?: Record<string, string>;
}

type CardType = "offtake" | "epc" | "schedule" | "supply" | "model";

interface TermsResponse {
  project_id: string;
  cards: Partial<Record<CardType, { terms: Record<string, unknown>; updated_by?: string; updated_at?: string }>>;
  can_edit: boolean;
  card_fields: Record<CardType, Record<string, string>>;
  card_gates: Record<CardType, string>;
}

type Maturity = "INTENT" | "INDICATIVE" | "AGREED" | "EXECUTED" | "EFFECTIVE";

const MATURITY_LEVELS: Maturity[] = ["INTENT", "INDICATIVE", "AGREED", "EXECUTED", "EFFECTIVE"];

// Mirrors MATURITY_DEFINITIONS in the engine, worded for the person choosing.
const MATURITY_HELP: Record<Maturity, string> = {
  INTENT: "Plan, mandate, letter of intent, MOU, or application in preparation",
  INDICATIVE: "Term sheet, quotation, or application submitted",
  AGREED: "Agreed form — all terms settled, not yet signed or granted",
  EXECUTED: "Signed, bound, granted, issued or passed",
  EFFECTIVE: "In force — conditions satisfied, policy incepted, appeal period expired",
};

type GateDetermination = "SATISFIED" | "BLOCKED" | "INCOMPLETE" | "WAIVED";

interface GateEvaluation {
  gate_id: string;
  gate_name: string;
  owners: string[];
  total_evidence: number;
  verified_count: number;
  completion_pct: number;
  is_complete: boolean;
  evidence_detail: EvidenceItem[];
  unlocks_capital: string[];
  unlocks_state?: string;
  blocking_items: string[];
  determination?: GateDetermination;
  maturity_shortfalls?: { key: string; required_maturity: Maturity; declared_maturity: Maturity | null }[];
  overdue_count?: number;
  uncommitted_count?: number;
  // Rules 4.0.0: a gate needs its items AND its commitment level AND no failed
  // coherence check or active trigger. `items_complete` is the items alone.
  items_complete?: boolean;
  commitment_checks?: CommitmentCheck[];
  coherence_checks?: CoherenceCheck[];
  triggers?: RegressionTrigger[];
  blocked_reasons?: string[];
  lens_readouts?: Partial<Record<Lens, LensReadout>>;
  waived_by_financing?: boolean;
}

interface CapitalUnlock {
  capital_type: string;
  // Eligibility for the capital provider's decision — GEX does not commit,
  // release or draw capital. `is_unlocked` is the engine's deprecated alias.
  decision_eligible?: boolean;
  is_unlocked: boolean;
  gating_gates: string[];
  best_progress_pct: number;
}

interface Snapshot {
  project_id: string;
  evaluated_at: string;
  current_state: string;
  previous_state?: string;
  regression?: {
    from_state: string;
    to_state: string;
    trigger_gate: string;
    reason: string;
  };
  gate_evaluations: GateEvaluation[];
  capital_unlocks: CapitalUnlock[];
  total_evidence: number;
  total_verified: number;
  overall_completion_pct: number;
  next_state?: string;
  gates_blocking_next_state: string[];
  // Rules 4.0.0 — the commitment each state makes possible, the two ladders,
  // and what the next state needs on them beyond gate evidence.
  rules_version?: string;
  financing_model?: string | null;
  state_label?: string | null;
  next_state_label?: string | null;
  commitments_blocking_next_state?: CommitmentShortfall[];
  offtake?: CommitmentLevel;
  epc?: CommitmentLevel;
  coherence_checks?: CoherenceCheck[];
  regression_triggers?: RegressionTrigger[];
}

interface EvidenceUpdateMeta {
  submittedBy?: string;
  notes?: string;
  maturity?: Maturity;
}

interface UploadedReviewDocument {
  name: string;
  size: number;
  uploadedAt: string;
  url?: string;
}

interface SubmissionDraft {
  submitTo: string;
  destination: string;
  leadsTo: string;
  documentName: string;
  documentSize: number;
  documentUrl: string;
  notes: string;
  // What the submitted instrument actually is. Required when the item has a
  // maturity requirement; the reviewer can confirm or lower it, never raise it.
  maturity: Maturity | "";
}

// ═══════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════

const STATUS_CONFIG: Record<
  string,
  { color: string; border: string; icon: any; label: string }
> = {
  NOT_STARTED: {
    color: "text-slate-500",
    border: "border-slate-300",
    icon: Clock,
    label: "Not Started",
  },
  IN_PROGRESS: {
    color: "text-slate-700",
    border: "border-slate-300",
    icon: Clock,
    label: "In Progress",
  },
  SUBMITTED: {
    color: "text-amber-600",
    border: "border-amber-300",
    icon: Upload,
    label: "Submitted",
  },
  UNDER_REVIEW: {
    color: "text-amber-600",
    border: "border-amber-300",
    icon: Eye,
    label: "Under Review",
  },
  VERIFIED: {
    color: "text-green-600",
    border: "border-green-300",
    icon: CheckCircle2,
    label: "Verified",
  },
  REJECTED: {
    color: "text-red-600",
    border: "border-red-300",
    icon: XCircle,
    label: "Rejected",
  },
  EXPIRED: {
    color: "text-red-600",
    border: "border-red-300",
    icon: AlertTriangle,
    label: "Expired",
  },
  // Until 4.0.0 this was missing, so a not-applicable item fell back to
  // NOT_STARTED and was offered a "Start" button for evidence nobody needs.
  NOT_APPLICABLE: {
    color: "text-slate-400",
    border: "border-slate-200",
    icon: MinusCircle,
    label: "Not required",
  },
};

const NOT_APPLICABLE_REASON: Record<string, string> = {
  FINANCING_MODEL: "Not required — balance-sheet funding (lender protection)",
  POWER_MODEL: "Not required for this project's power model",
};

const LENSES: Lens[] = ["PRODUCER", "OFFTAKER", "CAPITAL", "CERTIFIER"];

const LENS_LABELS: Record<Lens, string> = {
  PRODUCER: "Producer",
  OFFTAKER: "Offtaker",
  CAPITAL: "Capital",
  CERTIFIER: "Certifier",
};

const COHERENCE_STATUS: Record<CoherenceCheck["status"], { label: string; cls: string }> = {
  PASS: { label: "Pass", cls: "border-green-300 bg-green-50 text-green-700" },
  FAIL: { label: "Fail", cls: "border-red-300 bg-red-50 text-red-700" },
  NOT_EVALUABLE: { label: "Data missing", cls: "border-amber-300 bg-amber-50 text-amber-700" },
  NOT_APPLICABLE: { label: "N/A", cls: "border-slate-200 bg-slate-50 text-slate-500" },
};

const STATE_LABELS: Record<string, string> = {
  SPECULATIVE: "Speculative",
  TECHNICALLY_PLAUSIBLE: "Technically Plausible",
  COMMERCIALLY_PLAUSIBLE: "Commercially Plausible",
  BUILDABLE: "Buildable",
  STRUCTURALLY_BANKABLE: "Structurally Bankable",
  CREDIT_APPROVED: "Credit Approved",
  FINANCEABLE: "Financeable",
  OPERATIONAL: "Operational",
  REFINANCING_ELIGIBLE: "Refinancing Eligible",
};

const STATE_ORDER = Object.keys(STATE_LABELS);

const CAPITAL_LABELS: Record<string, string> = {
  GRANTS_TA: "Grants & TA",
  SEED_VC_ANGEL: "Seed / VC / Angel",
  STRATEGIC_EQUITY: "Strategic Equity",
  PROJECT_EQUITY: "Project Equity",
  DFI_MEZZ_GUARANTEES: "DFI / Mezz / Guarantees",
  SENIOR_DEBT_COMMITMENT: "Senior Debt Commitment",
  DEBT_DRAWDOWN: "Debt Drawdown",
  REFINANCE_BONDS_INFRA: "Refinance / Bonds / Infra",
};

const RELATED_VIEWS = [
  { label: "Bankability", href: "/finance/bankability" },
  { label: "Certainty", href: "/finance/bankability-scores" },
  { label: "Evidence", href: "/finance/evidence-hierarchy" },
  { label: "Spend wave", href: "/finance/spend-wave" },
  { label: "Drawdown", href: "/finance/drawdown-timeline" },
  { label: "Lineage", href: "/finance/lineage" },
];

function formatEvidenceKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function relatedReviewPath(evidenceKey: string): string {
  const normalized = evidenceKey.toLowerCase();
  if (normalized.includes("term_sheet") || normalized.includes("offtake")) {
    return "/term-sheet";
  }
  if (normalized.includes("insurance")) {
    return "/insurance";
  }
  if (normalized.includes("model") || normalized.includes("dscr")) {
    return "/finance-model";
  }
  if (normalized.includes("permit") || normalized.includes("certification")) {
    return "/evidence-hierarchy";
  }
  return "/data-room";
}

function documentLabel(evidence: EvidenceItem): string {
  return (
    evidence.document_name ||
    evidence.document_ref ||
    `${formatEvidenceKey(evidence.key)} Review Pack`
  );
}

function documentNameFromNotes(notes?: string): string | null {
  if (!notes) return null;
  const match = notes.match(/Document:\s*([^|]+)/i);
  return match ? match[1].trim() : null;
}

function hasFullDocument(
  evidence: EvidenceItem,
  uploadedDocuments: Record<string, UploadedReviewDocument>,
): boolean {
  return Boolean(
    evidence.document_url ||
      evidence.document_hash ||
      evidence.document_ref ||
      evidence.document_name ||
      uploadedDocuments[evidence.key] ||
      documentNameFromNotes(evidence.notes),
  );
}

function currentDocumentName(
  evidence: EvidenceItem,
  uploadedDocuments: Record<string, UploadedReviewDocument>,
): string | null {
  return (
    evidence.document_name ||
    evidence.document_ref ||
    uploadedDocuments[evidence.key]?.name ||
    documentNameFromNotes(evidence.notes) ||
    evidence.document_hash ||
    null
  );
}

function fileSizeLabel(size: number): string {
  if (!size) return "";
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatEvidenceTimestamp(evidence: EvidenceItem): string {
  const timestamp = evidence.verified_at || evidence.submitted_at;
  if (!timestamp) return "Not recorded";
  try {
    return new Date(timestamp).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return timestamp;
  }
}

const REVIEW_DESTINATIONS = [
  "Stage Gate Review Queue",
  "Evidence Data Room",
  "Independent Engineer Review",
  "Finance / Lender Diligence Queue",
  "Compliance Evidence Review",
];

const REVIEW_OUTCOMES = [
  "Submitted evidence package",
  "Under-review verification decision",
  "Gate blocker resolution request",
  "Capital-readiness evidence update",
];

function gateShortId(gateId: string): string {
  return gateId.split("_")[0];
}

function isGateBlockingNextState(
  gate: GateEvaluation,
  blockers: string[],
): boolean {
  const shortId = gateShortId(gate.gate_id);
  return blockers.some((blocker) => {
    const blockerShortId = gateShortId(blocker);
    return blocker === gate.gate_id || blockerShortId === shortId;
  });
}

function capitalImpactsForGate(
  gate: GateEvaluation,
  unlocks: CapitalUnlock[],
): CapitalUnlock[] {
  const shortId = gateShortId(gate.gate_id);
  const directCapital = new Set(gate.unlocks_capital);

  return unlocks.filter((unlock) => {
    if (directCapital.has(unlock.capital_type)) return true;
    return unlock.gating_gates.some((gateId) => {
      return gateId === gate.gate_id || gateShortId(gateId) === shortId;
    });
  });
}

function gateQueueRank(
  gate: GateEvaluation,
  blockers: string[],
  capitalImpacts: CapitalUnlock[],
): number {
  if (isGateBlockingNextState(gate, blockers)) return 0;
  if (gate.evidence_detail.some((item) => item.status === "UNDER_REVIEW")) {
    return 1;
  }
  if (gate.evidence_detail.some((item) => item.status === "SUBMITTED")) {
    return 2;
  }
  if (gate.evidence_detail.some((item) => item.status === "IN_PROGRESS")) {
    return 3;
  }
  if (capitalImpacts.some((impact) => !impact.is_unlocked)) return 4;
  if (gate.is_complete) return 6;
  return 5;
}

function gateQueueLabel(
  gate: GateEvaluation,
  blockers: string[],
  capitalImpacts: CapitalUnlock[],
): string {
  if (isGateBlockingNextState(gate, blockers)) return "Blocking";
  if (gate.evidence_detail.some((item) => item.status === "UNDER_REVIEW")) {
    return "Review";
  }
  if (gate.evidence_detail.some((item) => item.status === "SUBMITTED")) {
    return "Submitted";
  }
  if (gate.evidence_detail.some((item) => item.status === "IN_PROGRESS")) {
    return "In progress";
  }
  if (capitalImpacts.some((impact) => !impact.is_unlocked)) return "Capital";
  if (gate.is_complete) return "Complete";
  return "Watch";
}

function gateQueueLabelClass(label: string): string {
  switch (label) {
    case "Blocking":
      return "border-red-300 text-red-700 bg-white";
    case "Review":
    case "Submitted":
    case "In progress":
      return "border-amber-300 text-amber-700 bg-white";
    case "Complete":
      return "border-slate-300 text-slate-700 bg-slate-50";
    default:
      return "border-slate-300 text-slate-700 bg-white";
  }
}

function gateCertaintyDimension(gate: GateEvaluation): string | null {
  const text = `${gate.gate_name} ${gate.gate_id}`.toLowerCase();
  if (/permit|environ|regulat|certif|compliance|esg|sustain|45v|rfnbo|licens|social/.test(text)) return "CERTIFICATION";
  if (/offtake|ppa|revenue|price|market|commercial|buyer|demand/.test(text)) return "REVENUE";
  if (/epc|construct|technolog|engineer|plant|commission|build/.test(text)) return "EXECUTION";
  if (/cost|capex|opex|budget|financial.?model|debt|equity|capital|wacc|dscr/.test(text)) return "COST";
  if (/insurance|guarantee|credit|counterpart|lender|bank|sovereign/.test(text)) return "COUNTERPARTY";
  return null;
}

// ═══════════════════════════════════════════════════════════════
// COMPONENTS
// ═══════════════════════════════════════════════════════════════

function StateProgressionBar({
  currentState,
  nextState,
}: {
  currentState: string;
  nextState?: string;
}) {
  const currentIdx = STATE_ORDER.indexOf(currentState);
  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-2">
      {STATE_ORDER.map((state, idx) => {
        const isActive = idx === currentIdx;
        const isPast = idx < currentIdx;
        const isNext = state === nextState;
        return (
          <div key={state} className="flex items-center gap-1 flex-shrink-0">
            <div
              className={`px-2 py-1 rounded text-xs font-semibold whitespace-nowrap border transition-all ${
                isActive
                  ? "bg-green-600 text-white border-green-700 shadow-md"
                  : isPast
                    ? "bg-green-100 text-green-700 border-green-200"
                    : isNext
                      ? "bg-amber-50 text-amber-700 border-amber-300 border-dashed"
                      : "bg-gray-50 text-gray-400 border-gray-200"
              }`}
            >
              {STATE_LABELS[state] || state}
            </div>
            {idx < STATE_ORDER.length - 1 && (
              <div
                className={`w-3 h-0.5 flex-shrink-0 ${isPast ? "bg-green-400" : "bg-gray-200"}`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function ProjectContextBanner({
  projectId,
  project,
}: {
  projectId: string;
  project?: {
    name: string;
    location: string;
    molecule: string;
    status?: string;
    phase?: string;
  };
}) {
  return (
    <div className="rounded-lg border border-slate-300 bg-white px-5 py-4 shadow-sm">
      <div className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">
        Project in Scope
      </div>
      <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black text-slate-950">
            {project?.name ?? projectId}
          </h1>
          <p className="mt-1 text-sm font-medium text-slate-600">
            Stage Gates Review
            {project?.location ? ` · ${project.location}` : ""}
            {project?.molecule ? ` · ${project.molecule}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {project?.status && (
            <span className="rounded border border-slate-300 bg-slate-50 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-slate-700">
              {project.status}
            </span>
          )}
          {project?.phase && (
            <span className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700">
              {project.phase}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function NextGoalPost({
  snapshot,
  gateQueue,
}: {
  snapshot: Snapshot;
  gateQueue: Array<{
    gate: GateEvaluation;
    capitalImpacts: CapitalUnlock[];
    isBlockingNextState: boolean;
  }>;
}) {
  const nextState = snapshot.next_state;
  if (!nextState) return null;

  const blockingEntries = gateQueue.filter((g) => g.isBlockingNextState);
  // blocking_items is the engine's own list: applicable items that do not yet
  // count (unverified, or verified below the required maturity). Counting
  // "status !== VERIFIED" also counted not-applicable items and missed
  // maturity shortfalls.
  const totalRemaining = blockingEntries.reduce(
    (sum, { gate }) => sum + gate.blocking_items.length,
    0,
  );
  // Rules 4.0.0: a state can also wait on the offtake / EPC ladders even when
  // every gate it requires is clear.
  const shortfalls = snapshot.commitments_blocking_next_state || [];

  const unlockableCapital = new Set<string>();
  blockingEntries.forEach(({ capitalImpacts }) =>
    capitalImpacts
      .filter((c) => !c.is_unlocked)
      .forEach((c) => unlockableCapital.add(c.capital_type)),
  );

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
        <div className="flex items-baseline gap-2">
          <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
            Next
          </span>
          <span className="text-sm font-black text-slate-950">
            {STATE_LABELS[nextState] || nextState}
          </span>
        </div>
        <span className="font-mono text-xs text-slate-500">
          {blockingEntries.length === 0
            ? shortfalls.length === 0
              ? "all gates clear"
              : `gates clear · ${shortfalls.length} commitment shortfall${shortfalls.length === 1 ? "" : "s"}`
            : `${blockingEntries.length} blocking · ${totalRemaining} items` +
              (shortfalls.length ? ` · ${shortfalls.length} commitment` : "")}
        </span>
      </div>
      {snapshot.next_state_label && (
        <div className="border-b border-slate-100 px-4 py-1.5 text-xs text-slate-600">
          {snapshot.next_state_label}
        </div>
      )}

      {shortfalls.length > 0 && (
        <div className="divide-y divide-slate-50 border-b border-slate-100">
          {shortfalls.map((s) => (
            <div key={s.kind} className="flex items-center gap-3 px-4 py-2 text-xs">
              <span className="w-7 flex-shrink-0 font-mono text-slate-400">{gateShortId(s.gate)}</span>
              <span className="min-w-0 flex-1 text-red-700">{s.message}</span>
            </div>
          ))}
        </div>
      )}

      {blockingEntries.length > 0 && (
        <div className="divide-y divide-slate-50">
          {blockingEntries.map(({ gate }) => {
            const remaining = gate.blocking_items.length;
            const pct = Math.round(gate.completion_pct);
            const dim = gateCertaintyDimension(gate);
            return (
              <div
                key={gate.gate_id}
                className="flex items-center gap-3 px-4 py-2 text-xs"
              >
                <span className="w-7 flex-shrink-0 font-mono text-slate-400">
                  {gate.gate_id.split("_")[0]}
                </span>
                <span className="min-w-0 flex-1 truncate font-medium text-slate-900">
                  {gate.gate_name}
                </span>
                <div className="w-16 flex-shrink-0 h-1 rounded-full bg-slate-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-slate-700"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="w-8 flex-shrink-0 text-right font-mono text-slate-600">
                  {pct}%
                </span>
                <span className="w-20 flex-shrink-0 text-slate-500">
                  {remaining} remaining
                </span>
                {dim && (
                  <span className="flex-shrink-0 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                    {dim}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-4 py-2">
        {unlockableCapital.size > 0 && (
          <span className="text-xs text-slate-600">
            <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
              Unlocks
            </span>{" "}
            {Array.from(unlockableCapital)
              .map((c) => CAPITAL_LABELS[c] || c)
              .join(" · ")}
          </span>
        )}
        <div className="flex items-center gap-3 text-xs ml-auto">
          {RELATED_VIEWS.map((view) => (
            <a
              key={view.href}
              href={view.href}
              className="font-medium text-slate-400 hover:text-slate-900"
            >
              {view.label}
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Owner cell: who owns the request, have they committed, is it late ──────

type AssignableAccount = { user_id: string; name: string; business_function: string };
const assignableCache: Record<string, Promise<AssignableAccount[]>> = {};

function todayIso(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function apiErrorMessage(err: any): string {
  const detail = err?.detail ?? err?.response?.detail;
  if (detail && typeof detail === "object" && detail.message) return detail.message;
  return err?.message || "The change was not saved.";
}

// A not-applicable item needs no owner. If a request was raised for it anyway
// (the 2026-09-26 conversion raised six), show who was asked and let the
// project owner withdraw it; the row stays as the record.
function NotRequiredOwnerCell({
  ev,
  projectId,
  onChanged,
}: {
  ev: EvidenceItem;
  projectId: string;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!ev.assignee_user_id) return <div className="text-slate-400">—</div>;
  const withdraw = async () => {
    setBusy(true);
    setError(null);
    try {
      await bankabilityAPI.assignEvidence({ project_id: projectId, evidence_key: ev.key, assignee_user_id: null });
      onChanged();
    } catch (err: any) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="min-w-0 text-[11px] text-slate-500">
      <div className="truncate" title="A request was raised for an item this project does not need.">
        Asked: {ev.assignee_name || ev.assignee_user_id}
      </div>
      {ev.can_withdraw && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            withdraw();
          }}
          disabled={busy}
          className="mt-0.5 rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {busy ? "Withdrawing…" : "Withdraw request"}
        </button>
      )}
      {error && <div className="text-red-700">{error}</div>}
    </div>
  );
}

function OwnerCell({
  ev,
  fallbackOwners,
  projectId,
  onChanged,
}: {
  ev: EvidenceItem;
  fallbackOwners: string[];
  projectId: string;
  onChanged: () => void;
}) {
  const [mode, setMode] = useState<"view" | "commit" | "assign">("view");
  const [date, setDate] = useState(ev.due_date || "");
  const [accounts, setAccounts] = useState<AssignableAccount[] | null>(null);
  const [assignee, setAssignee] = useState(ev.assignee_user_id || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openAssign = async () => {
    setMode("assign");
    setError(null);
    try {
      assignableCache[projectId] ??= bankabilityAPI
        .assignableAccounts(projectId)
        .then((r: any) => r.accounts as AssignableAccount[]);
      setAccounts(await assignableCache[projectId]);
    } catch (err) {
      delete assignableCache[projectId];
      setError(apiErrorMessage(err));
    }
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      if (mode === "commit") {
        await bankabilityAPI.commitEvidence({ project_id: projectId, evidence_key: ev.key, due_date: date });
      } else {
        await bankabilityAPI.assignEvidence({
          project_id: projectId,
          evidence_key: ev.key,
          assignee_user_id: assignee || null,
        });
      }
      setMode("view");
      onChanged();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const state = ev.commitment;
  const statusLine =
    state === "OVERDUE" ? (
      <span className="font-semibold text-red-700">
        Overdue {ev.days_overdue} day{ev.days_overdue === 1 ? "" : "s"} · due {ev.due_date}
      </span>
    ) : state === "NOT_COMMITTED" ? (
      <span className="font-medium text-amber-700">Not yet committed</span>
    ) : state === "COMMITTED" ? (
      <span className="text-slate-500">Due {ev.due_date}</span>
    ) : state === "DONE" ? (
      <span className="text-emerald-700">Done</span>
    ) : (
      <span className="text-slate-500">{fallbackOwners.map((o) => o.replace(/_/g, " ")).join(", ")}</span>
    );

  return (
    <div className="min-w-0 text-slate-600" title={ev.request_note || undefined}>
      <div className={`truncate font-medium ${ev.assignee_user_id ? "text-slate-800" : "text-amber-700"}`}>
        {ev.assignee_user_id ? ev.assignee_name || ev.assignee_user_id : "Unassigned"}
      </div>
      <div className="truncate text-[11px]">{statusLine}</div>

      {mode === "view" && (ev.can_commit || ev.can_assign) && (
        <div className="mt-0.5 flex gap-2 text-[11px]">
          {ev.can_commit && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setMode("commit"); setError(null); }}
              className="font-medium text-blue-700 hover:underline"
            >
              {ev.committed_at ? "Move date" : "Commit to a date"}
            </button>
          )}
          {ev.can_assign && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); openAssign(); }}
              className="font-medium text-slate-600 hover:underline"
            >
              {ev.assignee_user_id ? "Reassign" : "Assign"}
            </button>
          )}
        </div>
      )}

      {mode !== "view" && (
        <div className="mt-1 space-y-1" onClick={(e) => e.stopPropagation()}>
          {mode === "commit" ? (
            <input
              id={`commit-date-${ev.key}`}
              type="date"
              min={todayIso()}
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full rounded border border-slate-300 px-1 py-0.5 text-[11px]"
              aria-label="Date you commit to"
            />
          ) : (
            <select
              id={`assignee-${ev.key}`}
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              className="w-full rounded border border-slate-300 px-1 py-0.5 text-[11px]"
              aria-label="Assign to"
              disabled={accounts === null}
            >
              <option value="">{accounts === null ? "Loading…" : "Unassigned"}</option>
              {(accounts || []).map((a) => (
                <option key={a.user_id} value={a.user_id}>
                  {a.name} · {(a.business_function || "").replace(/_/g, " ")}
                </option>
              ))}
            </select>
          )}
          {mode === "assign" && ev.committed_at && (
            <div className="text-[10px] text-slate-500">Reassigning clears the current date.</div>
          )}
          <div className="flex gap-2 text-[11px]">
            <button
              type="button"
              disabled={busy || (mode === "commit" && !date) || (mode === "assign" && accounts === null)}
              onClick={save}
              className="rounded bg-slate-900 px-2 py-0.5 font-medium text-white disabled:opacity-40"
            >
              {mode === "commit" ? "Commit" : "Save"}
            </button>
            <button type="button" onClick={() => setMode("view")} className="text-slate-500 hover:underline">
              Cancel
            </button>
          </div>
          {error && <div className="text-[10px] text-red-700">{error}</div>}
        </div>
      )}
    </div>
  );
}

function GateCard({
  gate,
  capitalImpacts,
  priorityLabel,
  isBlockingNextState,
  onUpdateEvidence,
  projectId,
  onRefresh,
  lens,
}: {
  projectId: string;
  onRefresh: () => void;
  lens: Lens | null;
  gate: GateEvaluation;
  capitalImpacts: CapitalUnlock[];
  priorityLabel: string;
  isBlockingNextState: boolean;
  onUpdateEvidence: (
    key: string,
    status: string,
    meta?: EvidenceUpdateMeta,
  ) => void;
}) {
  const { role } = useUserRole();
  const [expanded, setExpanded] = useState(false);
  const [submitEvidence, setSubmitEvidence] = useState<EvidenceItem | null>(
    null,
  );
  const [reviewEvidence, setReviewEvidence] = useState<EvidenceItem | null>(
    null,
  );
  const [uploadedDocuments, setUploadedDocuments] = useState<
    Record<string, UploadedReviewDocument>
  >({});
  const [submissionDraft, setSubmissionDraft] = useState<SubmissionDraft>({
    submitTo: gate.owners[0]?.replace(/_/g, " ") || "Gate owner",
    destination: REVIEW_DESTINATIONS[0],
    leadsTo: REVIEW_OUTCOMES[0],
    documentName: "",
    documentSize: 0,
    documentUrl: "",
    notes: "",
    maturity: "",
  });
  const completePct = Math.round(gate.completion_pct);
  // A lens filters what is shown; it never changes the gate's determination.
  const lensReadout = lens ? gate.lens_readouts?.[lens] : undefined;
  const visibleEvidence = lens
    ? gate.evidence_detail.filter((ev) => ev.lenses?.includes(lens))
    : gate.evidence_detail;
  const visibleCoherence = (gate.coherence_checks || []).filter(
    (c) => !lens || c.lenses.includes(lens),
  );
  const blockedReasons = gate.blocked_reasons || [];
  const hasCommitmentSection =
    (gate.commitment_checks?.length ?? 0) > 0 ||
    visibleCoherence.length > 0 ||
    (gate.triggers?.length ?? 0) > 0;

  const openSubmitWorkflow = (evidence: EvidenceItem) => {
    setSubmissionDraft({
      submitTo: gate.owners[0]?.replace(/_/g, " ") || "Gate owner",
      destination: REVIEW_DESTINATIONS[0],
      leadsTo: REVIEW_OUTCOMES[0],
      documentName: "",
      documentSize: 0,
      documentUrl: "",
      notes: "",
      // Pre-fill with what was previously declared, so a resubmission keeps it.
      maturity: evidence.declared_maturity ?? "",
    });
    setSubmitEvidence(evidence);
  };

  const handleSubmissionFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const documentUrl = URL.createObjectURL(file);
    setSubmissionDraft((draft) => ({
      ...draft,
      documentName: file.name,
      documentSize: file.size,
      documentUrl,
    }));
  };

  const submitEvidenceForReview = () => {
    if (!submitEvidence || !submissionDraft.documentName) return;
    if (submitEvidence.required_maturity && !submissionDraft.maturity) return;

    const uploadedAt = new Date().toISOString();
    setUploadedDocuments((current) => ({
      ...current,
      [submitEvidence.key]: {
        name: submissionDraft.documentName,
        size: submissionDraft.documentSize,
        uploadedAt,
        url: submissionDraft.documentUrl,
      },
    }));
    onUpdateEvidence(submitEvidence.key, "SUBMITTED", {
      submittedBy: role.user_name,
      maturity: submissionDraft.maturity || undefined,
      notes: [
        `Submit to: ${submissionDraft.submitTo}`,
        `Where: ${submissionDraft.destination}`,
        `Leads to: ${submissionDraft.leadsTo}`,
        `Document: ${submissionDraft.documentName}`,
        submissionDraft.notes ? `Notes: ${submissionDraft.notes}` : "",
      ]
        .filter(Boolean)
        .join(" | "),
    });
    setSubmitEvidence(null);
  };

  const handleReviewFile = (
    event: ChangeEvent<HTMLInputElement>,
    evidence: EvidenceItem,
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const uploadedAt = new Date().toISOString();
    const documentUrl = URL.createObjectURL(file);
    setUploadedDocuments((current) => ({
      ...current,
      [evidence.key]: {
        name: file.name,
        size: file.size,
        uploadedAt,
        url: documentUrl,
      },
    }));
    const existingNotes = evidence.notes ? `${evidence.notes} | ` : "";
    const notes = `${existingNotes}Document: ${file.name} | Review upload: full document attached`;
    setReviewEvidence({
      ...evidence,
      document_name: file.name,
      document_url: documentUrl,
      notes,
    });
    onUpdateEvidence(evidence.key, "UNDER_REVIEW", { notes });
  };

  return (
    <div
      className={`bg-white rounded-lg border overflow-hidden ${
        priorityLabel === "Review" || priorityLabel === "Submitted"
          ? "border-amber-300"
          : "border-slate-200"
      }`}
    >
      {/* Gate Header */}
      <div
        className={`cursor-pointer p-3 transition-colors hover:bg-slate-50 ${
          isBlockingNextState ? "border-l-2 border-l-red-600" : ""
        }`}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {gate.is_complete ? (
              <CheckCircle2 className="w-6 h-6 text-green-600 flex-shrink-0" />
            ) : (
              <div className="w-6 h-6 rounded-full border-2 border-gray-300 flex items-center justify-center flex-shrink-0">
                <span className="text-xs font-bold text-gray-500">
                  {completePct}
                </span>
              </div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-slate-400">
                  {gate.gate_id.split("_")[0]}
                </span>
                <h3 className="font-bold text-slate-900 text-sm">
                  {gate.gate_name}
                </h3>
                <span
                  className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${gateQueueLabelClass(priorityLabel)}`}
                >
                  {priorityLabel}
                </span>
                {gate.determination === "WAIVED" && (
                  // A waived gate counts toward the ladder but is not satisfied
                  // by evidence, and must never read as if it were.
                  <span
                    className="rounded border border-slate-300 bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-600"
                    title="Not required for this financing model. Counted for the state ladder; not satisfied by evidence."
                  >
                    Waived
                  </span>
                )}
                {(gate.commitment_checks || []).map((c) => (
                  <span
                    key={c.kind}
                    className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                      c.met
                        ? "border-green-300 bg-green-50 text-green-700"
                        : "border-red-300 bg-red-50 text-red-700"
                    }`}
                    title={c.reasons.join(" ") || undefined}
                  >
                    {c.kind} {c.actual}
                    {c.met ? ` ≥ ${c.required}` : ` · needs ${c.required}`}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                <span className="text-xs text-slate-500">
                  {gate.verified_count}/{gate.total_evidence} verified
                </span>
                {lens && lensReadout && (
                  <span className="rounded bg-slate-100 px-1.5 text-xs font-medium text-slate-700">
                    {LENS_LABELS[lens]}: {lensReadout.verified}/{lensReadout.applicable}
                  </span>
                )}
                {(gate.maturity_shortfalls?.length ?? 0) > 0 && (
                  <span className="text-xs font-medium text-amber-700">
                    · {gate.maturity_shortfalls!.length} verified but not mature enough
                  </span>
                )}
                {(gate.overdue_count ?? 0) > 0 && (
                  <span className="rounded bg-red-50 px-1.5 text-xs font-semibold text-red-700">
                    {gate.overdue_count} overdue
                  </span>
                )}
                {(gate.uncommitted_count ?? 0) > 0 && (
                  <span className="text-xs font-medium text-amber-700">
                    · {gate.uncommitted_count} not yet committed
                  </span>
                )}
                <span className="text-xs text-slate-400">Evidence</span>
                <ChevronRight className="h-3 w-3 text-slate-300" />
                <span className="text-xs text-slate-500">
                  Gate {completePct}%
                </span>
                {capitalImpacts.length > 0 && (
                  <>
                    <ChevronRight className="h-3 w-3 text-slate-300" />
                    <span className="text-xs text-slate-500">
                      Capital {capitalImpacts.length}
                    </span>
                  </>
                )}
                {gate.unlocks_state && (
                  <span className="text-xs px-1.5 py-0.5 bg-white text-slate-700 rounded border border-slate-300 flex items-center gap-1">
                    → {STATE_LABELS[gate.unlocks_state] || gate.unlocks_state}
                    <InfoTooltip text={HELP.BANKABILITY_STATE} />
                  </span>
                )}
              </div>
              {capitalImpacts.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {capitalImpacts.map((impact) => {
                    const ImpactIcon = impact.is_unlocked ? Unlock : Lock;
                    return (
                      <span
                        key={impact.capital_type}
                        className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-semibold ${
                          impact.is_unlocked
                            ? "border-slate-300 bg-slate-50 text-slate-700"
                            : "border-amber-300 bg-white text-amber-700"
                        }`}
                      >
                        <ImpactIcon className="h-3 w-3" />
                        {CAPITAL_LABELS[impact.capital_type] ||
                          impact.capital_type}
                        {!impact.is_unlocked &&
                          ` ${Math.round(impact.best_progress_pct)}%`}
                      </span>
                    );
                  })}
                </div>
              )}
              {blockedReasons.length > 0 && (
                // Rules 4.0.0: evidence alone does not pass a gate. These are
                // the commitment levels, failed coherence checks and active
                // post-FID triggers holding it, whatever its percentage says.
                <div className="mt-1.5 text-[11px] text-red-700">
                  <span className="font-semibold">
                    {gate.items_complete ? "Evidence complete, but blocked:" : "Also blocked:"}
                  </span>
                  <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
                    {blockedReasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Progress bar */}
            <div className="w-24 h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${gate.is_complete ? "bg-green-600" : "bg-slate-700"}`}
                style={{ width: `${completePct}%` }}
              />
            </div>
            <span className="text-xs font-bold text-slate-500 flex items-center gap-1">
              {completePct}% <InfoTooltip text={HELP.GATE_SCORE} />
            </span>
            {expanded ? (
              <ChevronDown className="w-4 h-4 text-gray-400" />
            ) : (
              <ChevronRight className="w-4 h-4 text-gray-400" />
            )}
          </div>
        </div>
      </div>

      {/* Evidence Detail */}
      {expanded && (
        <div className="border-t border-slate-100 px-3 pb-3">
          {/* Evidence table */}
          <div className="mt-3 overflow-x-auto">
            <div className="min-w-[1030px]">
              <div className="grid grid-cols-[minmax(220px,1.8fr)_72px_170px_132px_120px_118px_220px] gap-3 border-b border-slate-200 px-2 pb-2 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                <div>Evidence item</div>
                <div>Required</div>
                <div>Owner</div>
                <div>Reviewer</div>
                <div>Status</div>
                <div>Last updated</div>
                <div>Action</div>
              </div>
            {lens && visibleEvidence.length === 0 && (
              <div className="px-2 py-3 text-xs text-slate-500">
                No item in this gate is relied on by the {LENS_LABELS[lens].toLowerCase()}.
              </div>
            )}
            {visibleEvidence.map((ev) => {
              const cfg = STATUS_CONFIG[ev.status] || STATUS_CONFIG.NOT_STARTED;
              const StatusIcon = cfg.icon;
              const reviewDocumentReady = hasFullDocument(
                ev,
                uploadedDocuments,
              );
              const notApplicable = ev.status === "NOT_APPLICABLE";
              return (
                <div
                  key={ev.key}
                  className={`grid grid-cols-[minmax(220px,1.8fr)_72px_170px_132px_120px_118px_220px] items-center gap-3 border-b border-slate-100 px-2 py-2 text-xs last:border-b-0 ${
                    notApplicable ? "opacity-60" : ""
                  }`}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <StatusIcon
                        className={`h-3.5 w-3.5 flex-shrink-0 ${cfg.color}`}
                      />
                      <span className="truncate text-sm font-medium text-slate-900">
                        {ev.label || formatEvidenceKey(ev.key)}
                      </span>
                      {ev.scope === "PROJECT_FINANCE" && (
                        <span
                          className="flex-shrink-0 rounded border border-slate-300 px-1 text-[10px] font-semibold uppercase text-slate-500"
                          title="Lender protection: required for project finance, not asked of a balance-sheet project."
                        >
                          Lender
                        </span>
                      )}
                    </div>
                    {notApplicable && (
                      <div className="mt-0.5 pl-5 text-[11px] text-slate-500">
                        {NOT_APPLICABLE_REASON[ev.not_applicable_reason || ""] || "Not required for this project"}
                      </div>
                    )}
                    {!notApplicable && ev.required_maturity && (
                      <div
                        className={`mt-0.5 pl-5 text-[11px] ${
                          ev.maturity_status === "MET"
                            ? "text-slate-500"
                            : ev.maturity_status === "BELOW_REQUIRED"
                              ? "font-medium text-red-700"
                              : "text-amber-700"
                        }`}
                        title={MATURITY_HELP[ev.required_maturity]}
                      >
                        Requires {ev.required_maturity}
                        {ev.maturity_status === "MET" &&
                          ` · declared ${ev.declared_maturity}`}
                        {ev.maturity_status === "NOT_DECLARED" &&
                          " · maturity not declared — cannot count until it is"}
                        {ev.maturity_status === "BELOW_REQUIRED" &&
                          ` · declared ${ev.declared_maturity} — does not count`}
                      </div>
                    )}
                    {(ev.status === "IN_PROGRESS" ||
                      (ev.status === "UNDER_REVIEW" &&
                        !reviewDocumentReady)) && (
                      <div className="mt-1 truncate text-[11px] text-slate-500">
                        {ev.status === "IN_PROGRESS"
                          ? "Submission chain and full document required."
                          : "Full document required before decision."}
                      </div>
                    )}
                  </div>
                  <div className={notApplicable ? "text-slate-400" : "font-semibold text-slate-700"}>
                    {notApplicable ? "No" : "Yes"}
                  </div>
                  {notApplicable ? (
                    <NotRequiredOwnerCell ev={ev} projectId={projectId} onChanged={onRefresh} />
                  ) : (
                    <OwnerCell
                      ev={ev}
                      fallbackOwners={gate.owners}
                      projectId={projectId}
                      onChanged={onRefresh}
                    />
                  )}
                  <div className="truncate text-slate-600">
                    {notApplicable
                      ? "—"
                      : ev.verified_by ||
                        (ev.status === "UNDER_REVIEW"
                          ? "Gate reviewer"
                          : "Not yet reviewed")}
                  </div>
                  <div>
                    <span
                      className={`inline-flex rounded border bg-white px-2 py-0.5 text-[11px] font-semibold ${cfg.border} ${cfg.color}`}
                    >
                      {cfg.label}
                    </span>
                  </div>
                  <div className="text-slate-500">
                    {formatEvidenceTimestamp(ev)}
                  </div>
                  <div className="flex items-center gap-1.5">
                    {/* Status progression buttons */}
                    {ev.status === "NOT_STARTED" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onUpdateEvidence(ev.key, "IN_PROGRESS");
                        }}
                        className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700"
                      >
                        Start
                      </button>
                    )}
                    {ev.status === "IN_PROGRESS" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          openSubmitWorkflow(ev);
                        }}
                        className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700"
                      >
                        Define submit
                      </button>
                    )}
                    {ev.status === "SUBMITTED" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setReviewEvidence({
                            ...ev,
                            status: "UNDER_REVIEW",
                          });
                          onUpdateEvidence(ev.key, "UNDER_REVIEW");
                        }}
                        className="inline-flex items-center gap-1 rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700"
                      >
                        <FileText className="h-3 w-3" />
                        Review
                      </button>
                    )}
                    {ev.status === "UNDER_REVIEW" && (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setReviewEvidence(ev);
                          }}
                          className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-800 hover:bg-slate-50"
                        >
                          <FileText className="h-3 w-3" />
                          Document
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (reviewDocumentReady) {
                              onUpdateEvidence(ev.key, "VERIFIED");
                            }
                          }}
                          disabled={!reviewDocumentReady}
                          className={`rounded px-2 py-1 text-xs ${
                            reviewDocumentReady
                              ? "bg-green-600 text-white hover:bg-green-700"
                              : "cursor-not-allowed bg-slate-100 text-slate-400"
                          }`}
                        >
                          Verify
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (reviewDocumentReady) {
                              onUpdateEvidence(ev.key, "REJECTED");
                            }
                          }}
                          disabled={!reviewDocumentReady}
                          className={`rounded px-2 py-1 text-xs ${
                            reviewDocumentReady
                              ? "bg-red-600 text-white hover:bg-red-700"
                              : "cursor-not-allowed bg-slate-100 text-slate-400"
                          }`}
                        >
                          Reject
                        </button>
                      </>
                    )}
                    {ev.status === "REJECTED" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onUpdateEvidence(ev.key, "IN_PROGRESS");
                        }}
                        className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700"
                      >
                        Rework
                      </button>
                    )}
                    </div>
                </div>
              );
            })}
            </div>
          </div>

          {hasCommitmentSection && (
            <div className="mt-4 space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                Commitments and coherence
              </div>
              {(gate.commitment_checks || []).map((c) => (
                <div key={c.kind} className="text-xs">
                  <span className="font-semibold text-slate-800">
                    {c.kind === "offtake" ? "Offtake" : "EPC"} level {c.actual}
                  </span>{" "}
                  <span className={c.met ? "text-green-700" : "text-red-700"}>
                    {c.met ? `meets the ${c.required} this gate needs` : `— this gate needs ${c.required}`}
                  </span>
                  {!c.met && c.reasons.length > 0 && (
                    <ul className="mt-1 list-disc space-y-0.5 pl-5 text-slate-600">
                      {c.reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
              {visibleCoherence.length > 0 && (
                <div className="divide-y divide-slate-200 rounded border border-slate-200 bg-white">
                  {visibleCoherence.map((c) => (
                    <div key={c.id} className="flex items-start gap-3 px-3 py-2 text-xs">
                      <span className="w-7 flex-shrink-0 font-mono text-slate-400">{c.id}</span>
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-slate-900">{c.title}</div>
                        <div className="mt-0.5 text-slate-600">{c.detail}</div>
                        {c.missing.length > 0 && (
                          <div className="mt-0.5 text-amber-700">
                            Record in Commitment terms: {c.missing.join(", ")}
                          </div>
                        )}
                      </div>
                      <span
                        className={`flex-shrink-0 rounded border px-2 py-0.5 text-[10px] font-bold uppercase ${COHERENCE_STATUS[c.status].cls}`}
                      >
                        {COHERENCE_STATUS[c.status].label}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {(gate.triggers || []).map((t) => (
                <div
                  key={t.id}
                  className="flex items-start gap-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800"
                >
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                  <span>
                    <span className="font-semibold">{t.id} · {t.title}.</span> {t.detail} The gate stays
                    blocked until the card is cleared.
                  </span>
                </div>
              ))}
            </div>
          )}

          {submitEvidence && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4"
              onClick={() => setSubmitEvidence(null)}
            >
              <div
                className="w-full max-w-2xl rounded-lg border border-slate-200 bg-white shadow-xl"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      Define Submission Chain
                    </div>
                    <h4 className="mt-1 text-lg font-bold text-slate-950">
                      {formatEvidenceKey(submitEvidence.key)}
                    </h4>
                    <p className="mt-1 text-sm text-slate-600">
                      Submit only after defining who receives it, where it goes,
                      what workflow it triggers, and attaching the full document.
                    </p>
                  </div>
                  <button
                    onClick={() => setSubmitEvidence(null)}
                    className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                    aria-label="Close submission workflow"
                  >
                    <XCircle className="h-5 w-5" />
                  </button>
                </div>

                <div className="space-y-4 px-5 py-4">
                  <label className="block">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Submit to whom
                    </span>
                    <input
                      value={submissionDraft.submitTo}
                      onChange={(event) =>
                        setSubmissionDraft((draft) => ({
                          ...draft,
                          submitTo: event.target.value,
                        }))
                      }
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                      placeholder="Gate owner, reviewer, independent engineer"
                    />
                  </label>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Where it goes
                      </span>
                      <select
                        value={submissionDraft.destination}
                        onChange={(event) =>
                          setSubmissionDraft((draft) => ({
                            ...draft,
                            destination: event.target.value,
                          }))
                        }
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                      >
                        {REVIEW_DESTINATIONS.map((destination) => (
                          <option key={destination} value={destination}>
                            {destination}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="block">
                      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        What submit triggers
                      </span>
                      <select
                        value={submissionDraft.leadsTo}
                        onChange={(event) =>
                          setSubmissionDraft((draft) => ({
                            ...draft,
                            leadsTo: event.target.value,
                          }))
                        }
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                      >
                        {REVIEW_OUTCOMES.map((outcome) => (
                          <option key={outcome} value={outcome}>
                            {outcome}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <label className="block rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Full document
                    </span>
                    <input
                      type="file"
                      onChange={handleSubmissionFile}
                      className="mt-2 block w-full text-sm text-slate-700 file:mr-3 file:rounded file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white"
                    />
                    {submissionDraft.documentName ? (
                      <p className="mt-2 text-xs font-medium text-slate-700">
                        Attached: {submissionDraft.documentName}{" "}
                        {fileSizeLabel(submissionDraft.documentSize)}
                      </p>
                    ) : (
                      <p className="mt-2 text-xs text-amber-700">
                        A full document is required before submission.
                      </p>
                    )}
                  </label>

                  {submitEvidence.required_maturity && (
                    <label className="block">
                      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        What is this document?
                      </span>
                      <select
                        id="submission-maturity"
                        value={submissionDraft.maturity}
                        onChange={(event) =>
                          setSubmissionDraft((draft) => ({
                            ...draft,
                            maturity: event.target.value as Maturity | "",
                          }))
                        }
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                      >
                        <option value="">Choose the instrument's maturity…</option>
                        {MATURITY_LEVELS.map((level) => (
                          <option key={level} value={level}>
                            {level} — {MATURITY_HELP[level]}
                          </option>
                        ))}
                      </select>
                      <p className="mt-1 text-[11px] text-slate-500">
                        This item counts once verified at{" "}
                        <span className="font-semibold">
                          {submitEvidence.required_maturity}
                        </span>{" "}
                        or above. Declare what the document actually is — the
                        reviewer can confirm or lower it, but not raise it.
                      </p>
                      {submissionDraft.maturity &&
                        MATURITY_LEVELS.indexOf(submissionDraft.maturity) <
                          MATURITY_LEVELS.indexOf(submitEvidence.required_maturity) && (
                          <p className="mt-1 text-[11px] font-medium text-amber-700">
                            A {submissionDraft.maturity} document will be recorded but
                            will not count toward this gate.
                          </p>
                        )}
                    </label>
                  )}

                  <label className="block">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Reviewer context
                    </span>
                    <textarea
                      value={submissionDraft.notes}
                      onChange={(event) =>
                        setSubmissionDraft((draft) => ({
                          ...draft,
                          notes: event.target.value,
                        }))
                      }
                      rows={3}
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                      placeholder="Explain what changed, what the reviewer must check, and any known caveats."
                    />
                  </label>
                </div>

                <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-4">
                  <button
                    onClick={() => setSubmitEvidence(null)}
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={submitEvidenceForReview}
                    disabled={
                      !submissionDraft.submitTo ||
                      !submissionDraft.destination ||
                      !submissionDraft.leadsTo ||
                      !submissionDraft.documentName ||
                      (!!submitEvidence.required_maturity && !submissionDraft.maturity)
                    }
                    className={`rounded-lg px-3 py-2 text-xs font-semibold ${
                      submissionDraft.submitTo &&
                      submissionDraft.destination &&
                      submissionDraft.leadsTo &&
                      submissionDraft.documentName &&
                      (!submitEvidence.required_maturity || submissionDraft.maturity)
                        ? "bg-slate-950 text-white hover:bg-slate-800"
                        : "cursor-not-allowed bg-slate-100 text-slate-400"
                    }`}
                  >
                    Submit evidence
                  </button>
                </div>
              </div>
            </div>
          )}

          {reviewEvidence && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4"
              onClick={() => setReviewEvidence(null)}
            >
              <div
                className="w-full max-w-2xl rounded-lg border border-slate-200 bg-white shadow-xl"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      Evidence Document Review
                    </div>
                    <h4 className="mt-1 text-lg font-bold text-slate-950">
                      {documentLabel(reviewEvidence)}
                    </h4>
                    <p className="mt-1 text-sm text-slate-600">
                      {gate.gate_id.split("_")[0]} {gate.gate_name}
                    </p>
                  </div>
                  <button
                    onClick={() => setReviewEvidence(null)}
                    className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                    aria-label="Close document review"
                  >
                    <XCircle className="h-5 w-5" />
                  </button>
                </div>

                <div className="space-y-4 px-5 py-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Evidence key
                      </div>
                      <div className="mt-1 font-mono text-xs text-slate-900">
                        {reviewEvidence.key}
                      </div>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Status
                      </div>
                      <div className="mt-1 text-sm font-semibold text-slate-900">
                        {STATUS_CONFIG[reviewEvidence.status]?.label ||
                          reviewEvidence.status}
                      </div>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Submitted by
                      </div>
                      <div className="mt-1 text-sm font-semibold text-slate-900">
                        {reviewEvidence.submitted_by || "Not recorded"}
                      </div>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Document hash
                      </div>
                      <div className="mt-1 truncate font-mono text-xs text-slate-900">
                        {reviewEvidence.document_hash || "Pending hash"}
                      </div>
                    </div>
                  </div>

                  {reviewEvidence.notes && (
                    <div className="rounded-lg border border-slate-200 bg-white p-3">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Submitter notes
                      </div>
                      <p className="mt-1 text-sm text-slate-700">
                        {reviewEvidence.notes}
                      </p>
                    </div>
                  )}

                  <label className="block rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Full document required for decision
                    </span>
                    <input
                      type="file"
                      onChange={(event) =>
                        handleReviewFile(event, reviewEvidence)
                      }
                      className="mt-2 block w-full text-sm text-slate-700 file:mr-3 file:rounded file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white"
                    />
                    {hasFullDocument(reviewEvidence, uploadedDocuments) ? (
                      <p className="mt-2 text-xs font-medium text-slate-700">
                        Decision enabled. Document:{" "}
                        {currentDocumentName(reviewEvidence, uploadedDocuments)}
                      </p>
                    ) : (
                      <p className="mt-2 text-xs text-amber-700">
                        Verify and Reject remain locked until the full document
                        is attached.
                      </p>
                    )}
                  </label>

                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <div className="text-sm font-semibold text-slate-900">
                      Review source
                    </div>
                    <p className="mt-1 text-sm text-slate-600">
                      Open the attached file if present. If this demo record has
                      no stored file URL, use the related workspace to inspect
                      the term sheet, contract, or evidence pack before approving
                      or rejecting.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {(reviewEvidence.document_url ||
                        uploadedDocuments[reviewEvidence.key]?.url) && (
                        <a
                          href={
                            reviewEvidence.document_url ||
                            uploadedDocuments[reviewEvidence.key]?.url
                          }
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-lg bg-slate-950 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          Open uploaded document
                        </a>
                      )}
                      <a
                        href={relatedReviewPath(reviewEvidence.key)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-50"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                        Open related workspace
                      </a>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-4">
                  <button
                    onClick={() => setReviewEvidence(null)}
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    Close
                  </button>
                  <button
                    onClick={() => {
                      if (hasFullDocument(reviewEvidence, uploadedDocuments)) {
                        onUpdateEvidence(reviewEvidence.key, "REJECTED");
                        setReviewEvidence(null);
                      }
                    }}
                    disabled={!hasFullDocument(reviewEvidence, uploadedDocuments)}
                    className={`rounded-lg border px-3 py-2 text-xs font-semibold ${
                      hasFullDocument(reviewEvidence, uploadedDocuments)
                        ? "border-red-300 bg-white text-red-700 hover:bg-red-50"
                        : "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400"
                    }`}
                  >
                    Reject
                  </button>
                  <button
                    onClick={() => {
                      if (hasFullDocument(reviewEvidence, uploadedDocuments)) {
                        onUpdateEvidence(reviewEvidence.key, "VERIFIED");
                        setReviewEvidence(null);
                      }
                    }}
                    disabled={!hasFullDocument(reviewEvidence, uploadedDocuments)}
                    className={`rounded-lg px-3 py-2 text-xs font-semibold ${
                      hasFullDocument(reviewEvidence, uploadedDocuments)
                        ? "bg-slate-950 text-white hover:bg-slate-800"
                        : "cursor-not-allowed bg-slate-100 text-slate-400"
                    }`}
                  >
                    Verify
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Owners */}
          <div className="mt-3 pt-2 border-t border-gray-100">
            <span className="text-xs text-gray-500">
              Owners: {gate.owners.map((o) => o.replace(/_/g, " ")).join(", ")}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════

// ─── Commitments: the two ladders, coherence, and the terms behind them ──────

const CARD_LABELS: Record<CardType, string> = {
  offtake: "Offtake",
  epc: "EPC",
  schedule: "Schedule",
  supply: "Supply & power",
  model: "Financial model",
};

const FIELD_WORDS: Record<string, string> = {
  pct: "%",
  eur: "(EUR)",
  ld: "LD",
  fm: "Force majeure",
  cps: "Conditions precedent",
  cod: "COD",
  fid: "FID",
  co2: "CO2",
  ppa: "PPA",
  epc: "EPC",
  p80: "P80",
  ref: "reference",
};

// Labels are derived from the engine's field names so a new field needs no
// frontend change: "delay_ld_cap_eur" -> "Delay LD cap (EUR)".
function fieldLabel(field: string): string {
  let base = field;
  let unit = "";
  if (base.endsWith("_tonnes_per_year")) {
    base = base.slice(0, -"_tonnes_per_year".length);
    unit = " (t/yr)";
  } else if (base.endsWith("_mwh_per_year")) {
    base = base.slice(0, -"_mwh_per_year".length);
    unit = " (MWh/yr)";
  }
  const text = base.split("_").map((w) => FIELD_WORDS[w] ?? w).join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1) + unit;
}

function toFormValue(kind: string, value: unknown): string {
  if (value === undefined || value === null) return "";
  if (kind === "bool") return value ? "true" : "false";
  if (kind === "list") return Array.isArray(value) ? value.join(", ") : String(value);
  return String(value);
}

// An empty field is omitted: an unknown fact is absent, not zero or false.
// Invalid values are sent as typed so the server names the problem.
function fromForm(spec: Record<string, string>, form: Record<string, string>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [field, kind] of Object.entries(spec)) {
    const raw = (form[field] ?? "").trim();
    if (raw === "") continue;
    if (kind === "number") {
      const n = Number(raw);
      out[field] = Number.isFinite(n) ? n : raw;
    } else if (kind === "bool") {
      out[field] = raw === "true";
    } else if (kind === "list") {
      out[field] = raw.split(",").map((s) => s.trim()).filter(Boolean);
    } else {
      out[field] = raw;
    }
  }
  return out;
}

function TermsInput({
  kind,
  value,
  disabled,
  onChange,
}: {
  kind: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const cls =
    "w-full rounded border border-slate-300 px-2 py-1 text-xs disabled:bg-slate-50 disabled:text-slate-500";
  if (kind === "bool" || kind.startsWith("enum:")) {
    const options =
      kind === "bool"
        ? [["true", "Yes"], ["false", "No"]]
        : kind.slice(5).split("|").map((o) => [o, o.replace(/_/g, " ")]);
    return (
      <select className={cls} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        <option value="">Not recorded</option>
        {options.map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      className={cls}
      type={kind === "number" ? "number" : kind === "date" ? "date" : "text"}
      value={value}
      disabled={disabled}
      min={kind === "number" ? 0 : undefined}
      step={kind === "number" ? "any" : undefined}
      maxLength={kind === "str" ? 300 : undefined}
      placeholder={kind === "list" ? "comma-separated" : undefined}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function CommitmentTermsEditor({ projectId, onSaved }: { projectId: string; onSaved: () => void }) {
  const [data, setData] = useState<TermsResponse | null>(null);
  const [card, setCard] = useState<CardType>("offtake");
  const [form, setForm] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    setData(null);
    setLoadError(null);
    bankabilityAPI
      .getTerms(projectId)
      .then((d: TermsResponse) => live && setData(d))
      .catch((err: any) => live && setLoadError(apiErrorMessage(err)));
    return () => {
      live = false;
    };
  }, [projectId]);

  // Reset the form from what is stored whenever the card or the data changes.
  useEffect(() => {
    const spec = data?.card_fields?.[card] || {};
    const stored = data?.cards?.[card]?.terms || {};
    const next: Record<string, string> = {};
    for (const [field, kind] of Object.entries(spec)) next[field] = toFormValue(kind, stored[field]);
    setForm(next);
  }, [card, data]);

  if (loadError) {
    return (
      <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
        Could not load commitment terms: {loadError}
      </div>
    );
  }
  if (!data) return <div className="px-3 py-2 text-xs text-slate-500">Loading commitment terms…</div>;

  const spec = data.card_fields[card] || {};
  const stored = data.cards[card];
  const editable = data.can_edit;
  const cards = Object.keys(data.card_fields) as CardType[];

  const save = async () => {
    setBusy(true);
    setSaveError(null);
    setNotice(null);
    try {
      const res = await bankabilityAPI.saveTerms({
        project_id: projectId,
        card_type: card,
        terms: fromForm(spec, form),
      });
      setData(await bankabilityAPI.getTerms(projectId));
      setNotice(res.changed ? "Saved — gates re-evaluated." : "No change.");
      if (res.changed) onSaved();
    } catch (err: any) {
      setSaveError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center gap-1 border-b border-slate-100 px-3 py-2">
        {cards.map((c) => {
          const filled = Object.keys(data.cards[c]?.terms || {}).length;
          return (
            <button
              key={c}
              onClick={() => {
                setCard(c);
                setNotice(null);
                setSaveError(null);
              }}
              className={`rounded px-2.5 py-1 text-xs font-semibold ${
                c === card ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {CARD_LABELS[c] || c}
              {filled > 0 && <span className="ml-1 opacity-70">· {filled}</span>}
            </button>
          );
        })}
        <span className="ml-auto text-[11px] text-slate-500">
          Scored at {gateShortId(data.card_gates[card] || "")}
          {stored?.updated_at &&
            ` · saved ${stored.updated_at.slice(0, 16).replace("T", " ")} by ${stored.updated_by || "unknown"}`}
        </span>
      </div>
      {!editable && (
        <div className="border-b border-slate-100 bg-slate-50 px-3 py-1.5 text-[11px] text-slate-600">
          Read-only: only the company that owns this project can record its commitment terms.
        </div>
      )}
      <div className="grid grid-cols-1 gap-x-4 gap-y-2 p-3 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(spec).map(([field, kind]) => (
          <label key={field} className="text-xs">
            <span className="mb-0.5 block font-medium text-slate-700">{fieldLabel(field)}</span>
            <TermsInput
              kind={kind}
              value={form[field] ?? ""}
              disabled={!editable || busy}
              onChange={(v) => setForm((f) => ({ ...f, [field]: v }))}
            />
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 px-3 py-2">
        <span className="text-[11px] text-slate-500">
          Leave a field empty when the fact is unknown — empty is not zero. Saving replaces the whole{" "}
          {CARD_LABELS[card]} card and is recorded in its history.
        </span>
        {saveError && <span className="text-xs text-red-700">{saveError}</span>}
        {notice && <span className="text-xs text-green-700">{notice}</span>}
        {editable && (
          <button
            onClick={save}
            disabled={busy}
            className="ml-auto rounded bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {busy ? "Saving…" : `Save ${CARD_LABELS[card]} card`}
          </button>
        )}
      </div>
    </div>
  );
}

function CommitmentsPanel({
  snapshot,
  rules,
  projectId,
  onSaved,
}: {
  snapshot: Snapshot;
  rules: EngineRules | null;
  projectId: string;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  if (!snapshot.offtake && !snapshot.epc) return null; // engine older than rules 4.0.0

  const coherence = snapshot.coherence_checks || [];
  const triggers = snapshot.regression_triggers || [];
  const counts: Record<CoherenceCheck["status"], number> = {
    PASS: 0,
    FAIL: 0,
    NOT_EVALUABLE: 0,
    NOT_APPLICABLE: 0,
  };
  coherence.forEach((c) => (counts[c.status] += 1));
  const ladders = [
    {
      name: "Offtake",
      lv: snapshot.offtake,
      defs: rules?.offtake_level_definitions,
      extra: [snapshot.offtake?.form?.replace(/_/g, " "), snapshot.offtake?.effective ? "effective" : null]
        .filter(Boolean)
        .join(" · "),
    },
    {
      name: "EPC",
      lv: snapshot.epc,
      defs: rules?.epc_level_definitions,
      extra: snapshot.epc?.contracting_model?.replace(/_/g, " ") || "",
    },
  ];

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="grid gap-4 p-4 md:grid-cols-[1fr_1fr_auto]">
        {ladders.map(
          ({ name, lv, defs, extra }) =>
            lv && (
              <div key={name} className="min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">{name}</span>
                  <span className="font-mono text-lg font-black text-slate-950">{lv.level}</span>
                  {extra && <span className="text-[11px] text-slate-500">{extra}</span>}
                </div>
                {defs?.[lv.level] && <div className="text-xs text-slate-700">{defs[lv.level]}</div>}
                {lv.reasons.filter((r) => r !== defs?.[lv.level]).length > 0 && (
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-slate-500">
                    {lv.reasons
                      .filter((r) => r !== defs?.[lv.level])
                      .map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                  </ul>
                )}
              </div>
            ),
        )}
        <div className="flex flex-col items-start gap-1.5 md:items-end">
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Coherence checks</div>
          <div className="flex flex-wrap gap-1">
            {(["FAIL", "NOT_EVALUABLE", "PASS", "NOT_APPLICABLE"] as const)
              .filter((s) => counts[s] > 0)
              .map((s) => (
                <span
                  key={s}
                  className={`rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase ${COHERENCE_STATUS[s].cls}`}
                >
                  {counts[s]} {COHERENCE_STATUS[s].label}
                </span>
              ))}
          </div>
          {triggers.length > 0 && (
            <div className="text-[11px] font-semibold text-red-700">
              {triggers.length} post-FID trigger{triggers.length === 1 ? "" : "s"} active
            </div>
          )}
          <button
            onClick={() => setOpen(!open)}
            className="mt-1 inline-flex items-center gap-1 rounded border border-slate-300 px-2.5 py-1 text-xs font-semibold text-slate-800 hover:bg-slate-50"
          >
            <FileSignature className="h-3.5 w-3.5" />
            {open ? "Hide commitment terms" : "Commitment terms"}
          </button>
        </div>
      </div>
      <div className="border-t border-slate-100 px-4 py-1.5 text-[11px] text-slate-500">
        Levels are derived from verified evidence maturity and the recorded commitment terms — never entered
        directly. A failed coherence check blocks its gate; "data missing" blocks nothing but is not a pass.
      </div>
      {open && (
        <div className="border-t border-slate-100 p-3">
          <CommitmentTermsEditor projectId={projectId} onSaved={onSaved} />
        </div>
      )}
    </div>
  );
}

export function StageGatesPage() {
  const { selectedProjectId } = useSelectedProject();
  const { projects: visibleProjects } = useVisibleProjects();
  const selectedProject = visibleProjects.find(p => p.id === selectedProjectId);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Surfaced when an evidence-status action fails — never a silent dead-end.
  const [actionError, setActionError] = useState<string | null>(null);
  const [health, setHealth] = useState<{
    status: string;
    platform_db?: string;
    engine?: string;
  } | null>(null);
  const [rules, setRules] = useState<EngineRules | null>(null);
  const [lens, setLens] = useState<Lens | null>(null);

  // Definitions (lenses, O/E levels) come from the engine, loaded once.
  useEffect(() => {
    bankabilityAPI
      .getRules()
      .then((r: EngineRules) => setRules(r))
      .catch(() => setRules(null));
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await bankabilityAPI.evaluate(selectedProjectId);
      setSnapshot(data);
      setHealth(null);
    } catch (err: any) {
      setError(err.message || "Failed to load bankability data");
      try {
        const status = await bankabilityAPI.health();
        setHealth(status);
      } catch {
        setHealth(null);
      }
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleUpdateEvidence = async (
    evidenceKey: string,
    newStatus: string,
    meta?: EvidenceUpdateMeta,
  ) => {
    setActionError(null);
    try {
      const updated = await bankabilityAPI.updateEvidence({
        project_id: selectedProjectId,
        evidence_key: evidenceKey,
        new_status: newStatus,
        submitted_by: meta?.submittedBy,
        notes: meta?.notes,
        maturity: meta?.maturity,
      });
      setSnapshot(updated);
    } catch (err: any) {
      // Surface, don't swallow — a dead button with no feedback is the dead-end.
      console.error("Evidence update failed:", err);
      setActionError(
        `Could not update "${formatEvidenceKey(evidenceKey)}" → ${newStatus}: ${err?.message || "request failed"}. ` +
        `Check you are signed in and the bankability engine (port 8001) is reachable.`,
      );
    }
  };

  // "Seed Demo Data" removed 2026-09-23 along with POST /bankability/evidence/seed.
  // One click wrote 52 invented evidence rows into whichever project was
  // selected — real ones included — and the gates, bankability state and
  // capital unlocks on this very page were then computed from them.

  // ── Loading state ──
  if (loading && !snapshot) {
    return (
      <div className="space-y-6">
        <ProjectContextBanner
          projectId={selectedProjectId}
          project={selectedProject}
        />
        <div className="flex items-center justify-center py-20">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
          <span className="ml-3 text-gray-600">
            Evaluating bankability gates...
          </span>
        </div>
      </div>
    );
  }

  // ── Error state ──
  if (error && !snapshot) {
    return (
      <div className="space-y-6">
        <ProjectContextBanner
          projectId={selectedProjectId}
          project={selectedProject}
        />
        <div className="bg-red-50 border border-red-200 rounded-xl p-6">
          <h3 className="text-lg font-bold text-red-800 mb-2">
            Bankability Data Error
          </h3>
          <p className="text-sm text-red-700 mb-4">{error}</p>
          <div className="text-xs text-red-600 mb-4 space-y-1">
            <p>
              Project:{" "}
              <span className="font-semibold">
                {selectedProject?.name ?? selectedProjectId}
              </span>
            </p>
            <p>
              The screen loads through the platform backend proxy at{" "}
              <span className="font-mono">/api/v1/bankability</span>, not
              directly from the browser to port 8001.
            </p>
            {health && (
              <p>
                Proxy health: status={health.status} · db=
                {health.platform_db ?? "unknown"} · engine=
                {health.engine ?? "unknown"}
              </p>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={loadData}
              className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-semibold hover:bg-red-700"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!snapshot) return null;

  const blockers = snapshot.gates_blocking_next_state || [];
  const gateQueue = snapshot.gate_evaluations
    .map((gate) => {
      const capitalImpacts = capitalImpactsForGate(
        gate,
        snapshot.capital_unlocks,
      );
      const priorityLabel = gateQueueLabel(gate, blockers, capitalImpacts);
      return {
        gate,
        capitalImpacts,
        priorityLabel,
        isBlockingNextState: isGateBlockingNextState(gate, blockers),
        rank: gateQueueRank(gate, blockers, capitalImpacts),
      };
    })
    .sort((a, b) => {
      if (a.rank !== b.rank) return a.rank - b.rank;
      return a.gate.completion_pct - b.gate.completion_pct;
    });
  // Lenses exist from rules 4.0.0. Under a lens, a gate with nothing that party
  // relies on (no item, no coherence check) is hidden, and the count is shown.
  const lensesAvailable = snapshot.gate_evaluations.some((g) => g.lens_readouts);
  const activeLens = lensesAvailable ? lens : null;
  const shownQueue = activeLens
    ? gateQueue.filter(
        ({ gate }) =>
          (gate.lens_readouts?.[activeLens]?.applicable ?? 0) > 0 ||
          (gate.coherence_checks || []).some((c) => c.lenses.includes(activeLens)),
      )
    : gateQueue;
  const hiddenByLens = gateQueue.length - shownQueue.length;
  const underReviewCount = snapshot.gate_evaluations.reduce(
    (sum, gate) =>
      sum +
      gate.evidence_detail.filter((item) => item.status === "UNDER_REVIEW")
        .length,
    0,
  );
  const submittedCount = snapshot.gate_evaluations.reduce(
    (sum, gate) =>
      sum +
      gate.evidence_detail.filter((item) => item.status === "SUBMITTED")
        .length,
    0,
  );
  const blockedCapitalCount = snapshot.capital_unlocks.filter(
    (unlock) => !unlock.is_unlocked,
  ).length;
  const unlockedCapitalCount =
    snapshot.capital_unlocks.length - blockedCapitalCount;

  return (
    <div className="space-y-6">
      <ProjectContextBanner
        projectId={selectedProjectId}
        project={selectedProject}
      />

      {actionError && (
        <div className="flex items-start justify-between gap-3 rounded-lg border border-red-300 bg-red-50 px-4 py-2.5 text-sm text-red-800">
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="shrink-0 font-bold text-red-600 hover:text-red-800">✕</button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">
            Bankability Stage Gates
          </h1>
          <p className="text-sm text-gray-600 mt-1">
            {TAB_DESCRIPTIONS.STAGE_GATES}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 hover:bg-gray-100 rounded-lg"
          >
            <RefreshCw
              className={`w-5 h-5 text-gray-600 ${loading ? "animate-spin" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* State + Progression */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-center gap-3 mb-4">
          {/* <Shield className="w-6 h-6 text-green-600" /> */}
          <div>
            <span className="text-sm text-gray-500">Current State</span>
            <h2 className="text-xl font-black text-gray-900">
              {STATE_LABELS[snapshot.current_state] || snapshot.current_state}
            </h2>
            {snapshot.state_label && (
              // Rules 4.0.0: the commitment the state makes possible, read next
              // to its capital meaning.
              <p className="text-xs text-slate-600">{snapshot.state_label}</p>
            )}
          </div>
          {snapshot.next_state && (
            <div className="ml-auto text-right">
              <span className="text-xs text-gray-400">Next target</span>
              <div className="text-sm font-bold text-amber-700">
                {STATE_LABELS[snapshot.next_state]}
              </div>
              {snapshot.next_state_label && (
                <div className="text-[11px] text-slate-500">{snapshot.next_state_label}</div>
              )}
            </div>
          )}
        </div>
        <StateProgressionBar
          currentState={snapshot.current_state}
          nextState={snapshot.next_state || undefined}
        />

        {/* Regression Warning */}
        {snapshot.regression && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-600" />
              <span className="font-bold text-red-800 text-sm">
                Regression Detected
              </span>
            </div>
            <p className="text-sm text-red-700 mt-1">
              {STATE_LABELS[snapshot.regression.from_state]} →{" "}
              {STATE_LABELS[snapshot.regression.to_state]}:{" "}
              {snapshot.regression.reason}
            </p>
          </div>
        )}

      </div>

      <CommitmentsPanel
        snapshot={snapshot}
        rules={rules}
        projectId={selectedProjectId}
        onSaved={loadData}
      />

      {/* Next goal post */}
      {snapshot.next_state ? (
        <NextGoalPost snapshot={snapshot} gateQueue={gateQueue} />
      ) : (
        <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs">
          {RELATED_VIEWS.map((view) => (
            <a
              key={view.href}
              href={view.href}
              className="font-medium text-slate-400 hover:text-slate-900"
            >
              {view.label}
            </a>
          ))}
        </div>
      )}

      {/* Gate Review Queue */}
      <div className="space-y-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="text-base font-bold text-slate-950">
                Gate Review Queue
              </h3>
              <p className="mt-1 text-sm text-slate-600">
                Evidence, gate status, capital impact, and next action in one ordered queue.
              </p>
              {lensesAvailable && (
                <div className="mt-3 flex flex-wrap items-center gap-1">
                  <span className="mr-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
                    View as
                  </span>
                  {([null, ...LENSES] as (Lens | null)[]).map((l) => (
                    <button
                      key={l ?? "ALL"}
                      onClick={() => setLens(l)}
                      title={l ? rules?.lens_definitions?.[l] : "Every item, for every party"}
                      className={`rounded px-2 py-0.5 text-xs font-semibold ${
                        activeLens === l ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                      }`}
                    >
                      {l ? LENS_LABELS[l] : "All"}
                    </button>
                  ))}
                </div>
              )}
              {activeLens && (
                <p className="mt-1 max-w-xl text-[11px] text-slate-500">
                  {rules?.lens_definitions?.[activeLens]} A lens filters what is shown; every gate keeps
                  one determination.
                  {hiddenByLens > 0 &&
                    ` ${hiddenByLens} gate${hiddenByLens === 1 ? "" : "s"} carry nothing this party relies on.`}
                </p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
                  Blocking
                </div>
                <div className="mt-1 text-lg font-black text-slate-950">
                  {blockers.length}
                </div>
              </div>
              <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
                  Review
                </div>
                <div className="mt-1 text-lg font-black text-slate-950">
                  {underReviewCount + submittedCount}
                </div>
              </div>
              <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
                  Capital wait
                </div>
                <div className="mt-1 text-lg font-black text-slate-950">
                  {blockedCapitalCount}
                </div>
              </div>
              <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
                  Capital open
                </div>
                <div className="mt-1 text-lg font-black text-slate-950">
                  {unlockedCapitalCount}
                </div>
              </div>
            </div>
          </div>
        </div>

        {shownQueue.map(
          ({ gate, capitalImpacts, priorityLabel, isBlockingNextState }) => (
            <GateCard
              key={gate.gate_id}
              lens={activeLens}
              gate={gate}
              capitalImpacts={capitalImpacts}
              priorityLabel={priorityLabel}
              isBlockingNextState={isBlockingNextState}
              onUpdateEvidence={handleUpdateEvidence}
              projectId={selectedProjectId}
              onRefresh={loadData}
            />
          ),
        )}
      </div>
    </div>
  );
}
