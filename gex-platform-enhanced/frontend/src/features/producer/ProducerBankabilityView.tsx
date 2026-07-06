// Screen: Producer bankability view screen (/producer-bankability)
import React, { useState, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  CheckCircle, AlertCircle, Clock, Upload, Eye, FileText,
  Info, X, ChevronDown, ChevronUp, ArrowRight, Lock, Unlock, TrendingUp,
} from 'lucide-react';
import { type CommitmentStatus } from '@/data/customerProjects';
import {
  STATIC_EVIDENCE_CATALOG,
  evidenceMetaFallback,
  appliesToModel,
  effectiveSeverity,
  resolveEvidenceRoute,
  type PowerModel,
  type EvidenceSeverity,
} from '@/data/evidenceCatalog';
import { resolveActionRoute } from '@/lib/actionRouter';
import { useVisibleProjects } from '@/hooks/useVisibleProjects';
import { useSelectedProject } from '@/contexts/ProjectContext';
import { useUserRole } from '@/contexts/UserRoleContext';
import { AdversarialReviewEntryCard } from '@/components/AdversarialReviewEntryCard';

// ─── Types ────────────────────────────────────────────────────────────────────

type EvidenceStatus =
  | 'NOT_STARTED' | 'IN_PROGRESS' | 'SUBMITTED' | 'UNDER_REVIEW'
  | 'VERIFIED' | 'REJECTED' | 'EXPIRED' | 'NOT_APPLICABLE'
  // PRESUMED: synthesised from the static registry in fallback mode — the
  // registry counts it as non-blocking but NO evidence record exists. Never
  // rendered as verified; the engine never emits this status.
  | 'PRESUMED';

interface EvidenceItem {
  key: string;
  status: EvidenceStatus;
  // Policy metadata as served by the engine (EVIDENCE_META). When the engine
  // is down (static fallback), evidenceMetaFallback() fills these in — the
  // static catalog is a mirror, never the authority.
  applicable?: boolean;
  severity?: EvidenceSeverity;
  label?: string;
  section?: string;
  section_label?: string;
  applies_to?: string[];
  owner_function?: string;
  blocked_action?: string | null;
  route?: string | null;
  submitted_by?: string;
  verified_by?: string;
  submitted_at?: string;
  verified_at?: string;
  document_url?: string;
  notes?: string;
}

function severityBadge(s: EvidenceSeverity) {
  switch (s) {
    case 'deal_killer': return <span className="gex-badge gex-badge-red">DEAL KILLER</span>;
    case 'warning':     return <span className="gex-badge gex-badge-amber">WARNING</span>;
    default:            return <span className="gex-badge gex-badge-default">ADVISORY</span>;
  }
}

interface PremiseFinding {
  code: string;
  severity: EvidenceSeverity;
  message: string;
  blocked_action?: string;
  route?: string;
}

interface Gate {
  id: string;
  name: string;
  total_evidence: number;
  verified_count: number;
  completion_pct: number;
  is_complete: boolean;
  blocking_items: string[];
  evidence_items: EvidenceItem[];
  premise_findings?: PremiseFinding[];
  /** false = waived by financing model (lender gate on a balance-sheet project). */
  financing_applicable?: boolean;
}

// Lender-protection gate numbers — waived under BALANCE_SHEET financing.
// Mirrors the engine's _LENDER_GATES (matched on gate-number prefix because
// the static registry and the engine use different full ids).
const LENDER_GATE_PREFIXES = new Set(['G4', 'G6', 'G7', 'G8', 'G10']);

/**
 * Engine persona for the VIEWER's role. The engine scopes gates per persona
 * (PRODUCER sees G0/G1/G3/G5/G9/G11 only) — requesting PRODUCER for everyone
 * made finance-gate deep links (G4/G6/G7/G8/G10) land on a view where the
 * gate doesn't exist. Executives see all gates; finance roles see theirs.
 */
function enginePersona(role: { business_function: string; service_type?: string | null }): string {
  if (role.business_function === 'EXECUTIVE') return 'EXECUTIVE';
  if (
    role.business_function === 'FINANCE_TREASURY' ||
    role.service_type === 'BANK' || role.service_type === 'DFI' || role.service_type === 'INSURER'
  ) return 'FINANCE';
  if (role.business_function === 'COMPLIANCE_LEGAL' || role.service_type === 'CERTIFIER') return 'REGULATOR';
  return 'PRODUCER';
}

