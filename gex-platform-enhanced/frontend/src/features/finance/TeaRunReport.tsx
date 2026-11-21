// Screen part: the results of one TEA run, inside the Calculation chain (step 2).
/**
 * The run as stored when it was made (JML, 20 Nov 2026). Nothing here is recomputed:
 * every figure is read from the run's record, so the report reference prints the same
 * numbers next month. Dense tables, units on every figure, the basis of every factor,
 * no verdicts. Returns (NPV, IRR, payback) are not shown: the TEA is pre-tax and
 * unfinanced, and returns come from the financing case (step 4).
 *
 * Tabs: Overview · Capital · Operating costs · Cost by year · Sensitivity · Gabillon.
 * Graphs (TeaCharts.tsx): cost per kg on Overview, cost by year, Gabillon price vs required price.
 * Gabillon (PF engine) is used wherever it applies: the product's levelised Gabillon price
 * beside the required price, and the CEPCI forward's 90% band on capital. No Monte Carlo.
 *
 * House style (docs/GEX_UI_Reform_Project_Edit.md): one monospaced status line, no icons,
 * uppercase muted labels, numbers right-aligned in tabular figures with their unit, and a
 * standing on every figure (CALCULATED · STATED · DEFAULT · MODEL). The same sheets, in the
 * same order, are in the exported workbook (core/tea_report_workbook.py).
 */
import { Component, useState, type ReactNode } from 'react'
import { foot, label, nf, td, tdr, tdt, th, thr } from '@/lib/houseStyle'
import { CostByYearChart, CostPerKgBar, GabillonPriceChart } from './TeaCharts'

/* eslint-disable @typescript-eslint/no-explicit-any */
const TABS = ['Overview', 'Capital', 'Operating costs', 'Cost by year', 'Sensitivity', 'Gabillon'] as const
type Tab = typeof TABS[number]

const m = (n: number | null | undefined) => (n == null ? '—' : nf(n / 1e6, 2))
const pct = (n: number | null | undefined, d = 1) => (n == null ? '—' : `${nf(n * 100, d)}%`)

/** CALCULATED · STATED · DEFAULT · MODEL — what a figure rests on, in one word. */
function Standing({ s }: { s: string }) {
  return <span className="font-mono text-[10px] tracking-wide text-slate-600">{s}</span>
}

/** The run's verification state (UNVERIFIED · SUBMITTED · CONFIRMED · AUDITED), no icon. */
function StateChip({ b }: { b: any }) {
  const [word, tone] = b.state === 'verified' && b.review_basis === 'INDEPENDENT'
    ? ['CONFIRMED', 'border-teal-700 bg-teal-700 text-white']
    : b.state === 'superseded' ? ['SUPERSEDED', 'border-slate-400 text-slate-500']
    : ['SUBMITTED', 'border-amber-600 text-amber-800']
  const title = word === 'CONFIRMED' ? `Independently reviewed by ${b.reviewed_by_company ?? 'the appointed reviewer'}`
    : word === 'SUBMITTED' ? (b.state === 'verified' ? "Owner's internal review only; not independent" : 'Not yet reviewed') : 'A later run replaces it'
  return <span data-testid="state-chip" title={title} className={`rounded-sm border px-1 font-mono text-[10px] font-semibold ${tone}`}>{word}</span>
}

const OPEX_LABEL: Record<string, string> = {
  operating_labor: 'Operating labour', supervision: 'Supervision', direct_salary_overhead: 'Direct salary overhead',
  laboratory_charges: 'Laboratory', maintenance: 'Maintenance', taxes_insurance: 'Taxes and insurance',
  rent_of_land: 'Rent of land', environmental_charges: 'Environmental charges', operating_supplies: 'Operating supplies',
  general_plant_overhead: 'General plant overhead', interest_working_capital: 'Interest on working capital',
  patents_royalties: 'Patents and royalties', distribution_selling: 'Distribution and selling', rnd: 'Research and development',
}
// OpenPyTEA component key -> the name its default carries in defaults_used.
const DEFAULT_NAME: Record<string, string> = { interest_working_capital: 'working_capital_interest' }
const COMPONENT_STATED: Record<string, string> = {
  supervision: 'supervision_costs', maintenance: 'maintenance_costs', taxes_insurance: 'taxes_insurance_costs',
  rent_of_land: 'rent_of_land_costs', distribution_selling: 'distribution_selling_costs', rnd: 'RnD_costs',
}

