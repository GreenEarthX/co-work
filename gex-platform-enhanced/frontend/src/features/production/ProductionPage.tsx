// Screen: Production screen (/production)
import { useState, useMemo } from 'react';
import { Search, Eye, Edit, Trash2 } from 'lucide-react';
import { type CustomerProject } from '@/data/customerProjects';
import { useSelectedProject } from '@/contexts/ProjectContext';
import { useVisibleProjects } from '@/hooks/useVisibleProjects';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ProductionBatch {
  id: string;
  project_id: string;
  project_name: string;
  molecule: string;
  batch_number: string;
  volume_mt: number;
  production_date: string;
  quality_status: 'approved' | 'pending' | 'rejected';
  ghg_intensity: number;
  purity_pct: number;
}

// ─── Derive realistic batches from canonical projects ─────────────────────────

function makeBatchPrefix(id: string): string {
  if (id.includes('bremen'))        return 'BRH2';
  if (id.includes('rotterdam'))     return 'RTNH3';
  if (id.includes('sansebastian'))  return 'HLIO';
  if (id.includes('wales'))         return 'CSAF';
  if (id.includes('lehavre'))       return 'LHENG';
  return 'PROJ';
}

const GHG_BY_MOLECULE: Record<string, number> = {
  H2: 0.35, NH3: 0.41, 'e-Methanol': 0.52, SAF: 0.28, 'e-NG': 0.44,
};
const PURITY_BY_MOLECULE: Record<string, number> = {
  H2: 99.8, NH3: 99.9, 'e-Methanol': 99.5, SAF: 99.6, 'e-NG': 97.2,
};

