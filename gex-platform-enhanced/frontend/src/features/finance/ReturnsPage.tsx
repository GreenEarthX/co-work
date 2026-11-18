// Screen: Returns & Hurdle Rate (/finance/returns)
/**
 * Investor returns for the selected project: unlevered and levered IRR, NPV,
 * ROI and ROE, each IRR tested against its hurdle rate.
 *
 *  - The numbers are the PF engine's (core/returns.py). This screen collects
 *    inputs and shows the answer with its governance stamp; it computes nothing.
 *  - FCI is the Fixed Capital Investment, the CAPEX committed at FID. DEVEX is
 *    all pre-FID spend and sits before year 0.
 *  - Two cases, always labelled. Without a construction schedule the answer is
 *    the screening case (FCI in full at year 0). With one it is the scheduled
 *    case, shown beside the screening case with both cash-flow timelines, so
 *    the effect of the construction period is visible.
 *  - Project returns (before financing) and equity returns (after financing)
 *    are shown apart.
 *  - Starting values are ILLUSTRATIVE (see returnsModel.ts). Nothing is shown
 *    as a result until the user asks for a calculation.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Calculator, Loader2 } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import {
  BOUNDARY_LABEL, fetchReturns, fmtEur, fmtPct, hurdleLine, illustrativeInputs, preFidByYear, useDevexBrief,
  type Boundary, type ReturnsAnswer, type ReturnsInputs, type ReturnsResult,
} from './returnsModel'
import { useProjectDataset } from './useProjectDataset'
import { PublishedCases } from './PublishedCases'
import { DebtMetricsPanel, DownsideTable, ProvenancePanel } from './ReturnsDetail'

type Unit = 'eur_m' | 'pct' | 'years' | 'x'
type ScalarKey = Exclude<keyof ReturnsInputs,
  'pre_fid_spend_eur' | 'construction_schedule_eur' | 'ramp_up' | 'cod_months_after_fid' | 'valuation_boundary' | 'scenario'>

const GROUPS: { title: string; fields: [ScalarKey, string, Unit][] }[] = [
  { title: 'Investment and operations', fields: [
    ['fci_eur', 'FCI: Fixed Capital Investment', 'eur_m'],
    ['operating_years', 'Operating years', 'years'],
    ['revenue_y1_eur', 'Revenue, year 1', 'eur_m'],
    ['revenue_growth', 'Revenue growth per year', 'pct'],
    ['opex_y1_eur', 'OPEX, year 1', 'eur_m'],
    ['opex_growth', 'OPEX growth per year', 'pct'],
    ['opex_variable_share', 'Variable share of OPEX', 'pct'],
    ['tax_rate', 'Tax rate', 'pct'],
    ['depreciation_years', 'Depreciation, straight line', 'years'],
    ['residual_value_eur', 'Residual value, final year', 'eur_m'],
  ] },
  { title: 'Financing at FID', fields: [
    ['debt_eur', 'Debt', 'eur_m'],
    ['interest_rate', 'Interest rate', 'pct'],
    ['debt_tenor_years', 'Debt tenor', 'years'],
    ['grant_eur', 'Grants', 'eur_m'],
  ] },
  { title: 'Hurdle rate build-up', fields: [
    ['risk_free_rate', 'Risk-free rate', 'pct'],
    ['equity_beta', 'Equity beta', 'x'],
    ['equity_risk_premium', 'Equity risk premium', 'pct'],
    ['country_risk_premium', 'Country premium', 'pct'],
    ['technology_risk_premium', 'Technology premium', 'pct'],
    ['project_risk_premium', 'Project premium over WACC', 'pct'],
  ] },
]
const UNIT_LABEL: Record<Unit, string> = { eur_m: '€M', pct: '%', years: 'yr', x: '×' }
const toDisplay = (v: number, u: Unit) => +(u === 'eur_m' ? v / 1e6 : u === 'pct' ? v * 100 : v).toFixed(4)
const fromDisplay = (v: number, u: Unit) => (u === 'eur_m' ? v * 1e6 : u === 'pct' ? v / 100 : v)

const card = 'rounded border border-[var(--border)] bg-[var(--surface)]'
const inputClass =
  'w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-right font-mono text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none'

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className={`${card} px-3 py-2.5`}>
      <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
      <div className="mt-0.5 font-mono text-lg text-[var(--text-primary)]">{value}</div>
      {sub && <div className="text-xs text-[var(--text-secondary)]">{sub}</div>}
    </div>
  )
}

/** "4.5, 9, 5" → [4.5, 9, 5]. Zeros are kept: an idle construction year is still a year. */
function parseList(text: string): number[] {
  return text.split(',').map(s => s.trim()).filter(s => s !== '').map(Number).filter(n => isFinite(n) && n >= 0)
}