export function InputsChip({ status }: { status: any }) {
  const [open, setOpen] = useState(false)
  if (!status) return null
  const text = status.unchanged === true ? 'Inputs unchanged since this run'
    : status.unchanged === false ? 'Inputs changed since this run' : 'Inputs not fully checked'
  const tone = status.unchanged === true ? 'border-emerald-700 text-emerald-900'
    : status.unchanged === false ? 'border-amber-700 text-amber-900' : 'border-slate-500 text-slate-700'
  // a status-line chip: square, monospaced, no fill
  return (
    <span className="inline-block">
      <button type="button" data-testid="inputs-chip" onClick={() => setOpen(!open)}
        className={`rounded-sm border px-1 py-0 font-mono text-[10px] font-semibold ${tone}`}>{text}</button>
      {open && <table className="mt-1 text-[11px]"><tbody>{status.checks.map((c: any) => (
        <tr key={c.check}><td className="pr-2 font-semibold">{c.result}</td><td className="pr-2">{c.check}</td><td>{c.detail}</td></tr>
      ))}</tbody></table>}
    </span>
  )
}

function Overview({ b, a, ccy }: { b: any; a: any; ccy: string }) {
  const bd = a.breakdown
  const pk = bd.per_kg
  const varTotal = Object.values(pk.variable as Record<string, number>).reduce((s, v) => s + v, 0)
  const fixTotal = Object.values(pk.fixed as Record<string, number>).reduce((s, v) => s + v, 0)
  const cap = bd.capital_costs
  const fullT = bd.production_kg_per_year_full / 1000
  const row = (f: string, v: string, u: string, st: string, basis: ReactNode, strong = false) => (
    <tr><td className={`${td} ${strong ? 'font-semibold' : ''}`}>{f}</td><td className={`${tdr} ${strong ? 'font-semibold' : ''}`}>{v}</td>
      <td className={td}>{u}</td><td className={td}><Standing s={st} /></td><td className={td}>{basis}</td></tr>)
  return (
    <div className="grid gap-x-6 gap-y-3 lg:grid-cols-[3fr_2fr]">
      <div>
        <div className={label}>Headline</div>
        <table className="w-full text-xs">
          <thead><tr><th className={th}>Figure</th><th className={thr}>Value</th><th className={th}>Unit</th><th className={th}>Standing</th><th className={th}>Basis</th></tr></thead>
          <tbody>
            {row('Required price (LCOP)', nf(b.lcop, 3), `${ccy}/kg`, 'CALCULATED', <>Discounted cost ÷ discounted output at {pct(bd.discount_rate)}; pre-tax, no debt</>, true)}
            {row('Fixed capital', m(cap.fixed_capital), `M ${ccy}`, 'CALCULATED', <>ISBL + OSBL + D&amp;E + contingency (Capital tab)</>)}
            {row('Working capital', m(cap.working_capital), `M ${ccy}`, 'CALCULATED', 'Not in fixed capital; returned in the last year')}
            {row('Operating cost, full output', m(bd.variable_opex.total + bd.fixed_opex.total), `M ${ccy}/yr`, 'CALCULATED', <>Variable {m(bd.variable_opex.total)} + fixed {m(bd.fixed_opex.total)}</>)}
            {row('Output, full rate', nf(fullT), 't/yr', 'STATED', <>Nameplate × utilisation {nf(bd.plant_utilization, 2)}</>)}
            {row('Operating life', String(bd.project_lifetime), 'years', 'STATED', 'Including construction')}
          </tbody>
        </table>
      </div>
      <div>
        <div className={label}>Cost per kg</div>
        <table className="w-full text-xs" data-testid="cost-per-kg">
          <thead><tr><th className={th}>Part</th><th className={thr}>{ccy}/kg</th><th className={thr}>Share</th></tr></thead>
          <tbody>
            <tr><td className={td}>Capital (fixed + working, discounted)</td><td className={tdr}>{nf(pk.capital, 3)}</td><td className={tdr}>{pct(pk.capital / b.lcop, 0)}</td></tr>
            {Object.entries(pk.variable as Record<string, number>).map(([k, v]) => (
              <tr key={k}><td className={`${td} pl-4`}>{k}</td><td className={tdr}>{nf(v, 3)}</td><td className={tdr}>{pct(v / b.lcop, 0)}</td></tr>))}
            <tr><td className={td}>Variable, total</td><td className={tdr}>{nf(varTotal, 3)}</td><td className={tdr}>{pct(varTotal / b.lcop, 0)}</td></tr>
            <tr><td className={td}>Fixed operating (Operating costs tab)</td><td className={tdr}>{nf(fixTotal, 3)}</td><td className={tdr}>{pct(fixTotal / b.lcop, 0)}</td></tr>
            {pk.by_product_credit !== 0 && <tr><td className={td}>By-product credit</td><td className={tdr}>{nf(pk.by_product_credit, 3)}</td><td className={tdr}>{pct(pk.by_product_credit / b.lcop, 0)}</td></tr>}
            <tr><td className={tdt}>LCOP</td><td className={`${tdt} text-right font-mono tabular-nums`}>{nf(pk.levelized_cost, 3)}</td><td className={`${tdt} text-right font-mono`}>100%</td></tr>
          </tbody>
        </table>
      </div>
      <div className="lg:col-span-2"><CostPerKgBar pk={pk} ccy={ccy} /></div>
      <p className={`${foot} lg:col-span-2`}>{bd.note} The parts add back to the LCOP (difference {nf(Math.abs(pk.check) < 5e-7 ? 0 : pk.check, 6)}).</p>
      <div className="lg:col-span-2"><MarketReference mr={a.market_reference} compact /></div>
    </div>
  )
}

