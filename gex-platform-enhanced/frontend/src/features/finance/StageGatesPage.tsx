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
    | "EXPIRED";
  submitted_by?: string;
  verified_by?: string;
  submitted_at?: string;
  verified_at?: string;
  document_hash?: string;
  document_url?: string;
  document_ref?: string;
  document_name?: string;
  notes?: string;
}

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
}

interface CapitalUnlock {
  capital_type: string;
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
}

interface EvidenceUpdateMeta {
  submittedBy?: string;
  notes?: string;
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
  const totalRemaining = blockingEntries.reduce(
    (sum, { gate }) =>
      sum +
      gate.evidence_detail.filter((e) => e.status !== "VERIFIED").length,
    0,
  );

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
            ? "all gates clear"
            : `${blockingEntries.length} blocking · ${totalRemaining} items`}
        </span>
      </div>

      {blockingEntries.length > 0 && (
        <div className="divide-y divide-slate-50">
          {blockingEntries.map(({ gate }) => {
            const remaining = gate.evidence_detail.filter(
              (e) => e.status !== "VERIFIED",
            ).length;
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

function GateCard({
  gate,
  capitalImpacts,
  priorityLabel,
  isBlockingNextState,
  onUpdateEvidence,
}: {
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
  });
  const completePct = Math.round(gate.completion_pct);

  const openSubmitWorkflow = (evidence: EvidenceItem) => {
    setSubmissionDraft({
      submitTo: gate.owners[0]?.replace(/_/g, " ") || "Gate owner",
      destination: REVIEW_DESTINATIONS[0],
      leadsTo: REVIEW_OUTCOMES[0],
      documentName: "",
      documentSize: 0,
      documentUrl: "",
      notes: "",
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
              </div>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                <span className="text-xs text-slate-500">
                  {gate.verified_count}/{gate.total_evidence} verified
                </span>
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
            <div className="min-w-[980px]">
              <div className="grid grid-cols-[minmax(220px,1.8fr)_72px_120px_132px_120px_118px_220px] gap-3 border-b border-slate-200 px-2 pb-2 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                <div>Evidence item</div>
                <div>Required</div>
                <div>Owner</div>
                <div>Reviewer</div>
                <div>Status</div>
                <div>Last updated</div>
                <div>Action</div>
              </div>
            {gate.evidence_detail.map((ev) => {
              const cfg = STATUS_CONFIG[ev.status] || STATUS_CONFIG.NOT_STARTED;
              const StatusIcon = cfg.icon;
              const reviewDocumentReady = hasFullDocument(
                ev,
                uploadedDocuments,
              );
              return (
                <div
                  key={ev.key}
                  className="grid grid-cols-[minmax(220px,1.8fr)_72px_120px_132px_120px_118px_220px] items-center gap-3 border-b border-slate-100 px-2 py-2 text-xs last:border-b-0"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <StatusIcon
                        className={`h-3.5 w-3.5 flex-shrink-0 ${cfg.color}`}
                      />
                      <span className="truncate text-sm font-medium text-slate-900">
                        {formatEvidenceKey(ev.key)}
                      </span>
                    </div>
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
                  <div className="font-semibold text-slate-700">Yes</div>
                  <div className="truncate text-slate-600">
                    {gate.owners.map((o) => o.replace(/_/g, " ")).join(", ")}
                  </div>
                  <div className="truncate text-slate-600">
                    {ev.verified_by ||
                      (ev.status === "UNDER_REVIEW"
                        ? "Gate reviewer"
                        : "Unassigned")}
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
                      !submissionDraft.documentName
                    }
                    className={`rounded-lg px-3 py-2 text-xs font-semibold ${
                      submissionDraft.submitTo &&
                      submissionDraft.destination &&
                      submissionDraft.leadsTo &&
                      submissionDraft.documentName
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

export function StageGatesPage() {
  const { selectedProjectId } = useSelectedProject();
  const { projects: visibleProjects } = useVisibleProjects();
  const selectedProject = visibleProjects.find(p => p.id === selectedProjectId);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Surfaced when an evidence-status action fails — never a silent dead-end.
  const [actionError, setActionError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [health, setHealth] = useState<{
    status: string;
    platform_db?: string;
    engine?: string;
  } | null>(null);

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

  const handleSeedDemo = async () => {
    setSeeding(true);
    try {
      await bankabilityAPI.seedDemo(selectedProjectId);
      await loadData();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSeeding(false);
    }
  };

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
            <button
              onClick={handleSeedDemo}
              disabled={seeding}
              className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-semibold hover:bg-amber-700"
            >
              {seeding ? "Seeding..." : "Seed Demo Data"}
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
            onClick={handleSeedDemo}
            disabled={seeding}
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-gray-600"
          >
            {seeding ? "Seeding..." : "Seed Demo"}
          </button>
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
          </div>
          {snapshot.next_state && (
            <div className="ml-auto text-right">
              <span className="text-xs text-gray-400">Next target</span>
              <div className="text-sm font-bold text-amber-700">
                {STATE_LABELS[snapshot.next_state]}
              </div>
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

        {gateQueue.map(
          ({ gate, capitalImpacts, priorityLabel, isBlockingNextState }) => (
            <GateCard
              key={gate.gate_id}
              gate={gate}
              capitalImpacts={capitalImpacts}
              priorityLabel={priorityLabel}
              isBlockingNextState={isBlockingNextState}
              onUpdateEvidence={handleUpdateEvidence}
            />
          ),
        )}
      </div>
    </div>
  );
}
