// Screen: Gap analysis screen (/finance-gaps, /finance/gaps)
// ──────────────────────────────────────────────────────────
// FILE 1: GapAnalysis.tsx
// Route: /finance-gaps
// Zone: STRUCTURE (teal)
// API: GET /api/v1/structuring/{project_id}/gaps
// ──────────────────────────────────────────────────────────
 
import { useState, useEffect } from 'react';
import { AlertTriangle, Search } from 'lucide-react';
 
interface Gap {
  gap_id: string;
  gap_type: string;
  severity: string;
  description: string;
  current_value: string;
  required_value: string;
  delta: string;
  affected_gates: string[];
  affected_metrics: string[];
  risk_category: string;
}
 
const SEVERITY_STYLES: Record<string, { text: string; border: string; badge: string }> = {
  BLOCKING: { text: 'text-red-700', border: 'border-red-500', badge: 'bg-white text-red-700 border-red-200' },
  DEGRADING: { text: 'text-amber-700', border: 'border-amber-500', badge: 'bg-white text-amber-700 border-amber-200' },
  ADVISORY: { text: 'text-slate-700', border: 'border-slate-500', badge: 'bg-white text-slate-700 border-slate-200' },
};
 
export function GapAnalysis() {
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [loading, setLoading] = useState(true);
  const [projectId] = useState('proj_bremen_h2');
 
  useEffect(() => {
    fetch(`/api/v1/structuring/${projectId}/gaps`)
      .then(r => r.json())
      .then(data => { setGaps(data.gaps || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [projectId]);
 
  const blocking = gaps.filter(g => g.severity === 'BLOCKING');
  const degrading = gaps.filter(g => g.severity === 'DEGRADING');
  const advisory = gaps.filter(g => g.severity === 'ADVISORY');
 
  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            Gap Analysis
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
            What's blocking FID? Identify gaps, find instruments, build the package.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="rounded-full border border-red-200 bg-white px-3 py-1.5 text-sm font-semibold text-red-700">
            {blocking.length} Blocking
          </span>
          <span className="rounded-full border border-amber-200 bg-white px-3 py-1.5 text-sm font-semibold text-amber-700">
            {degrading.length} Degrading
          </span>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-semibold text-slate-700">
            {advisory.length} Advisory
          </span>
        </div>
      </div>
 
      {/* Zone indicator */}
      <div className="rounded-r-lg border border-l-4 border-[var(--border)] border-l-teal-500 bg-[var(--surface)] px-4 py-2.5">
        <span className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary)]">
          Structure Zone
        </span>
        <span className="ml-3 text-xs text-[var(--text-muted)]">
          Identify gaps → Find instruments → Build package
        </span>
      </div>
 
      {loading ? (
        <div className="py-12 text-center text-[var(--text-muted)]">Analyzing project gaps...</div>
      ) : (
        <div className="space-y-3">
          {gaps.map(gap => {
            const style = SEVERITY_STYLES[gap.severity] || SEVERITY_STYLES.ADVISORY;
            return (
              <div
                key={gap.gap_id}
                className={`rounded-xl border border-[var(--border)] border-l-4 bg-[var(--surface)] px-4 py-3.5 shadow-card ${style.border}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <AlertTriangle className={`h-4.5 w-4.5 ${style.text}`} />
                      <span className={`text-[11px] font-bold uppercase ${style.text}`}>
                        {gap.severity}
                      </span>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${style.badge}`}>
                        {gap.gap_type}
                      </span>
                      <span className="rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
                        {gap.risk_category}
                      </span>
                    </div>
                    <p className="text-sm font-medium leading-5" style={{ color: 'var(--text-primary)' }}>
                      {gap.description}
                    </p>
                    <div className="mt-3 grid grid-cols-3 gap-3 text-xs">
                      <div>
                        <span className="text-[11px] text-[var(--text-muted)]">Current</span>
                        <p className="mt-0.5 font-mono font-bold" style={{ color: 'var(--text-primary)' }}>
                          {gap.current_value}
                        </p>
                      </div>
                      <div>
                        <span className="text-[11px] text-[var(--text-muted)]">Required</span>
                        <p className="mt-0.5 font-mono font-bold text-[var(--text-primary)]">
                          {gap.required_value}
                        </p>
                      </div>
                      <div>
                        <span className="text-[11px] text-[var(--text-muted)]">Shortfall</span>
                        <p className={`mt-0.5 font-mono font-bold ${style.text}`}>
                          {gap.delta}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {gap.affected_gates.map(g => (
                        <span key={g} className="rounded border border-[var(--border)] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
                          {g}
                        </span>
                      ))}
                      {gap.affected_metrics.map(m => (
                        <span key={m} className="rounded border border-[var(--border)] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                  <button className="ml-4 flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]">
                    <Search className="h-4 w-4" />
                    Find Instruments
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
 
export default GapAnalysis;
 
 