/** The product's Gabillon price (PF engine) on the LCOP's own levelised basis. */
function MarketReference({ mr, compact = false }: { mr: any; compact?: boolean }) {
  if (!mr) return <p className={foot}>Gabillon market reference: not recorded for this run (runs before 21 Nov 2026).</p>
  if (!mr.applies) return <p className={foot} data-testid="market-reference-none">Gabillon market reference: {mr.reason}</p>
  const st = `MODEL · ${mr.calibration_status}`
  return (
    <div data-testid="market-reference">
      <div className={label}>Market reference · {mr.model} · {mr.molecule}</div>
      <table className="w-full text-xs">
        <thead><tr><th className={th}>Figure</th><th className={thr}>EUR/kg</th><th className={th}>Standing</th><th className={th}>Basis</th></tr></thead>
        <tbody>
          <tr><td className={`${td} font-semibold`}>Required price, this run</td><td className={`${tdr} font-semibold`}>{nf(mr.required_price, 3)}</td><td className={td}><Standing s="CALCULATED" /></td><td className={td}>LCOP</td></tr>
          <tr><td className={td}>Gabillon price, levelised (real)</td><td className={tdr}>{nf(mr.levelised_price, 3)}</td><td className={td}><Standing s={st} /></td><td className={td}>{mr.basis}</td></tr>
          <tr><td className={tdt}>Difference</td><td className={`${tdt} text-right font-mono tabular-nums`}>{nf(mr.difference, 3)}</td><td className={tdt}><Standing s="CALCULATED" /></td><td className={tdt}>Required price − Gabillon price</td></tr>
          {!compact && <>
            <tr><td className={td}>Gabillon spot</td><td className={tdr}>{nf(mr.spot, 3)}</td><td className={td}><Standing s={st} /></td><td className={td}>Calibrated {mr.last_calibrated}</td></tr>
            <tr><td className={td}>Long-run equilibrium (e^μ)</td><td className={tdr}>{nf(mr.long_term_equilibrium, 3)}</td><td className={td}><Standing s={st} /></td><td className={td}>Mean-reversion half-life {nf(mr.half_life_months, 1)} months</td></tr>
            <tr><td className={td}>Capex floor</td><td className={tdr}>{nf(mr.capex_floor, 3)}</td><td className={td}><Standing s={st} /></td><td className={td}>Gabillon parameter</td></tr>
          </>}
        </tbody>
      </table>
      <p className={foot}>{mr.standing} {mr.n_observations ?? 0} market observations.</p>
    </div>
  )
}

