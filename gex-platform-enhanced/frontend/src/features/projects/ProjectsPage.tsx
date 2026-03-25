import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MapPin, DollarSign, Zap, ChevronRight, BarChart2, X, ExternalLink,
} from 'lucide-react';
import { CUSTOMER_PROJECTS, type CustomerProject } from '@/data/customerProjects';
import { useSelectedProject } from '@/contexts/ProjectContext';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const MOLECULE_META: Record<string, { bg: string; text: string; label: string }> = {
  'H2':        { bg: 'bg-sky-50 dark:bg-sky-900/25',      text: 'text-sky-700 dark:text-sky-300',     label: 'Hydrogen'    },
  'NH3':       { bg: 'bg-violet-50 dark:bg-violet-900/25', text: 'text-violet-700 dark:text-violet-300', label: 'Ammonia'   },
  'e-Methanol':{ bg: 'bg-emerald-50 dark:bg-emerald-900/25',text: 'text-emerald-700 dark:text-emerald-300', label: 'e-Methanol' },
  'SAF':       { bg: 'bg-amber-50 dark:bg-amber-900/25',   text: 'text-amber-700 dark:text-amber-300', label: 'SAF'         },
  'e-NG':      { bg: 'bg-teal-50 dark:bg-teal-900/25',     text: 'text-teal-700 dark:text-teal-300',   label: 'e-Gas'       },
};

const STATUS_META: Record<string, { badge: string; label: string }> = {
  development:    { badge: 'gex-badge gex-badge-amber',   label: 'Development' },
  construction:   { badge: 'gex-badge gex-badge-blue',    label: 'Construction' },
  commissioning:  { badge: 'gex-badge gex-badge-default', label: 'Commissioning' },
  operating:      { badge: 'gex-badge gex-badge-green',   label: 'Operating' },
};

function progressColor(pct: number) {
  if (pct >= 85) return 'bg-emerald-500';
  if (pct >= 55) return 'bg-amber-400';
  return 'bg-brand-500';
}

// ─── Detail panel ─────────────────────────────────────────────────────────────

