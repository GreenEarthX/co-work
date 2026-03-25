// ──────────────────────────────────────────────────────────
// FILE 4: RiskAllocationMatrix.tsx
// Route: /finance-risk-matrix
// Zone: STRUCTURE (teal)
// API: GET /api/v1/structuring/{project_id}/risk-allocation
// ──────────────────────────────────────────────────────────
 
// Save as: src/features/finance/RiskAllocationMatrix.tsx
 
import React, { useState, useEffect } from 'react';
import { AlertTriangle, Search, Layers, ArrowRight } from 'lucide-react';
import { InfoTooltip } from '@/components/ui/InfoTooltip';
import { HELP, TAB_DESCRIPTIONS } from '@/config/helpText';

export function RiskAllocationMatrix() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [projectId] = useState('proj_bremen_h2');
 
  useEffect(() => {
    fetch(`/api/v1/structuring/${projectId}/risk-allocation`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [projectId]);
 
  const RISK_COLORS: Record<string, string> = {
    HIGH: 'text-red-400', MEDIUM: 'text-amber-400', LOW: 'text-green-400', NEGLIGIBLE: 'text-gray-500',
  };
 
  if (loading) return <div className="p-6 text-center text-gray-500">Computing risk allocation...</div>;
 
  const entries = data?.entries || [];
 
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            Risk Allocation Matrix
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
            {TAB_DESCRIPTIONS.RISK_ALLOCATION_MATRIX}
          </p>
        </div>
        <div className="flex gap-3">
          <span className="px-3 py-1.5 rounded-full bg-teal-900/30 text-teal-400 text-sm font-bold">
            {data?.total_mitigated || 0} Mitigated
          </span>
          <span className="px-3 py-1.5 rounded-full bg-gray-800 text-gray-300 text-sm font-bold">
            +{data?.total_residual_bps || 0}bps residual
          </span>
        </div>
      </div>
 
      <div className="border-l-4 border-teal-500 bg-teal-900/10 px-4 py-2 rounded-r-lg">
        <span className="text-xs font-bold uppercase tracking-wider text-teal-400">
          Structure Zone
        </span>
      </div>
 
      {/* Unmitigated blocking risks */}
      {(data?.unmitigated_blocking || []).length > 0 && (
        <div className="bg-red-900/20 border border-red-500/30 rounded-xl p-4">
          <h3 className="text-xs font-bold uppercase text-red-400 mb-2">
            Unmitigated Blocking Risks
          </h3>
          {data.unmitigated_blocking.map((r: string, i: number) => (
            <p key={i} className="text-sm text-red-300 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> {r}
            </p>
          ))}
        </div>
      )}
 
      {/* Matrix table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700">
              {[
                { label: 'Risk', tip: null },
                { label: 'Category', tip: null },
                { label: 'Prob.', tip: HELP.RISK_PROBABILITY },
                { label: 'Impact', tip: HELP.RISK_IMPACT },
                { label: 'Bearer', tip: null },
                { label: 'Instrument', tip: null },
                { label: 'Residual', tip: HELP.RESIDUAL_RISK },
                { label: 'Cost (bps)', tip: HELP.INSTRUMENT_COST_BPS },
              ].map(({ label, tip }) => (
                <th key={label} className="text-left py-3 px-3 text-xs font-bold uppercase tracking-wider text-gray-500">
                  <span className="flex items-center gap-1">{label}{tip && <InfoTooltip text={tip} />}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry: any, i: number) => (
              <tr key={i} className={`border-b border-gray-800 ${i % 2 === 0 ? '' : 'bg-gray-900/30'}`}>
                <td className="py-3 px-3 font-medium" style={{ color: 'var(--text-primary)' }}>
                  {entry.risk_name}
                </td>
                <td className="py-3 px-3">
                  <span className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400">
                    {entry.risk_category}
                  </span>
                </td>
                <td className={`py-3 px-3 font-bold ${RISK_COLORS[entry.probability] || ''}`}>
                  {entry.probability}
                </td>
                <td className={`py-3 px-3 font-bold ${RISK_COLORS[entry.impact] || ''}`}>
                  {entry.impact}
                </td>
                <td className="py-3 px-3 text-gray-300">{entry.bearer}</td>
                <td className="py-3 px-3">
                  {entry.instrument_mitigating === 'NONE' ? (
                    <span className="text-red-400 text-xs">No instrument</span>
                  ) : (
                    <span className="text-teal-400 text-xs">{entry.instrument_name}</span>
                  )}
                </td>
                <td className={`py-3 px-3 font-bold ${RISK_COLORS[entry.residual_risk] || ''}`}>
                  {entry.residual_risk}
                </td>
                <td className="py-3 px-3 font-mono">{entry.residual_cost_bps}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
 