/**
 * MoleculePriceCurve — Project-facing forward curve widget
 *
 * Reads the published Gabillon curve for a given molecule from localStorage
 * (set by GabillonAdminPage when CISO webmaster publishes) or falls back
 * to a live fetch from the finance engine at localhost:8001.
 *
 * Usage:
 *   <MoleculePriceCurve molecule="H2" compact />
 *   <MoleculePriceCurve molecule="SAF" showTable />
 */
import React, { useState, useEffect } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from 'recharts';
import { TrendingUp, TrendingDown, Minus, RefreshCw, AlertTriangle } from 'lucide-react';

// ─── Types ───────────────────────────────────────────────────────────────────

interface TermPoint {
  tenor_months: number;
  tenor_label: string;
  price_eur: number;
}

interface CurveData {
  molecule: string;
  spot_price_eur: number;
  convenience_yield: number;
  mean_reversion_half_life_months: number;
  seasonal_amplitude_pct: number;
  capex_floor_eur: number;
  calibration_error_pct: number;
  last_calibrated: string;
  n_observations: number;
  term_curve: TermPoint[];
  published_at?: string;
}

// ─── Config ──────────────────────────────────────────────────────────────────

const MOLECULE_META: Record<string, { label: string; unit: string; color: string }> = {
  H2:         { label: 'e-Hydrogen',  unit: '€/kg',  color: '#38bdf8' },
  NH3:        { label: 'e-Ammonia',   unit: '€/t',   color: '#a78bfa' },
  E_METHANOL: { label: 'e-Methanol',  unit: '€/t',   color: '#34d399' },
  E_NG:       { label: 'e-Nat. Gas',  unit: '€/MWh', color: '#fb923c' },
  SAF:        { label: 'SAF',         unit: '€/t',   color: '#facc15' },
  HVO:        { label: 'HVO',         unit: '€/t',   color: '#f87171' },
};

// ─── Props ───────────────────────────────────────────────────────────────────

interface Props {
  molecule: string;        // e.g. "H2" | "SAF" | "E_METHANOL" | "NH3" | "E_NG" | "HVO"
  compact?: boolean;       // smaller layout for embedding in project cards
  showTable?: boolean;     // show full term structure table beneath chart
  projectName?: string;    // if provided, shown as subtitle
}

// ─── Data loading ─────────────────────────────────────────────────────────────

async function loadCurve(molecule: string): Promise<CurveData | null> {
  // 1. Check localStorage for CISO-published curve
  const stored = localStorage.getItem(`gex_forward_curve_${molecule}`);
  if (stored) {
    try { return JSON.parse(stored); } catch { /* fall through */ }
  }

  // 2. Live fetch from finance engine
  try {
    const res = await fetch(`http://localhost:8001/api/v1/pricing/term-curve/${molecule}`);
    if (res.ok) {
      const data = await res.json();
      return data;
    }
  } catch { /* engine not running */ }

  // 3. Fallback: synthetic seed curve (no server needed)
  return buildFallbackCurve(molecule);
}

function buildFallbackCurve(molecule: string): CurveData {
  const spotMap: Record<string, number> = {
    H2: 5500, NH3: 700, E_METHANOL: 800, E_NG: 120, SAF: 1500, HVO: 1800,
  };
  const spot = spotMap[molecule] ?? 1000;
  const tenors = [1, 3, 6, 12, 24, 36, 60];
  const curve: TermPoint[] = tenors.map((t) => {
    const tau = t / 12;
    return {
      tenor_months: t,
      tenor_label: t < 12 ? `${t}M` : `${t / 12}Y`,
      price_eur: Math.round(spot * Math.exp(0.05 * tau) * 100) / 100,
    };
  });
  return {
    molecule,
    spot_price_eur: spot,
    convenience_yield: 0.05,
    mean_reversion_half_life_months: 8.3,
    seasonal_amplitude_pct: 9.4,
    capex_floor_eur: spot * 0.7,
    calibration_error_pct: 0,
    last_calibrated: '—',
    n_observations: 0,
    term_curve: curve,
  };
}

// ─── Market structure label ───────────────────────────────────────────────────

function marketStructure(curve: CurveData): { label: string; icon: React.ReactNode; color: string } {
  if (!curve.term_curve.length) return { label: 'N/A', icon: <Minus className="w-3.5 h-3.5" />, color: 'text-gray-400' };
  const first = curve.term_curve[0].price_eur;
  const last  = curve.term_curve[curve.term_curve.length - 1].price_eur;
  if (last > first * 1.02)  return { label: 'Contango', icon: <TrendingUp className="w-3.5 h-3.5" />, color: 'text-green-400' };
  if (last < first * 0.98)  return { label: 'Backwardation', icon: <TrendingDown className="w-3.5 h-3.5" />, color: 'text-amber-400' };
  return { label: 'Flat', icon: <Minus className="w-3.5 h-3.5" />, color: 'text-gray-400' };
}

// ─── Component ───────────────────────────────────────────────────────────────

