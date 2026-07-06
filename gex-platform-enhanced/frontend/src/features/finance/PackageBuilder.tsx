// Screen: Finance package builder screen (/finance-package)
// ──────────────────────────────────────────────────────────
// FILE 3: PackageBuilder.tsx
// Route: /finance-package
// Zone: STRUCTURE (teal)
// API: GET /api/v1/structuring/{project_id}/recommend
// ──────────────────────────────────────────────────────────
 
// Save as: src/features/finance/PackageBuilder.tsx
 

import { useState, useEffect } from 'react';
import { InfoTooltip } from '@/components/ui/InfoTooltip';
import { HELP, TAB_DESCRIPTIONS } from '@/config/helpText';

export function PackageBuilder() {
  const [recommendation, setRecommendation] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [projectId] = useState('proj_bremen_h2');
 
  useEffect(() => {
    fetch(`/api/v1/structuring/${projectId}/recommend`)
      .then(r => r.json())
      .then(data => { setRecommendation(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [projectId]);
 
  if (loading) return <div className="p-6 text-center text-gray-500">Computing optimal package...</div>;
  if (!recommendation) return <div className="p-6 text-center text-red-400">Failed to load recommendation</div>;
 
  const pkg = recommendation.package || {};
  const before = recommendation.before_metrics || {};
  const after = recommendation.after_metrics || {};
 
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
 
      <div className="border-l-4 border-teal-500 bg-teal-900/10 px-4 py-2 rounded-r-lg">
        <span className="text-xs font-bold uppercase tracking-wider text-teal-400">
          Structure Zone
        </span>
      </div>
 
      {/* Summary banner */}
      <div className="shadow-card rounded-2xl p-6 bg-gradient-to-r from-teal-900/20 to-blue-900/20 border border-teal-500/30">
        <p className="text-sm leading-relaxed" style={{ color: 'var(--text-primary)' }}>
          {recommendation.summary}
        </p>
      </div>
 
      {/* Before / After comparison */}
      <div className="grid grid-cols-2 gap-6">
        <div className="shadow-card rounded-2xl p-5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-4">Before Package</h3>
          <div className="space-y-3">
            {[
              ['WACC', `${before.wacc_pct}%`, HELP.WACC],
              ['DSCR P50', `${before.dscr_p50}x`, HELP.DSCR_P50],
              ['DSCR P90', `${before.dscr_p90}x`, HELP.DSCR_P90],
              ['LLCR', `${before.llcr}x`, HELP.LLCR],
              ['State', before.state, HELP.BANKABILITY_STATE],
            ].map(([label, value, tip]) => (
              <div key={label as string} className="flex justify-between">
                <span className="text-sm text-gray-500 flex items-center gap-1">{label} {tip && <InfoTooltip text={tip as string} />}</span>
                <span className="text-sm font-mono font-bold" style={{ color: 'var(--text-primary)' }}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div className="shadow-card rounded-2xl p-5 ring-2 ring-teal-500/30">
          <h3 className="text-xs font-bold uppercase tracking-wider text-teal-400 mb-4">After Package</h3>
          <div className="space-y-3">
            {[
              ['WACC', `${after.wacc_pct}%`, after.wacc_pct < before.wacc_pct],
              ['DSCR P50', `${after.dscr_p50}x`, after.dscr_p50 > before.dscr_p50],
              ['DSCR P90', `${after.dscr_p90}x`, after.dscr_p90 > before.dscr_p90],
              ['LLCR', `${after.llcr}x`, after.llcr > before.llcr],
              ['State', after.state, after.state !== before.state],
            ].map(([label, value, improved]) => (
              <div key={label as string} className="flex justify-between">
                <span className="text-sm text-gray-500">{label}</span>
                <span className={`text-sm font-mono font-bold ${improved ? 'text-teal-400' : ''}`}
                      style={improved ? {} : { color: 'var(--text-primary)' }}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>
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
 