// Screen: Structuring timeline screen (/finance-structuring-timeline)
// ──────────────────────────────────────────────────────────
// FILE 5: StructuringTimeline.tsx
// Route: /finance-structuring-timeline
// Zone: STRUCTURE (teal)
// API: GET /api/v1/structuring/{project_id}/recommend (timeline subset)
// ──────────────────────────────────────────────────────────
 
// Save as: src/features/finance/StructuringTimeline.tsx
 
import { useState, useEffect } from 'react';
import { TAB_DESCRIPTIONS } from '@/config/helpText';

export function StructuringTimeline() {
  const [timeline, setTimeline] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [projectId] = useState('proj_bremen_h2');
 
  useEffect(() => {
    fetch(`/api/v1/structuring/${projectId}/recommend`)
      .then(r => r.json())
      .then(data => {
        // Extract timeline from full recommendation
        const pkg = data.package || {};
        const items = (pkg.items || []).map((item: any, i: number) => ({
          instrument: item.instrument_name,
          provider: item.provider,
          type: item.instrument_type,
          action: 'APPLY',
          deadline: item.application_deadline,
          status: 'PLANNED',
          order: i + 1,
        }));
        setTimeline(items);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [projectId]);
 
  const ACTION_COLORS: Record<string, string> = {
    APPLY: 'bg-teal-900/30 text-teal-400 border-teal-500',
    NEGOTIATE: 'bg-amber-900/30 text-amber-400 border-amber-500',
    EXECUTE: 'bg-green-900/30 text-green-400 border-green-500',
    ACTIVATE: 'bg-blue-900/30 text-blue-400 border-blue-500',
  };
 
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
          Structuring Timeline
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          {TAB_DESCRIPTIONS.STRUCTURING_TIMELINE}
        </p>
      </div>
 
      <div className="border-l-4 border-teal-500 bg-teal-900/10 px-4 py-2 rounded-r-lg">
        <span className="text-xs font-bold uppercase tracking-wider text-teal-400">
          Structure Zone
        </span>
      </div>
 
      {loading ? (
        <div className="text-center py-12 text-gray-500">Building timeline...</div>
      ) : (
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-8 top-0 bottom-0 w-0.5 bg-gray-700" />
 
          <div className="space-y-6">
            {timeline.map((item, i) => {
              const actionStyle = ACTION_COLORS[item.action] || ACTION_COLORS.APPLY;
              return (
                <div key={i} className="flex items-start gap-6 relative">
                  {/* Step number */}
                  <div className="w-16 h-16 rounded-full bg-teal-600 flex items-center justify-center text-white font-bold text-lg z-10 flex-shrink-0">
                    {item.order}
                  </div>
                  {/* Card */}
                  <div className={`shadow-card rounded-xl p-4 flex-1 border-l-4 ${actionStyle.split(' ')[2]}`}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${actionStyle}`}>
                        {item.action}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-400">
                        {item.type}
                      </span>
                    </div>
                    <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                      {item.instrument}
                    </h3>
                    <p className="text-xs text-gray-500 mt-1">
                      {item.provider} · Window: {item.deadline}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
 
 