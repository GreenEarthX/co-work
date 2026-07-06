// Screen: Debt Cashflow & Waterfall screen (/finance/debt-waterfall)
/**
 * Debt Cashflow & Waterfall (PF Waterfall View) — Move 2 of the project-finance
 * harvest (see menu-architecture-map.md §10).
 *
 * NARROW & HONEST by design:
 *  - Surfaces ONLY engine-computed, API-backed outputs (/finance-model/metrics
 *    + /waterfall): CFADS, DSCR, EBITDA, debt service, DSRA, cash waterfall.
 *  - Every metric carries a visible governance stamp. The math is engine-real;
 *    the inputs are ILLUSTRATIVE (demo project parameters, not executed deal
 *    terms). A debt metric without provenance is the Finance equivalent of the
 *    fabricated "P&L MTD" tile removed from Commercial.
 *  - LLCR / PLCR / Sources & Uses are shown as EXPLICIT GAPS (not computed in
 *    the engine), never as soft placeholders or invented numbers.
 *  - NOT called "Debt Sizing" — that name is reserved until LLCR/PLCR + S&U
 *    are computed in the engine.
 */

import { useEffect, useState } from 'react'
import { ShieldAlert, AlertTriangle, Info } from 'lucide-react'
import { useUserRole } from '@/contexts/UserRoleContext'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'

interface Governance {
  model: string
  basis: string
  note: string
  input_sha: string
  computed_at: string
}
interface Metrics {
  cfads?: number; ebitda?: number; debt_service?: number; dscr?: number
  dscr_value?: number; dscr_threshold?: number; cash_available_post_debt?: number
  covenant_compliance?: { dscr_compliant?: boolean; dscr_threshold?: number } | boolean
}
interface Distribution {
  priority: number; name: string; category: string
  required: number; allocated: number; shortfall: number; funding_percentage: number
}
interface Waterfall {
  distributions?: Distribution[]; dsra_required?: number; remaining_for_equity?: number
  total_annual_debt_service?: number; total_shortfall?: number; covenant_compliant?: boolean
}

const eur = (n?: number) =>
  n == null || !isFinite(n) ? '—'
  : Math.abs(n) >= 1e6 ? `€${(n / 1e6).toFixed(1)}M`
  : Math.abs(n) >= 1e3 ? `€${(n / 1e3).toFixed(0)}k` : `€${n.toFixed(0)}`

