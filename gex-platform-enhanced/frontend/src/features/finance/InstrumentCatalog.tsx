// ──────────────────────────────────────────────────────────
// FILE 2: InstrumentCatalog.tsx
// Route: /finance-instruments
// Zone: STRUCTURE (teal)
// API: GET /api/v1/instruments/eligible/{project_id}
// ──────────────────────────────────────────────────────────
 
// Save as: src/features/finance/InstrumentCatalog.tsx
 
import React, { useState, useEffect } from 'react';
import { AlertTriangle, Search, Layers, ArrowRight } from 'lucide-react';
import { InfoTooltip } from '@/components/ui/InfoTooltip';
import { HELP, TAB_DESCRIPTIONS } from '@/config/helpText';

export function InstrumentCatalog() {
  const [instruments, setInstruments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [projectId] = useState('proj_bremen_h2');
 
  useEffect(() => {
    fetch(`/api/v1/instruments/eligible/${projectId}`)
      .then(r => r.json())
      .then(data => { setInstruments(data.instruments || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [projectId]);
 
  const toggleSelect = (id: string) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };
 
  const TYPE_COLORS: Record<string, string> = {
    GRANT: 'text-green-400 bg-green-900/30',
    CFD: 'text-blue-400 bg-blue-900/30',
    GCGC: 'text-teal-400 bg-teal-900/30',
    PARTIAL_CREDIT: 'text-purple-400 bg-purple-900/30',
    CONCESSIONAL_LOAN: 'text-cyan-400 bg-cyan-900/30',
    OFFTAKE_GUARANTEE: 'text-amber-400 bg-amber-900/30',
    PRI: 'text-red-400 bg-red-900/30',
    TAX_CREDIT: 'text-yellow-400 bg-yellow-900/30',
    EXPORT_CREDIT: 'text-orange-400 bg-orange-900/30',
    GREEN_BOND: 'text-emerald-400 bg-emerald-900/30',
    PERFORMANCE_GUARANTEE: 'text-indigo-400 bg-indigo-900/30',
    CAR_INSURANCE: 'text-pink-400 bg-pink-900/30',
    IRS: 'text-gray-400 bg-gray-900/30',
  };
 
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            Instrument Catalog
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
            {TAB_DESCRIPTIONS.INSTRUMENT_CATALOG}
          </p>
        </div>
        {selectedIds.length > 0 && (
          <button className="px-5 py-2.5 rounded-lg bg-teal-600 hover:bg-teal-500 text-white font-medium flex items-center gap-2 transition-colors">
            <Layers className="w-4 h-4" />
            Build Package ({selectedIds.length} selected)
            <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>
 
      <div className="border-l-4 border-teal-500 bg-teal-900/10 px-4 py-2 rounded-r-lg">
        <span className="text-xs font-bold uppercase tracking-wider text-teal-400">
          Structure Zone
        </span>
        <span className="text-xs text-gray-500 ml-3">
          Browse eligible instruments → Select → Build package
        </span>
      </div>
 
      {loading ? (
        <div className="text-center py-12 text-gray-500">Loading eligible instruments...</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {instruments.map((inst: any) => {
            const isSelected = selectedIds.includes(inst.id);
            const typeClass = TYPE_COLORS[inst.type] || 'text-gray-400 bg-gray-900/30';
            return (
              <div
                key={inst.id}
                onClick={() => toggleSelect(inst.id)}
                className={`shadow-card rounded-2xl p-5 cursor-pointer transition-all
                  ${isSelected ? 'ring-2 ring-teal-500 bg-teal-900/10' : 'hover:bg-gray-800/50'}`}
                style={{ borderColor: 'var(--border)' }}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${typeClass}`}>
                        {inst.type}
                      </span>
                      {isSelected && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-teal-600 text-white">
                          ✓ SELECTED
                        </span>
                      )}
                    </div>
                    <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                      {inst.name}
                    </h3>
                    <p className="text-xs text-gray-500 mt-1">{inst.provider}</p>
                    <div className="mt-3 flex items-center gap-4 text-xs">
                      <div>
                        <span className="text-gray-500 flex items-center gap-1">Rate reduction <InfoTooltip text={HELP.RATE_REDUCTION_BPS} /></span>
                        <p className="font-mono font-bold text-teal-400">
                          -{inst.rate_reduction_bps}bps
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500">Cost</span>
                        <p className="font-mono font-bold" style={{ color: 'var(--text-primary)' }}>
                          {inst.cost_bps}bps
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500 flex items-center gap-1">Coverage <InfoTooltip text={HELP.INSTRUMENT_COVERAGE} /></span>
                        <p className="font-mono font-bold" style={{ color: 'var(--text-primary)' }}>
                          {(inst.coverage * 100).toFixed(0)}%
                        </p>
                      </div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(inst.risks_addressed || []).map((r: string) => (
                        <span key={r} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">
                          {r}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
 