function factorStanding(defaults: any[], name: string): string {
  return defaults.some((x: any) => x.name === name) ? 'DEFAULT' : 'STATED'
}

function factorBasis(defaults: any[], name: string, stated?: string): string {
  const d = defaults.find((x: any) => x.name === name)
  if (d) return `${d.basis} (default ${d.value})`
  return stated ?? 'stated'
}

function Capital({ a, req, defaults, ccy }: { a: any; req: any; defaults: any[]; ccy: string }) {
  const bd = a.breakdown
  const cap = bd.capital_costs
  const quotes: any[] = req?.quote_plant?.equipment ?? []
  const q = req?.quote_plant ?? {}
  const sumDirect = bd.equipment.reduce((s: number, e: any) => s + e.direct_cost, 0)
  return (
    <div className="space-y-3">
      <table className="w-full text-xs">
        <thead><tr><th className={th}>Line</th><th className={th}>Source</th><th className={thr}>Price year</th>
          <th className={thr}>Quote, M {ccy}</th><th className={thr}>At cost base {bd.equipment[0]?.target_year}, M {ccy}</th></tr></thead>
        <tbody>
          {bd.equipment.map((e: any) => {
            const qq = quotes.find((x: any) => x.name === e.name)
            return <tr key={e.name}><td className={td}>{e.name}</td><td className={td}>{qq?.source ?? e.category}</td>
              <td className={tdr}>{e.cost_year}</td><td className={tdr}>{qq ? m(qq.installed_cost) : '—'}</td><td className={tdr}>{m(e.direct_cost)}</td></tr>
          })}
          <tr><td className={tdt} colSpan={4}>Lines, total</td><td className={`${tdt} text-right font-mono tabular-nums`}>{m(sumDirect)}</td></tr>
        </tbody>
      </table>
      <table className="w-full text-xs" data-testid="capital-build-up">
        <thead><tr><th className={th}>Build-up</th><th className={thr}>M {ccy}</th><th className={thr}>Factor</th><th className={th}>Standing</th><th className={th}>Basis</th></tr></thead>
        <tbody>
          <tr><td className={td}>ISBL</td><td className={tdr}>{m(cap.isbl)}</td><td className={tdr}>× {nf(bd.location_factor ?? 1, 2)}</td><td className={td}><Standing s="STATED" /></td>
            <td className={td}>Lines × location factor{q.loc_factor_basis ? ` (${q.loc_factor_basis})` : ''}{req?.quote_plant ? '; quotes taken as installed, no install factors' : ''}</td></tr>
          <tr><td className={td}>OSBL</td><td className={tdr}>{m(cap.osbl)}</td><td className={tdr}>{pct(cap.osbl / cap.isbl)} of ISBL</td><td className={td}><Standing s={factorStanding(defaults, 'openpytea.osbl_factor')} /></td>
            <td className={td}>{factorBasis(defaults, 'openpytea.osbl_factor', q.osbl_factor_basis ? `STATED: ${q.osbl_factor_basis}` : undefined)}</td></tr>
          <tr><td className={td}>Design and engineering</td><td className={tdr}>{m(cap.design_and_engineering)}</td>
            <td className={tdr}>{pct(cap.design_and_engineering / (cap.isbl + cap.osbl))} of ISBL+OSBL</td><td className={td}><Standing s={factorStanding(defaults, 'openpytea.de_factor')} /></td><td className={td}>{factorBasis(defaults, 'openpytea.de_factor')}</td></tr>
          <tr><td className={td}>Contingency</td><td className={tdr}>{m(cap.contingency)}</td>
            <td className={tdr}>{pct(cap.contingency / (cap.isbl + cap.osbl))} of ISBL+OSBL</td><td className={td}><Standing s={factorStanding(defaults, 'openpytea.contingency_factor')} /></td>
            <td className={td}>{factorBasis(defaults, 'openpytea.contingency_factor', req?.quote_plant ? 'STATED on the cost basis' : undefined)}</td></tr>
          <tr><td className={tdt}>Fixed capital</td><td className={`${tdt} text-right font-mono tabular-nums`}>{m(cap.fixed_capital)}</td><td className={tdt} /><td className={tdt}><Standing s="CALCULATED" /></td><td className={tdt} /></tr>
          <tr><td className={td}>Working capital</td><td className={tdr}>{m(cap.working_capital)}</td><td className={tdr}>{pct(cap.working_capital / cap.fixed_capital)} of fixed capital</td><td className={td}><Standing s={factorStanding(defaults, 'openpytea.working_capital')} /></td>
            <td className={td}>{factorBasis(defaults, 'openpytea.working_capital')}; not in fixed capital</td></tr>
        </tbody>
      </table>
      <p className={foot}>Fixed capital is the plant, not the funding requirement: interest during construction, financing fees,
        development and owner's costs and reserves are sized in the financing case (step 3).</p>
    </div>
  )
}

