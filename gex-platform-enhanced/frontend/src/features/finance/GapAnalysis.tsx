// Screen: Gap analysis screen (/finance-gaps, /finance/gaps)
// API: GET /api/v1/structuring/{project_id}/gaps
//
// Handoff v4 (2026-11-17), tasks 2-3: each gap follows the requirement it
// concerns, in the engine's words, and closes only when that requirement is
// verified; a gate stays incomplete until all its requirements are. DSCR, WACC,
// offtake coverage and the regulatory premium are DECISION TESTS against an
// attributed policy value, never gate thresholds; with no approved value they
// read "no approved threshold — no pass/fail".

import { useProjectResource } from './useProjectResource';
import { AlertTriangle, Search } from 'lucide-react';
import { ReadinessStamp, type Readiness } from '@/components/ReadinessStamp';

interface Policy {
  value: number | null;
  status: string | null;
  policy_party: string;
  effective_date: string | null;
  source: string | null;
  context: Record<string, unknown> | null;
}

interface DecisionTest {
  test: string;
  label: string;
  outcome: 'PASS' | 'FAIL' | 'NO_APPROVED_THRESHOLD' | 'NOT_ASSESSABLE';
  message: string;
  value: number | null;
  policy: Policy | null;
  proposed_values: Policy[];
  capital_decisions: string[];
}

export interface Gap {
  gap_id: string;
  gap_type: string;
  severity: string;
  kind: 'REQUIREMENT' | 'COMMITMENT' | 'DECISION_TEST';
  description: string;
  current_value: string;
  required_value: string;
  delta: string;
  affected_gates: string[];
  affected_metrics: string[];
  risk_category: string;
  requirement_label: string | null;
  gate_id: string | null;
  gate_name: string | null;
  gate_remaining_requirements: string[];
  decision_test: DecisionTest | null;
  capital_decisions: string[];
}

interface GateView { gate_id: string; gate_name: string; remaining_requirements: string[] }

const SEVERITY_STYLES: Record<string, { text: string; border: string }> = {
  BLOCKING: { text: 'text-red-700', border: 'border-red-500' },
  DEGRADING: { text: 'text-amber-700', border: 'border-amber-500' },
  ADVISORY: { text: 'text-slate-700', border: 'border-slate-500' },
  NOT_JUDGED: { text: 'text-slate-600', border: 'border-slate-300' },
};

function PolicyLine({ test }: { test: DecisionTest }) {
  const p = test.policy ?? test.proposed_values[0] ?? null;
  return (
    <div className="mt-2 text-xs text-[var(--text-secondary)]" data-testid="decision-test">
      <span className="font-semibold">{test.message}</span>
      {p ? (
        <span className="ml-2">
          {test.policy ? 'Policy' : 'Value shown for reference'}: {p.value ?? '—'} · {p.status ?? '—'} · party {p.policy_party}
          {p.effective_date ? ` · effective ${p.effective_date}` : ''}{p.source ? ` · source ${p.source}` : ''}
        </span>
      ) : (
        <span className="ml-2">No value proposed or approved.</span>
      )}
      {test.capital_decisions.length > 0 && (
        <span className="ml-2">Affects: {test.capital_decisions.join(', ')}</span>
      )}
    </div>
  );
}

export function GapAnalysis() {
  const { data, loading, error } = useProjectResource<{ gaps?: Gap[]; gates?: GateView[]; readiness?: Readiness }>(
    (pid) => `/api/v1/structuring/${pid}/gaps`);
  const gaps: Gap[] = data?.gaps || [];
  const count = (s: string) => gaps.filter(g => g.severity === s).length;

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Gap Analysis</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
            Open requirements by gate, in the gate engine's words, and the decision tests a capital provider applies.
          </p>
        </div>
        <div className="flex items-center gap-2.5 text-sm font-semibold">
          <span className="rounded-full border border-red-200 bg-white px-3 py-1.5 text-red-700">{count('BLOCKING')} Blocking</span>
          <span className="rounded-full border border-amber-200 bg-white px-3 py-1.5 text-amber-700">{count('DEGRADING')} Required</span>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-slate-700">{count('NOT_JUDGED')} Not judged</span>
        </div>
      </div>

      <ReadinessStamp readiness={data?.readiness} />

      {error ? (
        <div role="alert" className="p-6 text-center text-sm text-[var(--text-secondary)]">{error}</div>
      ) : loading ? (
        <div className="py-12 text-center text-[var(--text-muted)]">Analysing project gaps...</div>
      ) : (
        <>
          {(data?.gates || []).length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
              <h2 className="text-sm font-bold text-[var(--text-primary)]">Gates still incomplete</h2>
              <ul className="mt-2 space-y-1 text-xs text-[var(--text-secondary)]">
                {(data?.gates || []).map(g => (
                  <li key={g.gate_id}>
                    <span className="font-semibold">{g.gate_name}</span> — {g.remaining_requirements.length} requirement(s) open:
                    {' '}{g.remaining_requirements.join('; ')}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="space-y-3">
            {gaps.map(gap => {
              const style = SEVERITY_STYLES[gap.severity] || SEVERITY_STYLES.ADVISORY;
              return (
                <div key={gap.gap_id}
                     className={`rounded-xl border border-[var(--border)] border-l-4 bg-[var(--surface)] px-4 py-3.5 shadow-card ${style.border}`}>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
                        <AlertTriangle className={`h-4 w-4 ${style.text}`} />
                        <span className={`font-bold uppercase ${style.text}`}>{gap.severity.replace('_', ' ')}</span>
                        <span className="rounded-full border px-2 py-0.5">
                          {gap.kind === 'DECISION_TEST' ? 'Decision test' : gap.kind === 'COMMITMENT' ? 'Commitment' : 'Requirement'}
                        </span>
                        {gap.gate_name && <span className="rounded-full border px-2 py-0.5">{gap.gate_name}</span>}
                      </div>
                      <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{gap.description}</p>
                      {gap.kind === 'DECISION_TEST' && gap.decision_test && <PolicyLine test={gap.decision_test} />}
                      {gap.kind !== 'DECISION_TEST' && (
                        <p className="mt-2 text-xs text-[var(--text-secondary)]">
                          Current {gap.current_value} · needs {gap.required_value}
                        </p>
                      )}
                      {gap.kind === 'DECISION_TEST' && gap.gate_remaining_requirements.length > 0 && (
                        <p className="mt-1 text-xs text-[var(--text-muted)]">
                          Concerns G4 requirements still open: {gap.gate_remaining_requirements.join(', ')}
                        </p>
                      )}
                    </div>
                    <button className="ml-4 flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--surface-hover)]">
                      <Search className="h-4 w-4" /> Find Instruments
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export default GapAnalysis;