interface ProducerBankabilityData {
  project_id: string;
  visible_gates: Gate[];
  overall_completion: number;
  unlocked_capital: string[];
  next_milestone: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function gateImprovementHint(gate: Gate): string {
  if (gate.is_complete) return 'Gate fully complete. No further action required.';
  const remaining = 100 - gate.completion_pct;
  const blocking  = gate.blocking_items.map(i => i.replace(/_/g, ' ')).join(', ');
  return `${gate.completion_pct}% → 100% (+${remaining} pts): ${blocking || 'remaining evidence items'} must be submitted and verified.`;
}

function statusMeta(status: string): { icon: React.ReactNode; badge: string } {
  switch (status) {
    case 'VERIFIED':
      return { icon: <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />, badge: 'gex-badge gex-badge-green' };
    case 'PRESUMED':
      // Registry-presumed, no evidence record — deliberately NOT green.
      return { icon: <Info className="w-3.5 h-3.5 text-[var(--text-muted)]" />, badge: 'gex-badge gex-badge-default' };
    case 'SUBMITTED':
    case 'UNDER_REVIEW':
      return { icon: <Clock className="w-3.5 h-3.5 text-amber-500" />,   badge: 'gex-badge gex-badge-amber' };
    case 'REJECTED':
    case 'EXPIRED':
      return { icon: <AlertCircle className="w-3.5 h-3.5 text-red-500" />,   badge: 'gex-badge gex-badge-red'   };
    default:
      return { icon: <Clock className="w-3.5 h-3.5 text-[var(--text-muted)]" />, badge: 'gex-badge gex-badge-default' };
  }
}

function progressColor(pct: number, complete: boolean): string {
  if (complete || pct >= 100) return 'bg-emerald-500';
  if (pct >= 75)              return 'bg-amber-400';
  return 'bg-brand-500';
}

function commitmentLabel(status: CommitmentStatus): { text: string; cls: string } {
  switch (status) {
    case 'DRAWN':          return { text: 'Drawn',           cls: 'gex-badge gex-badge-green'   };
    case 'LEGAL_COMPLETE': return { text: 'Docs signed',     cls: 'gex-badge gex-badge-green'   };
    case 'CREDIT_APPROVED':return { text: 'Credit approved', cls: 'gex-badge gex-badge-blue'    };
    case 'TERM_SHEET':     return { text: 'Term sheet',      cls: 'gex-badge gex-badge-amber'   };
    case 'INDICATIVE':     return { text: 'Indicative',      cls: 'gex-badge gex-badge-amber'   };
    default:               return { text: 'No engagement',   cls: 'gex-badge gex-badge-default' };
  }
}

/** Parse a EUR amount string like "€102M" → number in millions for summing */
function parseEurM(amount: string): number {
  const m = amount.replace(/[^0-9.]/g, '');
  return parseFloat(m) || 0;
}

// ─── Tooltip ──────────────────────────────────────────────────────────────────

function InfoTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [open]);

  return (
    <div ref={ref} className="relative inline-flex">
      <button
        className="inline-flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--brand)] transition-colors"
        onClick={() => setOpen(v => !v)}
        aria-label="Show improvement details"
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      {open && (
        <div className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 w-72 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-dropdown p-3 text-xs text-[var(--text-secondary)] leading-relaxed animate-fade-in">
          <button
            className="absolute top-2 right-2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            onClick={() => setOpen(false)}
          >
            <X className="w-3 h-3" />
          </button>
          {text}
        </div>
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function ProducerBankabilityView({ projectId: propProjectId }: { projectId?: string }) {
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject();
  const { role, authSession } = useUserRole();
  const { projects: visibleProjects } = useVisibleProjects();
  // Deep-link support: /producer-bankability?project=<id>&gate=<gateId>
  // (blocker traces from /projects land here on the EXACT gate they cited).
  const [searchParams] = useSearchParams();
  const gateParam = searchParams.get('gate');
  const projectParam = searchParams.get('project');
  const projectId = propProjectId ?? projectParam ?? selectedProjectId;
  const canonicalProject = visibleProjects.find(p => p.id === projectId);
  const canViewCapitalStack = role.business_function === 'FINANCE_TREASURY' || role.business_function === 'EXECUTIVE';

  const [data, setData]         = useState<ProducerBankabilityData | null>(null);
  const [loading, setLoading]   = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  // True when gates come from the static registry, not the engine. The user
  // must always be able to tell which truth they are looking at.
  const [isStaticFallback, setIsStaticFallback] = useState(false);

  // Evidence document upload — the Upload icon next to a row IS the way to
  // work a document-type evidence item. POST → stored content-addressed,
  // status moves to SUBMITTED (never auto-VERIFIED), transition audited.
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadTarget, setUploadTarget] = useState<string | null>(null);
  const [uploadingKey, setUploadingKey] = useState<string | null>(null);

  const startUpload = (evidenceKey: string) => {
    setUploadTarget(evidenceKey);
    fileInputRef.current?.click();
  };

  // F5: the Eye button opens the documents actually on file for an item —
  // a SUBMITTED claim must trace to its sha256-stored document, in one click.
  interface EvidenceDoc { evidence_key: string; filename: string; sha256: string; size_bytes: number; uploaded_by: string; uploaded_at: string }
  const [docsOpenFor, setDocsOpenFor] = useState<string | null>(null);
  const [docs, setDocs] = useState<EvidenceDoc[] | null>(null);

  const toggleDocs = async (evidenceKey: string) => {
    if (docsOpenFor === evidenceKey) { setDocsOpenFor(null); setDocs(null); return; }
    setDocsOpenFor(evidenceKey);
    setDocs(null);
    if (!authSession?.token) { setDocs([]); return; }
    try {
      const res = await fetch(
        `/api/v1/bankability/evidence/documents?project_id=${encodeURIComponent(projectId)}&evidence_key=${encodeURIComponent(evidenceKey)}`,
        { headers: { Authorization: `Bearer ${authSession.token}` } },
      );
      setDocs(res.ok ? (await res.json()).documents : []);
    } catch {
      setDocs([]);
    }
  };

  const onEvidenceFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !uploadTarget || !authSession?.token) { setUploadTarget(null); return; }
    setUploadingKey(uploadTarget);
    try {
      const fd = new FormData();
      fd.append('project_id', projectId);
      fd.append('evidence_key', uploadTarget);
      fd.append('file', file);
      const res = await fetch('/api/v1/bankability/evidence/document', {
        method: 'POST',
        headers: { Authorization: `Bearer ${authSession.token}` },
        body: fd,
      });
      if (res.ok) await load();
      else console.error('Evidence upload failed:', res.status, await res.text());
    } finally {
      setUploadingKey(null);
      setUploadTarget(null);
    }
  };

  useEffect(() => { load(); }, [projectId]);

  // Sync the global project selection to the deep-linked project.
  useEffect(() => {
    if (projectParam && projectParam !== selectedProjectId) setSelectedProjectId(projectParam);
  }, [projectParam]); // eslint-disable-line react-hooks/exhaustive-deps

  // Gate ids differ between the static project registry (G1_GRID_UTILITIES_REALITY)
  // and the backend bankability engine (G1_GRID_WATER). The shared taxonomy is
  // the gate NUMBER prefix (G0…G12), so deep links match exact id first, then
  // fall back to the prefix — the trace must never dead-end on a vocabulary gap.
  const gateMatches = (id: string) =>
    !!gateParam && (id === gateParam || id.split('_')[0] === gateParam.split('_')[0]);

  // Once gates are loaded, expand the deep-linked gate and scroll it into view.
  // A deep link that matches nothing must say so — never miss silently.
  const [gateParamMissed, setGateParamMissed] = useState(false);
  useEffect(() => {
    if (!gateParam || !data) return;
    const target =
      data.visible_gates.find(g => g.id === gateParam) ??
      data.visible_gates.find(g => gateMatches(g.id));
    if (target) {
      setGateParamMissed(false);
      setExpanded(target.id);
      requestAnimationFrame(() => {
        document.getElementById(`gate-row-${target.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    } else {
      setGateParamMissed(true);
    }
  }, [gateParam, data]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/bankability/projects/${projectId}/bankability/${enginePersona(role)}`, {
        headers: authSession?.token ? { Authorization: `Bearer ${authSession.token}` } : {},
      });
      if (res.ok) {
        const raw = await res.json();
        setData({
          project_id: raw.project_id,
          visible_gates: (raw.gate_evaluations || []).map((g: any) => ({
            id: g.gate_id,
            name: g.gate_name,
            total_evidence: g.total_evidence,
            verified_count: g.verified_count,
            completion_pct: Math.round(g.completion_pct || 0),
            is_complete: g.is_complete,
            blocking_items: g.blocking_items || [],
            premise_findings: g.premise_findings || [],
            financing_applicable: g.financing_applicable !== false,
            evidence_items: (g.evidence_detail || []).map((e: any) => ({
              key: e.key,
              status: e.status,
              applicable: e.applicable,
              severity: e.severity,
              label: e.label,
              section: e.section,
              section_label: e.section_label,
              applies_to: e.applies_to,
              owner_function: e.owner_function,
              blocked_action: e.blocked_action,
              route: e.route,
              submitted_by: e.submitted_by,
              verified_by: e.verified_by,
              submitted_at: e.submitted_at,
              verified_at: e.verified_at,
              notes: e.notes,
            })),
          })),
          overall_completion: Math.round(raw.overall_completion_pct || 0),
          unlocked_capital: (raw.capital_unlocks || [])
            .filter((c: any) => c.is_unlocked)
            .map((c: any) => c.capital_type),
          next_milestone: raw.gates_blocking_next_state?.length
            ? `Complete ${raw.gates_blocking_next_state.join(', ')} → ${raw.next_state || 'next state'}`
            : `Progressing to ${raw.next_state || 'next state'}`,
        });
        setIsStaticFallback(false);
      } else {
        // Fall back to canonical project data
        const bk = canonicalProject?.bankability;
        setData({
          project_id: projectId,
          visible_gates: (bk?.gates ?? []).map(g => ({
            id: g.id,
            name: g.name,
            total_evidence: g.total_evidence,
            verified_count: g.verified_count,
            completion_pct: g.completion_pct,
            is_complete: g.is_complete,
            blocking_items: g.blocking_items,
            evidence_items: g.blocking_items.map(key => ({ key, status: 'IN_PROGRESS' as const })),
            financing_applicable:
              (canonicalProject?.financing_model ?? 'PROJECT_FINANCE') !== 'BALANCE_SHEET' ||
              !LENDER_GATE_PREFIXES.has(g.id.split('_')[0]),
          })),
          overall_completion: bk?.overall_completion ?? 0,
          unlocked_capital: bk?.unlocked_capital ?? [],
          next_milestone: bk?.next_milestone ?? '',
        });
        setIsStaticFallback(true);
      }
    } catch (e) {
      console.error('Failed to load bankability data:', e);
      const bk = canonicalProject?.bankability;
      setData({
        project_id: projectId,
        visible_gates: (bk?.gates ?? []).map(g => ({
          id: g.id,
          name: g.name,
          total_evidence: g.total_evidence,
          verified_count: g.verified_count,
          completion_pct: g.completion_pct,
          is_complete: g.is_complete,
          blocking_items: g.blocking_items,
          evidence_items: g.blocking_items.map(key => ({ key, status: 'IN_PROGRESS' as const })),
          financing_applicable:
            (canonicalProject?.financing_model ?? 'PROJECT_FINANCE') !== 'BALANCE_SHEET' ||
            !LENDER_GATE_PREFIXES.has(g.id.split('_')[0]),
        })),
        overall_completion: bk?.overall_completion ?? 0,
        unlocked_capital: bk?.unlocked_capital ?? [],
        next_milestone: bk?.next_milestone ?? '',
      });
      setIsStaticFallback(true);
    }
    setLoading(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-7 w-7 rounded-full border-2 border-[var(--brand)] border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-[var(--text-muted)] gap-2">
        <FileText className="w-8 h-8 opacity-40" />
        <p className="text-sm">No bankability data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-fade-in">

      {/* Hidden file chooser backing the per-row Upload buttons */}
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.png,.jpg,.zip"
        onChange={onEvidenceFileChosen}
      />

      {/* Deep-link miss — say so instead of silently landing generic */}
      {gateParamMissed && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800 px-4 py-2.5">
          <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
          <p className="text-xs text-amber-800 dark:text-amber-300">
            Gate <span className="font-mono font-bold">{gateParam}</span> is not in your
            persona's gate view ({enginePersona(role)}). It is owned by another function —
            ask a Finance/Executive colleague, or switch role, to work it.
          </p>
        </div>
      )}

      {/* ── Data provenance — the user must know which truth they see ── */}
      {isStaticFallback && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800 px-4 py-2.5">
          <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
          <p className="text-xs text-amber-800 dark:text-amber-300">
            <span className="font-bold uppercase tracking-[0.08em]">Static fallback</span>
            {' '}— registry data, not engine-authoritative. Evidence statuses are presumed
            from the project registry; no evidence records were read. Sign in or restore
            the bankability engine (port 8001) for authoritative gate evaluations.
          </p>
        </div>
      )}

      {/* ── Project selector ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-3.5 shadow-card">
        <div className="min-w-0">
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Viewing bankability for</div>
          <div className="mt-0.5 font-display font-bold text-[var(--text-primary)] truncate">
            {canonicalProject?.name ?? projectId}
          </div>
          {canonicalProject && (
            <div className="text-xs text-[var(--text-muted)]">{canonicalProject.location} · {canonicalProject.molecule}</div>
          )}
        </div>
        <select
          value={projectId}
          onChange={e => setSelectedProjectId(e.target.value)}
          className="gex-select text-sm shrink-0"
          aria-label="Select project"
        >
          {visibleProjects.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* ── KPI strip ── */}
      {(() => {
        const completedGates  = data.visible_gates.filter(g => g.is_complete).length;
        const totalGates      = data.visible_gates.length;
        const firstIncomplete = data.visible_gates.find(g => !g.is_complete);
        const capitalItems    = canonicalProject?.bankability.capital_status ?? [];
        const unlockedEur     = capitalItems.filter(c => c.is_unlocked).reduce((s, c) => s + parseEurM(c.amount), 0);
        const totalEur        = capitalItems.reduce((s, c) => s + parseEurM(c.amount), 0);
        const phaseLabel      = canonicalProject?.phase ?? '';

        return (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {/* Overall completion */}
              <div className="col-span-2 sm:col-span-1 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4 shadow-card">
                <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Overall Completion</div>
                <div className="mt-1 font-display text-3xl font-extrabold leading-none text-[var(--brand)]">
                  {data.overall_completion}%
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--border)]">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${progressColor(data.overall_completion, false)}`}
                    style={{ width: `${data.overall_completion}%` }}
                  />
                </div>
                {phaseLabel && (
                  <p className="mt-1.5 text-[10px] text-[var(--text-muted)] truncate">{phaseLabel}</p>
                )}
                {data.overall_completion === 0 && (
                  <p className="mt-1 text-[10px] font-semibold text-amber-600 dark:text-amber-400">
                    Start by completing your first gate below
                  </p>
                )}
              </div>

              {/* Gates */}
              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4 shadow-card">
                <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Gates</div>
                <div className="mt-1 font-display text-2xl font-extrabold leading-none text-[var(--text-primary)]">
                  {completedGates}
                  <span className="text-base font-medium text-[var(--text-muted)]"> / {totalGates}</span>
                </div>
                {completedGates < totalGates && firstIncomplete && (
                  <p className="mt-1 text-[10px] text-[var(--text-muted)] leading-snug">
                    Next: <span className="font-semibold text-[var(--text-secondary)]">{firstIncomplete.name}</span>
                  </p>
                )}
                {completedGates === totalGates && totalGates > 0 && (
                  <p className="mt-1 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">All gates complete</p>
                )}
              </div>

              {/* Unlocked capital */}
              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4 shadow-card">
                <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Unlocked Capital</div>
                {totalEur > 0 ? (
                  <>
                    <div className="mt-1 font-display text-2xl font-extrabold leading-none text-emerald-600 dark:text-emerald-400">
                      €{unlockedEur.toFixed(0)}M
                    </div>
                    <p className="mt-1 text-[10px] text-[var(--text-muted)]">
                      of €{totalEur.toFixed(0)}M total stack
                    </p>
                    {unlockedEur === 0 && (
                      <p className="mt-0.5 text-[10px] font-semibold text-amber-600 dark:text-amber-400">
                        Complete gates to unlock
                      </p>
                    )}
                  </>
                ) : (
                  <div className="mt-1 font-display text-2xl font-extrabold leading-none text-[var(--text-muted)]">
                    {data.unlocked_capital.length}
                  </div>
                )}
              </div>
            </div>

            {/* Next milestone — journey card */}
            {data.next_milestone && (
              <div className="flex items-start gap-3 rounded-xl border border-[var(--brand-light,#e0f7f7)] bg-[var(--brand-light)] px-4 py-3">
                <ArrowRight className="w-4 h-4 mt-0.5 shrink-0 text-[var(--brand)]" />
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--brand)] mb-0.5">Next milestone</p>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{data.next_milestone}</p>
                  {firstIncomplete && firstIncomplete.blocking_items.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {firstIncomplete.blocking_items.slice(0, 3).map(item => (
                        <span key={item} className="gex-badge gex-badge-amber">{item.replace(/_/g, ' ')}</span>
                      ))}
                      {firstIncomplete.blocking_items.length > 3 && (
                        <span className="gex-badge gex-badge-default">+{firstIncomplete.blocking_items.length - 3} more</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Capital stack — Finance/Executive only */}
            {canViewCapitalStack && capitalItems.length > 0 && (
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
                <div className="flex items-center gap-2 border-b border-[var(--border)] px-5 py-3.5">
                  <TrendingUp className="w-4 h-4 text-[var(--brand)]" />
                  <h3 className="flex-1 text-sm font-bold text-[var(--text-primary)]">Capital Stack</h3>
                  <span className="text-[10px] text-[var(--text-muted)]">Finance & Executive view</span>
                </div>
                <div className="divide-y divide-[var(--border)]">
                  {capitalItems.map(cap => {
                    const { text: commitText, cls: commitCls } = commitmentLabel(cap.commitment_status);
                    return (
                      <div key={cap.type} className="flex items-center gap-3 px-5 py-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            {cap.is_unlocked
                              ? <Unlock className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                              : <Lock   className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />}
                            <p className="text-sm font-semibold text-[var(--text-primary)] truncate">{cap.name}</p>
                          </div>
                          {!cap.is_unlocked && cap.gating_gates.length > 0 && (
                            <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                              Requires: {cap.gating_gates.join(', ')}
                            </p>
                          )}
                          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-[var(--border)]">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${cap.is_unlocked ? 'bg-emerald-500' : progressColor(cap.progress_pct, false)}`}
                              style={{ width: `${cap.progress_pct}%` }}
                            />
                          </div>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="font-mono text-sm font-bold text-[var(--text-primary)]">{cap.amount}</p>
                          <span className={commitCls}>{commitText}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        );
      })()}

      <AdversarialReviewEntryCard
        projectId={projectId}
        actorType="PRODUCER"
        title="Producer challenge review"
      />

      {/* ── Financial Gates ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="flex items-center gap-2 border-b border-[var(--border)] px-5 py-3.5">
          <FileText className="w-4 h-4 text-[var(--brand)]" />
          <h3 className="flex-1 text-sm font-bold text-[var(--text-primary)]">Financial Gates</h3>
          <InfoTip text="Each gate groups the evidence documents required at this stage. Click the expand arrow to see individual items. The info icon shows exactly which documents are blocking and how many percentage points remain to 100%." />
        </div>

        <div className="divide-y divide-[var(--border)]">
          {data.visible_gates.map(gate => {
            const isOpen   = expanded === gate.id;
            const barColor = progressColor(gate.completion_pct, gate.is_complete);

            return (
              <div
                key={gate.id}
                id={`gate-row-${gate.id}`}
                className={gateMatches(gate.id) ? 'ring-1 ring-inset ring-[var(--brand,#0ea5a0)]' : undefined}
              >
                {/* Gate header row */}
                <div className={`flex items-start gap-3 px-5 py-4 ${gate.financing_applicable === false ? 'opacity-50' : ''}`}>
                  <div className="mt-0.5 flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className={`text-sm font-semibold text-[var(--text-primary)] ${gate.financing_applicable === false ? 'line-through' : ''}`}>{gate.name}</p>
                      <span className="text-[10px] font-mono text-[var(--text-muted)]">{gate.id}</span>
                      {gate.financing_applicable === false && (
                        <span className="gex-badge gex-badge-default" title="Lender-protection gate — waived under balance-sheet financing. Does not block state transitions or dilute completion.">
                          N/A · BALANCE SHEET
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">
                      {gate.financing_applicable === false
                        ? 'Out of scope — no external capital provider relies on this gate'
                        : `${gate.verified_count} of ${gate.total_evidence} applicable evidence items verified`}
                    </p>

                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--border)]">
                      <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${gate.completion_pct}%` }} />
                    </div>

                    {gate.blocking_items.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {gate.blocking_items.map(item => (
                          <span key={item} className="gex-badge gex-badge-red">{item.replace(/_/g, ' ')}</span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0 pt-0.5">
                    <span className="font-mono text-sm font-bold text-[var(--text-primary)]">{gate.completion_pct}%</span>
                    <InfoTip text={gateImprovementHint(gate)} />
                    {gate.is_complete
                      ? <CheckCircle className="w-4 h-4 text-emerald-500" />
                      : <AlertCircle className="w-4 h-4 text-amber-500" />}
                    <button
                      className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                      onClick={() => setExpanded(isOpen ? null : gate.id)}
                      aria-label="Toggle evidence detail"
                    >
                      {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Evidence items (expandable) */}
                {isOpen && (() => {
                  const projectPowerModel = (canonicalProject?.energy_input?.power_model ?? null) as PowerModel | null;
                  const projectStatus = canonicalProject?.status ?? null;
                  const gatePrefix = gate.id.split('_')[0];

                  // Resolve each item's policy view: server metadata wins
                  // (engine evidence_detail carries label/severity/applicable);
                  // the static catalog only fills gaps when the engine is down.
                  const resolve = (ev: EvidenceItem) => {
                    const fb = evidenceMetaFallback(ev.key, gatePrefix);
                    const appliesTo = ev.applies_to ?? fb.applies_to;
                    return {
                      label: ev.label ?? fb.label,
                      section: ev.section ?? fb.section,
                      section_label: ev.section_label ?? fb.section_label,
                      owner_function: ev.owner_function ?? fb.owner_function,
                      blocked_action: ev.blocked_action ?? fb.blocked_action,
                      route: ev.route ?? fb.route,
                      applicable: ev.applicable ?? appliesToModel(appliesTo as string[], projectPowerModel),
                      severity: ev.severity ?? effectiveSeverity(fb, projectStatus),
                    };
                  };

                  // Static fallback returns only blocking_items as evidence —
                  // synthesise the rest of THIS gate's required list from the
                  // catalog (matched by gate prefix) so the full requirement
                  // is always visible, never just the gaps. Synthesised items
                  // are PRESUMED, never VERIFIED: the registry counts them as
                  // non-blocking but no evidence record exists, and GEX must
                  // not display a verification it cannot trace. In server mode
                  // evidence_detail is complete and nothing is synthesised.
                  const items: EvidenceItem[] = [...gate.evidence_items];
                  const existingKeys = new Set(items.map(e => e.key));
                  for (const [k, m] of Object.entries(STATIC_EVIDENCE_CATALOG)) {
                    if (m.gate === gatePrefix && !existingKeys.has(k)) {
                      items.push({ key: k, status: 'PRESUMED' });
                    }
                  }

                  // Group by section.
                  const bySection = new Map<string, { label: string; items: EvidenceItem[] }>();
                  for (const ev of items) {
                    const r = resolve(ev);
                    const sKey = `${r.section}__${r.section_label}`;
                    if (!bySection.has(sKey)) bySection.set(sKey, { label: r.section_label, items: [] });
                    bySection.get(sKey)!.items.push(ev);
                  }
                  const sections = Array.from(bySection.entries()).sort(([a], [b]) => a.localeCompare(b));

                  return (
                    <div className="border-t border-[var(--border)] bg-[var(--surface-muted)] px-5 py-3 animate-fade-in">
                      {/* Premise findings — undeclared power model is a finding, not a default */}
                      {(gate.premise_findings ?? []).map(f => (
                        <div
                          key={f.code}
                          className={`mb-3 flex items-start gap-2 rounded-lg border px-3 py-2 ${
                            f.severity === 'deal_killer'
                              ? 'border-rose-300 bg-rose-50 dark:bg-rose-950/20 dark:border-rose-800'
                              : 'border-amber-300 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800'
                          }`}
                        >
                          <AlertCircle className={`w-4 h-4 shrink-0 mt-0.5 ${f.severity === 'deal_killer' ? 'text-rose-600' : 'text-amber-600'}`} />
                          <div className="min-w-0 text-xs">
                            <span className="font-bold uppercase tracking-[0.08em]">{f.code.replace(/_/g, ' ')}</span>
                            {' '}{severityBadge(f.severity)}
                            <p className="mt-0.5 text-[var(--text-secondary)] leading-snug">{f.message}</p>
                            {f.blocked_action && (
                              <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                                Blocks: <span className="font-medium">{f.blocked_action}</span>
                                {f.route && (
                                  <>
                                    {' '}
                                    <Link to={resolveEvidenceRoute(f.route, projectId)!} className="font-bold text-[var(--brand)] hover:underline">
                                      → DECLARE POWER MODEL
                                    </Link>
                                  </>
                                )}
                              </p>
                            )}
                          </div>
                        </div>
                      ))}

                      {/* Power model context banner */}
                      {gate.id.startsWith('G1') && projectPowerModel && (
                        <div className="mb-3 flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2">
                          <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">Power model</span>
                          <span className={`gex-badge ${
                            projectPowerModel === 'OFF_GRID_BTM' ? 'gex-badge-green'
                            : projectPowerModel === 'GRID_CONNECTED' ? 'gex-badge-blue'
                            : 'gex-badge-amber'
                          }`}>{projectPowerModel.replace(/_/g, ' ')}</span>
                          <span className="text-[10px] text-[var(--text-muted)]">
                            {projectPowerModel === 'OFF_GRID_BTM'
                              ? '— Power Access & PPA items not applicable. Focus: BTM generation asset, curtailment within owned system, water.'
                              : projectPowerModel === 'GRID_CONNECTED'
                              ? '— Grid interconnection AND ≥1 signed PPA required. Off-grid BTM items N/A.'
                              : '— Both grid access and BTM generation evidence required.'}
                          </span>
                        </div>
                      )}

                      {sections.map(([sKey, section]) => {
                        const sectionLabel = section.label;
                        const sectionId = sKey.split('__')[0];
                        return (
                          <div key={sKey} className="mb-3">
                            <div className="flex items-center gap-2 mb-1.5">
                              <span className="text-[9px] font-bold uppercase tracking-[0.14em] text-[var(--brand)] bg-[var(--brand-subtle,#e8f5f5)] px-1.5 py-0.5 rounded">{sectionId}</span>
                              <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">{sectionLabel}</span>
                            </div>
                            <div className="space-y-1.5">
                              {section.items.map(ev => {
                                const r = resolve(ev);
                                // PRESUMED = registry says non-blocking, no evidence
                                // record — neither verified nor a missing-item finding.
                                const missing = ev.status !== 'VERIFIED' && ev.status !== 'PRESUMED';
                                const { icon, badge } = statusMeta(ev.status);
                                // The resolver — not this screen — decides where
                                // "work it" goes and whether the viewer may act.
                                const resolved = resolveActionRoute(
                                  role,
                                  { kind: `evidence:${ev.key}`, preferred_route: r.route ?? undefined, owner_function: r.owner_function },
                                  projectId,
                                );
                                const docsOpen = docsOpenFor === ev.key;
                                return (
                                  <div key={ev.key} className="rounded-lg overflow-hidden">
                                  <div
                                    className={`flex items-center justify-between border px-3 py-2 ${docsOpen ? 'rounded-t-lg border-b-0' : 'rounded-lg'} ${
                                      !r.applicable
                                        ? 'border-dashed border-[var(--border)] bg-transparent opacity-50'
                                        : missing && r.severity === 'deal_killer'
                                        ? 'border-rose-200 bg-rose-50 dark:bg-rose-950/20 dark:border-rose-800'
                                        : 'border-[var(--border)] bg-[var(--surface)]'
                                    }`}
                                  >
                                    <div className="flex items-start gap-2 min-w-0">
                                      {r.applicable ? icon : <span className="w-3.5 h-3.5 text-[var(--text-muted)]">—</span>}
                                      <div className="min-w-0">
                                        <p className={`text-xs font-medium truncate ${r.applicable ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)] line-through'}`}>
                                          {r.label}
                                        </p>
                                        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                                          {r.applicable ? (
                                            <span className={badge}>
                                              {ev.status === 'PRESUMED' ? 'PRESUMED · NO EVIDENCE RECORD' : ev.status.replace(/_/g, ' ')}
                                            </span>
                                          ) : (
                                            <span className="gex-badge gex-badge-default">N/A · {projectPowerModel?.replace(/_/g, ' ') ?? 'POWER MODEL'}</span>
                                          )}
                                        </div>
                                        {/* Sung structure: consequence + way. Never a dead end. */}
                                        {r.applicable && missing && r.blocked_action && (
                                          <p className="text-[9px] text-[var(--text-muted)] mt-0.5 leading-snug">
                                            Blocks: <span className="font-medium text-[var(--text-secondary)]">{r.blocked_action}</span>
                                            {resolved.route && (
                                              <>
                                                {' '}
                                                <Link to={resolved.route} className="font-bold text-[var(--brand)] hover:underline whitespace-nowrap">
                                                  → WORK IT
                                                </Link>
                                              </>
                                            )}
                                            {resolved.status === 'forbidden' && resolved.owner_function && (
                                              <span className="whitespace-nowrap text-[var(--text-muted)]">
                                                {' '}· worked by <span className="font-semibold">{resolved.owner_function}</span>
                                              </span>
                                            )}
                                          </p>
                                        )}
                                      </div>
                                    </div>
                                    <div className="flex flex-col items-end gap-1 shrink-0 ml-2">
                                      {r.applicable && missing && severityBadge(r.severity)}
                                      <span className="text-[9px] text-[var(--text-muted)]">{r.owner_function}</span>
                                      <div className="flex gap-1">
                                        {ev.document_url && (
                                          <button className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--brand)] hover:bg-[var(--surface-hover)] transition-colors">
                                            <FileText className="w-3 h-3" />
                                          </button>
                                        )}
                                        {r.applicable && (ev.status === 'NOT_STARTED' || ev.status === 'REJECTED' || ev.status === 'IN_PROGRESS') ? (
                                          <button
                                            className="p-1 rounded text-[var(--text-muted)] hover:text-emerald-600 hover:bg-[var(--surface-hover)] transition-colors disabled:opacity-40"
                                            onClick={() => startUpload(ev.key)}
                                            disabled={!authSession?.token || uploadingKey !== null}
                                            title={authSession?.token
                                              ? 'Upload evidence document (sha256-stored, audited, → SUBMITTED)'
                                              : 'Sign in to upload evidence'}
                                            aria-label={`Upload document for ${r.label}`}
                                          >
                                            {uploadingKey === ev.key
                                              ? <span className="inline-block w-3 h-3 rounded-full border border-emerald-500 border-t-transparent animate-spin" />
                                              : <Upload className="w-3 h-3" />}
                                          </button>
                                        ) : r.applicable ? (
                                          <button
                                            className={`p-1 rounded hover:bg-[var(--surface-hover)] transition-colors ${docsOpen ? 'text-[var(--brand)]' : 'text-[var(--text-muted)] hover:text-[var(--brand)]'}`}
                                            onClick={() => toggleDocs(ev.key)}
                                            title="View documents on file for this evidence item"
                                            aria-label={`View documents for ${r.label}`}
                                          >
                                            <Eye className="w-3 h-3" />
                                          </button>
                                        ) : null}
                                      </div>
                                    </div>
                                  </div>
                                  {/* F5: inline document panel — a SUBMITTED claim traces to its sha256-stored evidence */}
                                  {docsOpen && (
                                    <div className="rounded-b-lg border border-t-0 border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2">
                                      {docs === null ? (
                                        <p className="text-[10px] text-[var(--text-muted)]">Loading documents…</p>
                                      ) : docs.length === 0 ? (
                                        <p className="text-[10px] text-[var(--text-muted)]">
                                          {authSession?.token ? 'No documents on file. Use the upload button to attach evidence.' : 'Sign in to view documents.'}
                                        </p>
                                      ) : (
                                        <ul className="space-y-1">
                                          {docs.map(doc => (
                                            <li key={doc.sha256} className="flex items-center justify-between gap-2 text-[10px]">
                                              <a
                                                href={`/api/v1/bankability/evidence/document/${doc.sha256}/download`}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="flex items-center gap-1 min-w-0 text-[var(--brand)] hover:underline"
                                              >
                                                <FileText className="w-3 h-3 shrink-0" />
                                                <span className="truncate font-medium">{doc.filename}</span>
                                              </a>
                                              <span className="shrink-0 font-mono text-[var(--text-muted)]">
                                                {(doc.size_bytes / 1024).toFixed(1)} KB · {doc.sha256.slice(0, 8)} · {doc.uploaded_by}
                                              </span>
                                            </li>
                                          ))}
                                        </ul>
                                      )}
                                    </div>
                                  )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
