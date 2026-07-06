// Screen: Matching screen (/matching)
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowRight, Calendar, DollarSign, Filter, Info, MapPin, Play,
  RotateCcw, Settings2, Target, ChevronDown, ChevronUp,
} from 'lucide-react';
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Legend, Tooltip,
} from 'recharts';
import { DEFAULT_PROJECT_ID } from '@/data/customerProjects';
import { useVisibleProjects } from '@/hooks/useVisibleProjects';
import { useUserRole } from '@/contexts/UserRoleContext';

type MatchMode = 'buy' | 'sell';

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
  higher_is_better: boolean;
}

interface MatchingParams {
  project_id: string;
  molecule: string;
  volume_min: number;
  volume_max: number;
  price_limit: number;
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
  ghg_intensity: number;
  tenor_years: number;
  logistics: string;
  credit_rating: string;
  certificates: string[];
  gex_score: number;
  counterparty_location: string;
  card_kind: 'offer' | 'rfq';
}

interface CounterpartySpec {
  name: string;
  location: string;
  volume: number;
  price: number;
  score: number;
  date: string;
  ghg: number;
  tenor: number;
  logistics: string;
  credit: string;
  certs: string[];
  gex: number;
}

const ALL_DIMS: RadarDimension[] = [
  'price',
  'volume',
  'carbon_intensity',
  'contract_tenor',
  'logistics',
  'start_date',
  'credit_quality',
  'certificate',
  'gex_score',
];

const DEFAULT_DIMS: RadarDimension[] = [
  'price',
  'volume',
  'carbon_intensity',
  'contract_tenor',
  'credit_quality',
  'certificate',
  'gex_score',
];