export function DebtCashflowWaterfall() {
  const { authSession } = useUserRole()
  const { selectedProjectId } = useSelectedProject()
  const { projects } = useVisibleProjects()
  const project = projects.find((p) => p.id === selectedProjectId) ?? projects[0]

  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [waterfall, setWaterfall] = useState<Waterfall | null>(null)
  const [gov, setGov] = useState<Governance | null>(null)
  const [state, setState] = useState<'loading' | 'ok' | 'error' | 'unauth'>('loading')
  const [errMsg, setErrMsg] = useState('')

  useEffect(() => {
    let cancelled = false
    async function run() {
      const token = authSession?.token
      if (!token) { setState('unauth'); return }
      setState('loading')

      // Illustrative inputs derived from the project's CAPEX. These are demo
      // parameters, NOT executed deal terms — the governance stamp says so.
      const capex = project?.capex_eur && project.capex_eur > 0 ? project.capex_eur : 560_000_000
      const revenue = capex * 0.22
      const opex = revenue * 0.40
      const maintenanceCapex = capex * 0.015      // annual maintenance, NOT upfront capex
      const debtService = capex * 0.70 * 0.095    // 70% gearing, ~9.5% annuity
      const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }

      try {
        // Operating-period metrics: pass annual MAINTENANCE capex, not the full
        // upfront capex (that is financed, not deducted from period CFADS).
        const mRes = await fetch('/api/v1/finance-model/metrics', {
          method: 'POST', headers,
          body: JSON.stringify({ revenue, opex, capex: maintenanceCapex, debt_service: debtService, period: 'FY1' }),
        })
        if (!mRes.ok) throw new Error(`metrics ${mRes.status}`)
        const mJson = await mRes.json()
        const m: Metrics = mJson.metrics ?? mJson
        if (cancelled) return
        setMetrics(m)
        if (mJson.governance) setGov(mJson.governance)

        const cfads = m.cfads ?? revenue - opex
        const wRes = await fetch('/api/v1/finance-model/waterfall', {
          method: 'POST', headers,
          body: JSON.stringify({ cfads, senior_debt_service: debtService, dsra_required: debtService * 0.5 }),
        })
        if (wRes.ok) {
          const wJson = await wRes.json()
          if (!cancelled) { setWaterfall(wJson.waterfall ?? wJson); if (wJson.governance && !gov) setGov(wJson.governance) }
        }
        if (!cancelled) setState('ok')
      } catch (e) {
        if (!cancelled) { setErrMsg(String((e as Error).message)); setState('error') }
      }
    }
    run()
    return () => { cancelled = true }
  }, [authSession?.token, project?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // DSRA: the engine returns it inside the waterfall distribution rows, not
  // always top-level — fall back to the DSRA reserve row.
  const dsra = waterfall?.dsra_required
    ?? waterfall?.distributions?.find((d) => /dsra/i.test(d.name))?.required
  const cov = typeof metrics?.covenant_compliance === 'object' ? metrics?.covenant_compliance : undefined
  const dscrVal = metrics?.dscr_value ?? metrics?.dscr
  const dscrThreshold = metrics?.dscr_threshold ?? cov?.dscr_threshold
  const covenantOk = cov ? cov.dscr_compliant
    : typeof metrics?.covenant_compliance === 'boolean' ? metrics?.covenant_compliance : undefined

  return (
    <div className="space-y-4 animate-fade-in">
      <div>
        <h1 className="text-xl font-black text-[var(--text-primary)]">Debt Cashflow &amp; Waterfall</h1>
        <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
          Engine-computed PF cashflow & distribution — {project?.name ?? 'no project'}
        </p>
      </div>

      {/* GOVERNANCE STAMP — visible, on the whole view */}
      <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800 px-4 py-2.5">
        <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <div className="text-xs text-amber-800 dark:text-amber-300">
          <span className="font-bold uppercase tracking-[0.08em]">
            {(gov?.basis ?? 'ILLUSTRATIVE_INPUTS').replace(/_/g, ' ')}
          </span>{' '}
          — {gov?.note ?? 'Engine-computed mechanics on illustrative inputs (demo parameters, not executed deal terms). Not for credit decisions.'}
          {gov && (
            <span className="block mt-0.5 font-mono text-[10px] text-amber-700/80">
              {gov.model} · input {gov.input_sha} · {new Date(gov.computed_at).toLocaleString('en-GB')}
            </span>
          )}
        </div>
      </div>

      {state === 'unauth' && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-6 text-sm text-[var(--text-muted)]">
          Sign in to compute the debt cashflow & waterfall.
        </div>
      )}
      {state === 'loading' && (
        <div className="flex items-center justify-center h-32">
          <div className="h-6 w-6 rounded-full border-2 border-[var(--brand)] border-t-transparent animate-spin" />
        </div>
      )}
      {state === 'error' && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-300 bg-rose-50 dark:bg-rose-950/20 dark:border-rose-800 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          PF engine (port 8001 via /finance-model) unavailable or errored: <span className="font-mono">{errMsg}</span>
        </div>
      )}

      {state === 'ok' && (
        <>
          {/* Engine-computed metric cards — each carries the illustrative chip */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            <MetricCard label="CFADS" value={eur(metrics?.cfads)} sub="cash avail. for debt service" />
            <MetricCard label="EBITDA" value={eur(metrics?.ebitda)} />
            <MetricCard label="Debt Service" value={eur(metrics?.debt_service ?? waterfall?.total_annual_debt_service)} sub="senior, annual" />
            <MetricCard
              label="DSCR"
              value={dscrVal != null ? `${dscrVal.toFixed(2)}x` : '—'}
              sub={dscrThreshold != null ? `threshold ${dscrThreshold.toFixed(2)}x` : undefined}
              tone={dscrVal != null ? (dscrVal >= (dscrThreshold ?? 1.2) ? 'good' : 'bad') : undefined}
            />
            <MetricCard label="DSRA required" value={eur(dsra)} sub="debt service reserve" />
            <MetricCard label="Cash post-debt" value={eur(metrics?.cash_available_post_debt ?? waterfall?.remaining_for_equity)} />
            <MetricCard label="Equity distribution" value={eur(waterfall?.remaining_for_equity)} sub="after waterfall" />
            <MetricCard
              label="Covenant"
              value={covenantOk == null ? '—' : covenantOk ? 'COMPLIANT' : 'BREACH'}
              tone={covenantOk == null ? undefined : covenantOk ? 'good' : 'bad'}
            />
          </div>

          {/* Cash waterfall distribution */}
          {waterfall?.distributions && waterfall.distributions.length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
              <div className="px-4 py-2.5 border-b border-[var(--border)] flex items-center gap-2">
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Cash waterfall</h3>
                <span className="gex-badge gex-badge-default">ILLUSTRATIVE</span>
              </div>
              <table className="w-full text-xs">
                <thead className="text-[var(--text-muted)] uppercase tracking-[0.08em] text-[10px]">
                  <tr className="border-b border-[var(--border)]">
                    <th className="text-left px-4 py-1.5">#</th>
                    <th className="text-left px-2 py-1.5">Priority</th>
                    <th className="text-right px-2 py-1.5">Required</th>
                    <th className="text-right px-2 py-1.5">Allocated</th>
                    <th className="text-right px-2 py-1.5">Shortfall</th>
                    <th className="text-right px-4 py-1.5">Funded</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {waterfall.distributions.map((d) => (
                    <tr key={`${d.priority}-${d.name}`} className="border-b border-[var(--border)] last:border-0">
                      <td className="px-4 py-1.5 text-[var(--text-muted)]">{d.priority}</td>
                      <td className="px-2 py-1.5 font-sans text-[var(--text-primary)]">{d.name}<span className="text-[var(--text-muted)]"> · {d.category}</span></td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{eur(d.required)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{eur(d.allocated)}</td>
                      <td className={`px-2 py-1.5 text-right tabular-nums ${d.shortfall > 0 ? 'text-rose-500' : 'text-[var(--text-muted)]'}`}>{eur(d.shortfall)}</td>
                      <td className="px-4 py-1.5 text-right tabular-nums">{d.funding_percentage != null ? `${Math.round(d.funding_percentage)}%` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* EXPLICIT GAPS — not computed in the engine. Honest, not placeholders. */}
          <div>
            <div className="flex items-center gap-1.5 mb-2 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              <Info className="w-3 h-3" /> Not computed — engine primitive absent (§10)
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {[
                ['LLCR', 'Loan-life coverage — only consumed as a lock-up threshold today, never computed.'],
                ['PLCR', 'Project-life coverage — no engine primitive yet.'],
                ['Sources & Uses', 'Close-grade S&U statement — no engine primitive yet.'],
              ].map(([t, d]) => (
                <div key={t} className="rounded-lg border border-dashed border-[var(--border)] bg-transparent px-3 py-3 opacity-70">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-[var(--text-muted)] line-through">{t}</span>
                    <span className="gex-badge gex-badge-default">NOT COMPUTED</span>
                  </div>
                  <p className="mt-1 text-[10px] text-[var(--text-muted)] leading-snug">{d} Do not infer a value.</p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function MetricCard({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-muted)]">{label}</span>
        <span className="text-[8px] font-mono text-amber-600/80" title="Illustrative inputs — see governance stamp">ILLUS</span>
      </div>
      <div className={`mt-0.5 font-mono text-base font-bold tabular-nums ${
        tone === 'good' ? 'text-emerald-600' : tone === 'bad' ? 'text-rose-500' : 'text-[var(--text-primary)]'
      }`}>{value}</div>
      {sub && <div className="text-[9px] text-[var(--text-muted)]">{sub}</div>}
    </div>
  )
}