function Operating({ a, req, defaults, ccy }: { a: any; req: any; defaults: any[]; ccy: string }) {
  const bd = a.breakdown
  const streams: Record<string, any> = req?.quote_plant?.variable_opex ?? {}
  const q = req?.quote_plant ?? {}
  const stated: Record<string, number> = q.fixed_opex_components ?? {}
  const fixed = Object.entries(bd.fixed_opex.components as Record<string, number>)
  const rows = fixed.map(([k, v]) => {
    const dname = `openpytea.${DEFAULT_NAME[k] ?? k}`
    const d = defaults.find((x: any) => x.name === dname)
    const statedKey = COMPONENT_STATED[k] ?? k
    const basis = k === 'operating_labor' && q.operators_hired
      ? `STATED: ${nf(q.operators_hired)} operators × ${nf(q.operator_hourly_rate, 2)} ${ccy}/h`
      : stated[statedKey] != null ? 'STATED on the cost basis' : d ? `${d.value} ${d.basis} (OpenPyTEA default)` : '—'
    const standing = basis.startsWith('STATED') ? 'STATED' : d ? 'DEFAULT' : ''
    return { k, v, basis, standing, onCapital: !!d && /ISBL|OSBL/.test(d.basis) }
  })
  const onCapital = rows.filter(r => r.onCapital).reduce((s, r) => s + r.v, 0)
  return (
    <div className="space-y-3">
      <table className="w-full text-xs">
        <thead><tr><th className={th}>Variable input</th><th className={thr}>Per day</th><th className={th}>Unit</th>
          <th className={thr}>Price</th><th className={th}>Source</th><th className={thr}>M {ccy}/yr</th></tr></thead>
        <tbody>
          {Object.entries(bd.variable_opex.streams as Record<string, number>).map(([k, v]) => {
            const s = streams[k]
            return <tr key={k}><td className={td}>{k}</td><td className={tdr}>{s ? nf(s.consumption, 1) : '—'}</td><td className={td}>{s?.unit ?? '—'}</td>
              <td className={tdr}>{s ? nf(s.price, 2) : '—'}</td><td className={td}>{s?.source ?? '—'}</td><td className={tdr}>{m(v)}</td></tr>
          })}
          <tr><td className={tdt} colSpan={5}>Variable, at full output</td><td className={`${tdt} text-right font-mono tabular-nums`}>{m(bd.variable_opex.total)}</td></tr>
        </tbody>
      </table>
      <table className="w-full text-xs" data-testid="fixed-opex">
        <thead><tr><th className={th}>Fixed cost</th><th className={thr}>M {ccy}/yr</th><th className={th}>Standing</th><th className={th}>Basis</th></tr></thead>
        <tbody>
          {rows.map(r => <tr key={r.k}><td className={td}>{OPEX_LABEL[r.k] ?? r.k}{r.onCapital ? ' †' : ''}</td><td className={tdr}>{m(r.v)}</td><td className={td}><Standing s={r.standing} /></td><td className={td}>{r.basis}</td></tr>)}
          <tr><td className={tdt}>Fixed, per year in production</td><td className={`${tdt} text-right font-mono tabular-nums`}>{m(bd.fixed_opex.total)}</td><td className={tdt}><Standing s="CALCULATED" /></td><td className={tdt} /></tr>
        </tbody>
      </table>
      <p className={foot}>† Set as a percentage of capital: {m(onCapital)} M {ccy}/yr, {pct(onCapital / bd.fixed_opex.total, 0)} of fixed cost.
        These move with the capital estimate; state the real figure on the cost basis to replace a default.</p>
    </div>
  )
}

