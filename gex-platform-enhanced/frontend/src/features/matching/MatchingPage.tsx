import React, { useState, useMemo } from 'react';
import {
  Play, RotateCcw, Target, MapPin, Calendar, DollarSign,
  Filter, Settings2, ChevronDown, ChevronUp, Info,
} from 'lucide-react';
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Legend, Tooltip,
} from 'recharts';
import { CUSTOMER_PROJECTS } from '@/data/customerProjects';

// ─── Radar dimension catalogue ────────────────────────────────────────────────

export type RadarDimension =
  | 'price'
  | 'volume'
  | 'carbon_intensity'
  | 'contract_tenor'
  | 'logistics'
  | 'start_date'
  | 'credit_quality'
  | 'certificate'
  | 'gex_score';

interface DimMeta {
  label: string;
  description: string;
  unit: string;
  /** Higher = better (true) or lower = better (false) */
  higher_is_better: boolean;
}

const DIM_META: Record<RadarDimension, DimMeta> = {
  price:            { label: 'Price',            description: 'Offered price vs market benchmark — lower price scores higher for buyer.', unit: '€/kg',  higher_is_better: false },
  volume:           { label: 'Volume',           description: 'Volume commitment vs your project capacity — higher coverage scores higher.', unit: 'MT',   higher_is_better: true  },
  carbon_intensity: { label: 'Carbon Intensity', description: 'GHG intensity of supplied product — lower emissions scores higher.', unit: 'kgCO₂/kg', higher_is_better: false },
  contract_tenor:   { label: 'Contract Tenor',   description: 'Length of off-take agreement — longer tenor reduces revenue risk.', unit: 'years',  higher_is_better: true  },
  logistics:        { label: 'Logistics',        description: 'Delivery mode suitability: Pipeline > Ship > Truck for bulk green fuels.', unit: 'score',  higher_is_better: true  },
  start_date:       { label: 'Start Date',       description: 'Readiness of counterparty to start delivery relative to your COD.', unit: 'score',  higher_is_better: true  },
  credit_quality:   { label: 'Credit Quality',   description: 'Counterparty credit rating mapped to a 0–100 score (AAA = 100).', unit: 'score',  higher_is_better: true  },
  certificate:      { label: 'Certificate Fit',  description: 'Acceptance of required certificates (RFNBO, 45V, RED III, IOSSEC, etc.).', unit: 'score',  higher_is_better: true  },
  gex_score:        { label: 'GEX Score',        description: 'GreenEarthX internal composite counterparty rating.', unit: '/100',   higher_is_better: true  },
};

const ALL_DIMS = Object.keys(DIM_META) as RadarDimension[];
const DEFAULT_DIMS: RadarDimension[] = ['price', 'volume', 'carbon_intensity', 'contract_tenor', 'credit_quality', 'certificate', 'gex_score'];

// ─── Parameter option catalogues ──────────────────────────────────────────────

