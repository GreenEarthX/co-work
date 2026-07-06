// Screen: Pre-FID annual spend wave (/finance/spend-wave)
/**
 * SpendWaveView — stacked horizontal bars showing pre-FID spend by year,
 * one color per capital layer. Displays equity-first-loss compliance badge.
 */
import { useState } from 'react'
import { Banknote, ChevronDown, ChevronUp, ShieldCheck } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { useSelectedProject } from '@/contexts/ProjectContext'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

type CapitalLayer =
  | 'EQUITY_SEED'
  | 'EQUITY_SPONSOR'
  | 'GRANT'
  | 'BRIDGE'
  | 'CONCESSIONAL'
  | 'SENIOR_DEBT'

interface LayerMeta {
  label: string
  color: string      // Tailwind bg class
  textColor: string  // Tailwind text class
}

interface YearSpend {
  year: number
  layers: Partial<Record<CapitalLayer, number>>  // layer → spend in €M
}

// ═══════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════

const LAYER_META: Record<CapitalLayer, LayerMeta> = {
  EQUITY_SEED:    { label: 'Equity Seed',    color: 'bg-teal-600',    textColor: 'text-teal-600'    },
  EQUITY_SPONSOR: { label: 'Equity Sponsor', color: 'bg-teal-400',    textColor: 'text-teal-400'    },
  GRANT:          { label: 'Grant',          color: 'bg-emerald-500', textColor: 'text-emerald-500' },
  BRIDGE:         { label: 'Bridge',         color: 'bg-amber-500',   textColor: 'text-amber-500'   },
  CONCESSIONAL:   { label: 'Concessional',   color: 'bg-violet-500',  textColor: 'text-violet-500'  },
  SENIOR_DEBT:    { label: 'Senior Debt',    color: 'bg-blue-700',    textColor: 'text-blue-700'    },
}

const LAYER_ORDER: CapitalLayer[] = [
  'EQUITY_SEED', 'EQUITY_SPONSOR', 'GRANT', 'BRIDGE', 'CONCESSIONAL', 'SENIOR_DEBT',
]

// ═══════════════════════════════════════════════════════════════
// MOCK DATA — ETFuels Pecos I pre-FID spend profile (€M)
// ═══════════════════════════════════════════════════════════════

const MOCK_SPEND: Record<string, YearSpend[]> = {
  proj_etf_pecos1: [
    { year: 2025, layers: { EQUITY_SEED: 4.2, GRANT: 1.8 } },
    { year: 2026, layers: { EQUITY_SEED: 6.1, EQUITY_SPONSOR: 3.5, GRANT: 5.2, BRIDGE: 2.0 } },
    { year: 2027, layers: { EQUITY_SPONSOR: 12.4, GRANT: 8.6, BRIDGE: 6.8, CONCESSIONAL: 4.0 } },
    { year: 2028, layers: { EQUITY_SPONSOR: 18.0, GRANT: 3.2, BRIDGE: 9.5, CONCESSIONAL: 14.2 } },
    { year: 2029, layers: { EQUITY_SPONSOR: 8.0, BRIDGE: 3.0, CONCESSIONAL: 7.8 } },
  ],
  default: [
    { year: 2025, layers: { EQUITY_SEED: 2.0, GRANT: 1.0 } },
    { year: 2026, layers: { EQUITY_SEED: 3.5, EQUITY_SPONSOR: 5.0, GRANT: 4.0, BRIDGE: 1.5 } },
    { year: 2027, layers: { EQUITY_SPONSOR: 10.0, GRANT: 6.0, BRIDGE: 4.5, CONCESSIONAL: 3.0 } },
    { year: 2028, layers: { EQUITY_SPONSOR: 14.0, GRANT: 2.0, BRIDGE: 7.0, CONCESSIONAL: 10.0 } },
    { year: 2029, layers: { EQUITY_SPONSOR: 6.0, BRIDGE: 2.0, CONCESSIONAL: 5.0 } },
  ],
}

// ═══════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════

function yearTotal(y: YearSpend): number {
  return Object.values(y.layers).reduce((s, v) => s + (v ?? 0), 0)
}

function hasSeniorDebtPreFID(data: YearSpend[]): boolean {
  return data.some(y => (y.layers.SENIOR_DEBT ?? 0) > 0)
}

function fmt(n: number): string {
  return n.toFixed(1)
}

// ═══════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════

