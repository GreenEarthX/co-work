// Screen: Finance bankability view screen (/finance-bankability, /finance/bankability)
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CheckCircle, AlertTriangle, DollarSign, Shield, FileCheck,
  TrendingUp, Lock, Unlock, Info, X, ChevronDown, ChevronUp,
  Activity, ShieldAlert,
} from 'lucide-react';
import { type CustomerProject } from '@/data/customerProjects';
import { useVisibleProjects } from '@/hooks/useVisibleProjects';
import { useSelectedProject } from '@/contexts/ProjectContext';
import { InfoTooltip } from '@/components/ui/InfoTooltip';
import {
  StateStrip, BRIDGE_STATES,
  CapitalEligibilityBar, tranchesFromProject,
} from '@/components/primitives';

// ─── Types ────────────────────────────────────────────────────────────────────

interface CapitalType {
  type: string;
  name: string;
  amount: string;
  is_unlocked: boolean;
  gating_gates: string[];
  progress_pct: number;
}

interface FinanceGate {
  id: string;
  name: string;
  total_evidence: number;
  verified_count: number;
  completion_pct: number;
  is_complete: boolean;
  blocking_items: string[];
  icon: string;
  description: string;
}

interface FinanceBankabilityData {
  project_id: string;
  visible_gates: FinanceGate[];
  capital_status: CapitalType[];
  overall_completion: number;
  total_unlocked_amount: string;
  next_unlock_milestone: string;
  risk_alerts: string[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Static descriptors used ONLY when a capital row has zero gating gates
// (unconditional path).  No live percentages embedded — those would
// contradict the actual gate completion shown elsewhere.
// When gating gates exist, capitalImprovementHint() computes a causal
// message from the binding gate instead.
const CAPITAL_IMPROVEMENTS: Record<string, string> = {
  PROJECT_EQUITY:        'Unlocks once bankable offtake (G4) and EPC risk pricing (G5) are evidenced.',
  STRATEGIC_EQUITY:      'Unlocks on bankable offtake (G4).',
  SENIOR_DEBT_COMMITMENT:'Unlocks on IE sign-off (G6), insurance (G7), audited model (G8) and permits (G9).',
  DFI_MEZZ_GUARANTEES:   'Unlocks on EPC risk pricing (G5) and IE sign-off (G6).',
  DEBT_DRAWDOWN:         'Releases on financial close (G10) — CP checklist satisfied, equity injected, DSRA funded.',
  REFINANCE_BONDS_INFRA: 'Available after COD + 6–12 months stable operations (G11).',
  GRANTS_TA:             'Disburses on proven site control (G0).',
  SEED_VC_ANGEL:         'Releases on site (G0), grid (G1), certification path (G2) or input strategy (G3).',
};

// ─── Causal gate → capital mapping ──────────────────────────────────────────
// MUST mirror backend bankability_engine.py GATE_REGISTRY (lines 142–224).
// Keys   = canonical backend gate IDs (12 total: G0–G11).
// Values = canonical backend CapitalType enum members (8 total).
// Seed data in customerProjects.ts now uses the same canonical names, so no
// aliases are needed.  Re-add aliases here only if external producers begin
// emitting non-canonical CapitalType labels.
const GATE_CAPITAL_REASON: Record<string, Record<string, string>> = {
  G0_SITE_RIGHTS: {
    GRANTS_TA:              'Grant disbursement requires proven site control (land, zoning, stakeholder)',
    SEED_VC_ANGEL:          'Early equity requires site feasibility proof',
  },
  G1_GRID_UTILITIES_REALITY: {
    SEED_VC_ANGEL:          'Grid deliverability (interconnection, queue, water) underpins early-stage technical risk',
  },
  G2_CERTIFICATION_PATH_LOCKED: {
    SEED_VC_ANGEL:          'Locked certification route (RFNBO/GoO/ISCC) anchors revenue eligibility',
  },
  G3_INPUTS_SECURED: {
    SEED_VC_ANGEL:          'Secured power, CO₂/biomass and logistics strategy de-risk OPEX',
  },
  G4_OFFTAKE_BANKABLE: {
    STRATEGIC_EQUITY:       'Strategic investors require bankable offtake before commitment',
    PROJECT_EQUITY:         'Project equity release depends on contracted revenue visibility',
  },
  G5_EPC_RISK_PRICED: {
    PROJECT_EQUITY:         'Equity call requires fixed-price EPC with performance guarantees',
    DFI_MEZZ_GUARANTEES:    'DFI coverage needs EPC risk transferred before guarantee issuance',
  },
  G6_IE_SIGNOFF: {
    DFI_MEZZ_GUARANTEES:    'Independent engineer sign-off validates technical + cost assumptions',
    SENIOR_DEBT_COMMITMENT: 'Lenders require IE validation before credit committee submission',
  },
  G7_INSURANCE_BOUND: {
    SENIOR_DEBT_COMMITMENT: 'Bound insurance (CAR/EAR, DSU, liability) is a condition precedent for debt',
  },
  G8_AUDIT_GRADE_MODEL: {
    SENIOR_DEBT_COMMITMENT: 'Audited financial model (CFADS, DSCR) required for credit approval',
  },
  G9_PERMITS_SAFE: {
    SENIOR_DEBT_COMMITMENT: 'Permit completeness eliminates regulatory risk for lenders',
  },
  G10_FINANCIAL_CLOSE_CP: {
    DEBT_DRAWDOWN:          'All conditions precedent satisfied — security package perfected',
  },
  G11_COD_STABILIZATION: {
    REFINANCE_BONDS_INFRA:  'Refinancing requires proven operations (6–12 months stable)',
  },
};

function capitalImprovementHint(
  type: string,
  pct: number,
  gatingGateIds: string[],
  visibleGates: FinanceGate[],
): string {
  if (pct >= 100) return 'All requirements met. This capital type is unlocked.';
  if (gatingGateIds.length === 0) {
    return CAPITAL_IMPROVEMENTS[type] ?? 'Unconditional — no gating gates configured.';
  }
  // Find the binding gate (the one driving the current % — lowest completion among gating gates)
  const ranked = gatingGateIds
    .map(gid => visibleGates.find(g => g.id === gid))
    .filter((g): g is FinanceGate => !!g)
    .sort((a, b) => a.completion_pct - b.completion_pct);
  if (ranked.length === 0) return `Awaiting evidence on ${gatingGateIds.join(', ')}.`;
  const binding = ranked[0];
  const items = binding.blocking_items.slice(0, 3).map(i => i.replace(/_/g, ' ')).join(', ');
  const more = binding.blocking_items.length > 3 ? `, +${binding.blocking_items.length - 3} more` : '';
  return `Blocked by ${binding.name} (${binding.completion_pct}%). Submit: ${items || 'remaining evidence'}${more}.`;
}

function gateImprovementHint(gate: FinanceGate): string {
  if (gate.is_complete) return 'Gate fully complete. No action required.';
  const remaining = 100 - gate.completion_pct;
  const items = gate.blocking_items.map(i => i.replace(/_/g, ' ')).join(', ');
  return `${gate.completion_pct}% → 100% (+${remaining} pts): Submit and verify — ${items || 'remaining evidence items'}.`;
}

/**
 * Resolve the BINDING gate for a capital tranche — the lowest-completion
 * gating gate.  This is the gate the user must clear to advance unlock %.
 * Returns null when there are no gating gates (unconditional capital).
 */
function bindingGate(gatingGateIds: string[], visibleGates: FinanceGate[]): FinanceGate | null {
  const ranked = gatingGateIds
    .map(gid => visibleGates.find(g => g.id === gid))
    .filter((g): g is FinanceGate => !!g)
    .sort((a, b) => a.completion_pct - b.completion_pct);
  return ranked[0] ?? null;
}

function gateIcon(iconStr: string) {
  const map: Record<string, React.ReactNode> = {
    '📋': <FileCheck className="w-4 h-4" />,
    '🛡️': <Shield    className="w-4 h-4" />,
    '📊': <TrendingUp className="w-4 h-4" />,
    '💰': <DollarSign className="w-4 h-4" />,
  };
  return map[iconStr] ?? <FileCheck className="w-4 h-4" />;
}

function bridgeStateFromProject(project: CustomerProject | undefined, overallPct: number): string {
  if (!project) return 'identified'
  if (project.status === 'operating') return 'drawn'
  if (project.status === 'construction' || project.status === 'commissioning') return overallPct >= 80 ? 'drawable' : 'committed'
  // development
  if (overallPct >= 80) return 'eligible'
  if (overallPct >= 60) return 'evidenced'
  if (overallPct >= 40) return 'costed'
  if (overallPct >= 20) return 'scoped'
  return 'identified'
}

function progressColor(pct: number, unlocked: boolean) {
  if (unlocked || pct >= 100) return 'bg-emerald-500';
  if (pct >= 75)              return 'bg-amber-400';
  return 'bg-brand-500';
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

// ─── Fallback builder ─────────────────────────────────────────────────────────

/**
 * Capital progress per Bridge Doctrine §E.2:
 * "Capital is released because a condition has been met, not because a project exists."
 *
 * Causal rule (Hidalgo entropy + Sung causal compression):
 * - With NO gating gates → unconditional (100%)
 * - With gating gates → progress = MAX(gating_gate.completion_pct)
 *   (since unlock fires when ANY gating gate completes, per backend
 *   bankability_engine.compute_capital_unlocks)
 *
 * This guarantees the displayed % traces back to a specific gate's
 * evidence — no acausal numbers.
 */
function computeCapitalProgress(
  gatingGateIds: string[],
  visibleGates: FinanceGate[],
): number {
  if (gatingGateIds.length === 0) return 100;
  const pcts = gatingGateIds.map(gid => {
    const g = visibleGates.find(x => x.id === gid);
    return g?.completion_pct ?? 0;
  });
  return Math.max(0, ...pcts);
}

function buildFallback(projectId: string, project: CustomerProject | undefined): FinanceBankabilityData {
  const bk = project?.bankability;
  const GATE_ICONS: Record<string, string> = {
    G4_OFFTAKE_BANKABLE: '📋', G7_INSURANCE_BOUND: '🛡️',
    G8_AUDIT_GRADE_MODEL: '📊', G10_FINANCIAL_CLOSE_CP: '💰',
    G0_SITE_RIGHTS: '📋', G1_GRID_UTILITIES: '⚡',
    G3_TECH_VENDOR_LOCKED: '🔧', G11_GHG_VERIFIED: '🌿',
  };
  const visibleGates = (bk?.gates ?? []).map(g => ({
    id: g.id, name: g.name,
    total_evidence: g.total_evidence, verified_count: g.verified_count,
    completion_pct: g.completion_pct, is_complete: g.is_complete,
    blocking_items: g.blocking_items,
    icon: GATE_ICONS[g.id] ?? '📋',
    description: g.description,
  }));
  return {
    project_id: projectId,
    visible_gates: visibleGates,
    capital_status: (bk?.capital_status ?? []).map(c => ({
      type: c.type, name: c.name, amount: c.amount,
      is_unlocked: c.is_unlocked,
      gating_gates: c.gating_gates,
      // Causal: progress = max gating gate completion (NOT seed value)
      progress_pct: computeCapitalProgress(c.gating_gates, visibleGates),
    })),
    overall_completion: bk?.overall_completion ?? 0,
    total_unlocked_amount: (bk?.capital_status ?? []).filter(c => c.is_unlocked).map(c => c.amount).join(' + ') || '—',
    next_unlock_milestone: bk?.next_milestone ?? '',
    risk_alerts: bk?.risk_alerts ?? [],
  };
}

// ─── Main component ───────────────────────────────────────────────────────────

export function FinanceBankabilityView({ projectId: propProjectId }: { projectId?: string }) {
  const navigate = useNavigate();
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject();
  const { projects: visibleProjects } = useVisibleProjects();
  const projectId = propProjectId ?? selectedProjectId;
  const canonicalProject = visibleProjects.find(p => p.id === projectId);

  /**
   * Open the Data Room with a deep-link query so the user lands on the
   * specific gate's evidence bucket and the named document needed.
   * This closes the dead-end the icon used to be.
   */
  const openEvidence = (gateId: string, evidenceKey: string) => {
    const qs = new URLSearchParams({ gate: gateId, evidence: evidenceKey }).toString();
    navigate(`/finance/data-room?${qs}`);
  };

  const [data, setData]           = useState<FinanceBankabilityData | null>(null);
  const [loading, setLoading]     = useState(true);
  const [expanded, setExpanded]   = useState<string | null>(null);
  const [expandedGate, setExpandedGate] = useState<string | null>(null);
  const gateRowRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Causal navigation: open a gate row and scroll it into view.
  // Triggered from the Capital Unlock expanded panel so users can trace
  // a capital % back to the gate's actual blocking evidence.
  const jumpToGate = (gateId: string) => {
    setExpandedGate(gateId);
    requestAnimationFrame(() => {
      const el = gateRowRefs.current[gateId];
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  };

  useEffect(() => { load(); }, [projectId]);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/bankability/projects/${projectId}/bankability/FINANCE`);
      if (res.ok) {
        const raw = await res.json();
        const visibleGates = (raw.gate_evaluations || []).map((g: any) => ({
          id: g.gate_id,
          name: g.gate_name,
          total_evidence: g.total_evidence,
          verified_count: g.verified_count,
          completion_pct: Math.round(g.completion_pct || 0),
          is_complete: g.is_complete,
          blocking_items: g.blocking_items || [],
          icon: '📋',
          description: g.owners?.length ? `${g.owners.join(', ')} gate` : '',
        }));
        setData({
          project_id: raw.project_id,
          visible_gates: visibleGates,
          capital_status: (raw.capital_unlocks || []).map((c: any) => {
            const gatingGates: string[] = c.gating_gates || [];
            // Causal: progress = max gating gate completion (anchors UI to evidence)
            const progressPct = computeCapitalProgress(gatingGates, visibleGates);
            return {
              type: c.capital_type,
              name: c.capital_type.replace(/_/g, ' '),
              amount: 'N/A',
              is_unlocked: c.is_unlocked,
              gating_gates: gatingGates,
              progress_pct: progressPct,
            };
          }),
          overall_completion: Math.round(raw.overall_completion_pct || 0),
          total_unlocked_amount: `${(raw.capital_unlocks || []).filter((c: any) => c.is_unlocked).length} unlocked`,
          next_unlock_milestone: raw.gates_blocking_next_state?.length
            ? `Complete ${raw.gates_blocking_next_state.join(', ')} → ${raw.next_state || 'next state'}`
            : `Progressing to ${raw.next_state || 'next state'}`,
          risk_alerts: raw.regression ? [String(raw.regression)] : [],
        });
      } else {
        setData(buildFallback(projectId, canonicalProject));
      }
    } catch (e) {
      console.error('Failed to load bankability data:', e);
      setData(buildFallback(projectId, canonicalProject));
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
        <DollarSign className="w-8 h-8 opacity-40" />
        <p className="text-sm">No finance bankability data available</p>
      </div>
    );
  }

  const unlockedCount = data.capital_status.filter(c => c.is_unlocked).length;

  return (
    <div className="space-y-4 animate-fade-in">

      {/* ── Project selector ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-3.5 shadow-card">
        <div className="min-w-0">
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Finance bankability</div>
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

      {/* ── E.1 State Strip + E.2 Capital Eligibility Bar ── */}
      {canonicalProject && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-3 shadow-card space-y-3">
          <StateStrip
            states={BRIDGE_STATES}
            activeState={bridgeStateFromProject(canonicalProject, data.overall_completion)}
            verificationState={
              data.overall_completion >= 80 ? 'CONFIRMED'
              : data.overall_completion >= 40 ? 'SUBMITTED'
              : 'UNVERIFIED'
            }
            compact
          />
          <CapitalEligibilityBar
            tranches={tranchesFromProject(
              canonicalProject,
              (canonicalProject.bankability?.gates ?? []).filter(g => g.is_complete).map(g => g.id),
            )}
            currentPhase={canonicalProject.status}
            showLegend
          />
        </div>
      )}

      {/* ── KPI strip ── */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Gates Complete',     value: `${data.overall_completion}%`, accent: 'text-[var(--brand)]' },
          { label: 'Capital Unlocked',   value: `${unlockedCount} / ${data.capital_status.length}`, accent: 'text-emerald-600 dark:text-emerald-400' },
          { label: 'Risk Alerts',        value: String(data.risk_alerts.length), accent: data.risk_alerts.length ? 'text-amber-600 dark:text-amber-400' : 'text-[var(--text-muted)]' },
        ].map(({ label, value, accent }) => (
          <div key={label} className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 shadow-card">
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">{label}</div>
            <div className={`mt-1 font-display text-2xl font-extrabold leading-none ${accent}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Risk alerts ── */}
      {data.risk_alerts.length > 0 && (
        <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-800/40 dark:bg-amber-900/15">
          <AlertTriangle className="mt-0.5 w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="space-y-0.5">
            {data.risk_alerts.map((a, i) => (
              <p key={i} className="text-xs text-amber-700 dark:text-amber-300">{a}</p>
            ))}
          </div>
        </div>
      )}

      {/* ── Next milestone ── */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--brand-light)] px-4 py-2.5">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--brand)]">Next milestone · </span>
        <span className="text-xs text-[var(--text-secondary)]">{data.next_unlock_milestone}</span>
      </div>

      {/* ── Two-column layout ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">

        {/* Capital Unlock Status */}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
          <div className="flex items-center gap-2 border-b border-[var(--border)] px-5 py-3.5">
            <h3 className="flex-1 text-sm font-bold text-[var(--text-primary)]">Capital Unlock Status</h3>
            <InfoTip text="Each capital type below unlocks when its gating gates reach 100%. The info icon on each row shows exactly what evidence is still needed and how far you are from the unlock threshold." />
          </div>

          <div className="divide-y divide-[var(--border)]">
            {data.capital_status.map(cap => {
              const barColor = progressColor(cap.progress_pct, cap.is_unlocked);
              const isOpen   = expanded === cap.type;
              const binding  = bindingGate(cap.gating_gates, data.visible_gates);
              return (
                <div key={cap.type}>
                  <div className="flex items-center gap-3 px-5 py-3.5">
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${cap.is_unlocked ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-[var(--surface-muted)] text-[var(--text-muted)]'}`}>
                      {cap.is_unlocked ? <Unlock className="w-4 h-4" /> : <Lock className="w-4 h-4" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-[var(--text-primary)] truncate">{cap.name}</span>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="font-mono text-xs font-bold text-[var(--text-primary)]">{cap.progress_pct}%</span>
                          <InfoTip text={capitalImprovementHint(cap.type, cap.progress_pct, cap.gating_gates, data.visible_gates)} />
                          {cap.is_unlocked ? (
                            <span className="text-emerald-600 dark:text-emerald-400" title="Evidence threshold met">
                              <CheckCircle className="w-4 h-4" />
                            </span>
                          ) : binding ? (
                            // Document affordance — represents the specific evidence
                            // packet required by the binding gate.  Click goes
                            // straight to the first missing document in the Data
                            // Room.  The count (verified/total) makes the document
                            // burden explicit before the user even hovers.
                            (() => {
                              const firstMissing = binding.blocking_items[0];
                              const docTitle = firstMissing
                                ? `Open "${firstMissing.replace(/_/g, ' ')}" in Data Room (${binding.verified_count}/${binding.total_evidence} verified for ${binding.name})`
                                : `Open ${binding.name} in Data Room (${binding.verified_count}/${binding.total_evidence} verified)`;
                              return (
                                <button
                                  onClick={() => openEvidence(binding.id, firstMissing ?? '')}
                                  className="flex items-center gap-0.5 text-[var(--brand)] hover:underline font-mono"
                                  title={docTitle}
                                  aria-label={docTitle}
                                >
                                  <FileCheck className="w-4 h-4" />
                                  <span className="text-[9px] tabular-nums">
                                    {binding.verified_count}/{binding.total_evidence}
                                  </span>
                                  <span className="text-[10px]">→</span>
                                </button>
                              );
                            })()
                          ) : (
                            <span className="text-[var(--text-muted)]" title="No gating gate — unconditional capital">
                              <FileCheck className="w-4 h-4 opacity-40" />
                            </span>
                          )}
                        </div>
                      </div>
                      {/* Lock cause — visible without hover.
                          ABAC governs visibility (row appears = you have access).
                          Lock here means evidence threshold not met on the binding gate. */}
                      {!cap.is_unlocked && binding && (
                        <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                          Locked by{' '}
                          <button
                            onClick={() => jumpToGate(binding.id)}
                            className="text-[var(--brand)] hover:underline font-medium"
                          >
                            {binding.name} ({binding.completion_pct}%)
                          </button>
                        </p>
                      )}
                      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]">
                        <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${cap.progress_pct}%` }} />
                      </div>
                      <div className="mt-1 flex items-center justify-between">
                        <span className="text-[10px] text-[var(--text-muted)]">{cap.amount}</span>
                        {cap.is_unlocked
                          ? <span className="gex-badge gex-badge-green">Unlocked</span>
                          : <span className="gex-badge gex-badge-default">{100 - cap.progress_pct}% remaining</span>}
                      </div>
                    </div>
                    <button
                      className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                      onClick={() => setExpanded(isOpen ? null : cap.type)}
                      aria-label="Toggle gate details"
                    >
                      {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>

                  {/* Inline gate breakdown with causal chain + evidence items */}
                  {isOpen && (
                    <div className="border-t border-[var(--border)] bg-[var(--surface-muted)] px-5 py-3 space-y-3 animate-fade-in">
                      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Required gates</p>
                      {cap.gating_gates.length === 0 && (
                        <p className="text-xs text-emerald-600 dark:text-emerald-400 italic">No gating gates — capital pre-approved or unconditional.</p>
                      )}
                      {cap.gating_gates.map(gid => {
                        const g = data.visible_gates.find(x => x.id === gid);
                        const pct = g?.completion_pct ?? 0;
                        const reason = GATE_CAPITAL_REASON[gid]?.[cap.type];
                        return (
                          <div key={gid} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
                            <div className="flex items-center justify-between">
                              <button
                                onClick={() => g && jumpToGate(g.id)}
                                disabled={!g}
                                className="text-xs font-semibold text-[var(--brand)] hover:underline disabled:text-[var(--text-muted)] disabled:cursor-not-allowed disabled:no-underline text-left flex items-center gap-1"
                                title={g ? `Open ${g.name} in Financial Gates →` : 'Gate not visible to your role'}
                              >
                                {g?.name ?? gid}
                                {g && <span className="text-[10px]">→</span>}
                              </button>
                              <div className="flex items-center gap-1.5">
                                <span className={`font-mono text-xs font-bold ${pct >= 100 ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}`}>
                                  {pct}%
                                </span>
                                <span className="text-[10px] text-[var(--text-muted)]">{g ? `${g.verified_count}/${g.total_evidence}` : ''}</span>
                              </div>
                            </div>
                            {/* Causal reason */}
                            {reason && (
                              <p className="mt-1 text-[10px] text-[var(--brand)] leading-relaxed italic">{reason}</p>
                            )}
                            {/* Progress micro-bar */}
                            <div className="mt-1.5 h-1 w-full rounded-full bg-[var(--border)]">
                              <div className={`h-full rounded-full transition-all duration-500 ${pct >= 100 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-400' : 'bg-brand-500'}`} style={{ width: `${pct}%` }} />
                            </div>
                            {/* Blocking items detail — each item links to the Data Room
                                pre-filtered to that gate + evidence key, so the user has
                                a concrete path: see what's missing → upload/verify it. */}
                            {g && g.blocking_items.length > 0 && (
                              <div className="mt-2 space-y-1">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Missing evidence</p>
                                {g.blocking_items.map(item => (
                                  <button
                                    key={item}
                                    onClick={() => openEvidence(g.id, item)}
                                    className="flex w-full items-center gap-2 text-[11px] text-left hover:bg-[var(--surface-muted)] rounded px-1 py-0.5 group"
                                    title={`Open ${item.replace(/_/g, ' ')} in Data Room`}
                                  >
                                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                                    <span className="text-[var(--text-secondary)] group-hover:text-[var(--brand)] group-hover:underline">
                                      {item.replace(/_/g, ' ')}
                                    </span>
                                    <span className="ml-auto text-[10px] text-[var(--text-muted)] group-hover:text-[var(--brand)]">→ Data Room</span>
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Financial Gates */}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
          <div className="flex items-center gap-2 border-b border-[var(--border)] px-5 py-3.5">
            <FileCheck className="w-4 h-4 text-[var(--brand)]" />
            <h3 className="flex-1 text-sm font-bold text-[var(--text-primary)]">Financial Gates</h3>
            <InfoTip text="Financial gates are evidence checkpoints your project must pass to unlock capital. Each gate has a set of required documents — the info icon on each gate shows what's still blocking and how many percentage points remain." />
          </div>

          <div className="divide-y divide-[var(--border)]">
            {data.visible_gates.map(gate => {
              const barColor = progressColor(gate.completion_pct, gate.is_complete);
              const gateOpen = expandedGate === gate.id;
              return (
                <div
                  key={gate.id}
                  ref={(el) => { gateRowRefs.current[gate.id] = el; }}
                  className={`px-5 py-4 transition-colors ${gateOpen ? 'bg-[var(--brand-soft,rgba(14,165,160,0.06))]' : ''}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-2.5 min-w-0">
                      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-muted)] text-[var(--text-secondary)]">
                        {gateIcon(gate.icon)}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-[var(--text-primary)] leading-tight">{gate.name}</p>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5 truncate">{gate.description}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="font-mono text-sm font-bold text-[var(--text-primary)]">{gate.completion_pct}%</span>
                      <InfoTip text={gateImprovementHint(gate)} />
                      {gate.is_complete
                        ? <CheckCircle className="w-4 h-4 text-emerald-500" />
                        : <div className="text-[10px] font-mono text-[var(--text-muted)]">{gate.verified_count}/{gate.total_evidence}</div>}
                      <button
                        className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                        onClick={() => setExpandedGate(gateOpen ? null : gate.id)}
                        aria-label="Toggle blocking items"
                      >
                        {gateOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]">
                    <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${gate.completion_pct}%` }} />
                  </div>

                  {gateOpen && gate.blocking_items.length > 0 && (
                    <div className="mt-2 space-y-1 animate-fade-in">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Blocking evidence</p>
                      {gate.blocking_items.map(item => (
                        <button
                          key={item}
                          onClick={() => openEvidence(gate.id, item)}
                          className="flex w-full items-center gap-2 text-[11px] text-left hover:bg-[var(--surface-muted)] rounded px-1 py-0.5 group"
                          title={`Open ${item.replace(/_/g, ' ')} in Data Room`}
                        >
                          <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                          <span className="text-red-600 dark:text-red-400 font-medium group-hover:underline">
                            {item.replace(/_/g, ' ')}
                          </span>
                          <span className="ml-auto text-[10px] text-[var(--text-muted)] group-hover:text-[var(--brand)]">→ Data Room</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Pre-COD Metrics (§4.6) ── */}
      <PreCODMetricsPanel
        visibleGates={data.visible_gates}
        capitalStatus={data.capital_status}
        projectId={data.project_id}
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// PRE-COD METRICS PANEL (Bridge Doc v3.1)
// 4 GEX-native + 2 standard PF. DSCR demoted to footnote.
// ═══════════════════════════════════════════════════════════════

/**
 * Pre-COD metric definition with full causal lineage.
 *
 * Anti-entropy doctrine (Hidalgo) + auditability (Bloomberg/Kiodex):
 * every displayed value MUST trace to:
 *   - a formula (plain-language)
 *   - numerator + denominator with concrete numbers (when computable)
 *   - source endpoints / tables / gates that fed those numbers
 *   - the project ID the value was derived for
 *
 * `computed` distinguishes live-derived from awaiting-live-engine.
 */
interface ReadingBand {
  status: 'HEALTHY' | 'CAUTION' | 'CONCERN' | 'BLOCKED';
  range: string;        // e.g. "≥ 85%", "65 – 85%", "< 45%"
}

interface MetricComponent {
  label: string;        // e.g. "G5  EPC Risk Priced"
  verified: number;     // contribution to numerator
  total: number;        // contribution to denominator
  note?: string;        // e.g. "not yet visible to your role" when visibility-blocked
}

interface MetricLineage {
  // ── Bloomberg-style help (the WHAT and WHY) ──
  definition: string;        // one-sentence plain English
  formulaPretty: string;     // proper math notation, mono-spaced
  whyItMatters: string;      // economic/decision intuition
  decisionRule: string;      // what happens at threshold
  readingBands: ReadingBand[];

  // ── Causal inputs (the HOW) ──
  components: MetricComponent[];  // per-input breakdown that sums to numerator/denominator
  numerator: number | null;
  numeratorLabel: string;
  denominator: number | null;
  denominatorLabel: string;

  // ── Provenance (the FROM WHERE) ──
  sources: string[];
  projectId: string;
  computed: 'LIVE' | 'PARTIAL' | 'PENDING_ENGINE';
  pendingReason?: string;
}

interface PreCODMetric {
  id: string;
  label: string;
  value: number;
  unit: string;
  status: 'HEALTHY' | 'CAUTION' | 'CONCERN' | 'BLOCKED' | 'PENDING';
  threshold_target: number;
  thresholdLabel: string;
  invertedThreshold: boolean;
  maxScale: number;
  gateRelevance: string;
  lineage: MetricLineage;
}

/**
 * Compute the 6 Pre-COD metrics from live project data + visible gates.
 * Values that depend on the finance engine (port 8001) — LLCR, SUC, CBM —
 * are explicitly marked PENDING_ENGINE rather than faked.
 */
function computePreCODMetrics(
  visibleGates: FinanceGate[],
  capitalStatus: CapitalType[],
  projectId: string,
): PreCODMetric[] {
  // ── CEC: Capital Eligibility Coverage ────────────────────────────────────
  // = verified evidence across CAPEX-side gates ÷ total required evidence
  // (CAPEX-side = G5 EPC + G8 model + G10 financial close, per backend doctrine)
  const capexGateIds = ['G5_EPC_RISK_PRICED', 'G8_AUDIT_GRADE_MODEL', 'G10_FINANCIAL_CLOSE_CP'];
  const capexGates = visibleGates.filter(g => capexGateIds.includes(g.id));
  const cecVerified = capexGates.reduce((s, g) => s + g.verified_count, 0);
  const cecTotal    = capexGates.reduce((s, g) => s + g.total_evidence, 0);
  const cecValue    = cecTotal > 0 ? cecVerified / cecTotal : 0;

  // ── FRI: FID Readiness Index ─────────────────────────────────────────────
  // Proxied as: completion of FID-blocking gates (G4, G5, G6, G8)
  // True FRI requires AACE Class 3+ ratio from development_packages — pending engine
  const fidGateIds = ['G4_OFFTAKE_BANKABLE', 'G5_EPC_RISK_PRICED', 'G6_IE_SIGNOFF', 'G8_AUDIT_GRADE_MODEL'];
  const fidGates = visibleGates.filter(g => fidGateIds.includes(g.id));
  const friSum = fidGates.reduce((s, g) => s + g.completion_pct, 0);
  const friValue = fidGates.length > 0 ? friSum / (100 * fidGates.length) : 0;

  // ── RMR: Runway-to-Milestone Ratio ───────────────────────────────────────
  // Proxied as: fraction of capital tranches with committed sources
  // True RMR needs spend_wave cash vs drawdown_schedule next milestone — pending
  const committedCount = capitalStatus.filter(c => c.is_unlocked || c.progress_pct >= 50).length;
  const totalCount     = capitalStatus.length;
  const rmrValue       = totalCount > 0 ? (committedCount / totalCount) * 1.5 : 0;

  // ── SUC: Sources & Uses Coverage ─────────────────────────────────────────
  // True SUC = Σ committed sources ÷ Σ uses (CAPEX + financing costs + DSRA)
  // Needs capital_bridge + spend_wave totals — pending engine
  const sucUnlocked = capitalStatus.filter(c => c.is_unlocked).length;
  const sucValue    = totalCount > 0 ? sucUnlocked / totalCount : 0;

  // ── LLCR: Loan Life Coverage Ratio ───────────────────────────────────────
  // = PV(CFADS over loan life) ÷ debt outstanding at financial close
  // Strictly engine-derived
  // ── CBM: Cohort Burn Multiple ────────────────────────────────────────────
  // = project burn ÷ adjacency cohort median burn
  // Strictly adjacency-engine derived

  const statusFor = (val: number, target: number, inverted: boolean): PreCODMetric['status'] => {
    const ok = inverted ? val <= target : val >= target;
    if (ok) return 'HEALTHY';
    const gap = inverted ? val - target : target - val;
    return gap > 0.25 * target ? 'CONCERN' : 'CAUTION';
  };

  // Build per-component breakdowns so the user sees which gate contributes what
  const capexComponents: MetricComponent[] = capexGateIds.map(id => {
    const g = visibleGates.find(x => x.id === id);
    if (!g) return { label: id, verified: 0, total: 0, note: 'not visible to your role (ABAC)' };
    return { label: `${id.split('_')[0]}  ${g.name}`, verified: g.verified_count, total: g.total_evidence };
  });
  const fidComponents: MetricComponent[] = fidGateIds.map(id => {
    const g = visibleGates.find(x => x.id === id);
    if (!g) return { label: id, verified: 0, total: 100, note: 'not visible to your role (ABAC)' };
    return { label: `${id.split('_')[0]}  ${g.name}`, verified: g.completion_pct, total: 100 };
  });
  const capitalComponents: MetricComponent[] = capitalStatus.map(c => ({
    label: c.name,
    verified: c.is_unlocked ? 1 : 0,
    total: 1,
    note: c.is_unlocked ? 'unlocked' : `${c.progress_pct}% — gating gate not yet 100%`,
  }));
  const runwayComponents: MetricComponent[] = capitalStatus.map(c => ({
    label: c.name,
    verified: c.is_unlocked || c.progress_pct >= 50 ? 1 : 0,
    total: 1,
    note: c.is_unlocked ? 'unlocked' : `${c.progress_pct}% progress`,
  }));

  return [
    {
      id: 'CEC',
      label: 'CEC — Capital Eligibility Coverage',
      value: cecValue,
      unit: '%',
      status: statusFor(cecValue, 0.85, false),
      threshold_target: 0.85, thresholdLabel: '≥85% evidenced CAPEX',
      invertedThreshold: false, maxScale: 1.0, gateRelevance: 'G5 / G8 / G10',
      lineage: {
        definition: 'Share of CAPEX evidence required by lenders that the project has already verified at audit-grade quality.',
        formulaPretty: 'CEC  =  Σᵢ verified(gᵢ)  ÷  Σᵢ required(gᵢ)        for  gᵢ ∈ { G5, G8, G10 }',
        whyItMatters: 'Lenders close on evidence, not promises. Below 85% the G10 CP checklist cannot be satisfied even if other gates are green — financial close stalls.',
        decisionRule: 'CEC < 85% blocks G10_FINANCIAL_CLOSE_CP. CEC < 50% triggers re-underwriting per IFC ECA §4.3.',
        readingBands: [
          { status: 'HEALTHY', range: '≥ 85%' },
          { status: 'CAUTION', range: '65 – 85%' },
          { status: 'CONCERN', range: '45 – 65%' },
          { status: 'BLOCKED', range: '< 45%' },
        ],
        components: capexComponents,
        numerator: cecVerified, numeratorLabel: 'Σ verified evidence items',
        denominator: cecTotal,   denominatorLabel: 'Σ required evidence items',
        sources: [
          'GET /api/v1/bankability/projects/{project}/bankability/FINANCE',
          'Backend: bankability_engine.GATE_REGISTRY (G5_EPC_RISK_PRICED, G8_AUDIT_GRADE_MODEL, G10_FINANCIAL_CLOSE_CP)',
        ],
        projectId, computed: 'LIVE',
      },
    },
    {
      id: 'FRI',
      label: 'FRI — FID Readiness Index',
      value: friValue,
      unit: '%',
      status: statusFor(friValue, 1.00, false),
      threshold_target: 1.00, thresholdLabel: '100% FID-blocking gates complete',
      invertedThreshold: false, maxScale: 1.0, gateRelevance: 'G4 / G5 / G6 / G8',
      lineage: {
        definition: 'Readiness of the project to take a Final Investment Decision — the four gates that must all be at 100% before the IC vote can be tabled.',
        formulaPretty: 'FRI  =  (1 / n)  ·  Σᵢ completion(gᵢ)        for  gᵢ ∈ { G4, G5, G6, G8 },  n = 4',
        whyItMatters: 'A project at 80% FRI is one critical gate away from being un-fundable. This metric prevents premature IC submission.',
        decisionRule: 'FRI = 100% required to schedule the FID vote. AACE Class 3+ ratio on CAPEX is the strict version — pending wiring of development_packages.aace_history.',
        readingBands: [
          { status: 'HEALTHY', range: '= 100%' },
          { status: 'CAUTION', range: '80 – 100%' },
          { status: 'CONCERN', range: '50 – 80%' },
          { status: 'BLOCKED', range: '< 50%' },
        ],
        components: fidComponents,
        numerator: friSum, numeratorLabel: 'Σ gate completion % (0 – 400)',
        denominator: 100 * fidGates.length, denominatorLabel: '100  ×  n  (max possible)',
        sources: [
          'GET /api/v1/bankability/projects/{project}/bankability/FINANCE',
          'Strict version: GET /api/v1/development-packages/{project}/aace-history (pending)',
        ],
        projectId, computed: 'PARTIAL',
        pendingReason: 'Strict FRI needs AACE Class-3+ CAPEX ratio from development_packages.aace_history.',
      },
    },
    {
      id: 'SUC',
      label: 'SUC — Sources & Uses Coverage',
      value: sucValue,
      unit: 'x',
      status: statusFor(sucValue, 1.00, false),
      threshold_target: 1.00, thresholdLabel: '≥ 1.0× fully funded',
      invertedThreshold: false, maxScale: 1.5, gateRelevance: 'G10',
      lineage: {
        definition: 'Total committed capital sources divided by total project uses (CAPEX + financing costs + DSRA + contingency). 1.0× = fully funded; > 1.0× = headroom.',
        formulaPretty: 'SUC  =  Σ sources_committed  ÷  ( CAPEX + financing_costs + DSRA + contingency )',
        whyItMatters: 'A project at 0.91× is missing 9% of its required capital — the deal cannot close until that gap is filled or scope is cut.',
        decisionRule: 'SUC < 1.0× blocks G10. Below 0.9× generally requires sponsor cash injection or DFI top-up.',
        readingBands: [
          { status: 'HEALTHY', range: '≥ 1.05×' },
          { status: 'CAUTION', range: '1.00 – 1.05×' },
          { status: 'CONCERN', range: '0.90 – 1.00×' },
          { status: 'BLOCKED', range: '< 0.90×' },
        ],
        components: capitalComponents,
        numerator: sucUnlocked, numeratorLabel: 'Unlocked capital tranches (proxy count)',
        denominator: totalCount, denominatorLabel: 'Total tranches in stack (proxy count)',
        sources: [
          'GET /api/v1/bankability/projects/{project}/bankability/FINANCE (capital_unlocks)',
          'GET /api/v1/capital-bridge/{project} (pending — for EUR-denominated sources)',
          'GET /api/v1/spend-wave/{project} (pending — for EUR-denominated uses)',
        ],
        projectId, computed: 'PARTIAL',
        pendingReason: 'EUR-denominated sources/uses need capital_bridge + spend_wave integration.',
      },
    },
    {
      id: 'RMR',
      label: 'RMR — Runway-to-Milestone Ratio',
      value: rmrValue,
      unit: 'x',
      status: statusFor(rmrValue, 1.00, false),
      threshold_target: 1.00, thresholdLabel: '≥ 1.0× cash covers next gate',
      invertedThreshold: false, maxScale: 2.0, gateRelevance: 'G6 / G9 / G10',
      lineage: {
        definition: 'Cash currently on hand divided by the cash burn needed to reach the next gate. < 1.0× means the project runs out of money before the next milestone.',
        formulaPretty: 'RMR  =  cash_on_hand  ÷  ( monthly_burn  ×  months_to_next_gate )',
        whyItMatters: 'A project that runs out of cash before its next gate triggers a forced bridge round at distressed terms — equity dilution and rate increases.',
        decisionRule: 'RMR < 1.0× triggers a bridge-capital flag. < 0.5× is a deal-killer warning.',
        readingBands: [
          { status: 'HEALTHY', range: '≥ 1.20×' },
          { status: 'CAUTION', range: '1.00 – 1.20×' },
          { status: 'CONCERN', range: '0.50 – 1.00×' },
          { status: 'BLOCKED', range: '< 0.50×' },
        ],
        components: runwayComponents,
        numerator: committedCount, numeratorLabel: 'Tranches with ≥ 50% progress (proxy)',
        denominator: totalCount, denominatorLabel: 'Total tranches (proxy)',
        sources: [
          'GET /api/v1/spend-wave/{project} (pending — pre-FID burn)',
          'GET /api/v1/drawdown-schedule/{project} (pending — post-FID drawdowns)',
        ],
        projectId, computed: 'PARTIAL',
        pendingReason: 'True RMR needs spend_wave (cash) ÷ next milestone drawdown amount in EUR.',
      },
    },
    {
      id: 'LLCR',
      label: 'LLCR — Loan Life Coverage Ratio',
      value: 0,
      unit: 'x',
      status: 'PENDING',
      threshold_target: 1.40, thresholdLabel: '≥ 1.40× for covenant headroom',
      invertedThreshold: false, maxScale: 2.0, gateRelevance: 'G8 / G10',
      lineage: {
        definition: 'Present value of cash flow available for debt service over the full loan life, divided by the senior debt balance outstanding. A standard bank covenant.',
        formulaPretty: 'LLCR  =  Σₜ ( CFADSₜ  ÷  (1 + r_d)ᵗ )  ÷  senior_debt_outstanding',
        whyItMatters: 'Banks require LLCR ≥ 1.40× as a headroom buffer. Below this, the loan covenants trip on first-year stress scenarios.',
        decisionRule: 'LLCR < 1.40× blocks credit-committee approval. Below 1.20× is a hard refusal at most DFIs.',
        readingBands: [
          { status: 'HEALTHY', range: '≥ 1.40×' },
          { status: 'CAUTION', range: '1.20 – 1.40×' },
          { status: 'CONCERN', range: '1.00 – 1.20×' },
          { status: 'BLOCKED', range: '< 1.00×' },
        ],
        components: [],
        numerator: null, numeratorLabel: 'PV(CFADS), EUR M',
        denominator: null, denominatorLabel: 'Senior debt outstanding, EUR M',
        sources: [
          'POST /api/v1/finance-model/lifetime (gex_pf_engine, port 8001)',
          'GET /api/v1/capital-bridge/{project} (senior debt commitment)',
        ],
        projectId, computed: 'PENDING_ENGINE',
        pendingReason: 'Requires gex_pf_engine /model/lifetime to return projected CFADS schedule.',
      },
    },
    {
      id: 'CBM',
      label: 'CBM — Cohort Burn Multiple',
      value: 0,
      unit: 'x',
      status: 'PENDING',
      threshold_target: 0.80, thresholdLabel: '≤ 0.80× leaner than cohort',
      invertedThreshold: true, maxScale: 2.0, gateRelevance: 'All gates',
      lineage: {
        definition: 'Project annual burn rate divided by the median annual burn of its adjacency cohort (same molecule, scale, region, phase). < 1.0× means capital-efficient relative to peers.',
        formulaPretty: 'CBM  =  burn_project (EUR/yr)  ÷  burn_cohort_median (EUR/yr)        cohort per Adjacency §3.5',
        whyItMatters: 'Investors benchmark execution efficiency. A CBM > 1.5× signals over-spending — strategic equity discounts the valuation accordingly.',
        decisionRule: 'CBM ≤ 0.80× = leaner than cohort (positive signal). CBM > 1.50× requires a written justification at IC.',
        readingBands: [
          { status: 'HEALTHY', range: '≤ 0.80×' },
          { status: 'CAUTION', range: '0.80 – 1.20×' },
          { status: 'CONCERN', range: '1.20 – 1.50×' },
          { status: 'BLOCKED', range: '> 1.50×' },
        ],
        components: [],
        numerator: null, numeratorLabel: 'Project burn, EUR / yr',
        denominator: null, denominatorLabel: 'Cohort median burn, EUR / yr',
        sources: [
          'GET /api/v1/adjacency/cohort/{project}/burn-multiple (pending — Adjacency Doctrine §3.5)',
          'GET /api/v1/spend-wave/{project} (project burn numerator)',
        ],
        projectId, computed: 'PENDING_ENGINE',
        pendingReason: 'Requires nightly adjacency cohort computation + per-project burn rate.',
      },
    },
  ];
}

function statusColor(status: string): string {
  switch (status) {
    case 'HEALTHY':  return 'text-emerald-600 dark:text-emerald-400';
    case 'CAUTION':  return 'text-amber-600 dark:text-amber-400';
    case 'CONCERN':  return 'text-red-600 dark:text-red-400';
    case 'BLOCKED':  return 'text-red-700 dark:text-red-500';
    case 'PENDING':  return 'text-gray-400 dark:text-gray-500';
    default:         return 'text-[var(--text-muted)]';
  }
}

function statusBadge(status: string): { bg: string; text: string } {
  switch (status) {
    case 'HEALTHY':  return { bg: 'bg-emerald-100 dark:bg-emerald-900/30', text: 'text-emerald-700 dark:text-emerald-400' };
    case 'CAUTION':  return { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-700 dark:text-amber-400' };
    case 'CONCERN':  return { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400' };
    case 'BLOCKED':  return { bg: 'bg-red-200 dark:bg-red-900/40', text: 'text-red-800 dark:text-red-300' };
    default:         return { bg: 'bg-gray-100 dark:bg-gray-800/40', text: 'text-gray-500 dark:text-gray-400' };
  }
}

function metricBarColor(status: string): string {
  switch (status) {
    case 'HEALTHY':  return 'bg-emerald-500';
    case 'CAUTION':  return 'bg-amber-500';
    case 'CONCERN':  return 'bg-red-500';
    case 'BLOCKED':  return 'bg-red-700';
    default:         return 'bg-gray-300 dark:bg-gray-600';
  }
}

function formatMetricValue(m: PreCODMetric): string {
  if (m.status === 'PENDING') return 'PENDING';
  if (m.unit === '%') return `${(m.value * 100).toFixed(1)}%`;
  return `${m.value.toFixed(2)}x`;
}

/**
 * Overlay backend canonical values onto our client-side proxy shells.
 * Backend returns MetricResult with .value, .status, .next_action.
 * We keep the proxy's `lineage` (formula + sources) but flip `computed`
 * to LIVE since the value now comes from the canonical engine.
 */
function mergeBackendIntoProxies(proxies: PreCODMetric[], report: any): PreCODMetric[] {
  const idMap: Record<string, string> = { CEC: 'cec', FRI: 'fri', RMR: 'rmr', CBM: 'cbm', LLCR: 'llcr', SUC: 'suc' };
  return proxies.map(p => {
    const key = idMap[p.id];
    const r = key ? report[key] : null;
    if (!r) return p;
    const isPending = (r.status || '').toUpperCase() === 'PENDING';
    return {
      ...p,
      value:  typeof r.value === 'number' ? r.value : p.value,
      status: (r.status || p.status) as PreCODMetric['status'],
      lineage: {
        ...p.lineage,
        computed: isPending ? p.lineage.computed : 'LIVE',
        pendingReason: isPending ? (r.next_action || p.lineage.pendingReason) : undefined,
        sources: [
          `POST /api/v1/pre-cod-metrics/${p.lineage.projectId} (canonical backend computation)`,
          ...p.lineage.sources,
        ],
      },
    };
  });
}

// Computed-state badge — distinguishes live values from awaiting-engine
function computedBadge(c: MetricLineage['computed']) {
  switch (c) {
    case 'LIVE':           return { label: 'LIVE',           cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' };
    case 'PARTIAL':        return { label: 'PARTIAL',        cls: 'bg-amber-100  text-amber-700  dark:bg-amber-900/30  dark:text-amber-400'  };
    case 'PENDING_ENGINE': return { label: 'AWAITING ENGINE', cls: 'bg-gray-100   text-gray-600   dark:bg-gray-800/40   dark:text-gray-400'   };
  }
}

function formatNumber(n: number | null): string {
  if (n == null) return '—';
  if (Number.isInteger(n)) return n.toString();
  return n.toFixed(2);
}

// ── Immutable version history (snapshot trail) ───────────────────────────────
// Backed by pre_cod_snapshots table + GET /api/v1/pre-cod-metrics/{id}/history.
// A new version is persisted only when values CHANGE — the trail is an audit
// log of changes, not of page-views (matches evidence_ledger hash-chain intent).

interface MetricSnapshot {
  snapshot_id: string;
  computed_at: string;
  cec_value: number | null;
  fri_value: number | null;
  rmr_value: number | null;
  cbm_value: number | null;
  llcr_value: number | null;
  suc_value: number | null;
  overall_score: number | null;
  fid_signal: string | null;
}

interface SeriesPoint { at: string; value: number; }

const METRIC_SNAPSHOT_KEY: Record<string, keyof MetricSnapshot> = {
  CEC: 'cec_value', FRI: 'fri_value', RMR: 'rmr_value',
  CBM: 'cbm_value', LLCR: 'llcr_value', SUC: 'suc_value',
};

/** Chronological (oldest→newest) value series for one metric. */
function metricSeries(metricId: string, history: MetricSnapshot[]): SeriesPoint[] {
  const key = METRIC_SNAPSHOT_KEY[metricId];
  if (!key) return [];
  return history
    .map(h => ({ at: h.computed_at, value: h[key] as number | null }))
    .filter((p): p is SeriesPoint => typeof p.value === 'number')
    .reverse();
}

/** True when a freshly computed report differs from the latest snapshot. */
function reportDiffersFromSnapshot(report: any, snap: MetricSnapshot | undefined): boolean {
  if (!snap) return true;
  const eps = 1e-4;
  const pairs: [unknown, number | null][] = [
    [report?.cec?.value,  snap.cec_value],
    [report?.fri?.value,  snap.fri_value],
    [report?.rmr?.value,  snap.rmr_value],
    [report?.cbm?.value,  snap.cbm_value],
    [report?.llcr?.value, snap.llcr_value],
    [report?.suc?.value,  snap.suc_value],
  ];
  return pairs.some(([a, b]) => {
    const av = typeof a === 'number' ? a : null;
    if (av === null && b === null) return false;
    if (av === null || b === null) return true;
    return Math.abs(av - b) > eps;
  });
}

function formatDelta(m: PreCODMetric, delta: number): string {
  if (m.unit === '%') {
    const pts = delta * 100;
    return `${pts >= 0 ? '+' : ''}${pts.toFixed(1)} pts`;
  }
  return `${delta >= 0 ? '+' : ''}${delta.toFixed(2)}x`;
}

/** Minimal slate sparkline — last point dotted. No axes, no color noise. */
function Sparkline({ series }: { series: SeriesPoint[] }) {
  if (series.length < 2) return null;
  const W = 64, H = 14, pad = 1.5;
  const vals = series.map(p => p.value);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (series.length - 1)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - min) / span) * (H - 2 * pad);
  const pts = series.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const last = series[series.length - 1];
  return (
    <svg width={W} height={H} className="overflow-visible" aria-hidden>
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1" className="text-slate-400 dark:text-slate-500" />
      <circle cx={x(series.length - 1)} cy={y(last.value)} r="1.5" className="fill-slate-700 dark:fill-slate-300" />
    </svg>
  );
}

/** Thin version-delta line shown under each metric bar. */
function MetricHistoryLine({ m, series }: { m: PreCODMetric; series: SeriesPoint[] }) {
  if (series.length === 0) {
    return (
      <div className="mt-0.5 font-mono text-[9px] text-[var(--text-muted)]">
        no version history{m.lineage.computed === 'PENDING_ENGINE' ? ' · requires engine feed' : ' · first snapshot pending'}
      </div>
    );
  }
  const cur  = series[series.length - 1].value;
  const prev = series.length >= 2 ? series[series.length - 2].value : null;
  const delta = prev !== null ? cur - prev : null;
  const goodUp = !m.invertedThreshold;           // higher better, except CBM
  const flat = delta === null || Math.abs(delta) < 1e-4;
  const trend = flat ? '→' : (delta as number) > 0 ? '▲' : '▼';
  const improving = flat ? null : (goodUp ? (delta as number) > 0 : (delta as number) < 0);
  const color = improving === null ? 'text-[var(--text-muted)]'
    : improving ? 'text-emerald-600 dark:text-emerald-400'
    : 'text-red-600 dark:text-red-400';
  const lastAt = new Date(series[series.length - 1].at).toISOString().slice(0, 10);
  return (
    <div className="mt-0.5 flex items-center justify-between gap-2">
      <div className="flex items-center gap-1.5 font-mono text-[9px] text-[var(--text-muted)]">
        <span className={color}>{trend}</span>
        {delta !== null
          ? <span className={color}>{formatDelta(m, delta)} vs prior</span>
          : <span>first version</span>}
        <span>· {series.length} version{series.length === 1 ? '' : 's'} · {lastAt}</span>
      </div>
      <Sparkline series={series} />
    </div>
  );
}

/**
 * Render a metric row with a chevron that reveals the full lineage:
 *   formula · numerator · denominator · sources · project · computed state
 * This is the Bloomberg-style drill-down: every number traces to its inputs.
 */
function MetricRow({
  m,
  isOpen,
  onToggle,
  series,
}: {
  m: PreCODMetric;
  isOpen: boolean;
  onToggle: () => void;
  series: SeriesPoint[];
}) {
  const isPending    = m.status === 'PENDING';
  const pct          = isPending ? 0 : (m.value / m.maxScale) * 100;
  const thresholdPct = (m.threshold_target / m.maxScale) * 100;
  const badge        = statusBadge(m.status);
  const cb           = computedBadge(m.lineage.computed);

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <button
          onClick={onToggle}
          className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)] hover:text-[var(--brand)] transition-colors text-left"
          aria-label={`Toggle ${m.id} lineage`}
        >
          {isOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          {m.label}
        </button>
        <div className="flex items-center gap-2">
          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wider ${cb.cls}`} title="Computation state">
            {cb.label}
          </span>
          <span className={`font-mono text-sm font-bold tabular-nums ${statusColor(m.status)}`}>
            {formatMetricValue(m)}
          </span>
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${badge.bg} ${badge.text}`}>
            {m.status}
          </span>
        </div>
      </div>
      <div className="relative h-3 w-full rounded-full bg-[var(--border)] overflow-visible">
        <div
          className={`h-full rounded-full transition-all duration-500 ${metricBarColor(m.status)}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
        {!isPending && (
          <div
            className="absolute top-[-2px] h-[calc(100%+4px)] w-0.5 bg-gray-800 dark:bg-gray-300"
            style={{ left: `${Math.min(thresholdPct, 100)}%` }}
            title={m.thresholdLabel}
          />
        )}
      </div>
      <div className="flex items-center justify-between mt-0.5">
        <span className="text-[10px] text-[var(--text-muted)]">{m.thresholdLabel}</span>
        <span className="text-[10px] text-[var(--text-muted)]">{m.gateRelevance}</span>
      </div>

      {/* Immutable version delta — current vs prior snapshot */}
      <MetricHistoryLine m={m} series={series} />

      {/* Bloomberg-style help panel — definition, formula, inputs, reading bands, decision rule */}
      {isOpen && (
        <div className="mt-2 rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-3 space-y-3 animate-fade-in">

          {/* 1. Definition — what this metric IS */}
          <div>
            <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Definition</p>
            <p className="mt-0.5 text-[12px] text-[var(--text-primary)] leading-relaxed">
              {m.lineage.definition}
            </p>
          </div>

          {/* 2. Formula — proper math notation in a code-block */}
          <div>
            <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Formula</p>
            <pre className="mt-0.5 rounded border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[12px] font-mono text-[var(--text-primary)] whitespace-pre-wrap leading-relaxed">
{m.lineage.formulaPretty}
            </pre>
          </div>

          {/* 3. Inputs — actual numbers feeding the formula RIGHT NOW */}
          <div>
            <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Inputs (this project, right now)</p>
            {m.lineage.components.length > 0 ? (
              <div className="mt-0.5 rounded border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
                <table className="w-full text-[11px]">
                  <tbody className="divide-y divide-[var(--border)]">
                    {m.lineage.components.map((c, i) => (
                      <tr key={i}>
                        <td className="px-2 py-1 text-[var(--text-secondary)]">{c.label}</td>
                        <td className="px-2 py-1 text-right font-mono tabular-nums text-[var(--text-primary)] whitespace-nowrap">
                          {c.verified} / {c.total}
                        </td>
                        <td className="px-2 py-1 text-right text-[10px] text-[var(--text-muted)] italic whitespace-nowrap">
                          {c.note ?? ''}
                        </td>
                      </tr>
                    ))}
                    <tr className="bg-[var(--surface-muted)] font-semibold">
                      <td className="px-2 py-1 text-[var(--text-primary)]">Total  ({m.lineage.numeratorLabel} / {m.lineage.denominatorLabel})</td>
                      <td className="px-2 py-1 text-right font-mono tabular-nums text-[var(--text-primary)] whitespace-nowrap">
                        {formatNumber(m.lineage.numerator)} / {formatNumber(m.lineage.denominator)}
                      </td>
                      <td className="px-2 py-1 text-right font-mono text-[var(--text-primary)]">
                        = {formatMetricValue(m)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-0.5 text-[11px] text-amber-600 dark:text-amber-400 italic">
                {m.lineage.pendingReason ?? 'Inputs not yet available — awaiting engine wiring.'}
              </p>
            )}
          </div>

          {/* 4. Reading bands — what the value means */}
          <div>
            <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Reading</p>
            <div className="mt-0.5 flex flex-wrap gap-1.5">
              {m.lineage.readingBands.map((b, i) => {
                const bg = statusBadge(b.status);
                const isCurrent = b.status === m.status;
                return (
                  <span
                    key={i}
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold ${bg.bg} ${bg.text} ${
                      isCurrent ? 'ring-2 ring-offset-1 ring-[var(--brand)] ring-offset-[var(--surface-muted)]' : ''
                    }`}
                    title={isCurrent ? 'Current band' : ''}
                  >
                    {b.status} · {b.range}
                  </span>
                );
              })}
            </div>
          </div>

          {/* 5. Why it matters / decision rule */}
          <div className="grid gap-2 md:grid-cols-2">
            <div className="rounded border border-[var(--border)] bg-[var(--surface)] p-2">
              <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Why it matters</p>
              <p className="mt-0.5 text-[11px] text-[var(--text-secondary)] leading-relaxed">{m.lineage.whyItMatters}</p>
            </div>
            <div className="rounded border border-[var(--border)] bg-[var(--surface)] p-2">
              <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Decision rule</p>
              <p className="mt-0.5 text-[11px] text-[var(--text-secondary)] leading-relaxed">{m.lineage.decisionRule}</p>
            </div>
          </div>

          {/* 6. Provenance — sources & project ID at the bottom */}
          <details className="text-[10px]">
            <summary className="cursor-pointer text-[var(--text-muted)] font-semibold uppercase tracking-[0.12em] hover:text-[var(--brand)]">
              Provenance ({m.lineage.sources.length} source{m.lineage.sources.length === 1 ? '' : 's'})
            </summary>
            <ul className="mt-1 space-y-0.5">
              {m.lineage.sources.map((s, i) => (
                <li key={i} className="text-[10px] text-[var(--text-secondary)] font-mono leading-snug pl-2">
                  · {s}
                </li>
              ))}
              <li className="text-[10px] text-[var(--text-muted)] font-mono leading-snug pl-2 pt-1 border-t border-[var(--border)] mt-1">
                Project ID: {m.lineage.projectId}
              </li>
            </ul>
          </details>

        </div>
      )}
    </div>
  );
}

interface PreCODMetricsPanelProps {
  visibleGates: FinanceGate[];
  capitalStatus: CapitalType[];
  projectId: string;
}

// Mirrors backend pre_cod_metrics.py PRE_COD_RULES_VERSION / MODEL_VERSION —
// used only as the proxy-mode fallback label (backend stamp wins when live).
const PRE_COD_RULES_VERSION = 'PF_RULES_2026_06';
const PRE_COD_MODEL_VERSION = 'precod-1.0';

/**
 * Panel-level assumption stamp. Provenance before completeness: no pre-COD
 * forward ratio (DSCR-forward, LLCR, SUC) renders without scenario + basis +
 * reliance. When the backend is live the real stamp is shown; in proxy mode it
 * states the ratios are client-derived and not credit-approved.
 */
function PreCODGovernanceBanner({ gov, backendUp }: { gov?: any; backendUp: boolean }) {
  const basis = gov?.data_basis ?? (backendUp ? 'SEED' : 'PROXY (client-derived)');
  const scenario = gov?.scenario_id ?? 'UNSPECIFIED';
  const rules = gov?.rules_version ?? PRE_COD_RULES_VERSION;
  const model = gov?.model_version ?? PRE_COD_MODEL_VERSION;
  const completeness = gov?.input_completeness_pct;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800 px-4 py-2.5">
      <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
      <div className="text-xs text-amber-800 dark:text-amber-300">
        <span className="font-bold uppercase tracking-[0.08em]">Analytical preview · not credit-approved</span>
        {' '}— pre-COD ratios are forward-looking, depend on supplied inputs, and are not an independent verification of the project.
        <span className="block mt-0.5 font-mono text-[10px] text-amber-700/80">
          scenario {scenario} · basis {basis} · rules {rules} · model {model}
          {completeness != null ? ` · inputs ${completeness}% complete` : ''}
          {gov ? '' : ' · ⚠ proxy mode (start backend for the governed model)'}
        </span>
      </div>
    </div>
  );
}

function PreCODMetricsPanel({ visibleGates, capitalStatus, projectId }: PreCODMetricsPanelProps) {
  const [open, setOpen] = useState(true);
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null);
  const [backendReport, setBackendReport] = useState<any>(null);
  const [backendUp, setBackendUp] = useState<boolean>(false);
  const [history, setHistory] = useState<MetricSnapshot[]>([]);

  // Pull canonical computation + immutable version history from the backend.
  //   1. GET  /history          → prior snapshots (DESC)
  //   2. POST /                  → compute current values (no save yet)
  //   3. POST / save_snapshot    → persist ONLY when values changed vs latest
  //   4. GET  /history (reload)  → pick up the new version
  // Persisting only on change keeps the trail an audit log of changes, not of
  // page-views — the same discipline as the evidence_ledger hash chain.
  useEffect(() => {
    let cancelled = false;
    const histUrl = `/api/v1/pre-cod-metrics/${projectId}/history?limit=20`;
    (async () => {
      // 1) prior history
      let hist: MetricSnapshot[] = [];
      try {
        const h = await fetch(histUrl);
        if (h.ok) hist = await h.json();
      } catch { /* offline — proceed without history */ }

      // 2) compute current (no save)
      let report: any = null;
      try {
        const res = await fetch(`/api/v1/pre-cod-metrics/${projectId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_id: projectId, save_snapshot: false }),
        });
        if (!res.ok) throw new Error(`backend status ${res.status}`);
        report = await res.json();
      } catch {
        if (!cancelled) { setBackendUp(false); setHistory(hist); }
        return;
      }

      // 3) persist a new immutable version only when something changed
      if (reportDiffersFromSnapshot(report, hist[0])) {
        try {
          await fetch(`/api/v1/pre-cod-metrics/${projectId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: projectId, save_snapshot: true }),
          });
          const h2 = await fetch(histUrl);
          if (h2.ok) hist = await h2.json();
        } catch { /* save failed — render computed values without the new snapshot */ }
      }

      if (!cancelled) {
        setBackendReport(report);
        setBackendUp(true);
        setHistory(hist);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  // Prefer backend values; fall back to client-side proxies when offline.
  // Each row's lineage.computed reflects which source we actually used.
  const proxies = computePreCODMetrics(visibleGates, capitalStatus, projectId);
  const metrics = backendUp && backendReport
    ? mergeBackendIntoProxies(proxies, backendReport)
    : proxies;

  const active = metrics.filter(m => m.status !== 'PENDING');
  const failing = active.filter(m => m.status !== 'HEALTHY');
  const fidSignal = failing.length === 0 ? 'READY'
    : failing.some(m => m.status === 'BLOCKED') ? 'NOT_READY'
    : failing.length >= 3 ? 'APPROACHING' : 'PROGRESSING';
  const isG10Ready = fidSignal === 'READY';

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between border-b border-[var(--border)] px-5 py-3.5 hover:bg-[var(--surface-muted)] transition-colors"
      >
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-[var(--brand)]" />
          <h3 className="text-sm font-bold text-[var(--text-primary)]">
            Pre-COD Metrics
          </h3>
          <InfoTooltip text="Pre-COD financial intelligence: 4 GEX-native metrics (CEC, FRI, RMR, CBM) + 2 standard PF metrics (LLCR, S&U Coverage). Values come from POST /api/v1/pre-cod-metrics/{project_id} (canonical backend computation) with client-side proxies as offline fallback. DSCR is a footnote until T-2 quarters from COD." />
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold tracking-wider ${
              backendUp
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
            }`}
            title={backendUp
              ? 'Values returned by POST /api/v1/pre-cod-metrics/{project_id}'
              : 'Backend unreachable — values derived client-side from gate completion. Start backend on port 8000.'}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${backendUp ? 'bg-emerald-500' : 'bg-amber-500'}`} />
            {backendUp ? 'BACKEND LIVE' : 'PROXY MODE'}
          </span>
          {history.length > 0 && (
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold tracking-wider bg-slate-100 text-slate-600 dark:bg-slate-800/40 dark:text-slate-400"
              title={`${history.length} immutable snapshot${history.length === 1 ? '' : 's'} · last ${new Date(history[0].computed_at).toISOString().slice(0, 10)}`}
            >
              v{history.length}
            </span>
          )}
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-bold ${
            isG10Ready
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
              : fidSignal === 'NOT_READY'
              ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
              : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
          }`}>
            {fidSignal === 'READY' ? 'FID READY' : fidSignal.replace('_', ' ')}
          </span>
          {open ? <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />}
        </div>
      </button>

      {open && (
        <div className="px-5 py-4 space-y-4">

          {/* Governance / assumption stamp — no naked forward ratio. Surfaces the
              backend stamp when live; states reliance + basis either way. */}
          <PreCODGovernanceBanner gov={backendReport?.governance} backendUp={backendUp} />

          {/* GEX-native label */}
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">GEX-Native</p>

          <div className="space-y-3">
            {metrics.filter(m => ['CEC','FRI','RMR','CBM'].includes(m.id)).map(m => (
              <MetricRow
                key={m.id}
                m={m}
                isOpen={expandedMetric === m.id}
                onToggle={() => setExpandedMetric(expandedMetric === m.id ? null : m.id)}
                series={metricSeries(m.id, history)}
              />
            ))}
          </div>

          {/* Standard PF label */}
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)] pt-2">Standard PF</p>

          <div className="space-y-3">
            {metrics.filter(m => ['LLCR','SUC'].includes(m.id)).map(m => (
              <MetricRow
                key={m.id}
                m={m}
                isOpen={expandedMetric === m.id}
                onToggle={() => setExpandedMetric(expandedMetric === m.id ? null : m.id)}
                series={metricSeries(m.id, history)}
              />
            ))}
          </div>

          {/* DSCR footnote */}
          <div className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--surface-muted)] px-4 py-2.5">
            <p className="text-[10px] text-[var(--text-muted)]">
              <span className="font-semibold">DSCR:</span> <span className="font-semibold">Realized</span> DSCR has no current-period value before COD (no operating cashflows yet). The <span className="font-semibold">projected / scenario</span> DSCR — a first-class pre-COD bankability input — is modelled here and in Sensitivity Analysis. Realized DSCR becomes the primary covenant metric post-COD.
            </p>
          </div>

          {/* FID Readiness signal */}
          <div className={`rounded-xl border p-4 ${
            isG10Ready
              ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-800/40 dark:bg-emerald-900/15'
              : fidSignal === 'NOT_READY'
              ? 'border-red-200 bg-red-50 dark:border-red-800/40 dark:bg-red-900/15'
              : 'border-amber-200 bg-amber-50 dark:border-amber-800/40 dark:bg-amber-900/15'
          }`}>
            <div className="flex items-center gap-2 mb-1">
              <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-sm font-black ${
                isG10Ready
                  ? 'bg-emerald-600 text-white'
                  : fidSignal === 'NOT_READY'
                  ? 'bg-red-600 text-white'
                  : 'bg-amber-600 text-white'
              }`}>
                {fidSignal === 'READY' ? 'FID READY' : fidSignal.replace('_', ' ')}
              </span>
            </div>
            {failing.length > 0 && (
              <div className="mt-2 space-y-1">
                <p className={`text-xs font-semibold ${fidSignal === 'NOT_READY' ? 'text-red-700 dark:text-red-400' : 'text-amber-700 dark:text-amber-400'}`}>
                  Action needed ({failing.length}):
                </p>
                {failing.map(m => (
                  <div key={m.id} className={`flex items-center justify-between text-xs ${fidSignal === 'NOT_READY' ? 'text-red-600 dark:text-red-400' : 'text-amber-600 dark:text-amber-400'}`}>
                    <span>{m.id}: {formatMetricValue(m)}</span>
                    <span className="font-mono">{m.status}</span>
                  </div>
                ))}
              </div>
            )}
            {isG10Ready && (
              <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-400">
                All metrics at target. Proceed to G10 preparation.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