const LOGISTICS_OPTIONS = ['Pipeline', 'Ship (LH2)', 'Ship (NH3)', 'Ship (MeOH)', 'Truck', 'Rail'];
const CERTIFICATE_OPTIONS = ['RFNBO', '45V', 'RED III', 'IOSSEC', 'ISO 14064', 'CORSiA', 'ReFuelEU', 'None'];
const CREDIT_OPTIONS = ['AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'Not Rated'];

// Map credit rating → 0–100 score
const CREDIT_SCORE: Record<string, number> = {
  AAA: 100, AA: 88, A: 78, BBB: 65, BB: 50, B: 35, 'Not Rated': 20,
};
// Map logistics mode → 0–100 score
const LOGISTICS_SCORE: Record<string, number> = {
  'Pipeline': 95, 'Ship (NH3)': 82, 'Ship (MeOH)': 80, 'Ship (LH2)': 70,
  'Rail': 65, 'Truck': 45,
};
// Map certificate match → 0–100
function certScore(accepted: string[], required: string[]): number {
  if (required.length === 0) return 100;
  const hits = required.filter(r => accepted.includes(r)).length;
  return Math.round((hits / required.length) * 100);
}

// ─── Match types ──────────────────────────────────────────────────────────────

interface MatchingParams {
  project_id: string;
  molecule: string;
  volume_min: number;
  volume_max: number;
  price_max: number;
  delivery_start: string;
  delivery_end: string;
  ghg_max: number;
  min_tenor_years: number;
  logistics_modes: string[];
  required_certificates: string[];
  min_credit: string;
}

interface Match {
  id: string;
  supplier: string;
  supplier_location: string;
  buyer: string;
  molecule: string;
  volume_mt: number;
  price_eur_kg: number;
  match_score: number;
  delivery_date: string;
  // Dimensional attributes
  ghg_intensity: number;
  tenor_years: number;
  logistics: string;
  credit_rating: string;
  certificates: string[];
  gex_score: number;
}

// ─── Mock buyer pool (counterparties only) ────────────────────────────────────

interface BuyerSpec {
  name: string; volume: number; price: number; score: number; date: string;
  ghg: number; tenor: number; logistics: string; credit: string;
  certs: string[]; gex: number;
}

const BUYERS_BY_MOLECULE: Record<string, BuyerSpec[]> = {
  H2: [
    { name: 'BASF SE',            volume: 18_000, price: 6.40, score: 94, date: '2026-10-01', ghg: 0.34, tenor: 15, logistics: 'Pipeline',   credit: 'A',   certs: ['RED III', 'RFNBO'],        gex: 91 },
    { name: 'Thyssenkrupp Steel', volume: 12_000, price: 5.90, score: 88, date: '2026-11-15', ghg: 0.38, tenor: 10, logistics: 'Pipeline',   credit: 'BBB', certs: ['RED III'],                 gex: 82 },
    { name: 'Yara International', volume:  8_000, price: 6.10, score: 81, date: '2027-01-01', ghg: 0.41, tenor:  7, logistics: 'Ship (NH3)', credit: 'BBB', certs: ['RED III', 'ISO 14064'],    gex: 76 },
  ],
  NH3: [
    { name: 'OCI Global',         volume: 30_000, price: 0.45, score: 92, date: '2027-02-01', ghg: 0.40, tenor: 20, logistics: 'Ship (NH3)', credit: 'BBB', certs: ['RFNBO', 'RED III'],        gex: 89 },
    { name: 'CF Industries',      volume: 20_000, price: 0.42, score: 85, date: '2027-04-01', ghg: 0.43, tenor: 12, logistics: 'Ship (NH3)', credit: 'BB',  certs: ['RED III'],                 gex: 78 },
    { name: 'Trammo',             volume: 15_000, price: 0.48, score: 79, date: '2027-06-01', ghg: 0.46, tenor:  8, logistics: 'Ship (NH3)', credit: 'BB',  certs: ['ISO 14064'],               gex: 71 },
  ],
  'e-Methanol': [
    { name: 'Maersk',              volume:  9_000, price: 1.10, score: 96, date: '2027-03-15', ghg: 0.50, tenor: 20, logistics: 'Ship (MeOH)', credit: 'A',   certs: ['RFNBO', 'RED III', 'FuelEU Maritime'], gex: 95 },
    { name: 'CMA CGM',             volume:  6_500, price: 1.05, score: 89, date: '2027-05-01', ghg: 0.52, tenor: 15, logistics: 'Ship (MeOH)', credit: 'BBB', certs: ['RFNBO', 'RED III'],       gex: 86 },
    { name: 'Liquid Wind Trading', volume:  4_000, price: 1.15, score: 82, date: '2027-07-01', ghg: 0.55, tenor: 10, logistics: 'Ship (MeOH)', credit: 'BB',  certs: ['RED III'],                gex: 74 },
  ],
  SAF: [
    { name: 'British Airways', volume:  7_500, price: 2.80, score: 91, date: '2029-04-01', ghg: 0.27, tenor: 15, logistics: 'Truck',     credit: 'BBB', certs: ['ReFuelEU', 'CORSiA', 'RED III'], gex: 88 },
    { name: 'easyJet',         volume:  5_000, price: 2.65, score: 84, date: '2029-06-01', ghg: 0.29, tenor: 10, logistics: 'Truck',     credit: 'BB',  certs: ['ReFuelEU', 'RED III'],           gex: 79 },
    { name: 'Shell Aviation',  volume: 10_000, price: 2.50, score: 77, date: '2029-08-01', ghg: 0.30, tenor:  7, logistics: 'Truck',     credit: 'A',   certs: ['CORSiA', 'RED III'],             gex: 85 },
  ],
  'e-NG': [
    { name: 'Engie',             volume: 20_000, price: 1.05, score: 97, date: '2026-03-01', ghg: 0.43, tenor: 20, logistics: 'Pipeline',   credit: 'A',   certs: ['RED III', 'ISO 14064'],    gex: 96 },
    { name: 'TotalEnergies Gas', volume: 14_000, price: 0.98, score: 90, date: '2026-05-01', ghg: 0.45, tenor: 15, logistics: 'Pipeline',   credit: 'A',   certs: ['RED III', 'RFNBO'],        gex: 91 },
    { name: 'Uniper SE',         volume:  9_000, price: 1.02, score: 83, date: '2026-07-01', ghg: 0.47, tenor: 10, logistics: 'Pipeline',   credit: 'BBB', certs: ['RED III'],                 gex: 82 },
  ],
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

const RADAR_COLORS = ['#0ea5a0', '#f59e0b', '#6366f1', '#10b981', '#f43f5e'];

function scoreColor(score: number) {
  if (score >= 90) return 'gex-badge gex-badge-green';
  if (score >= 75) return 'gex-badge gex-badge-amber';
  return 'gex-badge gex-badge-red';
}

/** Normalise a raw value to 0–100 where 100 = best for buyer */
function normalise(dim: RadarDimension, value: number, allValues: number[]): number {
  const meta = DIM_META[dim];
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  if (max === min) return 75;
  const pct = ((value - min) / (max - min)) * 100;
  return Math.round(meta.higher_is_better ? pct : 100 - pct);
}

/** Build radar data array from selected matches + active dimensions */
function buildRadarData(
  matches: Match[],
  selected: Match[],
  dims: RadarDimension[],
  requiredCerts: string[],
): Array<Record<string, number | string>> {
  return dims.map(dim => {
    const raw: Record<string, number> = {};
    for (const m of selected) {
      switch (dim) {
        case 'price':            raw[m.id] = m.price_eur_kg; break;
        case 'volume':           raw[m.id] = m.volume_mt; break;
        case 'carbon_intensity': raw[m.id] = m.ghg_intensity; break;
        case 'contract_tenor':   raw[m.id] = m.tenor_years; break;
        case 'logistics':        raw[m.id] = LOGISTICS_SCORE[m.logistics] ?? 50; break;
        case 'start_date':       raw[m.id] = 100 - Math.min(100, Math.max(0,
          (new Date(m.delivery_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24 * 30))); break;
        case 'credit_quality':   raw[m.id] = CREDIT_SCORE[m.credit_rating] ?? 30; break;
        case 'certificate':      raw[m.id] = certScore(m.certificates, requiredCerts); break;
        case 'gex_score':        raw[m.id] = m.gex_score; break;
      }
    }
    const allVals = Object.values(raw);
    const entry: Record<string, number | string> = { dim: DIM_META[dim].label };
    for (const m of selected) {
      entry[m.id] = allVals.length > 1 ? normalise(dim, raw[m.id], allVals) : raw[m.id];
    }
    return entry;
  });
}

const DEFAULT_PARAMS: MatchingParams = {
  project_id:           CUSTOMER_PROJECTS[0].id,
  molecule:             CUSTOMER_PROJECTS[0].molecule,
  volume_min:           1_000,
  volume_max:           50_000,
  price_max:            8.0,
  delivery_start:       '2026-06-01',
  delivery_end:         '2029-12-31',
  ghg_max:              1.0,
  min_tenor_years:      5,
  logistics_modes:      ['Pipeline', 'Ship (LH2)', 'Ship (NH3)', 'Ship (MeOH)', 'Truck', 'Rail'],
  required_certificates: ['RED III'],
  min_credit:           'BB',
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function DimSelector({
  activeDims,
  onChange,
}: {
  activeDims: RadarDimension[];
  onChange: (dims: RadarDimension[]) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
      >
        <Settings2 className="w-3.5 h-3.5" />
        Radar axes ({activeDims.length})
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && (
        <div className="absolute left-0 top-full z-40 mt-1 w-64 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-dropdown p-3 animate-fade-in">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-2">Select radar dimensions</p>
          <div className="space-y-1">
            {ALL_DIMS.map(dim => {
              const active = activeDims.includes(dim);
              return (
                <label key={dim} className="flex items-start gap-2.5 cursor-pointer rounded-lg px-2 py-1.5 hover:bg-[var(--surface-hover)] transition-colors">
                  <input
                    type="checkbox"
                    checked={active}
                    onChange={() => {
                      if (active && activeDims.length <= 3) return; // min 3
                      onChange(active ? activeDims.filter(d => d !== dim) : [...activeDims, dim]);
                    }}
                    className="mt-0.5 accent-[var(--brand)] shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[var(--text-primary)]">{DIM_META[dim].label}</p>
                    <p className="text-[10px] text-[var(--text-muted)] leading-snug">{DIM_META[dim].description}</p>
                  </div>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Custom tooltip for recharts radar ───────────────────────────────────────

function RadarTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-dropdown px-3 py-2.5 text-xs">
      <p className="font-bold text-[var(--text-primary)] mb-1.5">{label}</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-[var(--text-secondary)]">{p.name}:</span>
          <span className="font-mono font-bold text-[var(--text-primary)]">{p.value}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function MatchingPage() {
  const [params, setParams]           = useState<MatchingParams>(DEFAULT_PARAMS);
  const [matches, setMatches]         = useState<Match[]>([]);
  const [isMatching, setIsMatching]   = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [activeDims, setActiveDims]   = useState<RadarDimension[]>(DEFAULT_DIMS);
  const [showParamsPanel, setShowParamsPanel] = useState(true);

  const selectedProject = CUSTOMER_PROJECTS.find(p => p.id === params.project_id);
  const selectedMatches = matches.filter(m => selectedIds.includes(m.id));

  const radarData = useMemo(() =>
    buildRadarData(matches, selectedMatches, activeDims, params.required_certificates),
    [selectedMatches, activeDims, params.required_certificates]
  );

  const runMatching = () => {
    setIsMatching(true);
    setShowResults(false);
    setSelectedIds([]);
    setTimeout(() => {
      const pool = BUYERS_BY_MOLECULE[params.molecule] ?? BUYERS_BY_MOLECULE['H2'];
      const results: Match[] = pool
        .filter(b => b.volume <= params.volume_max && b.price <= params.price_max)
        .map((b, i) => ({
          id:                `match_${String(i + 1).padStart(3, '0')}`,
          supplier:          selectedProject?.name ?? 'Our Project',
          supplier_location: selectedProject?.location ?? '',
          buyer:             b.name,
          molecule:          params.molecule,
          volume_mt:         b.volume,
          price_eur_kg:      b.price,
          match_score:       b.score,
          delivery_date:     b.date,
          ghg_intensity:     b.ghg,
          tenor_years:       b.tenor,
          logistics:         b.logistics,
          credit_rating:     b.credit,
          certificates:      b.certs,
          gex_score:         b.gex,
        }));
      setMatches(results);
      // Auto-select all initially so radar shows immediately
      setSelectedIds(results.map(r => r.id));
      setIsMatching(false);
      setShowResults(true);
    }, 2400);
  };

  const reset = () => {
    setParams(DEFAULT_PARAMS);
    setMatches([]);
    setSelectedIds([]);
    setShowResults(false);
  };

  const handleProjectChange = (projectId: string) => {
    const p = CUSTOMER_PROJECTS.find(x => x.id === projectId);
    setParams(prev => ({ ...prev, project_id: projectId, molecule: p?.molecule ?? prev.molecule }));
    setShowResults(false);
    setMatches([]);
    setSelectedIds([]);
  };

  const toggleSelect = (id: string) =>
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">Intelligent Matching</h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">Find and compare counterparties across multiple dimensions</p>
        </div>
        <div className="flex gap-2">
          <button onClick={reset} className="flex items-center gap-2 rounded-lg border border-[var(--border)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors">
            <RotateCcw className="w-3.5 h-3.5" /> Reset
          </button>
          <button onClick={runMatching} disabled={isMatching}
            className="flex items-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 transition-opacity disabled:opacity-50">
            <Play className="w-3.5 h-3.5" />
            {isMatching ? 'Matching…' : 'Run Matching'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">

        {/* ── Parameters panel ── */}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
          <button
            onClick={() => setShowParamsPanel(v => !v)}
            className="flex w-full items-center justify-between gap-2 border-b border-[var(--border)] px-5 py-3.5 text-left"
          >
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-[var(--brand)]" />
              <span className="text-sm font-bold text-[var(--text-primary)]">Matching Parameters</span>
            </div>
            {showParamsPanel ? <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />}
          </button>

          {showParamsPanel && (
            <div className="p-5 space-y-4">

              {/* Source project */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Source Project</label>
                <select value={params.project_id} onChange={e => handleProjectChange(e.target.value)}
                  className="gex-select w-full text-sm" aria-label="Source project">
                  {CUSTOMER_PROJECTS.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                {selectedProject && (
                  <p className="mt-1 text-[10px] text-[var(--text-muted)]">
                    {selectedProject.location} · {selectedProject.capacity_mtpd} MTPD
                  </p>
                )}
              </div>

              {/* Molecule (readonly) */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Molecule</label>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)]">
                  {params.molecule}
                </div>
              </div>

              {/* Volume */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Volume Range (MT)</label>
                <div className="grid grid-cols-2 gap-2">
                  <input type="number" value={params.volume_min} onChange={e => setParams({...params, volume_min: +e.target.value})}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none" />
                  <input type="number" value={params.volume_max} onChange={e => setParams({...params, volume_max: +e.target.value})}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none" />
                </div>
              </div>

              {/* Max price */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Max Price (€/kg)</label>
                <input type="number" step="0.1" value={params.price_max} onChange={e => setParams({...params, price_max: +e.target.value})}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none" />
              </div>

              {/* Max GHG */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Max Carbon Intensity (kgCO₂/kg)</label>
                <input type="number" step="0.05" value={params.ghg_max} onChange={e => setParams({...params, ghg_max: +e.target.value})}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none" />
              </div>

              {/* Min tenor */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Min Contract Tenor (years)</label>
                <input type="number" min="1" max="30" value={params.min_tenor_years} onChange={e => setParams({...params, min_tenor_years: +e.target.value})}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none" />
              </div>

              {/* Delivery period */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Delivery Period</label>
                <div className="grid grid-cols-2 gap-2">
                  <input type="date" value={params.delivery_start} onChange={e => setParams({...params, delivery_start: e.target.value})}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none" />
                  <input type="date" value={params.delivery_end} onChange={e => setParams({...params, delivery_end: e.target.value})}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none" />
                </div>
              </div>

              {/* Logistics modes */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Accepted Logistics</label>
                <div className="flex flex-wrap gap-1.5">
                  {LOGISTICS_OPTIONS.map(mode => {
                    const active = params.logistics_modes.includes(mode);
                    return (
                      <button key={mode}
                        onClick={() => setParams({...params, logistics_modes: active
                          ? params.logistics_modes.filter(m => m !== mode)
                          : [...params.logistics_modes, mode]})}
                        className={`rounded-lg border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.1em] transition-colors ${active
                          ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]'
                          : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-hover)]'}`}
                      >{mode}</button>
                    );
                  })}
                </div>
              </div>

              {/* Required certificates */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Required Certificates</label>
                <div className="flex flex-wrap gap-1.5">
                  {CERTIFICATE_OPTIONS.map(cert => {
                    const active = params.required_certificates.includes(cert);
                    return (
                      <button key={cert}
                        onClick={() => setParams({...params, required_certificates: active
                          ? params.required_certificates.filter(c => c !== cert)
                          : [...params.required_certificates, cert]})}
                        className={`rounded-lg border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.1em] transition-colors ${active
                          ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]'
                          : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-hover)]'}`}
                      >{cert}</button>
                    );
                  })}
                </div>
              </div>

              {/* Min credit */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Min Counterparty Credit</label>
                <select value={params.min_credit} onChange={e => setParams({...params, min_credit: e.target.value})}
                  className="gex-select w-full text-sm" aria-label="Minimum credit rating">
                  {CREDIT_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
          )}
        </div>

        {/* ── Results + Radar ── */}
        <div className="space-y-4">
          {isMatching ? (
            <div className="flex flex-col items-center justify-center gap-5 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-16 shadow-card">
              <div className="relative h-24 w-24">
                <div className="absolute inset-0 rounded-full border-2 border-[var(--border)]" />
                <div className="absolute inset-3 rounded-full border border-[var(--border)]" />
                <div className="absolute inset-6 rounded-full border border-[var(--brand)] opacity-40" />
                <div className="absolute inset-0 rounded-full border-t-2 border-[var(--brand)] animate-spin" />
                <Target className="absolute inset-0 m-auto w-8 h-8 text-[var(--brand)]" />
              </div>
              <div className="text-center">
                <p className="font-display font-bold text-[var(--text-primary)]">Scanning Market</p>
                <p className="text-sm text-[var(--text-muted)]">Analysing demand for {params.molecule}…</p>
              </div>
            </div>
          ) : showResults ? (
            <>
              {/* Match list */}
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
                <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3.5">
                  <h2 className="text-sm font-bold text-[var(--text-primary)]">
                    {matches.length} match{matches.length !== 1 ? 'es' : ''} · {selectedIds.length} selected for radar
                  </h2>
                  <span className="text-[10px] text-[var(--text-muted)]">Click rows to compare on radar</span>
                </div>
                <div className="divide-y divide-[var(--border)]">
                  {matches.map((m, idx) => {
                    const isSelected = selectedIds.includes(m.id);
                    const color = RADAR_COLORS[idx % RADAR_COLORS.length];
                    return (
                      <div
                        key={m.id}
                        onClick={() => toggleSelect(m.id)}
                        className={`cursor-pointer px-5 py-4 transition-colors ${isSelected ? 'bg-[var(--brand-light)]' : 'hover:bg-[var(--surface-hover)]'}`}
                      >
                        <div className="flex items-start justify-between gap-3 mb-2">
                          <div className="flex items-center gap-2.5">
                            {/* Color swatch matching radar line */}
                            <span className="inline-block h-3 w-3 shrink-0 rounded-full" style={{ background: color }} />
                            <div>
                              <p className="font-semibold text-[var(--text-primary)] text-sm">{m.supplier} → {m.buyer}</p>
                              <p className="text-xs text-[var(--text-muted)]">{m.molecule} · {m.logistics}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <span className={scoreColor(m.match_score)}>{m.match_score}% match</span>
                            <span className="gex-badge gex-badge-default">GEX {m.gex_score}</span>
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-[var(--text-secondary)] sm:grid-cols-4">
                          <div className="flex items-center gap-1"><DollarSign className="w-3 h-3 text-[var(--text-muted)]" />€{m.price_eur_kg}/kg</div>
                          <div className="flex items-center gap-1"><Target className="w-3 h-3 text-[var(--text-muted)]" />{m.volume_mt.toLocaleString()} MT</div>
                          <div className="flex items-center gap-1"><Calendar className="w-3 h-3 text-[var(--text-muted)]" />{m.tenor_years}yr tenor</div>
                          <div className="flex items-center gap-1"><MapPin className="w-3 h-3 text-[var(--text-muted)]" />{m.supplier_location}</div>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-1">
                          {m.certificates.map(c => (
                            <span key={c} className="gex-badge gex-badge-blue">{c}</span>
                          ))}
                          <span className={`gex-badge ${m.ghg_intensity < 0.5 ? 'gex-badge-green' : 'gex-badge-amber'}`}>
                            {m.ghg_intensity} kgCO₂/kg
                          </span>
                          <span className="gex-badge gex-badge-default">{m.credit_rating}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* ── Radar chart ── */}
              {selectedIds.length >= 2 ? (
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-[var(--text-primary)]">Counterparty Comparison Radar</h3>
                      <div className="group relative">
                        <Info className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                        <div className="invisible group-hover:visible absolute left-6 top-0 z-50 w-64 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-dropdown p-3 text-xs text-[var(--text-secondary)] leading-relaxed">
                          All values are normalised 0–100 relative to the selected bids. 100 = best for your project on each axis. The optimal counterparty fills the polygon maximally on all axes.
                        </div>
                      </div>
                    </div>
                    <DimSelector activeDims={activeDims} onChange={setActiveDims} />
                  </div>
                  <div className="p-5">
                    <ResponsiveContainer width="100%" height={360}>
                      <RadarChart data={radarData} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
                        <PolarGrid stroke="var(--border)" />
                        <PolarAngleAxis
                          dataKey="dim"
                          tick={{ fill: 'var(--text-secondary)', fontSize: 11, fontWeight: 600 }}
                        />
                        <PolarRadiusAxis
                          angle={30}
                          domain={[0, 100]}
                          tick={{ fill: 'var(--text-muted)', fontSize: 9 }}
                          tickCount={5}
                          axisLine={false}
                        />
                        {selectedMatches.map((m, idx) => (
                          <Radar
                            key={m.id}
                            name={m.buyer}
                            dataKey={m.id}
                            stroke={RADAR_COLORS[matches.indexOf(m) % RADAR_COLORS.length]}
                            fill={RADAR_COLORS[matches.indexOf(m) % RADAR_COLORS.length]}
                            fillOpacity={0.15}
                            strokeWidth={2}
                            dot={{ r: 3 }}
                          />
                        ))}
                        <Legend
                          wrapperStyle={{ fontSize: '12px', color: 'var(--text-secondary)', paddingTop: '8px' }}
                        />
                        <Tooltip content={<RadarTooltip />} />
                      </RadarChart>
                    </ResponsiveContainer>

                    {/* Dimension key */}
                    <div className="mt-4 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                      {activeDims.map(dim => (
                        <div key={dim} className="flex items-start gap-2 rounded-lg bg-[var(--surface-muted)] px-3 py-2">
                          <div className="min-w-0">
                            <span className="text-xs font-bold text-[var(--text-primary)]">{DIM_META[dim].label}</span>
                            <span className="ml-1 text-[10px] text-[var(--text-muted)]">({DIM_META[dim].unit})</span>
                            <p className="text-[10px] text-[var(--text-muted)] leading-snug">{DIM_META[dim].description}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : showResults && (
                <div className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] px-5 py-4 text-sm text-[var(--text-muted)]">
                  <Info className="w-4 h-4 shrink-0" />
                  Select at least 2 counterparties above to display the radar comparison.
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-16 shadow-card text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--brand-light)]">
                <Target className="w-7 h-7 text-[var(--brand)]" />
              </div>
              <div>
                <p className="font-display font-bold text-[var(--text-primary)]">Ready to Find Matches</p>
                <p className="mt-1 text-sm text-[var(--text-muted)]">Configure parameters and run matching to compare counterparties</p>
              </div>
              <button onClick={runMatching} className="rounded-lg bg-[var(--brand)] px-6 py-2.5 text-sm font-semibold text-white hover:opacity-90 transition-opacity">
                Start Matching
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