const LOGISTICS_OPTIONS = ['Pipeline', 'Ship (LH2)', 'Ship (NH3)', 'Ship (MeOH)', 'Truck', 'Rail'];
const CERTIFICATE_OPTIONS = ['RFNBO', '45V', 'RED III', 'IOSSEC', 'ISO 14064', 'CORSiA', 'ReFuelEU', 'FuelEU Maritime', 'None'];
const CREDIT_OPTIONS = ['AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'Not Rated'];

const CREDIT_SCORE: Record<string, number> = {
  AAA: 100,
  AA: 88,
  A: 78,
  BBB: 65,
  BB: 50,
  B: 35,
  'Not Rated': 20,
};

const LOGISTICS_SCORE: Record<string, number> = {
  Pipeline: 95,
  'Ship (NH3)': 82,
  'Ship (MeOH)': 80,
  'Ship (LH2)': 70,
  Rail: 65,
  Truck: 45,
};

const SUPPLIER_OFFERS_BY_MOLECULE: Record<string, CounterpartySpec[]> = {
  H2: [
    { name: 'North Sea Hydrogen Hub', location: 'Wilhelmshaven, Germany', volume: 16_000, price: 6.1, score: 93, date: '2026-09-01', ghg: 0.31, tenor: 12, logistics: 'Pipeline', certs: ['RFNBO', 'RED III'], credit: 'A', gex: 92 },
    { name: 'Air Liquide Green Molecules', location: 'Rotterdam, Netherlands', volume: 11_000, price: 6.5, score: 86, date: '2026-10-15', ghg: 0.36, tenor: 10, logistics: 'Pipeline', certs: ['RED III', 'ISO 14064'], credit: 'A', gex: 84 },
    { name: 'IberH2 Trading', location: 'Bilbao, Spain', volume: 8_500, price: 6.8, score: 78, date: '2026-11-30', ghg: 0.42, tenor: 7, logistics: 'Truck', certs: ['RED III'], credit: 'BBB', gex: 73 },
  ],
  NH3: [
    { name: 'OCI Global Supply', location: 'Rotterdam, Netherlands', volume: 28_000, price: 0.46, score: 91, date: '2027-02-15', ghg: 0.39, tenor: 15, logistics: 'Ship (NH3)', certs: ['RFNBO', 'RED III'], credit: 'BBB', gex: 88 },
    { name: 'Yara Clean Ammonia', location: 'Porsgrunn, Norway', volume: 18_000, price: 0.49, score: 84, date: '2027-04-01', ghg: 0.42, tenor: 10, logistics: 'Ship (NH3)', certs: ['RED III'], credit: 'A', gex: 81 },
    { name: 'Trammo Spot Desk', location: 'Antwerp, Belgium', volume: 12_000, price: 0.53, score: 75, date: '2027-05-20', ghg: 0.47, tenor: 6, logistics: 'Ship (NH3)', certs: ['ISO 14064'], credit: 'BB', gex: 69 },
  ],
  'e-Methanol': [
    { name: 'Liquid Wind Supply', location: 'Umea, Sweden', volume: 7_500, price: 1.08, score: 94, date: '2027-01-01', ghg: 0.44, tenor: 15, logistics: 'Ship (MeOH)', certs: ['RFNBO', 'RED III', 'FuelEU Maritime'], credit: 'A', gex: 93 },
    { name: 'C2X e-Methanol Desk', location: 'Copenhagen, Denmark', volume: 6_000, price: 1.15, score: 86, date: '2027-03-01', ghg: 0.49, tenor: 12, logistics: 'Ship (MeOH)', certs: ['RED III'], credit: 'BBB', gex: 84 },
    { name: 'Basque Green Molecules', location: 'Bilbao, Spain', volume: 4_500, price: 1.19, score: 79, date: '2027-04-15', ghg: 0.52, tenor: 8, logistics: 'Truck', certs: ['RED III', 'ISO 14064'], credit: 'BBB', gex: 76 },
  ],
  SAF: [
    { name: 'Neste Market Desk', location: 'Rotterdam, Netherlands', volume: 8_000, price: 2.65, score: 90, date: '2028-12-01', ghg: 0.24, tenor: 10, logistics: 'Truck', certs: ['ReFuelEU', 'CORSiA', 'RED III'], credit: 'A', gex: 90 },
    { name: 'World Energy Europe', location: 'Amsterdam, Netherlands', volume: 5_500, price: 2.78, score: 83, date: '2029-02-01', ghg: 0.27, tenor: 8, logistics: 'Truck', certs: ['CORSiA', 'RED III'], credit: 'BBB', gex: 81 },
    { name: 'SkyNRG Supply', location: 'Stockholm, Sweden', volume: 4_500, price: 2.9, score: 76, date: '2029-04-15', ghg: 0.3, tenor: 6, logistics: 'Truck', certs: ['ReFuelEU', 'RED III'], credit: 'BB', gex: 74 },
  ],
  'e-NG': [
    { name: 'Engie Gas Trading', location: 'Le Havre, France', volume: 18_000, price: 0.98, score: 95, date: '2026-06-01', ghg: 0.41, tenor: 18, logistics: 'Pipeline', certs: ['RED III', 'RFNBO'], credit: 'A', gex: 95 },
    { name: 'Uniper Green Gas', location: 'Hamburg, Germany', volume: 12_500, price: 1.04, score: 88, date: '2026-08-01', ghg: 0.45, tenor: 12, logistics: 'Pipeline', certs: ['RED III'], credit: 'BBB', gex: 86 },
    { name: 'TotalEnergies Gas Desk', location: 'Paris, France', volume: 9_000, price: 1.08, score: 80, date: '2026-09-15', ghg: 0.48, tenor: 9, logistics: 'Pipeline', certs: ['ISO 14064'], credit: 'A', gex: 82 },
  ],
};

const BUYER_RFQS_BY_MOLECULE: Record<string, CounterpartySpec[]> = {
  H2: [
    { name: 'BASF SE', location: 'Ludwigshafen, Germany', volume: 18_000, price: 6.4, score: 94, date: '2026-10-01', ghg: 0.34, tenor: 15, logistics: 'Pipeline', credit: 'A', certs: ['RED III', 'RFNBO'], gex: 91 },
    { name: 'Thyssenkrupp Steel', location: 'Duisburg, Germany', volume: 12_000, price: 5.9, score: 88, date: '2026-11-15', ghg: 0.38, tenor: 10, logistics: 'Pipeline', credit: 'BBB', certs: ['RED III'], gex: 82 },
    { name: 'Yara International', location: 'Oslo, Norway', volume: 8_000, price: 6.1, score: 81, date: '2027-01-01', ghg: 0.41, tenor: 7, logistics: 'Ship (NH3)', credit: 'BBB', certs: ['RED III', 'ISO 14064'], gex: 76 },
  ],
  NH3: [
    { name: 'OCI Global', location: 'Rotterdam, Netherlands', volume: 30_000, price: 0.45, score: 92, date: '2027-02-01', ghg: 0.4, tenor: 20, logistics: 'Ship (NH3)', credit: 'BBB', certs: ['RFNBO', 'RED III'], gex: 89 },
    { name: 'CF Industries', location: 'London, United Kingdom', volume: 20_000, price: 0.42, score: 85, date: '2027-04-01', ghg: 0.43, tenor: 12, logistics: 'Ship (NH3)', credit: 'BB', certs: ['RED III'], gex: 78 },
    { name: 'Trammo', location: 'Amsterdam, Netherlands', volume: 15_000, price: 0.48, score: 79, date: '2027-06-01', ghg: 0.46, tenor: 8, logistics: 'Ship (NH3)', credit: 'BB', certs: ['ISO 14064'], gex: 71 },
  ],
  'e-Methanol': [
    { name: 'Maersk', location: 'Copenhagen, Denmark', volume: 9_000, price: 1.1, score: 96, date: '2027-03-15', ghg: 0.5, tenor: 20, logistics: 'Ship (MeOH)', credit: 'A', certs: ['RFNBO', 'RED III', 'FuelEU Maritime'], gex: 95 },
    { name: 'CMA CGM', location: 'Marseille, France', volume: 6_500, price: 1.05, score: 89, date: '2027-05-01', ghg: 0.52, tenor: 15, logistics: 'Ship (MeOH)', credit: 'BBB', certs: ['RFNBO', 'RED III'], gex: 86 },
    { name: 'Liquid Wind Trading', location: 'Gothenburg, Sweden', volume: 4_000, price: 1.15, score: 82, date: '2027-07-01', ghg: 0.55, tenor: 10, logistics: 'Ship (MeOH)', credit: 'BB', certs: ['RED III'], gex: 74 },
  ],
  SAF: [
    { name: 'British Airways', location: 'London, United Kingdom', volume: 7_500, price: 2.8, score: 91, date: '2029-04-01', ghg: 0.27, tenor: 15, logistics: 'Truck', credit: 'BBB', certs: ['ReFuelEU', 'CORSiA', 'RED III'], gex: 88 },
    { name: 'easyJet', location: 'Luton, United Kingdom', volume: 5_000, price: 2.65, score: 84, date: '2029-06-01', ghg: 0.29, tenor: 10, logistics: 'Truck', credit: 'BB', certs: ['ReFuelEU', 'RED III'], gex: 79 },
    { name: 'Shell Aviation', location: 'The Hague, Netherlands', volume: 10_000, price: 2.5, score: 77, date: '2029-08-01', ghg: 0.3, tenor: 7, logistics: 'Truck', credit: 'A', certs: ['CORSiA', 'RED III'], gex: 85 },
  ],
  'e-NG': [
    { name: 'Engie', location: 'Paris, France', volume: 20_000, price: 1.05, score: 97, date: '2026-03-01', ghg: 0.43, tenor: 20, logistics: 'Pipeline', credit: 'A', certs: ['RED III', 'ISO 14064'], gex: 96 },
    { name: 'TotalEnergies Gas', location: 'Paris, France', volume: 14_000, price: 0.98, score: 90, date: '2026-05-01', ghg: 0.45, tenor: 15, logistics: 'Pipeline', credit: 'A', certs: ['RED III', 'RFNBO'], gex: 91 },
    { name: 'Uniper SE', location: 'Dusseldorf, Germany', volume: 9_000, price: 1.02, score: 83, date: '2026-07-01', ghg: 0.47, tenor: 10, logistics: 'Pipeline', credit: 'BBB', certs: ['RED III'], gex: 82 },
  ],
};

const RADAR_COLORS = ['#0ea5a0', '#f59e0b', '#6366f1', '#10b981', '#f43f5e'];

function getDimMeta(mode: MatchMode): Record<RadarDimension, DimMeta> {
  return {
    price: {
      label: 'Price',
      description: mode === 'buy'
        ? 'Quoted supplier price. Lower price scores higher for the buyer.'
        : 'Buyer bid price. Higher price scores higher for the seller.',
      unit: '€/kg',
      higher_is_better: mode === 'sell',
    },
    volume: {
      label: 'Volume',
      description: 'Volume commitment versus your project requirement or available output.',
      unit: 'MT',
      higher_is_better: true,
    },
    carbon_intensity: {
      label: 'Carbon Intensity',
      description: 'Lower emissions improve bankability and compliance fit.',
      unit: 'kgCO₂/kg',
      higher_is_better: false,
    },
    contract_tenor: {
      label: 'Contract Tenor',
      description: 'Longer commitment improves planning certainty.',
      unit: 'years',
      higher_is_better: true,
    },
    logistics: {
      label: 'Logistics',
      description: 'Delivery mode suitability for the selected molecule and route.',
      unit: 'score',
      higher_is_better: true,
    },
    start_date: {
      label: 'Start Date',
      description: 'Readiness to start close to your requested commercial window.',
      unit: 'score',
      higher_is_better: true,
    },
    credit_quality: {
      label: 'Credit Quality',
      description: 'Counterparty credit mapped to a 0–100 score.',
      unit: 'score',
      higher_is_better: true,
    },
    certificate: {
      label: 'Certificate Fit',
      description: 'Coverage of your required certificate stack.',
      unit: 'score',
      higher_is_better: true,
    },
    gex_score: {
      label: 'GEX Score',
      description: 'GreenEarthX internal composite counterparty rating.',
      unit: '/100',
      higher_is_better: true,
    },
  };
}

function defaultPriceLimit(mode: MatchMode) {
  return mode === 'buy' ? 8.0 : 0;
}

function buildDefaultParams(projectId: string, molecule: string, mode: MatchMode): MatchingParams {
  return {
    project_id: projectId,
    molecule,
    volume_min: 1_000,
    volume_max: 50_000,
    price_limit: defaultPriceLimit(mode),
    delivery_start: '2026-06-01',
    delivery_end: '2029-12-31',
    ghg_max: 1.0,
    min_tenor_years: 5,
    logistics_modes: [...LOGISTICS_OPTIONS],
    required_certificates: ['RED III'],
    min_credit: 'BB',
  };
}

function certScore(accepted: string[], required: string[]): number {
  if (required.length === 0) return 100;
  const hits = required.filter(requiredCert => accepted.includes(requiredCert)).length;
  return Math.round((hits / required.length) * 100);
}

function resolveMode(requestedMode: string | null, allowedModes: MatchMode[]): MatchMode {
  if (requestedMode === 'buy' || requestedMode === 'sell') {
    if (allowedModes.includes(requestedMode)) return requestedMode;
  }
  return allowedModes[0] ?? 'buy';
}

function scoreColor(score: number) {
  if (score >= 90) return 'gex-badge gex-badge-green';
  if (score >= 75) return 'gex-badge gex-badge-amber';
  return 'gex-badge gex-badge-red';
}

function normalise(
  dim: RadarDimension,
  value: number,
  allValues: number[],
  metaByDim: Record<RadarDimension, DimMeta>,
): number {
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  if (max === min) return 75;
  const pct = ((value - min) / (max - min)) * 100;
  return Math.round(metaByDim[dim].higher_is_better ? pct : 100 - pct);
}

function buildRadarData(
  selected: Match[],
  dims: RadarDimension[],
  requiredCerts: string[],
  mode: MatchMode,
): Array<Record<string, number | string>> {
  const metaByDim = getDimMeta(mode);

  return dims.map(dim => {
    const raw: Record<string, number> = {};

    for (const match of selected) {
      switch (dim) {
        case 'price':
          raw[match.id] = match.price_eur_kg;
          break;
        case 'volume':
          raw[match.id] = match.volume_mt;
          break;
        case 'carbon_intensity':
          raw[match.id] = match.ghg_intensity;
          break;
        case 'contract_tenor':
          raw[match.id] = match.tenor_years;
          break;
        case 'logistics':
          raw[match.id] = LOGISTICS_SCORE[match.logistics] ?? 50;
          break;
        case 'start_date':
          raw[match.id] = 100 - Math.min(
            100,
            Math.max(0, (new Date(match.delivery_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24 * 30)),
          );
          break;
        case 'credit_quality':
          raw[match.id] = CREDIT_SCORE[match.credit_rating] ?? 30;
          break;
        case 'certificate':
          raw[match.id] = certScore(match.certificates, requiredCerts);
          break;
        case 'gex_score':
          raw[match.id] = match.gex_score;
          break;
      }
    }

    const values = Object.values(raw);
    const entry: Record<string, number | string> = { dim: metaByDim[dim].label };
    for (const match of selected) {
      entry[match.id] = values.length > 1 ? normalise(dim, raw[match.id], values, metaByDim) : raw[match.id];
    }
    return entry;
  });
}

function meetsCreditThreshold(credit: string, minCredit: string) {
  return (CREDIT_SCORE[credit] ?? 0) >= (CREDIT_SCORE[minCredit] ?? 0);
}

function matchesFilters(candidate: CounterpartySpec, params: MatchingParams, mode: MatchMode) {
  const deliveryDate = new Date(candidate.date).getTime();
  const deliveryStart = new Date(params.delivery_start).getTime();
  const deliveryEnd = new Date(params.delivery_end).getTime();
  const withinDates = deliveryDate >= deliveryStart && deliveryDate <= deliveryEnd;
  const withinVolume = candidate.volume >= params.volume_min && candidate.volume <= params.volume_max;
  const withinPrice = mode === 'buy'
    ? candidate.price <= params.price_limit
    : candidate.price >= params.price_limit;
  const withinGhg = candidate.ghg <= params.ghg_max;
  const withinTenor = candidate.tenor >= params.min_tenor_years;
  const withinLogistics = params.logistics_modes.includes(candidate.logistics);
  const withinCredit = meetsCreditThreshold(candidate.credit, params.min_credit);
  const withinCertificates = certScore(candidate.certs, params.required_certificates) > 0;

  return withinDates && withinVolume && withinPrice && withinGhg && withinTenor && withinLogistics && withinCredit && withinCertificates;
}

function DimSelector({
  activeDims,
  metaByDim,
  onChange,
}: {
  activeDims: RadarDimension[];
  metaByDim: Record<RadarDimension, DimMeta>;
  onChange: (dims: RadarDimension[]) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(value => !value)}
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
                      if (active && activeDims.length <= 3) return;
                      onChange(active ? activeDims.filter(item => item !== dim) : [...activeDims, dim]);
                    }}
                    className="mt-0.5 accent-[var(--brand)] shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[var(--text-primary)]">{metaByDim[dim].label}</p>
                    <p className="text-[10px] text-[var(--text-muted)] leading-snug">{metaByDim[dim].description}</p>
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

function RadarTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-dropdown px-3 py-2.5 text-xs">
      <p className="font-bold text-[var(--text-primary)] mb-1.5">{label}</p>
      {payload.map((item: any) => (
        <div key={item.dataKey} className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: item.color }} />
          <span className="text-[var(--text-secondary)]">{item.name}:</span>
          <span className="font-mono font-bold text-[var(--text-primary)]">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

export function MatchingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { role } = useUserRole();
  const { projects: visibleProjects } = useVisibleProjects();

  const requestedMode = searchParams.get('mode');
  const requestedProjectId = searchParams.get('project');

  const capabilities = role.capabilities ?? [];
  const canBuy = role.company_type === 'OFFTAKER' || capabilities.includes('OFFTAKE');
  const canSell = role.company_type === 'PRODUCER' || capabilities.includes('PRODUCE') || capabilities.includes('SELL');

  const allowedModes = useMemo(() => {
    const modes: MatchMode[] = [];
    if (canBuy) modes.push('buy');
    if (canSell) modes.push('sell');
    if (modes.length === 0) modes.push('buy');
    return modes;
  }, [canBuy, canSell]);

  const [mode, setMode] = useState<MatchMode>(resolveMode(requestedMode, allowedModes));
  const [params, setParams] = useState<MatchingParams>(
    buildDefaultParams(DEFAULT_PROJECT_ID, 'H2', resolveMode(requestedMode, allowedModes)),
  );
  const [matches, setMatches] = useState<Match[]>([]);
  const [isMatching, setIsMatching] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [activeDims, setActiveDims] = useState<RadarDimension[]>(DEFAULT_DIMS);
  const [showParamsPanel, setShowParamsPanel] = useState(true);

  useEffect(() => {
    const nextMode = resolveMode(requestedMode, allowedModes);
    setMode(current => {
      if (current === nextMode) return current;
      setParams(previous => ({
        ...previous,
        price_limit: defaultPriceLimit(nextMode),
      }));
      return nextMode;
    });
  }, [allowedModes, requestedMode]);

  useEffect(() => {
    if (visibleProjects.length === 0) return;

    const requestedProject = visibleProjects.find(project => project.id === requestedProjectId);
    const currentProject = visibleProjects.find(project => project.id === params.project_id);
    const fallbackProject = requestedProject ?? currentProject ?? visibleProjects[0];

    if (!fallbackProject) return;
    if (params.project_id === fallbackProject.id && params.molecule === fallbackProject.molecule) return;

    setParams(current => ({
      ...current,
      project_id: fallbackProject.id,
      molecule: fallbackProject.molecule,
    }));
  }, [params.molecule, params.project_id, requestedProjectId, visibleProjects]);

  const selectedProject = visibleProjects.find(project => project.id === params.project_id) ?? visibleProjects[0];
  const selectedMatches = matches.filter(match => selectedIds.includes(match.id));
  const metaByDim = useMemo(() => getDimMeta(mode), [mode]);

  const radarData = useMemo(
    () => buildRadarData(selectedMatches, activeDims, params.required_certificates, mode),
    [activeDims, mode, params.required_certificates, selectedMatches],
  );

  const runMatching = () => {
    if (!selectedProject) return;

    setIsMatching(true);
    setShowResults(false);
    setSelectedIds([]);

    window.setTimeout(() => {
      const pool = mode === 'buy'
        ? SUPPLIER_OFFERS_BY_MOLECULE[params.molecule] ?? SUPPLIER_OFFERS_BY_MOLECULE.H2
        : BUYER_RFQS_BY_MOLECULE[params.molecule] ?? BUYER_RFQS_BY_MOLECULE.H2;

      const results: Match[] = pool
        .filter(counterparty => matchesFilters(counterparty, params, mode))
        .map((counterparty, index) => ({
          id: `match_${mode}_${String(index + 1).padStart(3, '0')}`,
          supplier: mode === 'buy' ? counterparty.name : selectedProject.name,
          supplier_location: mode === 'buy' ? counterparty.location : selectedProject.location,
          buyer: mode === 'buy' ? role.company_name || selectedProject.name : counterparty.name,
          molecule: params.molecule,
          volume_mt: counterparty.volume,
          price_eur_kg: counterparty.price,
          match_score: counterparty.score,
          delivery_date: counterparty.date,
          ghg_intensity: counterparty.ghg,
          tenor_years: counterparty.tenor,
          logistics: counterparty.logistics,
          credit_rating: counterparty.credit,
          certificates: counterparty.certs,
          gex_score: counterparty.gex,
          counterparty_location: counterparty.location,
          card_kind: mode === 'buy' ? 'offer' : 'rfq',
        }));

      setMatches(results);
      setSelectedIds(results.map(result => result.id));
      setIsMatching(false);
      setShowResults(true);
    }, 1600);
  };

  const reset = () => {
    const resetProject = visibleProjects.find(project => project.id === requestedProjectId) ?? visibleProjects[0];
    setParams(buildDefaultParams(resetProject?.id ?? DEFAULT_PROJECT_ID, resetProject?.molecule ?? 'H2', mode));
    setMatches([]);
    setSelectedIds([]);
    setShowResults(false);
  };

  const handleProjectChange = (projectId: string) => {
    const project = visibleProjects.find(item => item.id === projectId);
    setParams(current => ({
      ...current,
      project_id: projectId,
      molecule: project?.molecule ?? current.molecule,
    }));
    setMatches([]);
    setSelectedIds([]);
    setShowResults(false);
  };

  const handleModeChange = (nextMode: MatchMode) => {
    if (!allowedModes.includes(nextMode)) return;
    setMode(nextMode);
    setParams(current => ({
      ...current,
      price_limit: defaultPriceLimit(nextMode),
    }));
    setMatches([]);
    setSelectedIds([]);
    setShowResults(false);
  };

  const toggleSelect = (id: string) => {
    setSelectedIds(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]);
  };

  if (visibleProjects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-16 shadow-card text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--brand-light)]">
          <Target className="w-7 h-7 text-[var(--brand)]" />
        </div>
        <div>
          <p className="font-display font-bold text-[var(--text-primary)]">No Visible Projects</p>
          <p className="mt-1 text-sm text-[var(--text-muted)]">Matching needs at least one project in your client scope.</p>
        </div>
      </div>
    );
  }

  const modeLabel = mode === 'buy' ? 'Purchase' : 'Sales';
  const headerDescription = mode === 'buy'
    ? 'Scan supplier offers and issue RFQs for the selected buying project.'
    : 'Scan buyer RFQs and qualify downstream demand for the selected selling project.';
  const runLabel = mode === 'buy' ? 'Scan Supplier Offers' : 'Scan Buyer RFQs';
  const priceLabel = mode === 'buy' ? 'Max Purchase Price (€/kg)' : 'Min Sale Price (€/kg)';
  const logisticsLabel = mode === 'buy' ? 'Accepted Logistics' : 'Deliverable Logistics';
  const matchNoun = mode === 'buy' ? 'offer' : 'rfq';
  const comparisonHelp = mode === 'buy'
    ? 'All values are normalised 0–100 relative to the selected supplier offers. 100 = best for your buying project on each axis.'
    : 'All values are normalised 0–100 relative to the selected buyer RFQs. 100 = best for your selling project on each axis.';

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.12em] text-gray-600">
            {modeLabel} Matching
          </div>
          <h1 className="mt-3 font-display text-2xl font-bold text-[var(--text-primary)]">Intelligent Matching</h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">{headerDescription}</p>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          {allowedModes.length > 1 && (
            <div className="flex rounded-lg border border-[var(--border)] bg-[var(--surface)] p-1">
              {(['buy', 'sell'] as MatchMode[]).filter(item => allowedModes.includes(item)).map(item => (
                <button
                  key={item}
                  onClick={() => handleModeChange(item)}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                    mode === item ? 'bg-gray-900 text-white' : 'text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]'
                  }`}
                >
                  {item === 'buy' ? 'Purchase' : 'Sales'}
                </button>
              ))}
            </div>
          )}
          <button
            onClick={reset}
            className="flex items-center gap-2 rounded-lg border border-[var(--border)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset
          </button>
          <button
            onClick={runMatching}
            disabled={isMatching}
            className="flex items-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            {isMatching ? 'Matching…' : runLabel}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
          <button
            onClick={() => setShowParamsPanel(value => !value)}
            className="flex w-full items-center justify-between gap-2 border-b border-[var(--border)] px-5 py-3.5 text-left"
          >
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-[var(--brand)]" />
              <span className="text-sm font-bold text-[var(--text-primary)]">{modeLabel} Parameters</span>
            </div>
            {showParamsPanel ? <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />}
          </button>

          {showParamsPanel && (
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">
                  {mode === 'buy' ? 'Buying Project' : 'Selling Project'}
                </label>
                <select
                  value={params.project_id}
                  onChange={event => handleProjectChange(event.target.value)}
                  className="gex-select w-full text-sm"
                  aria-label="Source project"
                >
                  {visibleProjects.map(project => (
                    <option key={project.id} value={project.id}>{project.name}</option>
                  ))}
                </select>
                {selectedProject && (
                  <p className="mt-1 text-[10px] text-[var(--text-muted)]">
                    {selectedProject.location} · {selectedProject.capacity_mtpd} MTPD
                  </p>
                )}
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Molecule</label>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)]">
                  {params.molecule}
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Volume Range (MT)</label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    value={params.volume_min}
                    onChange={event => setParams({ ...params, volume_min: +event.target.value })}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none"
                  />
                  <input
                    type="number"
                    value={params.volume_max}
                    onChange={event => setParams({ ...params, volume_max: +event.target.value })}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">{priceLabel}</label>
                <input
                  type="number"
                  step="0.1"
                  value={params.price_limit}
                  onChange={event => setParams({ ...params, price_limit: +event.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Max Carbon Intensity (kgCO₂/kg)</label>
                <input
                  type="number"
                  step="0.05"
                  value={params.ghg_max}
                  onChange={event => setParams({ ...params, ghg_max: +event.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Min Contract Tenor (years)</label>
                <input
                  type="number"
                  min="1"
                  max="30"
                  value={params.min_tenor_years}
                  onChange={event => setParams({ ...params, min_tenor_years: +event.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Delivery Period</label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="date"
                    value={params.delivery_start}
                    onChange={event => setParams({ ...params, delivery_start: event.target.value })}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none"
                  />
                  <input
                    type="date"
                    value={params.delivery_end}
                    onChange={event => setParams({ ...params, delivery_end: event.target.value })}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">{logisticsLabel}</label>
                <div className="flex flex-wrap gap-1.5">
                  {LOGISTICS_OPTIONS.map(option => {
                    const active = params.logistics_modes.includes(option);
                    return (
                      <button
                        key={option}
                        onClick={() => setParams({
                          ...params,
                          logistics_modes: active
                            ? params.logistics_modes.filter(item => item !== option)
                            : [...params.logistics_modes, option],
                        })}
                        className={`rounded-lg border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.1em] transition-colors ${
                          active
                            ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]'
                            : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-hover)]'
                        }`}
                      >
                        {option}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Required Certificates</label>
                <div className="flex flex-wrap gap-1.5">
                  {CERTIFICATE_OPTIONS.map(option => {
                    const active = params.required_certificates.includes(option);
                    return (
                      <button
                        key={option}
                        onClick={() => setParams({
                          ...params,
                          required_certificates: active
                            ? params.required_certificates.filter(item => item !== option)
                            : [...params.required_certificates, option],
                        })}
                        className={`rounded-lg border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.1em] transition-colors ${
                          active
                            ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]'
                            : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-hover)]'
                        }`}
                      >
                        {option}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">Min Counterparty Credit</label>
                <select
                  value={params.min_credit}
                  onChange={event => setParams({ ...params, min_credit: event.target.value })}
                  className="gex-select w-full text-sm"
                  aria-label="Minimum credit rating"
                >
                  {CREDIT_OPTIONS.map(option => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>

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
                <p className="text-sm text-[var(--text-muted)]">
                  {mode === 'buy' ? `Analysing supplier offers for ${params.molecule}…` : `Analysing buyer RFQs for ${params.molecule}…`}
                </p>
              </div>
            </div>
          ) : showResults ? (
            <>
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
                <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3.5">
                  <h2 className="text-sm font-bold text-[var(--text-primary)]">
                    {matches.length} {matchNoun}{matches.length !== 1 ? 's' : ''} · {selectedIds.length} selected for radar
                  </h2>
                  <span className="text-[10px] text-[var(--text-muted)]">Click rows to compare on radar</span>
                </div>

                {matches.length === 0 ? (
                  <div className="px-5 py-10 text-center text-sm text-[var(--text-muted)]">
                    No {matchNoun}s matched the current filters.
                  </div>
                ) : (
                  <div className="divide-y divide-[var(--border)]">
                    {matches.map((match, index) => {
                      const isSelected = selectedIds.includes(match.id);
                      const color = RADAR_COLORS[index % RADAR_COLORS.length];
                      const counterpartyName = mode === 'buy' ? match.supplier : match.buyer;

                      return (
                        <div
                          key={match.id}
                          onClick={() => toggleSelect(match.id)}
                          className={`cursor-pointer px-5 py-4 transition-colors ${isSelected ? 'bg-[var(--brand-light)]' : 'hover:bg-[var(--surface-hover)]'}`}
                        >
                          <div className="flex items-start justify-between gap-3 mb-2">
                            <div className="flex items-center gap-2.5">
                              <span className="inline-block h-3 w-3 shrink-0 rounded-full" style={{ background: color }} />
                              <div>
                                <p className="font-semibold text-[var(--text-primary)] text-sm">{match.supplier} → {match.buyer}</p>
                                <p className="text-xs text-[var(--text-muted)]">
                                  {match.card_kind === 'offer' ? 'Supplier Offer' : 'Buyer RFQ'} · {match.molecule} · {match.logistics}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <span className={scoreColor(match.match_score)}>{match.match_score}% match</span>
                              <span className="gex-badge gex-badge-default">GEX {match.gex_score}</span>
                            </div>
                          </div>

                          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-[var(--text-secondary)] sm:grid-cols-4">
                            <div className="flex items-center gap-1"><DollarSign className="w-3 h-3 text-[var(--text-muted)]" />€{match.price_eur_kg}/kg</div>
                            <div className="flex items-center gap-1"><Target className="w-3 h-3 text-[var(--text-muted)]" />{match.volume_mt.toLocaleString()} MT</div>
                            <div className="flex items-center gap-1"><Calendar className="w-3 h-3 text-[var(--text-muted)]" />{match.tenor_years}yr tenor</div>
                            <div className="flex items-center gap-1"><MapPin className="w-3 h-3 text-[var(--text-muted)]" />{match.counterparty_location}</div>
                          </div>

                          <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            {match.certificates.map(certificate => (
                              <span key={certificate} className="gex-badge gex-badge-blue">{certificate}</span>
                            ))}
                            <span className={`gex-badge ${match.ghg_intensity < 0.5 ? 'gex-badge-green' : 'gex-badge-amber'}`}>
                              {match.ghg_intensity} kgCO₂/kg
                            </span>
                            <span className="gex-badge gex-badge-default">{match.credit_rating}</span>
                            <button
                              onClick={event => {
                                event.stopPropagation();
                                navigate(
                                  mode === 'buy'
                                    ? `/trader-dashboard?project=${params.project_id}&counterparty=${encodeURIComponent(counterpartyName)}`
                                    : `/contracts?project=${params.project_id}&counterparty=${encodeURIComponent(counterpartyName)}`,
                                );
                              }}
                              className="ml-auto inline-flex items-center gap-1 rounded-md border border-[var(--border)] bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors"
                            >
                              {mode === 'buy' ? 'Issue RFQ' : 'Review RFQ'}
                              <ArrowRight className="w-3 h-3" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {selectedIds.length >= 2 && matches.length > 0 ? (
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-[var(--text-primary)]">Counterparty Comparison Radar</h3>
                      <div className="group relative">
                        <Info className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                        <div className="invisible group-hover:visible absolute left-6 top-0 z-50 w-64 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-dropdown p-3 text-xs text-[var(--text-secondary)] leading-relaxed">
                          {comparisonHelp}
                        </div>
                      </div>
                    </div>
                    <DimSelector activeDims={activeDims} metaByDim={metaByDim} onChange={setActiveDims} />
                  </div>

                  <div className="p-5">
                    <ResponsiveContainer width="100%" height={360}>
                      <RadarChart data={radarData} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
                        <PolarGrid stroke="var(--border)" />
                        <PolarAngleAxis dataKey="dim" tick={{ fill: 'var(--text-secondary)', fontSize: 11, fontWeight: 600 }} />
                        <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: 'var(--text-muted)', fontSize: 9 }} tickCount={5} axisLine={false} />
                        {selectedMatches.map(match => (
                          <Radar
                            key={match.id}
                            name={mode === 'buy' ? match.supplier : match.buyer}
                            dataKey={match.id}
                            stroke={RADAR_COLORS[matches.indexOf(match) % RADAR_COLORS.length]}
                            fill={RADAR_COLORS[matches.indexOf(match) % RADAR_COLORS.length]}
                            fillOpacity={0.15}
                            strokeWidth={2}
                            dot={{ r: 3 }}
                          />
                        ))}
                        <Legend wrapperStyle={{ fontSize: '12px', color: 'var(--text-secondary)', paddingTop: '8px' }} />
                        <Tooltip content={<RadarTooltip />} />
                      </RadarChart>
                    </ResponsiveContainer>

                    <div className="mt-4 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                      {activeDims.map(dim => (
                        <div key={dim} className="flex items-start gap-2 rounded-lg bg-[var(--surface-muted)] px-3 py-2">
                          <div className="min-w-0">
                            <span className="text-xs font-bold text-[var(--text-primary)]">{metaByDim[dim].label}</span>
                            <span className="ml-1 text-[10px] text-[var(--text-muted)]">({metaByDim[dim].unit})</span>
                            <p className="text-[10px] text-[var(--text-muted)] leading-snug">{metaByDim[dim].description}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : matches.length > 0 ? (
                <div className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] px-5 py-4 text-sm text-[var(--text-muted)]">
                  <Info className="w-4 h-4 shrink-0" />
                  Select at least 2 counterparties above to display the radar comparison.
                </div>
              ) : null}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-16 shadow-card text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--brand-light)]">
                <Target className="w-7 h-7 text-[var(--brand)]" />
              </div>
              <div>
                <p className="font-display font-bold text-[var(--text-primary)]">Ready to Find Matches</p>
                <p className="mt-1 text-sm text-[var(--text-muted)]">
                  {mode === 'buy'
                    ? 'Configure purchase criteria and scan supplier offers.'
                    : 'Configure sales criteria and scan buyer RFQs.'}
                </p>
              </div>
              <button
                onClick={runMatching}
                className="rounded-lg bg-[var(--brand)] px-6 py-2.5 text-sm font-semibold text-white hover:opacity-90 transition-opacity"
              >
                {runLabel}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