function CostByYear({ a, ccy }: { a: any; ccy: string }) {
  const bd = a.breakdown
  const ys: any[] = bd.years
  const sum = (f: (y: any) => number) => ys.reduce((s, y) => s + f(y), 0)
  const dCost = sum(y => y.cost * y.discount_factor)
  const dProd = sum(y => y.production_kg * y.discount_factor)
  return (
    <div className="space-y-2">
      <CostByYearChart years={ys} ccy={ccy} />
      <div className="max-h-96 overflow-auto">
        <table className="w-full text-xs" data-testid="cost-by-year">
          <thead className="sticky top-0 bg-[var(--surface)]"><tr><th className={thr}>Year</th><th className={thr}>Output, t</th><th className={thr}>Capital</th>
            <th className={thr}>Fixed</th><th className={thr}>Variable</th><th className={thr}>By-product</th><th className={thr}>Cost</th><th className={thr}>Discount factor</th></tr></thead>
          <tbody>
            {ys.map(y => <tr key={y.year}><td className={tdr}>{y.year}</td><td className={tdr}>{nf(y.production_kg / 1000)}</td><td className={tdr}>{m(y.capital)}</td>
              <td className={tdr}>{m(y.fixed_opex)}</td><td className={tdr}>{m(y.variable_opex)}</td><td className={tdr}>{m(-y.by_product_revenue)}</td>
              <td className={tdr}>{m(y.cost)}</td><td className={tdr}>{nf(y.discount_factor, 4)}</td></tr>)}
          </tbody>
        </table>
      </div>
      <p className={foot}>M {ccy}. Discounted cost {m(dCost)} M {ccy} ÷ discounted output {nf(dProd / 1000)} t = {nf(dCost / dProd, 3)} {ccy}/kg (the LCOP).
        Revenue, tax and debt are not here: they are the financing case's.</p>
    </div>
  )
}

function Sensitivity({ s, base }: { s: any; base: number }) {
  if (!s || s.error) return <p className="text-xs">Not recorded for this run{s?.error ? `: ${s.error}` : ''}.</p>
  const rows: any[] = s.tornado
  const span = Math.max(...rows.map(r => Math.max(Math.abs(r.low_lcop - base), Math.abs(r.high_lcop - base))), 1e-9)
  const bar = (v: number) => `${(Math.abs(v - base) / span) * 50}%`
  return (
    <div className="space-y-2">
      <table className="w-full text-xs" data-testid="tornado">
        <thead><tr><th className={th}>Lever</th><th className={thr}>Base</th><th className={thr}>Low – high</th><th className={th}>Unit</th>
          <th className={thr}>LCOP low</th><th className={thr}>LCOP high</th><th className={th} style={{ width: '18%' }}>Swing around {nf(base, 3)}</th><th className={th}>Range basis</th></tr></thead>
        <tbody>
          {rows.map(r => {
            const lo = Math.min(r.low_lcop, r.high_lcop), hi = Math.max(r.low_lcop, r.high_lcop)
            const big = Math.abs(r.base_input ?? 0) >= 1e5
            const v = (x: number) => (big ? m(x) : nf(x, 2))
            return <tr key={r.parameter}><td className={td}>{r.label ?? r.parameter}</td><td className={tdr}>{v(r.base_input)}</td>
              <td className={tdr}>{v(r.low_input)} – {v(r.high_input)}</td><td className={td}>{big ? `M ${r.unit}` : r.unit ?? ''}</td>
              <td className={tdr}>{nf(r.low_lcop, 3)}</td><td className={tdr}>{nf(r.high_lcop, 3)}</td>
              <td className={td}><div className="relative h-3 bg-[var(--surface-hover,#f1f5f9)]">
                <div className="absolute inset-y-0 bg-slate-500" style={{ right: '50%', width: bar(lo) }} />
                <div className="absolute inset-y-0 bg-slate-800" style={{ left: '50%', width: bar(hi) }} />
                <div className="absolute inset-y-0 left-1/2 w-px bg-black" /></div></td>
              <td className={td}>{r.range_basis}</td></tr>
          })}
        </tbody>
      </table>
      <p className={foot}>Each lever moved alone; every point is a full run of the same plant. Ranges are screening conventions until a governed range exists.
        The cost-index range is Gabillon's (Gabillon tab); electricity has no Gabillon range because power is not storable.</p>
    </div>
  )
}

