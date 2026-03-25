/**
 * Plant Builder — Equipment-Level CAPEX/OPEX Configuration Engine
 * Route: /finance-plant-builder
 * Zone: STRUCTURE (teal)
 * API: /api/v1/plant-builder/*
 *
 * Bloomberg/Excel UX: compact, dense, keyboard-navigable, monospace numbers.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Factory, Plus, Trash2, RefreshCw, ChevronDown, ChevronRight,
  AlertTriangle, Award, TrendingUp, TrendingDown, Zap, Search,
  Filter, BarChart3, DollarSign, Settings,
} from 'lucide-react';
import { InfoTooltip } from '@/components/ui/InfoTooltip';
import { HELP, TAB_DESCRIPTIONS } from '@/config/helpText';

// ─── Types ────────────────────────────────────────────────────

interface EquipmentItem {
  id: string;
  name: string;
  category: string;
  unit_price_eur: number;
  installation_multiplier: number;
  annual_om_pct: number;
  annual_power_mwh: number;
  useful_life_years: number;
  molecule_output: string;
  capacity_tonnes_year: number;
  installed_cost_eur: number;
  cert_enables: string[];
  technology_maturity: string;
  oem: string;
  description: string;
  capex_layer: string;
}

interface ConfigLine {
  equipment_id: string;
  name: string;
  category: string;
  quantity: number;
  unit_price_eur: number;
  installed_cost_eur: number;
}

interface BuildResult {
  capex: {
    total_equipment_eur: number;
    total_installed_eur: number;
    contingency_eur: number;
    total_capex_eur: number;
    per_layer: Record<string, number>;
    by_category: Record<string, number>;
  };
  opex: {
    annual_om_eur: number;
    annual_power_eur: number;
    annual_water_eur: number;
    annual_labour_eur: number;
    annual_insurance_eur: number;
    total_annual_opex_eur: number;
  };
  output: {
    annual_output_tonnes: number;
    annualised_capex_eur: number;
    levelised_cost_eur_t: number;
    market_price_eur_t: number;
    competitive_gap_eur_t: number;
    subsidy_needed_eur_t: number;
    subsidy_needed_total_eur_yr: number;
  };
  certification: {
    readiness: Record<string, number>;
    blockers: string[];
    premium_eur_t: Record<string, number>;
    effective_price_with_certs: number;
  };
  equipment_lines: Array<{
    equipment_id: string;
    name: string;
    category: string;
    quantity: number;
    installed_cost_eur: number;
    annual_om_eur: number;
    annual_output_tonnes: number;
  }>;
}

// ─── Helpers ──────────────────────────────────────────────────

const fmt = (n: number, decimals = 0): string => {
  if (Math.abs(n) >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + 'B';
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(1) + 'k';
  return n.toFixed(decimals);
};

const fmtEur = (n: number): string => '€' + fmt(n);

const MATURITY_COLOR: Record<string, string> = {
  PROVEN: 'text-green-400',
  FIRST_OF_KIND: 'text-amber-400',
  DEMONSTRATION: 'text-red-400',
};

const CERT_COLOR: Record<string, string> = {
  RFNBO: 'text-teal-400',
  RED_III: 'text-blue-400',
  '45V': 'text-purple-400',
  CORSIA: 'text-amber-400',
  CertifHy: 'text-green-400',
};

const CATEGORY_ORDER = [
  'ELECTROLYSER', 'REACTOR', 'BOP', 'STORAGE',
  'INFRASTRUCTURE', 'UTILITIES', 'CONTROLS', 'SAFETY',
];

const MOLECULES = ['H2', 'SAF', 'NH3', 'E_METHANOL', 'ALL'];

const DEFAULT_MARKET_PRICES: Record<string, number> = {
  H2: 5000, SAF: 1500, NH3: 700, E_METHANOL: 800, E_NG: 1200,
};

// ─── Main Component ───────────────────────────────────────────

export function PlantBuilder() {
  // Catalog state
  const [catalog, setCatalog] = useState<EquipmentItem[]>([]);
  const [catalogByCategory, setCatalogByCategory] = useState<Record<string, EquipmentItem[]>>({});
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set(['ELECTROLYSER']));
  const [catalogSearch, setCatalogSearch] = useState('');
  const [catalogMolecule, setCatalogMolecule] = useState('');

  // Configuration state
  const [configLines, setConfigLines] = useState<ConfigLine[]>([]);
  const [molecule, setMolecule] = useState('H2');
  const [jurisdiction, setJurisdiction] = useState('FR');
  const [powerPrice, setPowerPrice] = useState(45.0);
  const [waterPrice, setWaterPrice] = useState(2.5);
  const [labourCount, setLabourCount] = useState(45);
  const [labourCost, setLabourCost] = useState(65000);
  const [contingency, setContingency] = useState(10);
  const [wacc, setWacc] = useState(9.0);
  const [projectLife, setProjectLife] = useState(20);
  const [marketPrice, setMarketPrice] = useState(5000);

  // Computation state
  const [result, setResult] = useState<BuildResult | null>(null);
  const [computing, setComputing] = useState(false);
  const [activeTab, setActiveTab] = useState<'capex' | 'opex' | 'lcoe' | 'cert'>('capex');

  // ── Load catalog ──────────────────────────────────────────
  const loadCatalog = useCallback(async (mol = '', cat = '') => {
    setCatalogLoading(true);
    try {
      const params = new URLSearchParams();
      if (mol) params.set('molecule', mol);
      if (cat) params.set('category', cat);
      const r = await fetch(`/api/v1/plant-builder/catalog?${params}`);
      const data = await r.json();
      setCatalog(data.items || []);
      setCatalogByCategory(data.by_category || {});
    } catch (e) {
      console.error('Catalog load failed', e);
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  useEffect(() => { loadCatalog(); }, [loadCatalog]);

  // ── Molecule change cascades market price default ──────────
  useEffect(() => {
    setMarketPrice(DEFAULT_MARKET_PRICES[molecule] ?? 1000);
  }, [molecule]);

  // ── Add to config ─────────────────────────────────────────
  const addItem = (item: EquipmentItem) => {
    setConfigLines(prev => {
      const existing = prev.find(l => l.equipment_id === item.id);
      if (existing) {
        return prev.map(l =>
          l.equipment_id === item.id ? { ...l, quantity: l.quantity + 1 } : l
        );
      }
      return [...prev, {
        equipment_id: item.id,
        name: item.name,
        category: item.category,
        quantity: 1,
        unit_price_eur: item.unit_price_eur,
        installed_cost_eur: item.installed_cost_eur,
      }];
    });
  };

  const updateQty = (id: string, qty: number) => {
    if (qty <= 0) {
      setConfigLines(prev => prev.filter(l => l.equipment_id !== id));
    } else {
      setConfigLines(prev => prev.map(l => l.equipment_id === id ? { ...l, quantity: qty } : l));
    }
  };

  const removeItem = (id: string) => setConfigLines(prev => prev.filter(l => l.equipment_id !== id));

  // ── Compute ───────────────────────────────────────────────
  const compute = async () => {
    if (configLines.length === 0) return;
    setComputing(true);
    try {
      const body = {
        project_id: 'GEX-PLANT-001',
        molecule,
        location_jurisdiction: jurisdiction,
        equipment: configLines.map(l => ({
          equipment_id: l.equipment_id,
          quantity: l.quantity,
        })),
        power_price_eur_mwh: powerPrice,
        water_price_eur_m3: waterPrice,
        labour_count: labourCount,
        labour_cost_eur_year: labourCost,
        insurance_pct_capex: 0.005,
        contingency_pct: contingency / 100,
        target_market_price_eur_t: marketPrice,
        wacc_pct: wacc / 100,
        project_life_years: projectLife,
      };
      const r = await fetch('/api/v1/plant-builder/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      setResult(data);
      setActiveTab('capex');
    } catch (e) {
      console.error('Configure failed', e);
    } finally {
      setComputing(false);
    }
  };

  const loadBreizh = async () => {
    try {
      const r = await fetch('/api/v1/plant-builder/breizh-reference');
      const ref = await r.json();
      setMolecule(ref.molecule);
      setJurisdiction(ref.jurisdiction);
      const op = ref.operating_parameters;
      setPowerPrice(op.power_price_eur_mwh);
      setWaterPrice(op.water_price_eur_m3);
      setLabourCount(op.labour_count);
      setLabourCost(op.labour_cost_eur_year);
      setContingency(op.contingency_pct * 100);
      setWacc(op.wacc_pct * 100);
      setProjectLife(op.project_life_years);
      setMarketPrice(op.target_market_price_eur_t);
      // Hydrate config lines from catalog
      const catalogR = await fetch('/api/v1/plant-builder/catalog');
      const catalogData = await catalogR.json();
      const itemMap: Record<string, EquipmentItem> = {};
      (catalogData.items || []).forEach((i: EquipmentItem) => { itemMap[i.id] = i; });
      setConfigLines(
        ref.reference_configuration
          .filter((l: any) => itemMap[l.equipment_id])
          .map((l: any) => {
            const item = itemMap[l.equipment_id];
            return {
              equipment_id: item.id,
              name: item.name,
              category: item.category,
              quantity: l.quantity,
              unit_price_eur: item.unit_price_eur,
              installed_cost_eur: item.installed_cost_eur,
            };
          })
      );
    } catch (e) {
      console.error('Breizh load failed', e);
    }
  };

  // ── Filtered catalog items ────────────────────────────────
  const filteredCatalog = (items: EquipmentItem[]) => {
    if (!catalogSearch) return items;
    const q = catalogSearch.toLowerCase();
    return items.filter(i =>
      i.name.toLowerCase().includes(q) ||
      i.oem.toLowerCase().includes(q) ||
      i.description.toLowerCase().includes(q)
    );
  };

  const toggleCat = (cat: string) => {
    setExpandedCats(prev => {
      const next = new Set(prev);
      next.has(cat) ? next.delete(cat) : next.add(cat);
      return next;
    });
  };

  // ── Totals for config summary ─────────────────────────────
  const totalInstalled = configLines.reduce(
    (sum, l) => sum + l.installed_cost_eur * l.quantity, 0
  );

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col" style={{ color: 'var(--text-primary)', background: 'var(--bg-primary)' }}>
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-3">
          <Factory className="w-5 h-5 text-teal-400" />
          <div>
            <h1 className="text-base font-bold tracking-tight">Plant Builder</h1>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {TAB_DESCRIPTIONS.PLANT_BUILDER}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadBreizh}
            className="px-3 py-1.5 text-xs rounded border font-mono"
            style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
            title="Load Breizh SAF Complex reference (GEX-BRZ-SAF-001)"
          >
            Load Breizh Reference
          </button>
          <button
            onClick={compute}
            disabled={configLines.length === 0 || computing}
            className="px-4 py-1.5 text-xs font-bold rounded bg-teal-600 hover:bg-teal-500 text-white disabled:opacity-40 flex items-center gap-1.5"
          >
            {computing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <BarChart3 className="w-3.5 h-3.5" />}
            {computing ? 'Computing…' : 'Compute'}
          </button>
        </div>
      </div>

      {/* ── Three-Panel Layout ── */}
      <div className="flex-1 flex overflow-hidden min-h-0">

        {/* ── LEFT: Catalog Browser ── */}
        <div className="w-64 flex flex-col border-r overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div className="px-3 py-2 border-b" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center gap-1 mb-2">
              <Search className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--text-muted)' }} />
              <input
                type="text"
                placeholder="Search catalog…"
                value={catalogSearch}
                onChange={e => setCatalogSearch(e.target.value)}
                className="w-full text-xs bg-transparent outline-none"
                style={{ color: 'var(--text-primary)' }}
              />
            </div>
            <div className="flex items-center gap-1">
              <Filter className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--text-muted)' }} />
              <select
                value={catalogMolecule}
                onChange={e => { setCatalogMolecule(e.target.value); loadCatalog(e.target.value); }}
                className="w-full text-xs bg-transparent outline-none"
                style={{ color: 'var(--text-primary)' }}
              >
                <option value="">All molecules</option>
                {MOLECULES.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {catalogLoading ? (
              <div className="p-4 text-xs" style={{ color: 'var(--text-muted)' }}>Loading catalog…</div>
            ) : (
              CATEGORY_ORDER.map(cat => {
                const items = filteredCatalog(catalogByCategory[cat] || []);
                if (items.length === 0) return null;
                const expanded = expandedCats.has(cat);
                return (
                  <div key={cat}>
                    <button
                      onClick={() => toggleCat(cat)}
                      className="w-full flex items-center justify-between px-3 py-1.5 text-left hover:bg-white/5"
                      style={{ borderBottom: '1px solid var(--border)' }}
                    >
                      <span className="text-xs font-bold tracking-wide text-teal-400">{cat}</span>
                      <div className="flex items-center gap-1">
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{items.length}</span>
                        {expanded ? <ChevronDown className="w-3 h-3" style={{ color: 'var(--text-muted)' }} />
                          : <ChevronRight className="w-3 h-3" style={{ color: 'var(--text-muted)' }} />}
                      </div>
                    </button>
                    {expanded && items.map(item => (
                      <div
                        key={item.id}
                        className="px-3 py-1.5 border-b hover:bg-teal-900/20 cursor-pointer group"
                        style={{ borderColor: 'var(--border)' }}
                        onClick={() => addItem(item)}
                        title={item.description}
                      >
                        <div className="flex items-start justify-between gap-1">
                          <span className="text-[11px] leading-tight flex-1" style={{ color: 'var(--text-primary)' }}>
                            {item.name}
                          </span>
                          <Plus className="w-3 h-3 shrink-0 text-teal-400 opacity-0 group-hover:opacity-100 mt-0.5" />
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                            {fmtEur(item.unit_price_eur)}
                          </span>
                          <span className={`text-[10px] ${MATURITY_COLOR[item.technology_maturity] || ''}`}>
                            {item.technology_maturity === 'PROVEN' ? '✓' : item.technology_maturity === 'FIRST_OF_KIND' ? '~' : '⚠'}
                          </span>
                          {item.oem && (
                            <span className="text-[10px] truncate" style={{ color: 'var(--text-muted)' }}>
                              {item.oem.split('/')[0].trim()}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* ── CENTRE: Configuration ── */}
        <div className="flex-1 flex flex-col overflow-hidden border-r" style={{ borderColor: 'var(--border)', minWidth: 0 }}>
          {/* Config header */}
          <div className="flex items-center justify-between px-4 py-2 border-b" style={{ borderColor: 'var(--border)' }}>
            <span className="text-xs font-bold" style={{ color: 'var(--text-muted)' }}>
              CONFIGURATION · {configLines.length} items · {fmtEur(totalInstalled)} installed
            </span>
            {configLines.length > 0 && (
              <button
                onClick={() => setConfigLines([])}
                className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
              >
                <Trash2 className="w-3 h-3" /> Clear
              </button>
            )}
          </div>

          {/* Equipment list */}
          <div className="flex-1 overflow-y-auto">
            {configLines.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 gap-2">
                <Factory className="w-8 h-8" style={{ color: 'var(--text-muted)' }} />
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  Click equipment in the catalog to add it to your plant
                </p>
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="sticky top-0" style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)' }}>
                    <th className="text-left px-3 py-1.5 font-semibold" style={{ color: 'var(--text-muted)' }}>Equipment</th>
                    <th className="text-right px-2 py-1.5 font-semibold" style={{ color: 'var(--text-muted)' }}>Qty</th>
                    <th className="text-right px-2 py-1.5 font-semibold" style={{ color: 'var(--text-muted)' }}>Unit</th>
                    <th className="text-right px-3 py-1.5 font-semibold" style={{ color: 'var(--text-muted)' }}>Installed</th>
                    <th className="px-2 py-1.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {configLines.map(line => (
                    <tr
                      key={line.equipment_id}
                      className="border-b hover:bg-white/5"
                      style={{ borderColor: 'var(--border)' }}
                    >
                      <td className="px-3 py-1.5">
                        <div className="font-medium leading-tight">{line.name}</div>
                        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                          {line.category} · {line.equipment_id}
                        </div>
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <input
                          type="number"
                          min={1}
                          max={20}
                          value={line.quantity}
                          onChange={e => updateQty(line.equipment_id, parseInt(e.target.value) || 1)}
                          className="w-10 text-right font-mono bg-transparent border rounded px-1 outline-none focus:border-teal-500"
                          style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                        />
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono" style={{ color: 'var(--text-muted)' }}>
                        {fmtEur(line.installed_cost_eur)}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono font-semibold">
                        {fmtEur(line.installed_cost_eur * line.quantity)}
                      </td>
                      <td className="px-2 py-1.5">
                        <button onClick={() => removeItem(line.equipment_id)} className="text-red-400 hover:text-red-300">
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Operating parameters */}
          <div className="border-t p-3" style={{ borderColor: 'var(--border)' }}>
            <p className="text-[10px] font-bold uppercase tracking-wider mb-2" style={{ color: 'var(--text-muted)' }}>
              Operating Parameters
            </p>
            <div className="grid grid-cols-4 gap-2">
              {[
                { label: 'Molecule', type: 'select', value: molecule, setter: setMolecule, options: ['H2', 'SAF', 'NH3', 'E_METHANOL'] },
                { label: 'Jurisdiction', type: 'select', value: jurisdiction, setter: setJurisdiction, options: ['FR', 'DE', 'NL', 'ES', 'GB', 'US'] },
                { label: 'Power €/MWh', type: 'number', value: powerPrice, setter: setPowerPrice, step: 1 },
                { label: 'Market €/t', type: 'number', value: marketPrice, setter: setMarketPrice, step: 100 },
                { label: 'WACC %', type: 'number', value: wacc, setter: setWacc, step: 0.5 },
                { label: 'Life yrs', type: 'number', value: projectLife, setter: setProjectLife, step: 1 },
                { label: 'Contingency %', type: 'number', value: contingency, setter: setContingency, step: 1 },
                { label: 'Labour FTE', type: 'number', value: labourCount, setter: setLabourCount, step: 5 },
              ].map(({ label, type, value, setter, options, step }) => (
                <div key={label}>
                  <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{label}</label>
                  {type === 'select' ? (
                    <select
                      value={value as string}
                      onChange={e => (setter as (v: any) => void)(e.target.value)}
                      className="w-full text-xs font-mono bg-transparent border rounded px-1.5 py-0.5 outline-none"
                      style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                    >
                      {(options || []).map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input
                      type="number"
                      value={value as number}
                      step={step}
                      onChange={e => (setter as (v: any) => void)(parseFloat(e.target.value))}
                      className="w-full text-xs font-mono bg-transparent border rounded px-1.5 py-0.5 outline-none"
                      style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── RIGHT: Results Sidebar ── */}
        <div className="w-72 flex flex-col overflow-hidden">
          {!result ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center p-6">
                <BarChart3 className="w-10 h-10 mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  Configure equipment and click Compute to see CAPEX, OPEX, levelised cost, and certification readiness.
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* Tab selector */}
              <div className="flex border-b" style={{ borderColor: 'var(--border)' }}>
                {(['capex', 'opex', 'lcoe', 'cert'] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`flex-1 py-2 text-[10px] font-bold uppercase tracking-wider ${
                      activeTab === tab ? 'text-teal-400 border-b-2 border-teal-400' : ''
                    }`}
                    style={{ color: activeTab === tab ? undefined : 'var(--text-muted)' }}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {/* ── CAPEX Tab ── */}
                {activeTab === 'capex' && (
                  <>
                    <KpiRow label="Equipment" value={fmtEur(result.capex.total_equipment_eur)} />
                    <KpiRow label="Installed" value={fmtEur(result.capex.total_installed_eur)} />
                    <KpiRow label="Contingency" value={fmtEur(result.capex.contingency_eur)} muted />
                    <KpiRow label="Total CAPEX" value={fmtEur(result.capex.total_capex_eur)} highlight />

                    <Divider label="By Category" />
                    {Object.entries(result.capex.by_category)
                      .sort(([, a], [, b]) => b - a)
                      .map(([cat, val]) => (
                        <div key={cat} className="flex items-center gap-2">
                          <div className="flex-1">
                            <div className="flex justify-between text-[11px] mb-0.5">
                              <span style={{ color: 'var(--text-muted)' }}>{cat}</span>
                              <span className="font-mono">{fmtEur(val)}</span>
                            </div>
                            <div className="h-1 rounded-full" style={{ background: 'var(--border)' }}>
                              <div
                                className="h-1 rounded-full bg-teal-500"
                                style={{ width: `${Math.min(100, (val / result.capex.total_capex_eur) * 100)}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      ))}

                    <Divider label="By Layer" />
                    {Object.entries(result.capex.per_layer)
                      .sort()
                      .map(([layer, val]) => (
                        <KpiRow key={layer} label={`Layer ${layer}`} value={fmtEur(val)} />
                      ))}
                  </>
                )}

                {/* ── OPEX Tab ── */}
                {activeTab === 'opex' && (
                  <>
                    <KpiRow label="O&M" value={fmtEur(result.opex.annual_om_eur)} />
                    <KpiRow label="Power" value={fmtEur(result.opex.annual_power_eur)} />
                    <KpiRow label="Water" value={fmtEur(result.opex.annual_water_eur)} />
                    <KpiRow label="Labour" value={fmtEur(result.opex.annual_labour_eur)} />
                    <KpiRow label="Insurance" value={fmtEur(result.opex.annual_insurance_eur)} muted />
                    <KpiRow label="Total OPEX/yr" value={fmtEur(result.opex.total_annual_opex_eur)} highlight />

                    <Divider label="OPEX Waterfall" />
                    {[
                      { label: 'O&M', val: result.opex.annual_om_eur, color: 'bg-blue-500' },
                      { label: 'Power', val: result.opex.annual_power_eur, color: 'bg-amber-500' },
                      { label: 'Labour', val: result.opex.annual_labour_eur, color: 'bg-teal-500' },
                      { label: 'Other', val: result.opex.annual_water_eur + result.opex.annual_insurance_eur, color: 'bg-purple-500' },
                    ].map(({ label, val, color }) => (
                      <div key={label} className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-sm shrink-0 ${color}`} />
                        <div className="flex-1">
                          <div className="flex justify-between text-[11px] mb-0.5">
                            <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                            <span className="font-mono">{fmtEur(val)}</span>
                          </div>
                          <div className="h-1 rounded-full" style={{ background: 'var(--border)' }}>
                            <div
                              className={`h-1 rounded-full ${color}`}
                              style={{ width: `${Math.min(100, (val / result.opex.total_annual_opex_eur) * 100)}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </>
                )}

                {/* ── LCOE Tab ── */}
                {activeTab === 'lcoe' && (
                  <>
                    <KpiRow label="Annual Output" value={`${fmt(result.output.annual_output_tonnes)} t/yr`} />
                    <KpiRow label="Annualised CAPEX" value={fmtEur(result.output.annualised_capex_eur)} muted />
                    <KpiRow label="LCOH/LCOSAF" value={`€${result.output.levelised_cost_eur_t.toFixed(0)}/t`} highlight tooltip={HELP.LEVELISED_COST} />

                    <Divider label="Competitive Position" />
                    <KpiRow label="Market Reference" value={`€${result.output.market_price_eur_t.toFixed(0)}/t`} />

                    <div className="p-2 rounded" style={{ background: 'var(--bg-secondary)' }}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[11px] flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>Competitive Gap <InfoTooltip text={HELP.COMPETITIVE_GAP} /></span>
                        <span className={`text-sm font-bold font-mono ${result.output.competitive_gap_eur_t > 0 ? 'text-red-400' : 'text-green-400'}`}>
                          {result.output.competitive_gap_eur_t > 0 ? '+' : ''}{result.output.competitive_gap_eur_t.toFixed(0)} €/t
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        {result.output.competitive_gap_eur_t > 0 ? (
                          <TrendingUp className="w-3.5 h-3.5 text-red-400" />
                        ) : (
                          <TrendingDown className="w-3.5 h-3.5 text-green-400" />
                        )}
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                          {result.output.competitive_gap_eur_t > 0
                            ? 'Subsidy required for price parity'
                            : 'Competitive at market — no subsidy required'}
                        </span>
                      </div>
                    </div>

                    {result.output.subsidy_needed_eur_t > 0 && (
                      <>
                        <KpiRow
                          label="Subsidy Needed"
                          value={`€${result.output.subsidy_needed_eur_t.toFixed(0)}/t`}
                          warn
                        />
                        <KpiRow
                          label="Total Support/yr"
                          value={fmtEur(result.output.subsidy_needed_total_eur_yr)}
                          warn
                        />
                      </>
                    )}

                    {Object.keys(result.certification.premium_eur_t).length > 0 && (
                      <>
                        <Divider label="With Certification" />
                        <KpiRow
                          label="Net Price (best cert)"
                          value={`€${result.certification.effective_price_with_certs.toFixed(0)}/t`}
                          positive
                        />
                        {Object.entries(result.certification.premium_eur_t).map(([regime, prem]) => (
                          <KpiRow key={regime} label={`+ ${regime} premium`} value={`+€${prem}/t`} positive />
                        ))}
                      </>
                    )}
                  </>
                )}

                {/* ── CERT Tab ── */}
                {activeTab === 'cert' && (
                  <>
                    <Divider label="Readiness Score (0–100)" />
                    {Object.entries(result.certification.readiness)
                      .sort(([, a], [, b]) => b - a)
                      .map(([regime, score]) => {
                        const status = score >= 80 ? 'READY' : score >= 40 ? 'PARTIAL' : 'BLOCKED';
                        const barColor = score >= 80 ? 'bg-green-500' : score >= 40 ? 'bg-amber-500' : 'bg-red-500';
                        const prem = result.certification.premium_eur_t[regime] || 0;
                        return (
                          <div key={regime}>
                            <div className="flex items-center justify-between text-[11px] mb-1">
                              <span className={CERT_COLOR[regime] || 'text-gray-400'}>{regime}</span>
                              <div className="flex items-center gap-2">
                                {prem > 0 && (
                                  <span className="text-green-400 font-mono">+€{prem}/t</span>
                                )}
                                <span className={`font-bold font-mono ${score >= 80 ? 'text-green-400' : score >= 40 ? 'text-amber-400' : 'text-red-400'}`}>
                                  {score}%
                                </span>
                                <span className={`text-[10px] px-1 rounded ${score >= 80 ? 'bg-green-900/30 text-green-400' : score >= 40 ? 'bg-amber-900/30 text-amber-400' : 'bg-red-900/30 text-red-400'}`}>
                                  {status}
                                </span>
                              </div>
                            </div>
                            <div className="h-1.5 rounded-full mb-2" style={{ background: 'var(--border)' }}>
                              <div
                                className={`h-1.5 rounded-full ${barColor} transition-all`}
                                style={{ width: `${score}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}

                    {result.certification.blockers.length > 0 && (
                      <>
                        <Divider label="Blockers" />
                        {result.certification.blockers.map((b, i) => (
                          <div key={i} className="flex items-start gap-1.5 py-1">
                            <AlertTriangle className="w-3 h-3 text-red-400 shrink-0 mt-0.5" />
                            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{b}</span>
                          </div>
                        ))}
                      </>
                    )}

                    {Object.keys(result.certification.premium_eur_t).length > 0 && (
                      <>
                        <Divider label="Achievable Premiums" />
                        {Object.entries(result.certification.premium_eur_t).map(([regime, prem]) => (
                          <div key={regime} className="flex items-center gap-2 py-0.5">
                            <Award className="w-3 h-3 text-teal-400 shrink-0" />
                            <span className="flex-1 text-[11px]" style={{ color: 'var(--text-muted)' }}>{regime}</span>
                            <span className="text-[11px] font-mono font-bold text-teal-400">+€{prem}/t</span>
                          </div>
                        ))}
                        <KpiRow
                          label="Net Cost with Best Cert"
                          value={`€${result.certification.effective_price_with_certs.toFixed(0)}/t`}
                          positive
                        />
                      </>
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Sub-components ────────────────────────────────────────────

function KpiRow({
  label,
  value,
  highlight = false,
  muted = false,
  warn = false,
  positive = false,
  tooltip,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  muted?: boolean;
  warn?: boolean;
  positive?: boolean;
  tooltip?: string;
}) {
  return (
    <div className={`flex items-center justify-between py-1 ${highlight ? 'border-t border-b' : ''}`}
      style={highlight ? { borderColor: 'var(--border)' } : undefined}>
      <span
        className="text-[11px] flex items-center gap-1"
        style={{ color: highlight ? 'var(--text-primary)' : 'var(--text-muted)' }}
      >
        {label}{tooltip && <InfoTooltip text={tooltip} />}
      </span>
      <span
        className={`text-[11px] font-mono font-semibold ${
          highlight ? 'text-base font-bold' :
          warn ? 'text-red-400' :
          positive ? 'text-green-400' :
          muted ? '' : ''
        }`}
        style={(!warn && !positive && !highlight) ? { color: 'var(--text-primary)' } : undefined}
      >
        {value}
      </span>
    </div>
  );
}

function Divider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 my-1">
      <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
        {label}
      </span>
      <div className="flex-1 h-px" style={{ background: 'var(--border)' }} />
    </div>
  );
}

export default PlantBuilder;