function ProjectDetail({ project, onClose, onSelectBankability }: {
  project: CustomerProject;
  onClose: () => void;
  onSelectBankability: () => void;
}) {
  const mol = MOLECULE_META[project.molecule] ?? MOLECULE_META['H2'];
  const st  = STATUS_META[project.status] ?? STATUS_META['development'];
  const bankPct = project.bankability.overall_completion;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm animate-fade-in"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-xl rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-dropdown overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-[var(--border)] px-6 py-4">
          <div className="flex items-center gap-3">
            <div className={`flex h-10 w-10 items-center justify-center rounded-xl text-sm font-bold ${mol.bg} ${mol.text}`}>
              {project.molecule}
            </div>
            <div>
              <h2 className="font-display text-lg font-bold text-[var(--text-primary)]">{project.name}</h2>
              <div className="flex items-center gap-1 text-xs text-[var(--text-muted)]">
                <MapPin className="w-3 h-3" />
                {project.location}
                <span className="ml-1 font-mono">({project.lat.toFixed(4)}°N, {Math.abs(project.lng).toFixed(4)}°{project.lng >= 0 ? 'E' : 'W'})</span>
              </div>
            </div>
          </div>
          <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-5">
          <p className="text-sm text-[var(--text-secondary)]">{project.description}</p>

          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Molecule', value: mol.label },
              { label: 'Status',   value: <span className={st.badge}>{st.label}</span> },
              { label: 'Capacity', value: `${project.capacity_mtpd} MTPD` },
              { label: 'CAPEX',    value: `€${(project.capex_eur / 1_000_000).toFixed(0)}M` },
              { label: 'Phase',    value: project.phase },
              { label: 'Target COD', value: new Date(project.completion_date).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }) },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2.5">
                <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">{label}</div>
                <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">{value}</div>
              </div>
            ))}
          </div>

          {/* Bankability mini-bar */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Bankability</span>
              <span className="font-mono text-sm font-bold text-[var(--text-primary)]">{bankPct}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-[var(--border)]">
              <div className={`h-full rounded-full transition-all duration-700 ${progressColor(bankPct)}`} style={{ width: `${bankPct}%` }} />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex gap-3 border-t border-[var(--border)] px-6 py-4">
          <button
            onClick={onSelectBankability}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
          >
            <BarChart2 className="w-4 h-4" />
            View Bankability
          </button>
          <button onClick={onClose} className="rounded-lg border border-[var(--border)] px-4 py-2.5 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function ProjectsPage() {
  const navigate = useNavigate();
  const { setSelectedProjectId } = useSelectedProject();
  const [filter, setFilter]       = useState<string>('all');
  const [search, setSearch]       = useState('');
  const [detail, setDetail]       = useState<CustomerProject | null>(null);

  const filtered = CUSTOMER_PROJECTS.filter(p => {
    const matchMol = filter === 'all' || p.molecule === filter;
    const matchStr = search === '' || p.name.toLowerCase().includes(search.toLowerCase()) || p.location.toLowerCase().includes(search.toLowerCase());
    return matchMol && matchStr;
  });

  const handleBankability = (project: CustomerProject) => {
    setSelectedProjectId(project.id);
    setDetail(null);
    navigate('/producer-bankability');
  };

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">Projects & Assets</h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            {CUSTOMER_PROJECTS.length} active projects across 5 sites
          </p>
        </div>
      </div>

      {/* ── Filters ── */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="gex-select text-sm"
        >
          <option value="all">All molecules</option>
          <option value="H2">Hydrogen</option>
          <option value="NH3">Ammonia</option>
          <option value="e-Methanol">e-Methanol</option>
          <option value="SAF">SAF</option>
          <option value="e-NG">e-Gas (e-NG)</option>
        </select>
        <div className="relative flex-1" style={{ maxWidth: '320px' }}>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search projects or locations…"
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] py-[7px] pl-4 pr-4 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--brand)] focus:outline-none focus:ring-2 focus:ring-[var(--brand-ring)]"
          />
        </div>
      </div>

      {/* ── Project cards ── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {filtered.map(project => {
          const mol   = MOLECULE_META[project.molecule] ?? MOLECULE_META['H2'];
          const st    = STATUS_META[project.status] ?? STATUS_META['development'];
          const bPct  = project.bankability.overall_completion;
          return (
            <div
              key={project.id}
              className="gex-card flex flex-col rounded-2xl p-5 transition-shadow hover:shadow-card-md"
            >
              {/* Card header */}
              <div className="flex items-start justify-between gap-3 mb-4">
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-xs font-bold ${mol.bg} ${mol.text}`}>
                    {project.molecule === 'e-Methanol' ? 'MeOH' : project.molecule}
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-display font-bold text-[var(--text-primary)] truncate leading-tight">{project.name}</h3>
                    <div className="flex items-center gap-1 mt-0.5 text-xs text-[var(--text-muted)]">
                      <MapPin className="w-3 h-3 shrink-0" />
                      <span className="truncate">{project.location}</span>
                    </div>
                  </div>
                </div>
                <span className={`${st.badge} shrink-0`}>{st.label}</span>
              </div>

              {/* Key stats */}
              <div className="grid grid-cols-2 gap-2 mb-4">
                {[
                  { icon: <Zap className="w-3 h-3" />,        label: 'Capacity', value: `${project.capacity_mtpd} MTPD` },
                  { icon: <DollarSign className="w-3 h-3" />, label: 'CAPEX',    value: `€${(project.capex_eur / 1_000_000).toFixed(0)}M` },
                ].map(({ icon, label, value }) => (
                  <div key={label} className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2">
                    <div className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">
                      {icon}{label}
                    </div>
                    <div className="mt-0.5 font-mono text-sm font-bold text-[var(--text-primary)]">{value}</div>
                  </div>
                ))}
              </div>

              {/* Bankability strip */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">Bankability</span>
                  <span className="font-mono text-xs font-bold text-[var(--text-primary)]">{bPct}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-[var(--border)]">
                  <div className={`h-full rounded-full transition-all duration-700 ${progressColor(bPct)}`} style={{ width: `${bPct}%` }} />
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2 mt-auto">
                <button
                  onClick={() => setDetail(project)}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-[var(--border)] py-2 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
                >
                  Details
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => handleBankability(project)}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-[var(--brand)] py-2 text-xs font-semibold text-white hover:opacity-90 transition-opacity"
                >
                  <BarChart2 className="w-3.5 h-3.5" />
                  Bankability
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Detail panel ── */}
      {detail && (
        <ProjectDetail
          project={detail}
          onClose={() => setDetail(null)}
          onSelectBankability={() => handleBankability(detail)}
        />
      )}
    </div>
  );
}