function IndexBand({ ib, ccy, defaults = [] }: { ib: any; ccy: string; defaults?: any[] }) {
  if (!ib || ib.error) return <p className="text-xs">Not recorded for this run{ib?.error ? `: ${ib.error}` : ''}.</p>
  const flat = ib.applies && ib.index_low.fixed_capital === ib.base.fixed_capital && ib.index_high.fixed_capital === ib.base.fixed_capital
  const unstated = defaults.find((d: any) => d.name === 'quote.cost_year')
  return (
    <div className="space-y-2 text-xs">
      <p>{ib.method}. The index moves only the lines priced in an earlier year; a line priced in the cost-base year is not escalated.</p>
      {flat && <p data-testid="index-band-flat" className="font-semibold">No line is priced before the cost-base year, so the index moves nothing: the band is zero.
        {unstated ? ` ${unstated.basis}.` : ''} A line whose real price year is earlier must state it, or this band understates the uncertainty.</p>}
      {!ib.applies ? <p data-testid="index-band-none">{ib.reason}</p> : <>
        <table className="w-full" data-testid="index-band">
          <thead><tr><th className={thr}>Year</th><th className={thr}>CEPCI 5%</th><th className={thr}>Expected</th><th className={thr}>CEPCI 95%</th><th className={th}>Approved row</th></tr></thead>
          <tbody>{Object.entries(ib.years as Record<string, any>).map(([y, f]) => (
            <tr key={y}><td className={tdr}>{y}</td><td className={tdr}>{nf(f.low, 1)}</td><td className={tdr}>{nf(f.value, 1)}</td><td className={tdr}>{nf(f.high, 1)}</td><td className={`${td} font-mono`}>{String(f.ref_id).slice(0, 8)}</td></tr>))}</tbody>
        </table>
        <table className="w-full">
          <thead><tr><th className={th}>Case</th><th className={thr}>Fixed capital, M {ccy}</th><th className={thr}>LCOP, {ccy}/kg</th></tr></thead>
          <tbody>
            <tr><td className={td}>Index at 5%</td><td className={tdr}>{m(ib.index_low.fixed_capital)}</td><td className={tdr}>{nf(ib.index_low.lcop, 3)}</td></tr>
            <tr><td className={td}>Expected (this run)</td><td className={tdr}>{m(ib.base.fixed_capital)}</td><td className={tdr}>{nf(ib.base.lcop, 3)}</td></tr>
            <tr><td className={td}>Index at 95%</td><td className={tdr}>{m(ib.index_high.fixed_capital)}</td><td className={tdr}>{nf(ib.index_high.lcop, 3)}</td></tr>
          </tbody>
        </table>
      </>}
      <div><span className="font-semibold">Not in this band:</span><ul className="ml-4 list-disc">{(ib.not_covered ?? []).map((n: string) => <li key={n}>{n}</li>)}</ul></div>
    </div>
  )
}

