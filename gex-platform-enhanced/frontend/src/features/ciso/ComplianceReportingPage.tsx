// Screen: Compliance reporting screen (/ciso-compliance, /ciso-policy)
import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Clock, ChevronDown, ChevronRight, Download } from 'lucide-react';

// ─── Types ───────────────────────────────────────────────────────────────────

interface ComplianceDomain {
  domain: string;
  score: number;
  controls: number;
  passed: number;
}

interface ComplianceFramework {
  id: string;
  name: string;
  description: string;
  score: number;
  status: 'certified' | 'in_progress' | 'partial' | 'not_started';
  cert_expiry: string | null;
  domains: ComplianceDomain[];
}

interface ComplianceData {
  overall_score: number;
  frameworks: ComplianceFramework[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; badge: string }> = {
  certified:   { label: 'Certified',   badge: 'gex-badge gex-badge-green' },
  in_progress: { label: 'In Progress', badge: 'gex-badge gex-badge-amber' },
  partial:     { label: 'Partial',     badge: 'gex-badge gex-badge-amber' },
  not_started: { label: 'Not Started', badge: 'gex-badge gex-badge-default' },
};

const FRAMEWORK_COLOR: Record<string, string> = {
  iso_27001: 'from-blue-500 to-blue-600',
  soc2:      'from-violet-500 to-violet-600',
  gdpr:      'from-emerald-500 to-emerald-600',
  abac:      'from-indigo-500 to-indigo-600',
};

function ScoreBar({ score, color: _color }: { score: number; color?: string }) {
  const bg = score >= 80 ? 'bg-emerald-500' : score >= 60 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="h-1.5 w-full rounded-full bg-[var(--border)]">
      <div className={`h-full rounded-full transition-all duration-700 ${bg}`} style={{ width: `${score}%` }} />
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const color = score >= 80 ? '#10b981' : score >= 60 ? '#f59e0b' : '#ef4444';
  const r = 22;
  const circ = 2 * Math.PI * r;
  const dash = circ - (score / 100) * circ;
  return (
    <div className="relative w-14 h-14 flex-shrink-0">
      <svg className="w-full h-full -rotate-90" viewBox="0 0 56 56">
        <circle cx="28" cy="28" r={r} fill="none" strokeWidth="5" className="stroke-[var(--border)]" />
        <circle cx="28" cy="28" r={r} fill="none" strokeWidth="5"
          strokeLinecap="round"
          stroke={color}
          strokeDasharray={circ}
          strokeDashoffset={dash}
          style={{ transition: 'stroke-dashoffset 0.8s ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-xs font-extrabold" style={{ color }}>{score}</span>
      </div>
    </div>
  );
}

// ─── Framework accordion ─────────────────────────────────────────────────────

function FrameworkCard({ fw }: { fw: ComplianceFramework }) {
  const [open, setOpen] = useState(false);
  const cfg = STATUS_CONFIG[fw.status] ?? STATUS_CONFIG.not_started;
  const grad = FRAMEWORK_COLOR[fw.id] ?? 'from-gray-500 to-gray-600';

  const totalControls = fw.domains.reduce((s, d) => s + d.controls, 0);
  const totalPassed   = fw.domains.reduce((s, d) => s + d.passed, 0);
  const gap           = totalControls - totalPassed;

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
      {/* Header stripe */}
      <div className={`h-1.5 w-full bg-gradient-to-r ${grad}`} />

      {/* Summary row */}
      <button
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-4 px-5 py-4 text-left hover:bg-[var(--surface-hover)] transition-colors"
      >
        <ScoreRing score={fw.score} />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-bold text-[var(--text-primary)]">{fw.name}</span>
            <span className={cfg.badge}>{cfg.label}</span>
            {fw.cert_expiry && (
              <span className="text-[10px] text-[var(--text-muted)]">
                Expires {new Date(fw.cert_expiry).toLocaleDateString('en-GB')}
              </span>
            )}
          </div>
          <div className="mt-0.5 text-xs text-[var(--text-muted)]">{fw.description}</div>
          <div className="mt-2 flex items-center gap-3 text-xs text-[var(--text-secondary)]">
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{totalPassed} passed</span>
            <span>·</span>
            {gap > 0
              ? <span className="text-amber-600 dark:text-amber-400 font-semibold">{gap} gap{gap > 1 ? 's' : ''}</span>
              : <span className="text-emerald-600 dark:text-emerald-400 font-semibold">No gaps</span>}
            <span>·</span>
            <span>{totalControls} controls</span>
          </div>
        </div>
        {open
          ? <ChevronDown className="w-4 h-4 flex-shrink-0 text-[var(--text-muted)]" />
          : <ChevronRight className="w-4 h-4 flex-shrink-0 text-[var(--text-muted)]" />}
      </button>

      {/* Domain breakdown */}
      {open && (
        <div className="border-t border-[var(--border)]">
          <div className="overflow-x-auto">
            <table className="gex-table">
              <thead>
                <tr>
                  <th>Domain / Control Area</th>
                  <th>Passed</th>
                  <th>Controls</th>
                  <th style={{ minWidth: '120px' }}>Coverage</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {fw.domains.map(dom => {
                  const pct = dom.controls > 0 ? Math.round((dom.passed / dom.controls) * 100) : dom.score;
                  const ok  = pct >= 80;
                  const warn = pct >= 60 && pct < 80;
                  return (
                    <tr key={dom.domain}>
                      <td className="text-sm text-[var(--text-primary)] max-w-[260px]">{dom.domain}</td>
                      <td className="font-mono text-sm text-[var(--text-secondary)]">
                        {dom.passed}/{dom.controls}
                      </td>
                      <td className="font-mono text-sm text-[var(--text-muted)]">{dom.controls}</td>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="flex-1">
                            <ScoreBar score={dom.score} />
                          </div>
                          <span className={`text-xs font-bold w-8 text-right
                            ${ok ? 'text-emerald-600 dark:text-emerald-400'
                              : warn ? 'text-amber-600 dark:text-amber-400'
                              : 'text-red-600 dark:text-red-400'}`}>
                            {dom.score}%
                          </span>
                        </div>
                      </td>
                      <td>
                        {ok
                          ? <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 text-xs font-semibold">
                              <CheckCircle className="w-3.5 h-3.5" /> OK
                            </span>
                          : pct === 0
                          ? <span className="flex items-center gap-1 text-red-600 dark:text-red-400 text-xs font-semibold">
                              <XCircle className="w-3.5 h-3.5" /> Not started
                            </span>
                          : <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400 text-xs font-semibold">
                              <Clock className="w-3.5 h-3.5" /> Gap
                            </span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Policy matrix page ───────────────────────────────────────────────────────

function PolicyMatrixPage() {
  const [matrix, setMatrix] = useState<any>(null);

  useEffect(() => {
    fetch('/api/v1/ciso/policy-matrix')
      .then(r => r.ok ? r.json() : null)
      .then(d => setMatrix(d))
      .catch(() => null);
  }, []);

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
  const [data, setData]   = useState<ComplianceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab]     = useState<'frameworks' | 'matrix'>('frameworks');

  useEffect(() => {
    fetch('/api/v1/ciso/compliance')
      .then(r => r.ok ? r.json() : null)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const overall = data?.overall_score ?? 74;
  const scoreColor = overall >= 75 ? 'text-emerald-600 dark:text-emerald-400'
    : overall >= 50 ? 'text-amber-600 dark:text-amber-400'
    : 'text-red-600 dark:text-red-400';

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">Compliance Reporting</h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            ISO 27001 · SOC 2 · GDPR · GEX ABAC Policy — BP Global Energy
          </p>
        </div>
        <button className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors">
          <Download className="w-3.5 h-3.5" /> Export Report
        </button>
      </div>

      {/* ── Overall score + framework scores ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {/* Overall */}
        <div className="col-span-2 sm:col-span-1 flex flex-col items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-5 shadow-card">
          <div className={`font-display text-5xl font-extrabold ${scoreColor}`}>{overall}</div>
          <div className="mt-1 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Overall Score
          </div>
          <div className="mt-2 w-full">
            <ScoreBar score={overall} />
          </div>
        </div>

        {/* Per-framework */}
        {(data?.frameworks ?? []).map(fw => {
          const cfg = STATUS_CONFIG[fw.status];
          return (
            <div key={fw.id} className="flex flex-col justify-between rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 shadow-card">
              <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">{fw.name}</div>
              <div className={`mt-1 font-display text-2xl font-extrabold ${
                fw.score >= 80 ? 'text-emerald-600 dark:text-emerald-400'
                : fw.score >= 60 ? 'text-amber-600 dark:text-amber-400'
                : 'text-red-600 dark:text-red-400'}`}>{fw.score}</div>
              <div className="mt-1.5">
                <ScoreBar score={fw.score} />
              </div>
              <span className={`mt-2 self-start ${cfg.badge}`}>{cfg.label}</span>
            </div>
          );
        })}
      </div>

      {/* ── Tab bar ── */}
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

      {/* ── Content ── */}
      {loading ? (
        <div className="py-12 text-center text-sm text-[var(--text-muted)]">Loading compliance data…</div>
      ) : tab === 'frameworks' ? (
        <div className="space-y-4">
          {(data?.frameworks ?? []).map(fw => (
            <FrameworkCard key={fw.id} fw={fw} />
          ))}
        </div>
      ) : (
        <PolicyMatrixPage />
      )}

    </div>
  );
}
