// ──────────────────────────────────────────────────────────
// FILE 6: DemandPipeline.tsx
// Route: /finance-demand
// Zone: STRUCTURE (teal)
// API: GET /api/v1/demand/pipeline/{project_id}
//      GET /api/v1/demand/coverage/{project_id}
// ──────────────────────────────────────────────────────────
 
// Save as: src/features/finance/DemandPipeline.tsx
 
import React, { useState, useEffect } from 'react';
import { AlertTriangle, Search, Layers, ArrowRight } from 'lucide-react';
import { InfoTooltip } from '@/components/ui/InfoTooltip';
import { HELP, TAB_DESCRIPTIONS } from '@/config/helpText';

export function DemandPipeline() {
  const [coverage, setCoverage] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [projectId] = useState('proj_bremen_h2');
 
  useEffect(() => {
    fetch(`/api/v1/demand/coverage/${projectId}?total_production=10000`)
      .then(r => r.json())
      .then(d => { setCoverage(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [projectId]);
 
  const STATUS_STYLES: Record<string, string> = {
    CONTRACT_EXECUTED: 'bg-green-900/30 text-green-400',
    BINDING_TERM_SHEET: 'bg-teal-900/30 text-teal-400',
    LOI: 'bg-amber-900/30 text-amber-400',
    EOI: 'bg-gray-800 text-gray-400',
  };
 
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
          Demand Pipeline
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          {TAB_DESCRIPTIONS.DEMAND_PIPELINE}
        </p>
      </div>
 
      <div className="border-l-4 border-teal-500 bg-teal-900/10 px-4 py-2 rounded-r-lg">
        <span className="text-xs font-bold uppercase tracking-wider text-teal-400">
          Structure Zone
        </span>
      </div>
 
      {loading ? (
        <div className="text-center py-12 text-gray-500">Loading demand pipeline...</div>
      ) : coverage ? (
        <>
          {/* Coverage summary */}
          <div className="grid grid-cols-4 gap-4">
            {[
              ['Firm Coverage', `${(coverage.firm_coverage_pct * 100).toFixed(0)}%`,
               coverage.bankable_threshold_met ? 'text-green-400' : 'text-red-400'],
              ['Signals', coverage.signal_count, 'text-blue-400'],
              ['Gap', `${coverage.gap_tonnes?.toLocaleString() || 0}t`, 'text-amber-400'],
              ['Anchor', coverage.anchor_buyer || 'None', 'text-teal-400'],
            ].map(([label, value, color]) => (
              <div key={label as string} className="shadow-card rounded-xl p-4 text-center">
                <p className="text-xs text-gray-500 uppercase">{label}</p>
                <p className={`text-2xl font-bold font-mono mt-1 ${color}`}>{value}</p>
              </div>
            ))}
          </div>
 
          {/* Coverage bar */}
          <div className="shadow-card rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-500 flex items-center gap-1">Offtake Coverage vs 70% Bankable Threshold <InfoTooltip text={HELP.OFFTAKE_COVERAGE} /></span>
              <span className={`text-xs font-bold ${coverage.bankable_threshold_met ? 'text-green-400' : 'text-red-400'}`}>
                {coverage.bankable_threshold_met ? '✓ THRESHOLD MET' : '✗ BELOW THRESHOLD'}
              </span>
            </div>
            <div className="w-full h-6 bg-gray-800 rounded-full relative overflow-hidden">
              {/* Contracted */}
              <div
                className="h-full bg-green-600 absolute left-0 top-0"
                style={{ width: `${Math.min(coverage.contracted_pct * 100, 100)}%` }}
              />
              {/* LOI */}
              <div
                className="h-full bg-amber-600/50 absolute top-0"
                style={{
                  left: `${coverage.contracted_pct * 100}%`,
                  width: `${coverage.loi_pct * 100}%`,
                }}
              />
              {/* EOI */}
              <div
                className="h-full bg-gray-600/50 absolute top-0"
                style={{
                  left: `${(coverage.contracted_pct + coverage.loi_pct) * 100}%`,
                  width: `${coverage.eoi_pct * 100}%`,
                }}
              />
              {/* 70% threshold line */}
              <div className="absolute top-0 bottom-0 w-0.5 bg-red-500"
                   style={{ left: '70%' }} />
            </div>
            <div className="flex gap-4 mt-2 text-[10px]">
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded bg-green-600" /> Contracted
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded bg-amber-600" /> LOI
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded bg-gray-600" /> EOI
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-1 bg-red-500" /> 70% threshold
              </span>
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-12">
          <p className="text-gray-500">No demand signals recorded yet.</p>
          <button className="mt-4 px-4 py-2 rounded-lg bg-teal-600 text-white text-sm">
            Add Demand Signal
          </button>
        </div>
      )}
    </div>
  );
}
 