// Screen: Shared panels (no screen) — debt metrics, downside and provenance of one returns result
/**
 * Used by the Returns calculator and by a published case, so a case reads the
 * same wherever it is shown. Nothing here computes: figures are the engine's.
 * DSCR is judged only against an APPROVED policy value (lib/decisionPolicy).
 */
import { judge, outcomeTone, policyLine, MESSAGES, useDecisionTests } from '@/lib/decisionPolicy'
import { fmtEur, fmtPct, type DebtMetrics, type Downside, type Provenance } from './returnsModel'

const card = 'rounded border border-[var(--border)] bg-[var(--surface)]'
const title = 'mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]'
const x = (n: number | null | undefined) => (n == null || !isFinite(n) ? '—' : `${n.toFixed(2)}x`)
const bps = (n: number | null | undefined) => (n == null ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(0)} bps`)

export function DebtMetricsPanel({ dm }: { dm?: DebtMetrics }) {
  const tests = useDecisionTests().data?.tests
  if (!dm) return null
  const outcome = judge(dm.dscr_min, tests?.DSCR_COVENANT)
  return (
    <div className={`${card} p-4`}>
      <div className={title}>Debt metrics, deterministic (PF engine)</div>
      {dm.note ? <div className="text-sm text-[var(--text-secondary)]">{dm.note}</div> : (
        <div className="grid gap-3 md:grid-cols-3 text-sm">
          <div>
            <div className="text-xs text-[var(--text-muted)]">DSCR minimum</div>
            <div className={`font-mono text-lg ${outcomeTone(outcome)}`}>{x(dm.dscr_min)}</div>
            <div className="text-xs text-[var(--text-secondary)]">Covenant test: {policyLine(tests?.DSCR_COVENANT)}</div>
            {outcome !== 'PASS' && outcome !== 'FAIL' && <div className="text-xs text-[var(--text-muted)]">{MESSAGES[outcome]}</div>}
          </div>
          <div>
            <div className="text-xs text-[var(--text-muted)]">DSCR average</div>
            <div className="font-mono text-lg">{x(dm.dscr_avg)}</div>
          </div>
          <div>
            <div className="text-xs text-[var(--text-muted)]">LLCR at COD</div>
            <div className="font-mono text-lg">{x(dm.llcr)}</div>
            <div className="text-xs text-[var(--text-secondary)]">{dm.llcr_status ?? ''} · no decision test is wired to an LLCR floor</div>
          </div>
        </div>
      )}
    </div>
  )
}

export function DownsideTable({ d }: { d?: Downside }) {
  if (!d) return null
  return (
    <div className={`${card} p-4`}>
      <div className={title}>Downside sensitivities</div>
      <div className="mb-2 text-xs text-[var(--text-secondary)]">{d.basis} Shock set: {d.shock_set_status}.</div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-[var(--text-muted)]">
            <tr><th className="py-1">Shock</th><th>Unlevered IRR</th><th>Δ</th><th>Levered IRR</th><th>Δ</th>
              <th>Project NPV</th><th>DSCR min</th><th>LLCR</th></tr>
          </thead>
          <tbody className="font-mono">
            {d.rows.map(r => (
              <tr key={r.id} className="border-t border-[var(--border)]">
                <td className="py-1 font-sans">{r.label}</td>
                {r.error ? <td colSpan={7} className="font-sans text-red-700">{r.error}</td> : (<>
                  <td>{fmtPct(r.unlevered_irr)}</td><td>{bps(r.delta_unlevered_irr_bps)}</td>
                  <td>{fmtPct(r.levered_irr)}</td><td>{bps(r.delta_levered_irr_bps)}</td>
                  <td>{fmtEur(r.npv_unlevered_eur)}</td><td>{x(r.dscr_min)}</td><td>{x(r.llcr)}</td>
                </>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ProvenancePanel({ p }: { p?: Provenance }) {
  if (!p) return null
  const tea = p.tea_case as { status?: string; note?: string; claim_id?: string }
  return (
    <div className={`${card} p-4 text-sm`}>
      <div className={title}>Calculation provenance</div>
      <dl className="grid grid-cols-[12rem_1fr] gap-x-3 gap-y-1">
        <dt className="text-[var(--text-muted)]">Model</dt>
        <dd>{p.calculation.engine} · {p.calculation.module} · v{p.calculation.model_version}</dd>
        <dt className="text-[var(--text-muted)]">TEA case</dt>
        <dd>{tea?.claim_id ? `claim ${tea.claim_id}` : `${tea?.status ?? '—'}${tea?.note ? ` — ${tea.note}` : ''}`}</dd>
        <dt className="text-[var(--text-muted)]">Boundary · scenario</dt><dd>{p.valuation_boundary} · {p.scenario}</dd>
        <dt className="text-[var(--text-muted)]">Inputs sha256</dt><dd className="font-mono text-xs break-all">{p.inputs_sha256}</dd>
        <dt className="text-[var(--text-muted)]">Computed</dt><dd>{new Date(p.calculation.computed_at).toLocaleString('en-GB')}</dd>
      </dl>
      {p.assumptions.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-[var(--text-secondary)]">
          {p.assumptions.map((a, i) => <li key={i}>{a.name}: {String(a.value)} — {a.source ?? 'no source'} ({a.verification_status ?? 'UNVERIFIED'})</li>)}
        </ul>
      )}
      <table className="mt-3 w-full text-xs">
        <tbody>
          {p.validation_checks.map(c => (
            <tr key={c.check} className="border-t border-[var(--border)]">
              <td className="py-1">{c.check}</td>
              <td className={c.outcome === 'PASS' ? 'text-green-700' : c.outcome === 'WARN' ? 'text-amber-700' : 'text-[var(--text-muted)]'}>{c.outcome}</td>
              <td className="text-[var(--text-muted)]">{c.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 text-xs text-[var(--text-secondary)]">{p.validity}</div>
    </div>
  )
}
