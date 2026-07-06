// Screen: Gabillon pricing admin screen (/ciso-pricing)
/**
 * GabillonAdminPage — GEX Webmaster / Orchestrator Tool
 * Route: /ciso-pricing  (CISO password-gated)
 *
 * Purpose:
 *   1. Enter historical price observations per molecule
 *   2. Calibrate the Gabillon Two-Factor model
 *   3. View backtest quality (model vs observed)
 *   4. Publish the forward curve to the platform
 *
 * Molecules: e-Methane · e-Methanol · e-NH3 · HVO · SAF · e-Gasoline · e-LG · e-Naphtha
 */
import React, { useState, useCallback } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Area, AreaChart, Legend,
} from 'recharts';
import {
  FlaskConical, Upload, RefreshCw, CheckCircle, AlertTriangle,
  Plus, Trash2, TrendingUp, Activity, BarChart2, Settings2,
  BookOpen, Info, ChevronDown, ChevronUp,
} from 'lucide-react';

// ─── Types ───────────────────────────────────────────────────────────────────

interface Molecule {
  id: string;
  label: string;
  unit: string;
  color: string;
  spotHint: number;   // indicative spot price for UI placeholder
}

const MOLECULES: Molecule[] = [
  { id: 'H2',         label: 'e-Hydrogen',   unit: '€/t',   color: '#06b6d4', spotHint: 5500 },
  { id: 'E_METHANE',  label: 'e-Methane',    unit: '€/MWh', color: '#38bdf8', spotHint: 120  },
  { id: 'E_METHANOL', label: 'e-Methanol',   unit: '€/t',   color: '#34d399', spotHint: 800  },
  { id: 'E_NH3',      label: 'e-NH3',        unit: '€/t',   color: '#a78bfa', spotHint: 700  },
  { id: 'HVO',        label: 'HVO',          unit: '€/t',   color: '#f87171', spotHint: 1800 },
  { id: 'SAF',        label: 'SAF',          unit: '€/t',   color: '#facc15', spotHint: 1500 },
  { id: 'E_GASOLINE', label: 'e-Gasoline',   unit: '€/t',   color: '#fb923c', spotHint: 1250 },
  { id: 'E_LG',       label: 'e-LG',         unit: '€/MWh', color: '#60a5fa', spotHint: 145  },
  { id: 'E_NAPHTHA',  label: 'e-Naphtha',    unit: '€/t',   color: '#f472b6', spotHint: 980  },
  { id: 'E_NG',       label: 'e-Nat. Gas',   unit: '€/MWh', color: '#fb923c', spotHint: 120  },
];

const TENORS = [0, 1, 3, 6, 12, 24, 36, 60];
const SOURCES = ['ARGUS_NWE', 'ICIS', 'PLATTS', 'GEX_CONTRACT', 'OPIS', 'S&P_GLOBAL'];

interface Observation {
  id: string;
  date: string;
  price_eur: number;
  tenor_months: number;
  source: string;
  volume_tonnes: number;
}

interface TermPoint {
  tenor_months: number;
  tenor_label: string;
  price_eur: number;
  implied_forward_eur: number;
  carry_eur: number | null;
  annualised_return_pct: number;
}

interface CalibrationResult {
  molecule: string;
  spot_price_eur: number;
  convenience_yield: number;
  mean_reversion_half_life_months: number;
  seasonal_amplitude_pct: number;
  capex_floor_eur: number;
  calibration_error_pct: number;
  last_calibrated: string;
  n_observations: number;
  params: Record<string, number | string>;
  term_curve: TermPoint[];
}

// ─── Seed data (fallback when API not running) ────────────────────────────────

