import React, { useState, useEffect, useRef } from 'react';
import {
  CheckCircle, AlertTriangle, DollarSign, Shield, FileCheck,
  TrendingUp, Lock, Unlock, Info, X, ChevronDown, ChevronUp,
} from 'lucide-react';
import { getProjectById, CUSTOMER_PROJECTS } from '@/data/customerProjects';
import { useSelectedProject } from '@/contexts/ProjectContext';

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

const CAPITAL_IMPROVEMENTS: Record<string, string> = {
  PROJECT_EQUITY:
    'Secure a bankable off-take agreement (G4) and bind insurance coverage (G7). ' +
    'Currently 79% ready — submit the 10-year take-or-pay term and political-risk insurance to close the gap.',
  SENIOR_DEBT_COMMITMENT:
    'Complete the audit-grade financial model (G8) and achieve financial-close readiness (G10). ' +
    'Currently 53% ready — certify stress tests and confirm equity + senior-debt commitments.',
  DFI_MEZZ_GUARANTEES:
    'All DFI guarantee conditions are met. No further action required.',
  DEBT_DRAWDOWN:
    'Financial-close readiness (G10) must reach 100% before drawdown can proceed. ' +
    'Currently 25% ready — obtain senior-debt commitment letter and equity-funding confirmation.',
};

function capitalImprovementHint(type: string, pct: number): string {
  if (pct >= 100) return 'All requirements met. This capital type is unlocked.';
  return CAPITAL_IMPROVEMENTS[type] ??
    `Reach 100% by completing all gating gate evidence requirements. Currently ${pct}% complete.`;
}

function gateImprovementHint(gate: FinanceGate): string {
  if (gate.is_complete) return 'Gate fully complete. No action required.';
  const remaining = 100 - gate.completion_pct;
  const items = gate.blocking_items.map(i => i.replace(/_/g, ' ')).join(', ');
  return `${gate.completion_pct}% → 100% (+${remaining} pts): Submit and verify — ${items || 'remaining evidence items'}.`;
}

function capIcon(type: string) {
  if (type.includes('EQUITY'))    return <TrendingUp className="w-4 h-4" />;
  if (type.includes('DEBT'))      return <DollarSign  className="w-4 h-4" />;
  if (type.includes('GUARANTEE')) return <Shield      className="w-4 h-4" />;
  return <FileCheck className="w-4 h-4" />;
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

function buildFallback(projectId: string, project: ReturnType<typeof getProjectById>): FinanceBankabilityData {
  const bk = project?.bankability;
  const GATE_ICONS: Record<string, string> = {
    G4_OFFTAKE_BANKABLE: '📋', G7_INSURANCE_BOUND: '🛡️',
    G8_AUDIT_GRADE_MODEL: '📊', G10_FINANCIAL_CLOSE_CP: '💰',
    G0_SITE_RIGHTS: '📋', G1_GRID_UTILITIES: '⚡',
    G3_TECH_VENDOR_LOCKED: '🔧', G11_GHG_VERIFIED: '🌿',
  };
  return {
    project_id: projectId,
    visible_gates: (bk?.gates ?? []).map(g => ({
      id: g.id, name: g.name,
      total_evidence: g.total_evidence, verified_count: g.verified_count,
      completion_pct: g.completion_pct, is_complete: g.is_complete,
      blocking_items: g.blocking_items,
      icon: GATE_ICONS[g.id] ?? '📋',
      description: g.description,
    })),
    capital_status: (bk?.capital_status ?? []).map(c => ({
      type: c.type, name: c.name, amount: c.amount,
      is_unlocked: c.is_unlocked, gating_gates: c.gating_gates,
      progress_pct: c.progress_pct,
    })),
    overall_completion: bk?.overall_completion ?? 0,
    total_unlocked_amount: (bk?.capital_status ?? []).filter(c => c.is_unlocked).map(c => c.amount).join(' + ') || '—',
    next_unlock_milestone: bk?.next_milestone ?? '',
    risk_alerts: bk?.risk_alerts ?? [],
  };
}

// ─── Main component ───────────────────────────────────────────────────────────

export function FinanceBankabilityView({ projectId: propProjectId }: { projectId?: string }) {
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject();
  const projectId = propProjectId ?? selectedProjectId;
  const canonicalProject = getProjectById(projectId);

  const [data, setData]           = useState<FinanceBankabilityData | null>(null);
  const [loading, setLoading]     = useState(true);
  const [expanded, setExpanded]   = useState<string | null>(null);

  useEffect(() => { load(); }, [projectId]);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/bankability/projects/${projectId}/bankability/FINANCE`);
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
            icon: '📋',
            description: g.owners?.length ? `${g.owners.join(', ')} gate` : '',
          })),
          capital_status: (raw.capital_unlocks || []).map((c: any) => ({
            type: c.capital_type,
            name: c.capital_type.replace(/_/g, ' '),
            amount: 'N/A',
            is_unlocked: c.is_unlocked,
            gating_gates: c.gating_gates || [],
            progress_pct: Math.round(c.best_progress_pct || 0),
          })),
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
          {CUSTOMER_PROJECTS.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

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
            <DollarSign className="w-4 h-4 text-[var(--brand)]" />
            <h3 className="flex-1 text-sm font-bold text-[var(--text-primary)]">Capital Unlock Status</h3>
            <InfoTip text="Each capital type below unlocks when its gating gates reach 100%. The info icon on each row shows exactly what evidence is still needed and how far you are from the unlock threshold." />
          </div>

          <div className="divide-y divide-[var(--border)]">
            {data.capital_status.map(cap => {
              const barColor = progressColor(cap.progress_pct, cap.is_unlocked);
              const isOpen   = expanded === cap.type;
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
                          <InfoTip text={capitalImprovementHint(cap.type, cap.progress_pct)} />
                          {capIcon(cap.type)}
                        </div>
                      </div>
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

                  {/* Inline gate breakdown */}
                  {isOpen && (
                    <div className="border-t border-[var(--border)] bg-[var(--surface-muted)] px-5 py-3 space-y-2 animate-fade-in">
                      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Required gates</p>
                      {cap.gating_gates.map(gid => {
                        const g = data.visible_gates.find(x => x.id === gid);
                        return (
                          <div key={gid} className="flex items-center justify-between text-xs">
                            <span className="text-[var(--text-secondary)]">{g?.name ?? gid}</span>
                            <span className={`font-mono font-bold ${(g?.completion_pct ?? 0) >= 100 ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}`}>
                              {g?.completion_pct ?? 0}%
                            </span>
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
              return (
                <div key={gate.id} className="px-5 py-4">
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
                    </div>
                  </div>

                  <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]">
                    <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${gate.completion_pct}%` }} />
                  </div>

                  {gate.blocking_items.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {gate.blocking_items.map(item => (
                        <span key={item} className="gex-badge gex-badge-red">
                          {item.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