// Only operating or construction projects have batches
function deriveBatches(projects: CustomerProject[]): ProductionBatch[] {
  const batches: ProductionBatch[] = [];
  let seq = 1;
  for (const p of projects) {
    if (p.status === 'development') continue; // not yet producing
    const prefix = makeBatchPrefix(p.id);
    const ghg    = GHG_BY_MOLECULE[p.molecule] ?? 0.45;
    const purity = PURITY_BY_MOLECULE[p.molecule] ?? 99.5;
    // Produce 2-3 batches per producing project, offset dates by project
    const batchCount = p.status === 'operating' ? 4 : 2;
    for (let i = 0; i < batchCount; i++) {
      const dayOffset = i * 3;
      const date = new Date('2026-02-20');
      date.setDate(date.getDate() + dayOffset);
      const dailyVol = p.capacity_mtpd * (0.85 + Math.sin(seq) * 0.05);
      batches.push({
        id:             `batch_${String(seq).padStart(3, '0')}`,
        project_id:     p.id,
        project_name:   p.name,
        molecule:       p.molecule,
        batch_number:   `${prefix}-2026-${String(i + 1).padStart(3, '0')}`,
        volume_mt:      +dailyVol.toFixed(1),
        production_date: date.toISOString().slice(0, 10),
        quality_status: i === 1 ? 'pending' : 'approved',
        ghg_intensity:  +(ghg + (i === 0 ? 0 : 0.03)).toFixed(2),
        purity_pct:     +(purity - (i === 1 ? 0.1 : 0)).toFixed(1),
      });
      seq++;
    }
  }
  return batches;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<string, string> = {
  approved: 'gex-badge gex-badge-green',
  pending:  'gex-badge gex-badge-amber',
  rejected: 'gex-badge gex-badge-red',
};

// ─── Page ─────────────────────────────────────────────────────────────────────

export function ProductionPage() {
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject();
  const { projects: visibleProjects } = useVisibleProjects();
  const [search, setSearch]   = useState('');
  const allBatches = useMemo(() => deriveBatches(visibleProjects), [visibleProjects]);
  const [batches, setBatches] = useState<ProductionBatch[]>(allBatches);

  const filtered = useMemo(() =>
    batches.filter(b => {
      const matchProject = selectedProjectId === 'all' || b.project_id === selectedProjectId;
      const matchSearch  = search === '' ||
        b.batch_number.toLowerCase().includes(search.toLowerCase()) ||
        b.project_name.toLowerCase().includes(search.toLowerCase());
      return matchProject && matchSearch;
    }),
    [batches, selectedProjectId, search]
  );

  const totalVol     = filtered.reduce((s, b) => s + b.volume_mt, 0);
  const approvedCnt  = filtered.filter(b => b.quality_status === 'approved').length;
  const pendingCnt   = filtered.filter(b => b.quality_status === 'pending').length;
  // const avgGhg       = filtered.length
  //   ? (filtered.reduce((s, b) => s + b.ghg_intensity, 0) / filtered.length).toFixed(2)
  //   : '—';

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">Production Management</h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">Monitor production batches and quality control</p>
        </div>
      </div>

      {/* ── Filters ── */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={selectedProjectId}
          onChange={e => setSelectedProjectId(e.target.value)}
          className="gex-select text-sm"
          aria-label="Filter by project"
        >
          <option value="all">All projects</option>
          {visibleProjects.filter(p => p.status !== 'development').map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <div className="relative flex-1" style={{ maxWidth: '320px' }}>
          <Search className="absolute left-3 top-1/2 w-3.5 h-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search batches…"
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] py-[7px] pl-9 pr-4 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--brand)] focus:outline-none focus:ring-2 focus:ring-[var(--brand-ring)]"
          />
        </div>
      </div>

      {/* ── KPI strip ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Batches',          value: String(filtered.length),       accent: 'text-[var(--text-primary)]' },
          { label: 'Total Volume (MT)', value: totalVol.toFixed(1),          accent: 'text-[var(--brand)]' },
          { label: 'Approved',         value: String(approvedCnt),           accent: 'text-emerald-600 dark:text-emerald-400' },
          { label: 'Pending Review',   value: String(pendingCnt),            accent: 'text-amber-600 dark:text-amber-400' },
        ].map(({ label, value, accent }) => (
          <div key={label} className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 shadow-card">
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">{label}</div>
            <div className={`mt-1 font-display text-2xl font-extrabold leading-none ${accent}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Table ── */}
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Production Batches</h2>
        </div>

        {filtered.length === 0 ? (
          <div className="px-6 py-12 text-center text-sm text-[var(--text-muted)]">
            No batches found for the selected filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="gex-table">
              <thead>
                <tr>
                  {['Batch', 'Project', 'Volume', 'Quality', 'GHG kg/kg', 'Purity', 'Date', ''].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(batch => (
                  <tr key={batch.id}>
                    <td>
                      <div className="font-mono font-semibold text-[var(--text-primary)]">{batch.batch_number}</div>
                      <div className="text-xs text-[var(--text-muted)]">{batch.molecule}</div>
                    </td>
                    <td className="text-[var(--text-secondary)]">{batch.project_name}</td>
                    <td className="font-mono font-semibold text-[var(--text-primary)]">{batch.volume_mt} MT</td>
                    <td>
                      <span className={STATUS_BADGE[batch.quality_status] ?? 'gex-badge gex-badge-default'}>
                        {batch.quality_status}
                      </span>
                    </td>
                    <td className="font-mono text-[var(--text-secondary)]">{batch.ghg_intensity}</td>
                    <td className="font-mono text-[var(--text-secondary)]">{batch.purity_pct}%</td>
                    <td className="text-[var(--text-muted)]">{batch.production_date}</td>
                    <td>
                      <div className="flex items-center gap-1">
                        <button className="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--brand)] hover:bg-[var(--surface-hover)] transition-colors">
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        <button className="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--brand)] hover:bg-[var(--surface-hover)] transition-colors">
                          <Edit className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setBatches(bs => bs.filter(b => b.id !== batch.id))}
                          className="p-1.5 rounded text-[var(--text-muted)] hover:text-red-500 hover:bg-[var(--surface-hover)] transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