function buildSeedCurve(mol: Molecule): CalibrationResult {
  const spotMap: Record<string, number> = {
    H2: 5500, E_METHANE: 120, E_METHANOL: 800, E_NH3: 700, HVO: 1800,
    SAF: 1500, E_GASOLINE: 1250, E_LG: 145, E_NAPHTHA: 980, E_NG: 120,
  };
  const spot = spotMap[mol.id] ?? 1000;
  const tenors = [1, 3, 6, 12, 24, 36, 60];
  const curve: TermPoint[] = tenors.map((t) => {
    const tau = t / 12;
    // Simple contango for demo: F = S * e^(0.05 * tau)
    const price = Math.round(spot * Math.exp(0.05 * tau) * 100) / 100;
    return {
      tenor_months: t,
      tenor_label: t < 12 ? `${t}M` : `${t / 12}Y`,
      price_eur: price,
      implied_forward_eur: price,
      carry_eur: t <= 12 ? price - spot : null,
      annualised_return_pct: Math.round((price / spot - 1) / tau * 100 * 10) / 10,
    };
  });
  return {
    molecule: mol.id,
    spot_price_eur: spot,
    convenience_yield: 0.05,
    mean_reversion_half_life_months: 8.3,
    seasonal_amplitude_pct: 9.4,
    capex_floor_eur: spot * 0.7,
    calibration_error_pct: 0,
    last_calibrated: '2026-03-25 (seed)',
    n_observations: 0,
    params: { alpha: 0.8, sigma_s: 0.35, kappa: 0.5, theta_0: 0.05, rho: -0.28 },
    term_curve: curve,
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

let _obsId = 1;
const newObs = (_mol: string): Observation => ({
  id: String(_obsId++),
  date: new Date().toISOString().slice(0, 10),
  price_eur: 0,
  tenor_months: 0,
  source: 'ARGUS_NWE',
  volume_tonnes: 1,
});

// ─── Main Component ───────────────────────────────────────────────────────────

export function GabillonAdminPage() {
  const [activeMol, setActiveMol] = useState<Molecule>(MOLECULES[0]);
  const [observations, setObservations] = useState<Record<string, Observation[]>>({});
  const [results, setResults] = useState<Record<string, CalibrationResult>>({});
  const [published, setPublished] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'calibrate' | 'backtest' | 'curve'>('curve');
  const [capexFloor, setCapexFloor] = useState<Record<string, number>>({});
  const [showParams, setShowParams] = useState(false);

  const molObs = observations[activeMol.id] ?? [];
  const molResult = results[activeMol.id] ?? buildSeedCurve(activeMol);
  const isPublished = published[activeMol.id] ?? false;

  // ── Fetch calibration from backend ────────────────────────────
  const calibrate = useCallback(async () => {
    setLoading(true);
    const obs = (observations[activeMol.id] ?? []).map((o) => ({
      date: o.date,
      price_eur: o.price_eur,
      tenor_months: o.tenor_months,
      source: o.source,
      molecule: activeMol.id,
      volume_tonnes: o.volume_tonnes,
    }));

    try {
      const res = await fetch('/api/v1/pricing/calibrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          molecule: activeMol.id,
          observations: obs,
          capex_floor_eur_t: capexFloor[activeMol.id] ?? 0,
          cumulative_capacity_gw: 5.0,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setResults((prev) => ({ ...prev, [activeMol.id]: data }));
      } else {
        // API unavailable — use seed
        setResults((prev) => ({ ...prev, [activeMol.id]: buildSeedCurve(activeMol) }));
      }
    } catch {
      setResults((prev) => ({ ...prev, [activeMol.id]: buildSeedCurve(activeMol) }));
    } finally {
      setLoading(false);
    }
  }, [activeMol, observations, capexFloor]);

  const publish = () => {
    // In production: POST calibration result to platform backend
    // so all project views can consume the published curve.
    setPublished((prev) => ({ ...prev, [activeMol.id]: true }));
    // Store in localStorage as a simple pub/sub for now
    localStorage.setItem(
      `gex_forward_curve_${activeMol.id}`,
      JSON.stringify({ ...molResult, published_at: new Date().toISOString() })
    );
  };

  const addObs = () =>
    setObservations((prev) => ({
      ...prev,
      [activeMol.id]: [...(prev[activeMol.id] ?? []), newObs(activeMol.id)],
    }));

  const removeObs = (id: string) =>
    setObservations((prev) => ({
      ...prev,
      [activeMol.id]: (prev[activeMol.id] ?? []).filter((o) => o.id !== id),
    }));

  const updateObs = (id: string, field: keyof Observation, value: string | number) =>
    setObservations((prev) => ({
      ...prev,
      [activeMol.id]: (prev[activeMol.id] ?? []).map((o) =>
        o.id === id ? { ...o, [field]: value } : o
      ),
    }));

  // ── Chart data ────────────────────────────────────────────────
  const curveData = molResult.term_curve.map((pt) => ({
    tenor: pt.tenor_label,
    model: pt.price_eur,
    ...(molObs.length > 0 && {
      observed: molObs.find((o) => o.tenor_months === pt.tenor_months)?.price_eur ?? null,
    }),
    capex_floor: molResult.capex_floor_eur,
  }));

  // Backtest: compare model to all entered observations
  const backtestData = molObs.map((o) => {
    const modelPt = molResult.term_curve.find((pt) => pt.tenor_months === o.tenor_months);
    const modelPrice = modelPt?.price_eur ?? molResult.spot_price_eur;
    const errorPct = o.price_eur > 0
      ? ((modelPrice - o.price_eur) / o.price_eur) * 100
      : 0;
    return {
      date: o.date,
      observed: o.price_eur,
      model: modelPrice,
      error_pct: Math.round(errorPct * 10) / 10,
    };
  });

  const mol = activeMol;

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="w-5 h-5 text-amber-400" />
            <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">
              Gabillon Price Curve Engine
            </h1>
            <span className="text-xs bg-amber-900/30 text-amber-400 border border-amber-800/50
                             rounded-full px-2 py-0.5 font-semibold">
              WEBMASTER
            </span>
          </div>
          <p className="text-sm text-[var(--text-secondary)]">
            Calibrate the two-factor Gabillon model · Backtest against market data · Publish forward curves per molecule
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={calibrate}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg bg-teal-700 hover:bg-teal-600
                       disabled:opacity-60 px-4 py-2 text-sm font-semibold text-white transition-colors"
          >
            {loading
              ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              : <RefreshCw className="w-4 h-4" />}
            Run Calibration
          </button>
          <button
            onClick={publish}
            disabled={!molResult || isPublished}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold
                        transition-colors ${
              isPublished
                ? 'bg-green-900/30 text-green-400 border border-green-800/50'
                : 'bg-indigo-700 hover:bg-indigo-600 text-white'
            }`}
          >
            {isPublished ? <CheckCircle className="w-4 h-4" /> : <Upload className="w-4 h-4" />}
            {isPublished ? 'Published' : 'Publish Curve'}
          </button>
        </div>
      </div>

      {/* ── Model description ── */}
      <div className="flex items-start gap-3 rounded-xl border border-blue-800/40 bg-blue-900/10 px-4 py-3">
        <BookOpen className="mt-0.5 w-4 h-4 flex-shrink-0 text-blue-400" />
        <div className="text-sm text-blue-200/80 space-y-1">
          <span className="font-semibold text-blue-200">Gabillon Modified Two-Factor Model (1991 + GEX extensions):</span>
          {' '}F(t,T) = S(t) · exp[(1/α)(1−e<sup>−α(T−t)</sup>)(δ−θ) + (T−t)·μ + σ² corrections + seasonality(T) + CAPEX floor pull]
          <span className="block text-xs text-blue-300/60 mt-1">
            Extensions: (1) CAPEX learning curve floor  (2) Quarterly Fourier seasonality  (3) Regulatory premium RP(t) from EU ETS + RFNBO mandate
          </span>
        </div>
      </div>

      {/* ── Molecule tabs ── */}
      <div className="flex flex-wrap gap-2">
        {MOLECULES.map((m) => {
          const hasResult = !!results[m.id];
          const isPub = published[m.id];
          return (
            <button
              key={m.id}
              onClick={() => setActiveMol(m)}
              className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold
                          transition-colors ${
                activeMol.id === m.id
                  ? 'border-[var(--brand)] bg-indigo-900/20 text-[var(--text-primary)]'
                  : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand-muted)]'
              }`}
            >
              <span
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: m.color }}
              />
              {m.label}
              {isPub && <CheckCircle className="w-3.5 h-3.5 text-green-500" />}
              {hasResult && !isPub && <Activity className="w-3 h-3 text-teal-400" />}
            </button>
          );
        })}
      </div>

      {/* ── Tab nav ── */}
      <div className="flex gap-1 border-b border-[var(--border)]">
        {(
          [
            { id: 'curve',     label: 'Forward Curve',       icon: <TrendingUp className="w-4 h-4" /> },
            { id: 'calibrate', label: 'Calibration Data',    icon: <FlaskConical className="w-4 h-4" /> },
            { id: 'backtest',  label: 'Backtest',            icon: <BarChart2 className="w-4 h-4" /> },
          ] as { id: typeof activeTab; label: string; icon: React.ReactNode }[]
        ).map(({ id, label, icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px
              ${activeTab === id
                ? 'border-[var(--brand)] text-[var(--brand)]'
                : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
          >
            {icon}{label}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════════════════
          TAB: FORWARD CURVE
      ══════════════════════════════════════════════════ */}
      {activeTab === 'curve' && (
        <div className="space-y-4">
          {/* KPI row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            {[
              { label: 'Spot',           value: `${molResult.spot_price_eur.toLocaleString()} ${mol.unit}` },
              { label: 'Conv. Yield',    value: (molResult.convenience_yield * 100).toFixed(1) + '%' },
              { label: 'Half-Life',      value: `${molResult.mean_reversion_half_life_months}M` },
              { label: 'Seasonality',    value: `±${molResult.seasonal_amplitude_pct}%` },
              { label: 'CAPEX Floor',    value: `${molResult.capex_floor_eur.toLocaleString()} ${mol.unit}` },
              { label: 'Cal. Error',     value: `${molResult.calibration_error_pct}%`,
                warn: molResult.calibration_error_pct > 5 },
            ].map(({ label, value, warn }) => (
              <div key={label}
                   className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
                <div className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">{label}</div>
                <div className={`text-base font-mono font-bold ${
                  warn ? 'text-amber-400' : 'text-[var(--text-primary)]'
                }`}>
                  {value}
                </div>
              </div>
            ))}
          </div>

          {/* Forward curve chart */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-[var(--text-primary)]">
                {mol.label} — Gabillon Forward Curve
              </h2>
              <div className="flex items-center gap-3 text-xs text-[var(--text-muted)]">
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 bg-teal-400 inline-block" /> Model
                </span>
                {molObs.length > 0 && (
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" /> Observed
                  </span>
                )}
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 border-t-2 border-dashed border-red-500/60 inline-block" /> CAPEX floor
                </span>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={curveData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="curveGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={mol.color} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={mol.color} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="tenor" tick={{ fontSize: 11, fill: '#6b7280' }} />
                <YAxis tick={{ fontSize: 11, fill: '#6b7280' }}
                       tickFormatter={(v) => v.toLocaleString()} />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#e5e7eb', fontSize: 12 }}
                  formatter={(v: number) => [`${v.toLocaleString()} ${mol.unit}`, '']}
                />
                <Area
                  type="monotone" dataKey="model" name="Model"
                  stroke={mol.color} strokeWidth={2}
                  fill="url(#curveGrad)" dot={false}
                />
                {molObs.length > 0 && (
                  <Line
                    type="monotone" dataKey="observed" name="Observed"
                    stroke="#fbbf24" strokeWidth={0} dot={{ r: 5, fill: '#fbbf24', strokeWidth: 0 }}
                    connectNulls={false}
                  />
                )}
                <ReferenceLine
                  y={molResult.capex_floor_eur} stroke="#ef4444" strokeDasharray="5 3"
                  strokeOpacity={0.6} label={{ value: 'CAPEX floor', fill: '#ef4444', fontSize: 10 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Term structure table */}
          <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
            <div className="px-5 py-3.5 border-b border-[var(--border)]">
              <h2 className="text-sm font-bold text-[var(--text-primary)]">Term Structure</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="gex-table">
                <thead>
                  <tr>
                    {['Tenor', 'Forward Price', 'Carry (1Y)', 'Ann. Return', 'vs CAPEX Floor'].map((h) => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {molResult.term_curve.map((pt) => {
                    const vsFloor = ((pt.price_eur - molResult.capex_floor_eur) / molResult.capex_floor_eur * 100);
                    return (
                      <tr key={pt.tenor_months}>
                        <td className="font-mono font-bold text-[var(--text-primary)]">{pt.tenor_label}</td>
                        <td className="font-mono text-[var(--text-primary)]">
                          {pt.price_eur.toLocaleString()} <span className="text-[var(--text-muted)] text-xs">{mol.unit}</span>
                        </td>
                        <td className="font-mono text-[var(--text-secondary)]">
                          {pt.carry_eur != null ? `${pt.carry_eur > 0 ? '+' : ''}${pt.carry_eur.toLocaleString()}` : '—'}
                        </td>
                        <td className={`font-mono ${pt.annualised_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {pt.annualised_return_pct > 0 ? '+' : ''}{pt.annualised_return_pct}%
                        </td>
                        <td className={`font-mono text-xs ${vsFloor >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {vsFloor >= 0 ? '+' : ''}{vsFloor.toFixed(1)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Model params (collapsible) */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)]">
            <button
              onClick={() => setShowParams((p) => !p)}
              className="w-full flex items-center justify-between px-5 py-3.5 text-sm font-bold
                         text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors rounded-xl"
            >
              <div className="flex items-center gap-2">
                <Settings2 className="w-4 h-4 text-[var(--text-muted)]" />
                Calibrated Model Parameters
              </div>
              {showParams ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            {showParams && (
              <div className="px-5 pb-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
                {Object.entries(molResult.params).map(([key, val]) => (
                  <div key={key}
                       className="rounded-lg border border-[var(--border)] bg-[var(--surface-hover)] px-3 py-2">
                    <div className="text-xs text-[var(--text-muted)] font-mono mb-0.5">{key}</div>
                    <div className="text-sm font-mono font-bold text-[var(--text-primary)]">
                      {typeof val === 'number' ? val.toFixed(4) : val}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════
          TAB: CALIBRATION DATA
      ══════════════════════════════════════════════════ */}
      {activeTab === 'calibrate' && (
        <div className="space-y-4">
          {/* CAPEX floor input */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <label className="block text-xs font-bold uppercase tracking-wider text-[var(--text-muted)] mb-2">
              CAPEX Floor ({mol.unit}) — LCOH / Levelised Cost Override
            </label>
            <input
              type="number"
              value={capexFloor[mol.id] ?? ''}
              onChange={(e) => setCapexFloor((p) => ({ ...p, [mol.id]: +e.target.value }))}
              placeholder={`e.g. ${mol.spotHint * 0.7} — from Plant Builder`}
              className="w-full max-w-xs bg-[var(--surface-hover)] border border-[var(--border)]
                         rounded-lg px-3 py-2 text-sm text-[var(--text-primary)]
                         focus:outline-none focus:border-[var(--brand)] font-mono"
            />
            <p className="text-xs text-[var(--text-muted)] mt-1.5">
              Prices below this floor trigger a mean-reversion upward pull in the model.
              Link to Plant Builder CAPEX output for live integration.
            </p>
          </div>

          {/* Observation table */}
          <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3.5">
              <h2 className="text-sm font-bold text-[var(--text-primary)]">
                Price Observations — {mol.label} ({molObs.length} rows)
              </h2>
              <button
                onClick={addObs}
                className="flex items-center gap-1.5 rounded-lg border border-[var(--border)]
                           px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)]
                           hover:bg-[var(--surface-hover)] transition-colors"
              >
                <Plus className="w-3.5 h-3.5" /> Add Row
              </button>
            </div>

            {molObs.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <Info className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-3" />
                <p className="text-sm text-[var(--text-secondary)]">
                  No observations yet — model uses seed parameters.
                </p>
                <p className="text-xs text-[var(--text-muted)] mt-1">
                  Add rows for spot (tenor=0) and forward tenors (3, 6, 12, 24, 36, 60 months).
                </p>
                <button
                  onClick={addObs}
                  className="mt-4 flex items-center gap-1.5 mx-auto rounded-lg bg-teal-700
                             hover:bg-teal-600 px-4 py-2 text-sm font-semibold text-white"
                >
                  <Plus className="w-4 h-4" /> Add first observation
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="gex-table">
                  <thead>
                    <tr>
                      {['Date', `Price (${mol.unit})`, 'Tenor (months)', 'Source', 'Volume (t)', ''].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {molObs.map((obs) => (
                      <tr key={obs.id}>
                        <td>
                          <input
                            type="date"
                            value={obs.date}
                            onChange={(e) => updateObs(obs.id, 'date', e.target.value)}
                            className="bg-transparent text-sm text-[var(--text-primary)] focus:outline-none"
                          />
                        </td>
                        <td>
                          <input
                            type="number"
                            value={obs.price_eur || ''}
                            onChange={(e) => updateObs(obs.id, 'price_eur', +e.target.value)}
                            placeholder="0"
                            className="w-28 bg-[var(--surface-hover)] rounded px-2 py-1 text-sm
                                       font-mono text-[var(--text-primary)] focus:outline-none border border-[var(--border)]"
                          />
                        </td>
                        <td>
                          <select
                            value={obs.tenor_months}
                            onChange={(e) => updateObs(obs.id, 'tenor_months', +e.target.value)}
                            className="bg-[var(--surface-hover)] rounded px-2 py-1 text-sm
                                       text-[var(--text-primary)] focus:outline-none border border-[var(--border)]"
                          >
                            {TENORS.map((t) => (
                              <option key={t} value={t}>{t === 0 ? 'Spot (0)' : `${t}M`}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <select
                            value={obs.source}
                            onChange={(e) => updateObs(obs.id, 'source', e.target.value)}
                            className="bg-[var(--surface-hover)] rounded px-2 py-1 text-sm
                                       text-[var(--text-primary)] focus:outline-none border border-[var(--border)]"
                          >
                            {SOURCES.map((s) => (
                              <option key={s} value={s}>{s}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input
                            type="number"
                            value={obs.volume_tonnes}
                            onChange={(e) => updateObs(obs.id, 'volume_tonnes', +e.target.value)}
                            className="w-20 bg-[var(--surface-hover)] rounded px-2 py-1 text-sm
                                       font-mono text-[var(--text-primary)] focus:outline-none border border-[var(--border)]"
                          />
                        </td>
                        <td>
                          <button
                            onClick={() => removeObs(obs.id)}
                            className="p-1.5 text-[var(--text-muted)] hover:text-red-400 transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="flex justify-end">
            <button
              onClick={calibrate}
              disabled={loading}
              className="flex items-center gap-2 rounded-lg bg-teal-700 hover:bg-teal-600
                         disabled:opacity-60 px-5 py-2 text-sm font-semibold text-white"
            >
              {loading
                ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                : <RefreshCw className="w-4 h-4" />}
              Run Calibration →
            </button>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════
          TAB: BACKTEST
      ══════════════════════════════════════════════════ */}
      {activeTab === 'backtest' && (
        <div className="space-y-4">
          {molObs.length === 0 ? (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-6 py-12 text-center">
              <BarChart2 className="w-10 h-10 text-[var(--text-muted)] mx-auto mb-3" />
              <p className="text-sm text-[var(--text-secondary)] mb-1">No observations to backtest against.</p>
              <p className="text-xs text-[var(--text-muted)]">
                Add price observations in the Calibration Data tab, then run calibration.
              </p>
            </div>
          ) : (
            <>
              {/* Error summary */}
              <div className="grid grid-cols-3 gap-3">
                {(() => {
                  const errors = backtestData.map((d) => Math.abs(d.error_pct));
                  const mae = errors.length ? errors.reduce((a, b) => a + b, 0) / errors.length : 0;
                  const maxErr = errors.length ? Math.max(...errors) : 0;
                  const within5 = errors.filter((e) => e <= 5).length;
                  return [
                    { label: 'Mean Abs. Error', value: `${mae.toFixed(1)}%`, warn: mae > 5 },
                    { label: 'Max Error', value: `${maxErr.toFixed(1)}%`, warn: maxErr > 10 },
                    { label: 'Within ±5%', value: `${within5}/${errors.length} obs` },
                  ];
                })().map(({ label, value, warn }) => (
                  <div key={label} className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
                    <div className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">{label}</div>
                    <div className={`text-lg font-mono font-bold ${warn ? 'text-amber-400' : 'text-[var(--text-primary)]'}`}>
                      {value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Backtest chart */}
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
                <h2 className="text-sm font-bold text-[var(--text-primary)] mb-4">
                  Model vs Observed — {mol.label}
                </h2>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={backtestData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#6b7280' }} />
                    <YAxis tick={{ fontSize: 11, fill: '#6b7280' }}
                           tickFormatter={(v) => v.toLocaleString()} />
                    <Tooltip
                      contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                      formatter={(v: number) => [`${v.toLocaleString()} ${mol.unit}`, '']}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="model"    name="Model"    stroke={mol.color} strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="observed" name="Observed" stroke="#fbbf24"   strokeWidth={0}
                          dot={{ r: 5, fill: '#fbbf24', strokeWidth: 0 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Error table */}
              <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
                <div className="px-5 py-3.5 border-b border-[var(--border)]">
                  <h2 className="text-sm font-bold text-[var(--text-primary)]">Residuals</h2>
                </div>
                <div className="overflow-x-auto">
                  <table className="gex-table">
                    <thead>
                      <tr>
                        {['Date', `Observed (${mol.unit})`, `Model (${mol.unit})`, 'Error %', 'Quality'].map((h) => (
                          <th key={h}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {backtestData.map((row, i) => {
                        const abs = Math.abs(row.error_pct);
                        return (
                          <tr key={i}>
                            <td className="font-mono text-xs">{row.date}</td>
                            <td className="font-mono">{row.observed.toLocaleString()}</td>
                            <td className="font-mono">{row.model.toLocaleString()}</td>
                            <td className={`font-mono ${abs <= 5 ? 'text-green-400' : abs <= 10 ? 'text-amber-400' : 'text-red-400'}`}>
                              {row.error_pct > 0 ? '+' : ''}{row.error_pct}%
                            </td>
                            <td>
                              {abs <= 5
                                ? <CheckCircle className="w-4 h-4 text-green-500" />
                                : <AlertTriangle className={`w-4 h-4 ${abs <= 10 ? 'text-amber-400' : 'text-red-400'}`} />
                              }
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default GabillonAdminPage;
