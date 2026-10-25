// Screen: Compliance reporting screen (/ciso-compliance, /ciso-policy)
/**
 * Real data only (2026-10-25). The ISO 27001 / SOC 2 / GDPR scores, control
 * counts and certificate dates this screen showed were invented (with a default
 * overall score of 74), and the header named a sample company. No certification
 * or control-assessment store exists, so the server answers `recorded: false` and
 * this screen says so. The policy matrix is the live access rule.
 */
import { useState, useEffect } from 'react';
import { FileCheck } from 'lucide-react';
import { cisoCall } from './cisoApi';

// ─── Policy matrix page ───────────────────────────────────────────────────────

function PolicyMatrixPage() {
  const [matrix, setMatrix] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    cisoCall('/ciso/policy-matrix').then(setMatrix).catch(e => setError(e.message));
  }, []);

  if (error) return <p className="text-sm text-amber-700 dark:text-amber-300">Policy matrix unavailable: {error}</p>;
  if (!matrix) return null;

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Gate Visibility Matrix</h2>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">Which bankability gates each actor type can access</p>
        </div>
        <div className="overflow-x-auto">
          <table className="gex-table">
            <thead>
              <tr>
                <th>Actor Type</th>
                <th>Visible Gates</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(matrix.gate_visibility).map(([actor, gates]: [string, any]) => (
                <tr key={actor}>
                  <td className="font-mono text-xs font-semibold text-[var(--text-primary)] whitespace-nowrap">
                    {actor}
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {(gates as string[]).map(g => (
                        <span key={g}
                          className="rounded bg-indigo-100 dark:bg-indigo-900/30 px-1.5 py-0.5 text-[10px] font-mono text-indigo-700 dark:text-indigo-300">
                          {g}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Clearance ↔ Sensitivity Map</h2>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {Object.entries(matrix.sensitivity_clearance_map).map(([sens, lvl]: [string, any]) => (
            <div key={sens} className="flex items-center justify-between px-5 py-3">
              <span className="gex-badge gex-badge-default font-mono text-xs">{sens}</span>
              <span className="text-sm text-[var(--text-secondary)]">{lvl}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function ComplianceReportingPage() {
  const [data, setData] = useState<{ recorded: boolean; note: string } | null>(null);
  const [company, setCompany] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'frameworks' | 'matrix'>('frameworks');

  useEffect(() => {
    Promise.all([cisoCall('/ciso/compliance'), cisoCall('/ciso/overview')])
      .then(([c, ov]) => { setData(c); setCompany(ov.company_name ?? ''); })
      .catch(e => setError(e.message));
  }, []);

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">Compliance Reporting</h1>
        <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
          Certifications and access policy{company ? ` — ${company}` : ''}
        </p>
      </div>

      <div className="flex gap-1 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-1 w-fit">
        {[
          { id: 'frameworks', label: 'Compliance Frameworks' },
          { id: 'matrix',     label: 'Policy Matrix' },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id as any)}
            className={`rounded-lg px-4 py-2 text-sm font-semibold transition-colors
              ${tab === t.id
                ? 'bg-[var(--brand)] text-white'
                : 'text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'matrix' ? <PolicyMatrixPage /> : (
        <div className="flex items-start gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4 shadow-card">
          <FileCheck className="mt-0.5 w-4 h-4 text-[var(--text-muted)]" />
          <p className="text-sm text-[var(--text-secondary)]">
            {error ? `Compliance unavailable: ${error}` : data ? data.note : 'Loading…'}
          </p>
        </div>
      )}
    </div>
  );
}