export function MoleculePriceCurve({ molecule, compact = false, showTable = false, projectName }: Props) {
  const [curve, setCurve]     = useState<CurveData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(false);

  const meta = MOLECULE_META[molecule] ?? { label: molecule, unit: '€/t', color: '#6b7280' };

  const fetchCurve = async () => {
    setLoading(true);
    setError(false);
    const data = await loadCurve(molecule);
    if (data) { setCurve(data); } else { setError(true); }
    setLoading(false);
  };

  useEffect(() => { fetchCurve(); }, [molecule]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6
                      flex items-center justify-center gap-2 text-sm text-[var(--text-muted)]">
        <span className="w-4 h-4 border-2 border-[var(--border)] border-t-teal-400 rounded-full animate-spin" />
        Loading {meta.label} curve…
      </div>
    );
  }

  if (error || !curve) {
    return (
      <div className="rounded-2xl border border-amber-800/40 bg-amber-900/10 p-5 flex items-center gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0" />
        <div>
          <p className="text-sm font-semibold text-amber-200">Curve not available</p>
          <p className="text-xs text-amber-300/60 mt-0.5">
            Finance engine offline. CISO webmaster can publish a static curve via Pricing Admin.
          </p>
        </div>
        <button onClick={fetchCurve} className="ml-auto p-1.5 text-amber-400 hover:text-amber-200">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>
    );
  }

  const struct = marketStructure(curve);
  const chartData = curve.term_curve.map((pt) => ({
    tenor: pt.tenor_label,
    price: pt.price_eur,
    floor: curve.capex_floor_eur,
  }));

  const isPublished = !!curve.published_at;
  const isSeed      = curve.n_observations === 0;

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">

      {/* Header */}
      <div className="px-5 py-3.5 border-b border-[var(--border)] flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: meta.color }} />
          <div>
            <span className="text-sm font-bold text-[var(--text-primary)]">{meta.label} Forward Curve</span>
            {projectName && (
              <span className="text-xs text-[var(--text-muted)] ml-2">— {projectName}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isSeed && (
            <span className="text-xs bg-amber-900/30 text-amber-400 border border-amber-800/50
                             rounded-full px-2 py-0.5">Seed params</span>
          )}
          {isPublished && (
            <span className="text-xs bg-green-900/30 text-green-400 border border-green-800/50
                             rounded-full px-2 py-0.5">Published</span>
          )}
        </div>
      </div>

      <div className={compact ? 'p-4' : 'p-5'}>

        {/* KPI row */}
        <div className={`grid gap-3 mb-4 ${compact ? 'grid-cols-3' : 'grid-cols-2 sm:grid-cols-5'}`}>
          {[
            { label: 'Spot',        value: `${curve.spot_price_eur.toLocaleString()} ${meta.unit}` },
            { label: 'Structure',   value: struct.label, extra: struct.icon, color: struct.color },
            { label: 'Half-Life',   value: `${curve.mean_reversion_half_life_months}M` },
            ...(!compact ? [
              { label: 'Seasonality', value: `±${curve.seasonal_amplitude_pct}%` },
              { label: 'CAPEX Floor', value: `${curve.capex_floor_eur.toLocaleString()} ${meta.unit}` },
            ] : []),
          ].map(({ label, value, extra, color }) => (
            <div key={label}
                 className="rounded-lg border border-[var(--border)] bg-[var(--surface-hover)] px-3 py-2.5">
              <div className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">{label}</div>
              <div className={`flex items-center gap-1.5 text-sm font-mono font-bold ${color ?? 'text-[var(--text-primary)]'}`}>
                {extra}{value}
              </div>
            </div>
          ))}
        </div>

        {/* Chart */}
        <ResponsiveContainer width="100%" height={compact ? 160 : 220}>
          <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`grad_${molecule}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={meta.color} stopOpacity={0.3} />
                <stop offset="95%" stopColor={meta.color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="tenor" tick={{ fontSize: 10, fill: '#6b7280' }} />
            <YAxis tick={{ fontSize: 10, fill: '#6b7280' }}
                   tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)}
                   width={40} />
            <Tooltip
              contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
              formatter={(v: number) => [`${v.toLocaleString()} ${meta.unit}`, 'Forward']}
            />
            <Area
              type="monotone" dataKey="price" name="Forward"
              stroke={meta.color} strokeWidth={2}
              fill={`url(#grad_${molecule})`} dot={false}
            />
            <ReferenceLine
              y={curve.capex_floor_eur} stroke="#ef4444" strokeDasharray="4 3" strokeOpacity={0.5}
            />
          </AreaChart>
        </ResponsiveContainer>

        {/* Last calibrated */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-[var(--border)]">
          <span className="text-xs text-[var(--text-muted)]">
            Calibrated: {curve.last_calibrated}
            {isSeed && ' · using seed parameters (no market data)'}
            {!isSeed && ` · ${curve.n_observations} observations`}
          </span>
          <button onClick={fetchCurve}
                  className="p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Optional term structure table */}
        {showTable && !compact && (
          <div className="mt-4 overflow-x-auto">
            <table className="gex-table">
              <thead>
                <tr>
                  {['Tenor', 'Forward Price', 'vs Spot', 'vs CAPEX Floor'].map((h) => <th key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {curve.term_curve.map((pt) => {
                  const vsSpot  = ((pt.price_eur - curve.spot_price_eur) / curve.spot_price_eur * 100).toFixed(1);
                  const vsFloor = ((pt.price_eur - curve.capex_floor_eur) / curve.capex_floor_eur * 100).toFixed(1);
                  return (
                    <tr key={pt.tenor_months}>
                      <td className="font-mono font-bold text-[var(--text-primary)]">{pt.tenor_label}</td>
                      <td className="font-mono">{pt.price_eur.toLocaleString()} <span className="text-xs text-[var(--text-muted)]">{meta.unit}</span></td>
                      <td className={`font-mono text-xs ${+vsSpot >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {+vsSpot >= 0 ? '+' : ''}{vsSpot}%
                      </td>
                      <td className={`font-mono text-xs ${+vsFloor >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {+vsFloor >= 0 ? '+' : ''}{vsFloor}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default MoleculePriceCurve;
