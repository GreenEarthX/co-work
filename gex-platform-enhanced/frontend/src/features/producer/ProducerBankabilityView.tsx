import React, { useState, useEffect, useRef } from 'react';
import {
  CheckCircle, AlertCircle, Clock, Upload, Eye, FileText,
  Info, X, ChevronDown, ChevronUp,
} from 'lucide-react';
import { getProjectById, CUSTOMER_PROJECTS } from '@/data/customerProjects';
import { useSelectedProject } from '@/contexts/ProjectContext';

// ─── Types ────────────────────────────────────────────────────────────────────

interface EvidenceItem {
  key: string;
  status: 'NOT_STARTED' | 'IN_PROGRESS' | 'SUBMITTED' | 'UNDER_REVIEW' | 'VERIFIED' | 'REJECTED' | 'EXPIRED';
  submitted_by?: string;
  verified_by?: string;
  submitted_at?: string;
  verified_at?: string;
  document_url?: string;
  notes?: string;
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
  const projectId = propProjectId ?? selectedProjectId;
  const canonicalProject = getProjectById(projectId);

  const [data, setData]         = useState<ProducerBankabilityData | null>(null);
  const [loading, setLoading]   = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => { load(); }, [projectId]);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/bankability/projects/${projectId}/bankability/PRODUCER`);
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
            evidence_items: (g.evidence_detail || []).map((e: any) => ({
              key: e.key,
              status: e.status,
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
          })),
          overall_completion: bk?.overall_completion ?? 0,
          unlocked_capital: bk?.unlocked_capital ?? [],
          next_milestone: bk?.next_milestone ?? '',
        });
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
        })),
        overall_completion: bk?.overall_completion ?? 0,
        unlocked_capital: bk?.unlocked_capital ?? [],
        next_milestone: bk?.next_milestone ?? '',
      });
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
          {CUSTOMER_PROJECTS.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* ── KPI strip ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
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
        </div>

        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4 shadow-card">
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Gates</div>
          <div className="mt-1 font-display text-2xl font-extrabold leading-none text-[var(--text-primary)]">
            {data.visible_gates.filter(g => g.is_complete).length}
            <span className="text-base font-medium text-[var(--text-muted)]"> / {data.visible_gates.length}</span>
          </div>
        </div>

        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4 shadow-card">
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Unlocked Capital</div>
          <div className="mt-1 font-display text-2xl font-extrabold leading-none text-emerald-600 dark:text-emerald-400">
            {data.unlocked_capital.length}
          </div>
        </div>
      </div>

      {/* ── Unlocked capital types ── */}
      {data.unlocked_capital.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {data.unlocked_capital.map(c => (
            <span key={c} className="gex-badge gex-badge-green">{c.replace(/_/g, ' ')}</span>
          ))}
        </div>
      )}

      {/* ── Next milestone ── */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--brand-light)] px-4 py-2.5">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--brand)]">Next milestone · </span>
        <span className="text-xs text-[var(--text-secondary)]">{data.next_milestone}</span>
      </div>

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
              <div key={gate.id}>
                {/* Gate header row */}
                <div className="flex items-start gap-3 px-5 py-4">
                  <div className="mt-0.5 flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">{gate.name}</p>
                      <span className="text-[10px] font-mono text-[var(--text-muted)]">{gate.id}</span>
                    </div>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">
                      {gate.verified_count} of {gate.total_evidence} evidence items verified
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
                {isOpen && (
                  <div className="border-t border-[var(--border)] bg-[var(--surface-muted)] px-5 py-3 space-y-2 animate-fade-in">
                    <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-2">Evidence items</p>
                    {gate.evidence_items.map(ev => {
                      const { icon, badge } = statusMeta(ev.status);
                      return (
                        <div key={ev.key} className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
                          <div className="flex items-center gap-2 min-w-0">
                            {icon}
                            <div className="min-w-0">
                              <p className="text-xs font-medium text-[var(--text-primary)] truncate">
                                {ev.key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                              </p>
                              <span className={badge}>{ev.status.replace(/_/g, ' ')}</span>
                            </div>
                          </div>
                          <div className="flex gap-1 shrink-0 ml-2">
                            {ev.document_url && (
                              <button className="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--brand)] hover:bg-[var(--surface-hover)] transition-colors">
                                <FileText className="w-3.5 h-3.5" />
                              </button>
                            )}
                            {(ev.status === 'NOT_STARTED' || ev.status === 'REJECTED') ? (
                              <button className="p-1.5 rounded text-[var(--text-muted)] hover:text-emerald-600 hover:bg-[var(--surface-hover)] transition-colors">
                                <Upload className="w-3.5 h-3.5" />
                              </button>
                            ) : (
                              <button className="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--brand)] hover:bg-[var(--surface-hover)] transition-colors">
                                <Eye className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
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
    </div>
  );
}
