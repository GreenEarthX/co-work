// ──────────────────────────────────────────────────────────
// FILE 1: GapAnalysis.tsx
// Route: /finance-gaps
// Zone: STRUCTURE (teal)
// API: GET /api/v1/structuring/{project_id}/gaps
// ──────────────────────────────────────────────────────────
 
import React, { useState, useEffect } from 'react';
import { AlertTriangle, ArrowRight, Search, Shield, Zap } from 'lucide-react';
 
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
 
const SEVERITY_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  BLOCKING: { bg: 'bg-red-900/20', text: 'text-red-400', border: 'border-red-500' },
  DEGRADING: { bg: 'bg-amber-900/20', text: 'text-amber-400', border: 'border-amber-500' },
  ADVISORY: { bg: 'bg-blue-900/20', text: 'text-blue-400', border: 'border-blue-500' },
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
    <div className="p-6 space-y-6">
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
        <div className="flex items-center gap-3">
          <span className="px-3 py-1.5 rounded-full bg-red-900/30 text-red-400 text-sm font-bold">
            {blocking.length} Blocking
          </span>
          <span className="px-3 py-1.5 rounded-full bg-amber-900/30 text-amber-400 text-sm font-bold">
            {degrading.length} Degrading
          </span>
          <span className="px-3 py-1.5 rounded-full bg-blue-900/30 text-blue-400 text-sm font-bold">
            {advisory.length} Advisory
          </span>
        </div>
      </div>
 
      {/* Zone indicator */}
      <div className="border-l-4 border-teal-500 bg-teal-900/10 px-4 py-2 rounded-r-lg">
        <span className="text-xs font-bold uppercase tracking-wider text-teal-400">
          Structure Zone
        </span>
        <span className="text-xs text-gray-500 ml-3">
          Identify gaps → Find instruments → Build package
        </span>
      </div>
 
      {loading ? (
        <div className="text-center py-12 text-gray-500">Analyzing project gaps...</div>
      ) : (
        <div className="space-y-4">
          {gaps.map(gap => {
            const style = SEVERITY_STYLES[gap.severity] || SEVERITY_STYLES.ADVISORY;
            return (
              <div
                key={gap.gap_id}
                className={`shadow-card rounded-2xl p-5 border-l-4 ${style.border} ${style.bg}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className={`w-5 h-5 ${style.text}`} />
                      <span className={`text-xs font-bold uppercase ${style.text}`}>
                        {gap.severity}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300">
                        {gap.gap_type}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300">
                        {gap.risk_category}
                      </span>
                    </div>
                    <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      {gap.description}
                    </p>
                    <div className="mt-3 grid grid-cols-3 gap-4 text-xs">
                      <div>
                        <span className="text-gray-500">Current</span>
                        <p className="font-mono font-bold mt-0.5" style={{ color: 'var(--text-primary)' }}>
                          {gap.current_value}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500">Required</span>
                        <p className="font-mono font-bold mt-0.5 text-teal-400">
                          {gap.required_value}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500">Shortfall</span>
                        <p className={`font-mono font-bold mt-0.5 ${style.text}`}>
                          {gap.delta}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 flex gap-2">
                      {gap.affected_gates.map(g => (
                        <span key={g} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">
                          {g}
                        </span>
                      ))}
                      {gap.affected_metrics.map(m => (
                        <span key={m} className="text-[10px] px-1.5 py-0.5 rounded bg-teal-900/30 text-teal-400">
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                  <button className="ml-4 px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 text-white text-sm font-medium flex items-center gap-2 transition-colors">
                    <Search className="w-4 h-4" />
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
 
 