// The recorded drawdown timeline: funding draws per tranche and quarter ("Q1-2029"), in €M.
interface DrawdownTranche { cells?: Record<string, { amount?: number }> }

function drawdownsByYear(tranches: DrawdownTranche[]): number[] {
  const byYear = new Map<number, number>()
  for (const t of tranches) {
    for (const [quarter, cell] of Object.entries(t.cells ?? {})) {
      const year = Number(quarter.match(/\d{4}/)?.[0])
      if (year) byYear.set(year, (byYear.get(year) ?? 0) + (cell.amount ?? 0))
    }
  }
  return [...byYear.keys()].sort((a, b) => a - b).map(y => +(byYear.get(y) ?? 0).toFixed(3))
}

const groupTitle = 'mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]'
const yrs = (n: number | null) => (n == null ? 'not reached' : `${n.toFixed(1)} yr`)
const change = (a: number | null, b: number | null, show: (d: number) => string) =>
  a == null || b == null ? '—' : show(a - b)
const signed = (text: string, d: number) => (d > 0 ? `+${text}` : text)

/** The screening case beside the scheduled case: figures, both timelines, and what differs. */
function CaseComparison({ r }: { r: ReturnsResult }) {
  const s = r.screening_case
  const d = r.difference
  if (!s || !d) return null

  const pp = (x: number) => signed(`${(x * 100).toFixed(1)} pp`, x)
  const eur = (x: number) => signed(fmtEur(x), x)
  const years = (x: number) => signed(`${x.toFixed(1)} yr`, x)
  const rows: [string, string, string, string][] = [
    ['Project IRR (unlevered)', fmtPct(s.unlevered_irr, 2), fmtPct(r.unlevered_irr, 2), change(r.unlevered_irr, s.unlevered_irr, pp)],
    ['Project NPV at the project hurdle', fmtEur(s.npv_unlevered_eur), fmtEur(r.npv_unlevered_eur), change(r.npv_unlevered_eur, s.npv_unlevered_eur, eur)],
    ['Project payback from FID', yrs(s.payback_years), yrs(r.payback_years), change(r.payback_years, s.payback_years, years)],
    ['Equity IRR (levered)', fmtPct(s.levered_irr, 2), fmtPct(r.levered_irr, 2), change(r.levered_irr, s.levered_irr, pp)],
    ['Equity NPV at the equity hurdle', fmtEur(s.npv_levered_eur), fmtEur(r.npv_levered_eur), change(r.npv_levered_eur, s.npv_levered_eur, eur)],
    ['Equity payback from FID', yrs(s.equity_payback_years), yrs(r.equity_payback_years), change(r.equity_payback_years, s.equity_payback_years, years)],
    ['Equity invested', fmtEur(s.equity_invested_eur), fmtEur(r.equity_invested_eur), change(r.equity_invested_eur, s.equity_invested_eur, eur)],
  ]

  const first = r.flows.first_period
  const periods = Array.from({ length: r.first_operating_period + 2 - first + 1 }, (_, i) => first + i)
  const at = (flows: number[], period: number) => fmtEur(flows[period - first])
  const lastPeriod = (flows: number[]) => first + flows.length - 1
  const totals = d.project_undiscounted_total_eur
  const sameTotal = Math.abs(totals.scheduled - totals.screening) <= 0.001 * Math.abs(totals.screening)
  const cell = 'px-2 py-1.5 text-right font-mono text-[var(--text-primary)]'
  const head = 'px-2 py-1.5 text-right text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]'

  return (
    <div className={`${card} space-y-4 p-4`}>
      <div>
        <div className={groupTitle}>Screening case against scheduled case</div>
        <table className="w-full text-sm">
          <thead><tr>
            <th className={`${head} text-left`}>Measure</th>
            <th className={head}>Screening (FCI at year 0)</th>
            <th className={head}>Scheduled</th>
            <th className={head}>Change</th>
          </tr></thead>
          <tbody>
            {rows.map(([label, a, b, c]) => (
              <tr key={label} className="border-t border-[var(--border)]">
                <td className="px-2 py-1.5 text-[var(--text-secondary)]">{label}</td>
                <td className={cell}>{a}</td><td className={cell}>{b}</td><td className={cell}>{c}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <div className={groupTitle}>Cash-flow timelines (year 0 = FID)</div>
        <table className="w-full text-sm">
          <thead><tr>
            <th className={`${head} text-left`}>Year</th>
            <th className={head}>Project, screening</th>
            <th className={head}>Project, scheduled</th>
            <th className={head}>Equity, screening</th>
            <th className={head}>Equity, scheduled</th>
          </tr></thead>
          <tbody>
            {periods.map(p => (
              <tr key={p} className="border-t border-[var(--border)]">
                <td className="px-2 py-1.5 font-mono text-[var(--text-secondary)]">{p}</td>
                <td className={cell}>{at(s.flows.unlevered, p)}</td>
                <td className={cell}>{at(r.flows.unlevered, p)}</td>
                <td className={cell}>{at(s.flows.levered, p)}</td>
                <td className={cell}>{at(r.flows.levered, p)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          Operating years continue to year {lastPeriod(s.flows.unlevered)} in the screening case and year{' '}
          {lastPeriod(r.flows.unlevered)} in the scheduled case.
        </p>
      </div>

      <div>
        <div className={groupTitle}>What differs</div>
        <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--text-secondary)]">
          <li>
            Operations start in year {d.first_operating_period.scheduled} after FID in the scheduled case and in year{' '}
            {d.first_operating_period.screening} in the screening case, which assumes no construction period.
          </li>
          <li>
            {sameTotal
              ? `Undiscounted project cash is the same in both cases (${fmtEur(totals.scheduled)}), so the change in project IRR and NPV is timing only: CAPEX is spread over the construction years and operating cash starts later.`
              : `Undiscounted project cash is ${fmtEur(totals.screening - totals.scheduled)} lower in the scheduled case.`}
          </li>
          {d.ramp_up_applied && (
            <li>Output ramps up over the first operating years. The screening case assumes full output from year 1.</li>
          )}
          {d.idc_eur > 0 && (
            <li>
              Equity pays {fmtEur(d.idc_eur)} of interest during construction, which the screening case leaves out.
              Project flows carry no financing, so this changes equity returns only.
            </li>
          )}
        </ul>
      </div>
    </div>
  )
}

export function ReturnsPage() {
  const { selectedProjectId } = useSelectedProject()
  const { projects } = useVisibleProjects()
  const project = projects.find(p => p.id === selectedProjectId)
  const validProject = !!selectedProjectId && selectedProjectId !== 'all'
  // Pre-FID spend comes through the DEVEX brief, so a viewer the brief is not
  // open to (a bank without a share) gets no DEVEX here either.
  const brief = useDevexBrief(validProject ? selectedProjectId : null)
  const preFid = preFidByYear(brief.data)
  const fci = project?.capex_eur ?? 0
  const spendKey = preFid.eur.join(',')
  const drawdownDs = useProjectDataset<DrawdownTranche[]>('drawdown_tranches', validProject ? selectedProjectId : null)
  const drawdowns = drawdownDs.data ? drawdownsByYear(drawdownDs.data) : []

  const [inputs, setInputs] = useState<ReturnsInputs>(() => illustrativeInputs(0, []))
  const [preFidText, setPreFidText] = useState('')
  const [scheduleText, setScheduleText] = useState('')
  const [rampText, setRampText] = useState('')
  const [codText, setCodText] = useState('')
  const [boundary, setBoundary] = useState<Boundary>('FULL_PROJECT')
  const [scenario, setScenario] = useState('BASE')
  const [answer, setAnswer] = useState<ReturnsAnswer | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A new project, or its recorded figures arriving, resets the form and clears
  // the previous answer: a result must never outlive the inputs it came from.
  useEffect(() => {
    setInputs(illustrativeInputs(fci, preFid.eur))
    setPreFidText(preFid.eur.map(v => +(v / 1e6).toFixed(3)).join(', '))
    setScheduleText('')
    setRampText('')
    setCodText('')
    setAnswer(null)
    setError(null)
  }, [selectedProjectId, fci, spendKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // The schedule must total the FCI and hold no pre-FID spend. The engine
  // enforces it; this says so before the user asks.
  const schedule = parseList(scheduleText)
  const scheduledEur = schedule.reduce((s, v) => s + v, 0) * 1e6
  const devexEur = parseList(preFidText).reduce((s, v) => s + v, 0) * 1e6
  const gapEur = scheduledEur - inputs.fci_eur
  const tolerance = 0.005 * inputs.fci_eur
  const reconcile = schedule.length === 0 ? null
    : Math.abs(gapEur) <= tolerance
      ? { ok: true, text: `Schedule ${fmtEur(scheduledEur)} over ${schedule.length} years reconciles to the FCI.` }
      : devexEur > 0 && Math.abs(gapEur - devexEur) <= tolerance
        ? { ok: false, text: `Schedule ${fmtEur(scheduledEur)} exceeds the FCI by the pre-FID spend (${fmtEur(devexEur)}). DEVEX is counted before year 0 and must not also be in the schedule.` }
        : { ok: false, text: `Schedule ${fmtEur(scheduledEur)} does not reconcile to the FCI ${fmtEur(inputs.fci_eur)} (difference ${fmtEur(gapEur)}). The engine will refuse it.` }

  const current = (): ReturnsInputs => ({
    ...inputs,
    pre_fid_spend_eur: parseList(preFidText).filter(n => n > 0).map(n => n * 1e6),
    construction_schedule_eur: schedule.map(n => n * 1e6),
    cod_months_after_fid: codText.trim() !== '' && isFinite(Number(codText)) ? Math.round(Number(codText)) : null,
    ramp_up: parseList(rampText).filter(n => n > 0).map(n => n / 100),
    valuation_boundary: boundary,
    scenario,
  })

  async function calculate() {
    setBusy(true)
    setError(null)
    try {
      setAnswer(await fetchReturns(current()))
    } catch (e) {
      setAnswer(null)
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!selectedProjectId || selectedProjectId === 'all') {
    return <div className="p-6 text-sm text-[var(--text-muted)]">Select a single project to see its returns.</div>
  }

  const r = answer?.returns
  const basisText = preFid.basis === 'SPEND_WAVE' ? 'from the recorded spend wave'
    : preFid.basis === 'PACKAGES' ? 'the pre-FID package total, placed in one year'
    : brief.denied ? 'not shared with you for this project'
    : 'none recorded'

  return (
    <div className="mx-auto max-w-6xl space-y-4 pb-8">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Returns and hurdle rate</h1>
        <p className="text-sm text-[var(--text-secondary)]">
          {project?.name ?? selectedProjectId} · unlevered and levered IRR, NPV, ROI and ROE, computed by the PF engine.
        </p>
      </div>

      <PublishedCases projectId={selectedProjectId} inputs={current} isOwnerFinance={!!brief.data?.can_manage_shares} />

      {!brief.loading && !brief.data?.can_manage_shares && (
        <div className="rounded border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs text-[var(--text-secondary)]">
          Calculator: your own inputs, not the owner's case. A figure below is not this project's published return.
          {brief.denied && ' Pre-FID spend has not been shared with you, so none is prefilled.'}
        </div>
      )}

      <div className="flex items-start gap-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          Starting values are ILLUSTRATIVE, not this project&apos;s agreed terms. Replace them before reading a result.
          {fci <= 0 && ' No CAPEX is recorded for this project: enter the FCI.'}
        </span>
      </div>

      <div className={`${card} space-y-4 p-4`}>
        {GROUPS.map(g => (
          <div key={g.title}>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{g.title}</div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
              {g.fields.map(([key, label, unit]) => (
                <label key={key} className="block text-xs text-[var(--text-secondary)]">
                  {label} <span className="text-[var(--text-muted)]">({UNIT_LABEL[unit]})</span>
                  <input
                    type="number" step="any" className={`${inputClass} mt-1`}
                    value={toDisplay(inputs[key], unit)}
                    onChange={e => setInputs(prev => ({ ...prev, [key]: fromDisplay(Number(e.target.value) || 0, unit) }))}
                  />
                </label>
              ))}
            </div>
          </div>
        ))}
        <label className="block text-xs text-[var(--text-secondary)]">
          DEVEX — pre-FID spend by year, oldest first (€M, comma separated) ·{' '}
          <span className="text-[var(--text-muted)]">{basisText}</span>
          <input type="text" className={`${inputClass} mt-1 text-left`} value={preFidText}
            onChange={e => setPreFidText(e.target.value)} placeholder="e.g. 4.5, 9, 5" />
        </label>
        <label className="block text-xs text-[var(--text-secondary)]">
          Construction schedule: CAPEX by year from FID, year 0 first (€M, comma separated). Leave empty for the
          screening case, with the FCI in full at year 0.
          <input type="text" className={`${inputClass} mt-1 text-left`} value={scheduleText}
            onChange={e => setScheduleText(e.target.value)} placeholder="e.g. 70, 93, 122" />
        </label>
        {reconcile && (
          <div className={`text-xs ${reconcile.ok ? 'text-[var(--text-secondary)]' : 'text-red-700 dark:text-red-300'}`}>
            {reconcile.text}
          </div>
        )}
        {drawdowns.length > 0 && (
          <div className="text-xs text-[var(--text-muted)]">
            <button type="button" onClick={() => setScheduleText(drawdowns.join(', '))}
              className="text-[var(--brand)] hover:underline">
              Fill from the recorded drawdown timeline
            </button>{' '}
            ({drawdowns.length} years). These are funding draws by calendar year, not CAPEX: check the total against
            the FCI and remove any pre-FID draws.
          </div>
        )}
        <label className="block text-xs text-[var(--text-secondary)]">
          COD: months after FID. Leave empty for the end of the last construction year. A value that is not a
          multiple of 12 gives a part first operating year and a part last one.
          <input type="number" min={0} step={1} className={`${inputClass} mt-1 text-left`} value={codText}
            onChange={e => setCodText(e.target.value)} placeholder="e.g. 24" />
        </label>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-xs text-[var(--text-secondary)]">
            Valuation boundary
            <select className={`${inputClass} mt-1 text-left`} value={boundary} onChange={e => setBoundary(e.target.value as Boundary)}>
              {(Object.keys(BOUNDARY_LABEL) as Boundary[]).map(b => <option key={b} value={b}>{BOUNDARY_LABEL[b]}</option>)}
            </select>
          </label>
          <label className="block text-xs text-[var(--text-secondary)]">
            Scenario
            <input type="text" className={`${inputClass} mt-1 text-left`} value={scenario} onChange={e => setScenario(e.target.value)} />
          </label>
        </div>
        <label className="block text-xs text-[var(--text-secondary)]">
          Ramp-up: output in the first operating years, % of full (comma separated). Empty means full output from the
          first operating year.
          <input type="text" className={`${inputClass} mt-1 text-left`} value={rampText}
            onChange={e => setRampText(e.target.value)} placeholder="e.g. 60, 85" />
        </label>
        <div className="flex items-center gap-3">
          <button type="button" onClick={calculate} disabled={busy}
            className="inline-flex items-center gap-2 rounded bg-[var(--brand)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
            Calculate
          </button>
          {brief.data && !brief.data.read_only && (
            <Link to="/finance/devex-brief" state={{ inputs: current() }}
              className="text-sm text-[var(--brand)] hover:underline">
              Open the DEVEX brief with these inputs
            </Link>
          )}
        </div>
        {error && <div className="text-sm text-red-700 dark:text-red-300">{error}</div>}
      </div>

      {r && (
        <>
          <div className={`${card} px-3 py-2 text-sm`}>
            <span className="font-semibold text-[var(--text-primary)]">
              {r.case === 'SCHEDULED' ? 'Scheduled case.' : 'Screening case.'}
            </span>{' '}
            <span className="text-[var(--text-secondary)]">{r.case_label}</span>
            {r.valuation_boundary && (
              <div className="text-xs text-[var(--text-secondary)]">
                {r.valuation_boundary_label ?? BOUNDARY_LABEL[r.valuation_boundary]} · scenario {r.scenario}
                {!brief.data?.can_manage_shares && ' · your own inputs, not the owner\'s case'}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="FCI" value={fmtEur(r.fci_eur)}
              sub={r.first_operating_period > 1
                ? `Fixed Capital Investment, over ${r.first_operating_period} construction years`
                : 'Fixed Capital Investment, in full at year 0'} />
            <Tile label="DEVEX (pre-FID)" value={brief.denied && r.devex_eur === 0 ? 'not shared' : fmtEur(r.devex_eur)}
              sub={brief.denied && r.devex_eur === 0 ? 'none entered; the owner has not shared its pre-FID spend' : 'paid before year 0, by equity'} />
            <Tile label="Total investment" value={fmtEur(r.total_investment_eur)} sub="FCI + DEVEX" />
            <Tile label="Equity invested" value={fmtEur(r.equity_invested_eur)}
              sub={r.idc_eur > 0
                ? `equity at FID + DEVEX + ${fmtEur(r.idc_eur)} interest during construction`
                : 'equity at FID + DEVEX'} />
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div className={`${card} p-3`}>
              <div className={groupTitle}>Project returns, before financing</div>
              <div className="grid grid-cols-2 gap-3">
                <Tile label="Unlevered IRR" value={fmtPct(r.unlevered_irr)} sub={hurdleLine(r.hurdle_test.unlevered)} />
                <Tile label="NPV" value={fmtEur(r.npv_unlevered_eur)} sub={`at project hurdle ${fmtPct(r.hurdle.project_hurdle)}`} />
                <Tile label="Payback" value={yrs(r.payback_years)} sub="from FID, undiscounted" />
                <Tile label="ROI" value={fmtPct(r.roi_avg_annual)} sub={`average per year · cumulative ${fmtPct(r.roi_cumulative, 0)}`} />
              </div>
            </div>
            <div className={`${card} p-3`}>
              <div className={groupTitle}>Equity returns, after financing</div>
              <div className="grid grid-cols-2 gap-3">
                <Tile label="Levered IRR" value={fmtPct(r.levered_irr)} sub={hurdleLine(r.hurdle_test.levered)} />
                <Tile label="NPV" value={fmtEur(r.npv_levered_eur)} sub={`at equity hurdle ${fmtPct(r.hurdle.equity_hurdle)}`} />
                <Tile label="Payback" value={yrs(r.equity_payback_years)} sub="from FID, undiscounted" />
                <Tile label="ROE" value={fmtPct(r.roe_avg_annual)} sub="average net income / equity" />
              </div>
            </div>
          </div>

          <CaseComparison r={r} />

          <DebtMetricsPanel dm={r.debt_metrics} />
          <DownsideTable d={r.downside} />
          <ProvenancePanel p={r.provenance} />

          <div className={`${card} p-4`}>
            <div className={groupTitle}>Timing assumptions</div>
            <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--text-secondary)]">
              {r.timing.assumptions.map(line => <li key={line}>{line}</li>)}
            </ul>
          </div>

          <div className={`${card} p-4`}>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Hurdle rate</div>
            <table className="w-full text-sm">
              <tbody className="font-mono text-[var(--text-primary)]">
                {([
                  [`Cost of equity (${r.hurdle.cost_of_equity_basis})`, fmtPct(r.hurdle.cost_of_equity, 2)],
                  ['Cost of debt, after tax', fmtPct(r.hurdle.cost_of_debt_after_tax, 2)],
                  ['Weights, equity / debt', `${fmtPct(r.hurdle.equity_weight, 0)} / ${fmtPct(r.hurdle.debt_weight, 0)}`],
                  ['WACC, after tax', fmtPct(r.hurdle.wacc_after_tax, 2)],
                  ['Project premium', fmtPct(r.hurdle.project_risk_premium, 2)],
                  ['Project hurdle (tests unlevered IRR)', fmtPct(r.hurdle.project_hurdle, 2)],
                  ['Equity hurdle (tests levered IRR)', fmtPct(r.hurdle.equity_hurdle, 2)],
                ] as [string, string][]).map(([k, v]) => (
                  <tr key={k} className="border-t border-[var(--border)] first:border-t-0">
                    <td className="py-1.5 font-sans text-[var(--text-secondary)]">{k}</td>
                    <td className="py-1.5 text-right">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <details className={`${card} p-4 text-sm`}>
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
              Definitions and limits of this calculation
            </summary>
            <dl className="mt-3 space-y-1.5">
              {Object.entries(r.definitions).map(([k, v]) => (
                <div key={k} className="grid grid-cols-[11rem_1fr] gap-2">
                  <dt className="font-mono text-xs text-[var(--text-muted)]">{k}</dt>
                  <dd className="text-[var(--text-secondary)]">{v}</dd>
                </div>
              ))}
            </dl>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-[var(--text-secondary)]">
              {r.limitations.map(l => <li key={l}>{l}</li>)}
            </ul>
          </details>

          {answer?.governance && (
            <div className="text-xs text-[var(--text-muted)]">
              Governance: {answer.governance.basis} · {answer.governance.note} · inputs {answer.governance.input_sha} ·{' '}
              {new Date(answer.governance.computed_at).toLocaleString('en-GB')}
            </div>
          )}
        </>
      )}
    </div>
  )
}