export function SpendWaveView() {
  const { selectedProjectId } = useSelectedProject()
  const [detailOpen, setDetailOpen] = useState(false)

  const data = MOCK_SPEND[selectedProjectId] ?? MOCK_SPEND['default']
  const totalPreFID = data.reduce((s, y) => s + yearTotal(y), 0)
  const maxYear = Math.max(...data.map(yearTotal))
  const seniorPresent = hasSeniorDebtPreFID(data)
  const equityFirstLossCompliant = !seniorPresent

  // Aggregate totals per layer across all years
  const layerTotals: Partial<Record<CapitalLayer, number>> = {}
  for (const y of data) {
    for (const [layer, amt] of Object.entries(y.layers)) {
      layerTotals[layer as CapitalLayer] = (layerTotals[layer as CapitalLayer] ?? 0) + (amt ?? 0)
    }
  }

  return (
    <div className="space-y-4 max-w-5xl mx-auto pb-8">

      {/* Header */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="flex items-start justify-between px-6 py-4 bg-gradient-to-r from-gray-900 to-gray-800">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Banknote className="w-4 h-4 text-gray-400" />
              <span className="text-xs font-bold uppercase tracking-widest text-gray-400">Pre-FID Spend Wave</span>
            </div>
            <h1 className="text-2xl font-black text-white">Annual Capital Deployment</h1>
            <p className="text-sm text-gray-400 mt-0.5">Stacked by capital layer, pre-Financial Investment Decision</p>
          </div>
          <div className="flex items-center gap-2 mt-2">
            {equityFirstLossCompliant ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-600 text-white text-xs font-bold">
                <ShieldCheck className="w-3.5 h-3.5" />
                Equity First-Loss: COMPLIANT
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-bold">
                Equity First-Loss: NON-COMPLIANT
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
          <div className="text-2xl font-black tabular-nums text-gray-900">{fmt(totalPreFID)}M</div>
          <div className="text-xs font-semibold text-gray-500 mt-1">Total Pre-FID Spend</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
          <div className="text-2xl font-black tabular-nums text-gray-900">{data.length}</div>
          <div className="text-xs font-semibold text-gray-500 mt-1">Years</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
          <div className="text-2xl font-black tabular-nums text-gray-900">
            {Object.keys(layerTotals).length}
          </div>
          <div className="text-xs font-semibold text-gray-500 mt-1">Active Layers</div>
        </div>
      </div>

      {/* Stacked bar chart */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 rounded-t-xl flex items-center gap-2">
          <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">
            Annual Spend by Capital Layer
          </h3>
          <InfoTooltip text="Each horizontal bar represents one year's pre-FID spend, segmented by capital layer. Senior debt should NOT appear pre-FID in a compliant structure." />
        </div>
        <div className="px-4 py-4 space-y-3">
          {data.map(yearData => {
            const total = yearTotal(yearData)
            return (
              <div key={yearData.year} className="flex items-center gap-3">
                {/* Year label */}
                <div className="w-12 text-right text-xs font-bold tabular-nums text-gray-700 shrink-0">
                  {yearData.year}
                </div>
                {/* Bar */}
                <div className="flex-1 flex h-8 rounded-lg overflow-hidden bg-gray-100">
                  {LAYER_ORDER.map(layer => {
                    const amt = yearData.layers[layer]
                    if (!amt || amt <= 0) return null
                    const widthPct = (amt / maxYear) * 100
                    const meta = LAYER_META[layer]
                    return (
                      <div
                        key={layer}
                        className={`${meta.color} flex items-center justify-center text-white text-[10px] font-bold transition-all`}
                        style={{ width: `${widthPct}%`, minWidth: widthPct > 3 ? undefined : '12px' }}
                        title={`${meta.label}: ${fmt(amt)}M`}
                      >
                        {widthPct > 8 ? `${fmt(amt)}` : ''}
                      </div>
                    )
                  })}
                </div>
                {/* Total */}
                <div className="w-16 text-right text-xs font-semibold tabular-nums text-gray-600 shrink-0">
                  {fmt(total)}M
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 px-1">
        {LAYER_ORDER.filter(l => layerTotals[l]).map(layer => {
          const meta = LAYER_META[layer]
          return (
            <div key={layer} className="flex items-center gap-1.5">
              <div className={`w-3 h-3 rounded-sm ${meta.color}`} />
              <span className="text-xs text-gray-600">{meta.label}</span>
              <span className="text-xs font-semibold tabular-nums text-gray-800">{fmt(layerTotals[layer] ?? 0)}M</span>
            </div>
          )
        })}
      </div>

      {/* Detail breakdown (collapsible) */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <button
          type="button"
          onClick={() => setDetailOpen(v => !v)}
          className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
        >
          <span className="text-xs font-black uppercase tracking-widest text-gray-600">
            Detailed Year-by-Layer Breakdown
          </span>
          {detailOpen ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </button>
        {detailOpen && (
          <div className="px-4 py-3 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-1.5 pr-3 font-semibold text-gray-500 uppercase tracking-wide">Year</th>
                  {LAYER_ORDER.filter(l => layerTotals[l]).map(layer => (
                    <th key={layer} className="text-right py-1.5 px-2 font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">
                      {LAYER_META[layer].label}
                    </th>
                  ))}
                  <th className="text-right py-1.5 pl-3 font-semibold text-gray-500 uppercase tracking-wide">Total</th>
                </tr>
              </thead>
              <tbody>
                {data.map(yearData => (
                  <tr key={yearData.year} className="border-b border-gray-50 hover:bg-gray-50/60">
                    <td className="py-2 pr-3 font-bold text-gray-800 tabular-nums">{yearData.year}</td>
                    {LAYER_ORDER.filter(l => layerTotals[l]).map(layer => (
                      <td key={layer} className="py-2 px-2 text-right tabular-nums text-gray-700">
                        {yearData.layers[layer] ? `${fmt(yearData.layers[layer]!)}M` : '--'}
                      </td>
                    ))}
                    <td className="py-2 pl-3 text-right tabular-nums font-bold text-gray-900">
                      {fmt(yearTotal(yearData))}M
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-gray-200">
                  <td className="pt-2 pr-3 text-xs font-black text-gray-700 uppercase">Total</td>
                  {LAYER_ORDER.filter(l => layerTotals[l]).map(layer => (
                    <td key={layer} className="pt-2 px-2 text-right tabular-nums font-bold text-gray-900">
                      {fmt(layerTotals[layer] ?? 0)}M
                    </td>
                  ))}
                  <td className="pt-2 pl-3 text-right tabular-nums font-black text-gray-900">
                    {fmt(totalPreFID)}M
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>

      {/* Compliance note */}
      {!equityFirstLossCompliant && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-900 space-y-1">
          <p className="font-bold">Senior Debt Detected Pre-FID</p>
          <p>
            Senior debt tranches should not appear in the pre-FID capital structure.
            Equity and concessional capital must absorb first-loss risk before Financial Investment Decision.
          </p>
        </div>
      )}
    </div>
  )
}
