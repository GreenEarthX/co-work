// Screen: Finance package builder screen (/finance-package)
// ──────────────────────────────────────────────────────────
// FILE 3: PackageBuilder.tsx
// Route: /finance-package
// Zone: STRUCTURE (teal)
// API: GET /api/v1/structuring/{project_id}/recommend
// ──────────────────────────────────────────────────────────

// Save as: src/features/finance/PackageBuilder.tsx


import { useProjectResource } from './useProjectResource';
import { InfoTooltip } from '@/components/ui/InfoTooltip';
import { HELP, TAB_DESCRIPTIONS } from '@/config/helpText';
import { ReadinessStamp } from '@/components/ReadinessStamp';

export function PackageBuilder() {
  const { data: recommendation, loading, error } = useProjectResource<any>((pid) => `/api/v1/structuring/${pid}/recommend`);

  if (loading) return <div className="p-6 text-center text-gray-500">Computing optimal package...</div>;
  if (error) return <div role="alert" className="p-6 text-center text-sm text-[var(--text-secondary)]">{error}</div>;
  if (!recommendation) return <div className="p-6 text-center text-red-400">Failed to load recommendation</div>;

  const pkg = recommendation.package || {};
  const before = recommendation.before_metrics || {};
  const est = recommendation.after_metrics || {};
  const outcome = pkg.conditional_outcome || {};
  const fmt = (v: number | null | undefined, suffix: string) => (v === null || v === undefined ? '—' : `${v}${suffix}`);

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
          Package Builder
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          {TAB_DESCRIPTIONS.PACKAGE_BUILDER}
        </p>
      </div>

      <ReadinessStamp readiness={recommendation.readiness} />

      <div className="shadow-card rounded-2xl p-6 border border-teal-500/30">
        <p className="text-sm leading-relaxed" style={{ color: 'var(--text-primary)' }}>
          {recommendation.summary}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="shadow-card rounded-2xl p-5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-4">Before package (recorded inputs)</h3>
          <div className="space-y-3">
            {[
              ['WACC', fmt(before.wacc === null || before.wacc === undefined ? null : +(before.wacc * 100).toFixed(2), '%'), HELP.WACC],
              ['DSCR P50', fmt(before.dscr_p50, 'x'), HELP.DSCR_P50],
              ['DSCR P90', fmt(before.dscr_p90, 'x'), HELP.DSCR_P90],
              ['LLCR', 'Unavailable here — engine-computed on a returns case', HELP.LLCR],
              ['State (gate engine)', before.state ?? 'not evaluated', HELP.BANKABILITY_STATE],
            ].map(([label, value, tip]) => (
              <div key={label as string} className="flex justify-between gap-4">
                <span className="text-sm text-gray-500 flex items-center gap-1">{label} {tip && <InfoTooltip text={tip as string} />}</span>
                <span className="text-sm font-mono font-bold text-right" style={{ color: 'var(--text-primary)' }}>{value}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="shadow-card rounded-2xl p-5 border border-dashed border-slate-400" data-testid="package-estimates">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">After package — ESTIMATE</h3>
          <p className="text-[11px] text-slate-500 mb-4">{est.method}</p>
          <div className="space-y-3">
            {(['wacc_pct', 'dscr_p50', 'dscr_p90', 'llcr'] as const).map((k) => {
              const e = est[k] || {};
              const suffix = k === 'wacc_pct' ? '%' : 'x';
              return (
                <div key={k} className="flex justify-between gap-4">
                  <span className="text-sm text-gray-500">{e.label}</span>
                  <span className="text-sm font-mono">{e.value === null || e.value === undefined ? (e.basis === 'UNAVAILABLE' ? 'Unavailable' : '—') : `${e.value}${suffix}`}
                    <span className="ml-2 text-[10px] uppercase text-slate-500">{e.basis}</span></span>
                </div>
              );
            })}
            <div className="flex justify-between gap-4">
              <span className="text-sm text-gray-500">State</span>
              <span className="text-sm font-mono">{pkg.current_state ?? 'not evaluated'} <span className="text-[10px] uppercase text-slate-500">unchanged</span></span>
            </div>
          </div>
        </div>
      </div>

      <div className="shadow-card rounded-2xl p-5" data-testid="conditional-outcome">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">
          {outcome.label || 'conditional — not achieved'}
        </h3>
        <p className="mt-1 text-sm" style={{ color: 'var(--text-primary)' }}>
          {outcome.would_follow
            ? `${outcome.would_follow_label || outcome.would_follow} would follow only once the gate engine finds these requirements verified:`
            : 'No further state.'}
        </p>
        <ul className="mt-2 space-y-1 text-xs text-[var(--text-secondary)]">
          {(outcome.gates || []).map((g: any) => (
            <li key={g.gate_id}><span className="font-semibold">{g.gate_name}</span>: {[...(g.open_requirements || []), ...(g.open_reasons || [])].join('; ')}</li>
          ))}
        </ul>
      </div>

      {/* Package items */}
      <div>
        <h2 className="text-lg font-bold mb-4" style={{ color: 'var(--text-primary)' }}>
          Instruments in Package ({(pkg.items || []).length})
        </h2>
        <div className="space-y-3">
          {(pkg.items || []).map((item: any, i: number) => (
            <div key={i} className="shadow-card rounded-xl p-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                  {item.instrument_name}
                </p>
                <p className="text-xs text-gray-500">{item.provider} · {item.instrument_type}</p>
              </div>
              <div className="flex items-center gap-6 text-xs">
                <div className="text-center">
                  <span className="text-gray-500">Rate cut</span>
                  <p className="font-mono font-bold text-teal-400">-{item.rate_reduction_bps}bps</p>
                </div>
                <div className="text-center">
                  <span className="text-gray-500">Cost</span>
                  <p className="font-mono font-bold">{item.cost_bps}bps</p>
                </div>
                <div className="text-center">
                  <span className="text-gray-500">Coverage</span>
                  <p className="font-mono font-bold">{(item.coverage_pct * 100).toFixed(0)}%</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Warnings */}
      {(pkg.stackability_warnings || []).length > 0 && (
        <div className="bg-amber-900/20 border border-amber-500/30 rounded-xl p-4">
          <h3 className="text-xs font-bold uppercase text-amber-400 mb-2 flex items-center gap-1">Stackability Warnings <InfoTooltip text={HELP.STACKABILITY_WARNING} /></h3>
          {pkg.stackability_warnings.map((w: string, i: number) => (
            <p key={i} className="text-sm text-amber-300">{w}</p>
          ))}
        </div>
      )}
    </div>
  );
}