/** Everything Gabillon prices for this run: the product's price and the cost index. */
function Gabillon({ a, ccy, defaults }: { a: any; ccy: string; defaults: any[] }) {
  const mr = a.market_reference
  return (
    <div className="space-y-4">
      <section>
        <MarketReference mr={mr} />
        {mr?.applies && <div className="mt-2"><GabillonPriceChart mr={mr} /></div>}
        {mr?.applies && <div className="mt-2 max-h-64 overflow-auto">
          <table className="w-full text-xs" data-testid="gabillon-deck">
            <thead className="sticky top-0 bg-[var(--surface)]"><tr><th className={thr}>Year</th><th className={thr}>Operating year</th>
              <th className={thr}>Nominal, EUR/kg</th><th className={thr}>Real, EUR/kg</th></tr></thead>
            <tbody>{mr.years.map((y: any) => <tr key={y.year}><td className={tdr}>{y.year}</td><td className={tdr}>{y.operating_year}</td>
              <td className={tdr}>{nf(y.price_nominal, 3)}</td><td className={tdr}>{nf(y.price_real, 3)}</td></tr>)}</tbody>
          </table>
        </div>}
      </section>
      <section>
        <div className={label}>Cost index · CEPCI forward (Gabillon P-forward, approved rows)</div>
        <IndexBand ib={a.index_band} ccy={ccy} defaults={defaults} />
      </section>
    </div>
  )
}

/** One run's results must never take the whole page down (the 3 Nov blank login lesson). */
class ReportBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null }
  static getDerivedStateFromError(e: Error) { return { error: e.message } }
  render() {
    return this.state.error
      ? <p className="text-xs text-red-800" data-testid="report-error">This run's results could not be shown: {this.state.error}</p>
      : this.props.children
  }
}

export function TeaRunReport({ b }: { b: any }) {
  return <ReportBoundary><TeaRunReportBody b={b} /></ReportBoundary>
}

function TeaRunReportBody({ b }: { b: any }) {
  const [tab, setTab] = useState<Tab>('Overview')
  const ti = b.tea_inputs ?? {}
  const a = ti.analysis
  if (!a?.breakdown) {
    return <p className="text-xs text-[var(--text-muted)]" data-testid="report-not-recorded">
      This run was made before results were recorded with each run (20 Nov 2026): only its headline figures exist. Run the TEA again from the same cost basis for the full results.</p>
  }
  const ccy = a.breakdown.currency
  const defaults: any[] = ti.defaults_used ?? []
  return (
    <div className="border border-slate-300 bg-[var(--surface)] p-3" data-testid="tea-run-report">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 border-b border-slate-400 pb-1 font-mono text-[11px] text-slate-700" data-testid="status-line">
        <span className="font-semibold text-slate-900" data-testid="report-ref">{b.report?.ref}</span>
        <span>·</span><span>{b.engine} {b.engine_version}</span>
        <span>·</span><span>{a.cost_basis?.cepci_basis ?? `cost year ${a.cost_basis?.cost_year}`}</span>
        <span>·</span><span>{ccy}</span>
        <span>·</span><span>run {String(b.created_at).slice(0, 16).replace('T', ' ')} by {b.run_by}</span>
        <span>·</span><StateChip b={b} />
        <span>·</span><InputsChip status={b.inputs_now} />
        <button type="button" className="ml-auto rounded-sm border border-slate-400 px-2 py-0 font-sans" onClick={() => window.print()}>Print</button>
      </div>
      <div role="tablist" className="flex gap-4 border-b border-slate-300 text-xs">
        {TABS.map(t => <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
          className={`py-1 ${tab === t ? '-mb-px border-b-2 border-slate-900 font-semibold text-slate-900' : 'text-slate-500'}`}>{t}</button>)}
      </div>
      <div className="pt-2">
        {tab === 'Overview' && <Overview b={b} a={a} ccy={ccy} />}
        {tab === 'Capital' && <Capital a={a} req={ti.request} defaults={defaults} ccy={ccy} />}
        {tab === 'Operating costs' && <Operating a={a} req={ti.request} defaults={defaults} ccy={ccy} />}
        {tab === 'Cost by year' && <CostByYear a={a} ccy={ccy} />}
        {tab === 'Sensitivity' && <Sensitivity s={a.sensitivity} base={b.lcop} />}
        {tab === 'Gabillon' && <Gabillon a={a} ccy={ccy} defaults={defaults} />}
      </div>
    </div>
  )
}
