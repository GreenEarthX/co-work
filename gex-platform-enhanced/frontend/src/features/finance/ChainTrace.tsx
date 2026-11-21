/**
 * The calculation chain behind one published returns case (JML, 18 Nov 2026):
 * source versions, reconciliation checks and remaining assumptions, exactly as
 * stored in the version (hashed with it). Shown to the owner and to a reader
 * the owner shared the version with. Nothing here is recomputed.
 */
export interface ChainCheck {
  check: string; result: 'PASS' | 'FAIL' | 'REPORTED' | 'MISSING'; detail?: string
  difference?: number; difference_pct?: number | null; [k: string]: unknown
}
export interface Assumption { name: string; value: unknown; source: string; verification_status: string }
export interface Chain {
  source_versions: {
    cost_basis: { version_number: number; content_sha256: string; saved_by: string; saved_at: string; catalogue_sha256: string }
    tea_base_case: { claim_id: string; cost_basis_hash: string; engine?: string; engine_version?: string; result_status?: string
      run_by?: string; reviewed_by?: string; review_basis?: string; reviewed_at?: string; review_conditions?: string[] | null }
    financing_case: { version_number: number; content_sha256: string; saved_by: string }
  }
  checks: ChainCheck[]
  remaining_assumptions: Assumption[]
  reconciliation_vs_previous?: {
    previous_version_number: number; previous_content_sha256: string; previous_withdrawn: boolean
    previous_withdrawal_reason?: string | null
    previous_results: Record<string, number | null>
    inputs_changed: { item: string; previous: unknown; this: unknown }[]
  }
}

const tone: Record<string, string> = {
  PASS: 'bg-emerald-100 text-emerald-900', FAIL: 'bg-red-100 text-red-900',
  REPORTED: 'bg-amber-100 text-amber-900', MISSING: 'bg-slate-200 text-slate-800',
}

export function reviewLabel(basis?: string) {
  return basis === 'INDEPENDENT' ? 'Independent review' : basis === 'OWNER_INTERNAL'
    ? "Owner's internal review — not independent" : basis === 'TEST'
      ? 'TEST review by a test account — not a review' : 'not reviewed on the chain'
}

function fmtVal(v: unknown) {
  if (typeof v === 'number') return Math.abs(v) >= 1000 ? v.toLocaleString('en-GB', { maximumFractionDigits: 0 }) : String(v)
  return String(v)
}

export function ChainTrace({ chain }: { chain: Chain | null | undefined }) {
  if (!chain) {
    return (
      <div data-testid="chain-untraced" className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        Not traced to a saved calculation chain: this version was published from inputs typed on the Returns
        screen. Its TEA case and input versions are what the owner stated.
      </div>
    )
  }
  const s = chain.source_versions
  return (
    <div data-testid="chain-trace" className="space-y-3 rounded border border-[var(--border)] p-3 text-xs">
      <div className="font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Calculation chain — source versions</div>
      <ol className="grid gap-2 md:grid-cols-3">
        <li className="rounded bg-[var(--surface-hover,#f8fafc)] p-2">
          <div className="font-semibold">1 · Cost Basis v{s.cost_basis.version_number}</div>
          <div>saved by {s.cost_basis.saved_by} · {s.cost_basis.saved_at.slice(0, 16).replace('T', ' ')}</div>
          <div className="font-mono">sha256 {s.cost_basis.content_sha256.slice(0, 12)}</div>
        </li>
        <li className="rounded bg-[var(--surface-hover,#f8fafc)] p-2">
          <div className="font-semibold">2 · TEA {s.tea_base_case.claim_id}</div>
          <div>{s.tea_base_case.engine} {s.tea_base_case.engine_version ?? ''} · {s.tea_base_case.result_status}</div>
          <div>run by {s.tea_base_case.run_by} · reviewed by {s.tea_base_case.reviewed_by}</div>
          <div className="font-semibold">{reviewLabel(s.tea_base_case.review_basis)}</div>
          {!!s.tea_base_case.review_conditions?.length && <div>Conditions: {s.tea_base_case.review_conditions.join('; ')}</div>}
          <div className="font-mono">basis {s.tea_base_case.cost_basis_hash.slice(0, 12)}</div>
        </li>
        <li className="rounded bg-[var(--surface-hover,#f8fafc)] p-2">
          <div className="font-semibold">3 · Financing case v{s.financing_case.version_number}</div>
          <div>saved by {s.financing_case.saved_by}</div>
          <div className="font-mono">sha256 {s.financing_case.content_sha256.slice(0, 12)}</div>
        </li>
      </ol>
      <div>
        <div className="mb-1 font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Reconciliation checks</div>
        <table className="w-full">
          <tbody>
            {chain.checks.map(c => (
              <tr key={c.check} className="border-t border-[var(--border)] align-top">
                <td className="py-1 pr-2"><span className={`rounded px-1.5 py-0.5 font-semibold ${tone[c.result] ?? ''}`}>{c.result}</span></td>
                <td className="py-1 pr-2 font-medium">{c.check}</td>
                <td className="py-1">
                  {c.difference !== undefined && <span className="font-mono">Δ {fmtVal(c.difference)}{c.difference_pct != null ? ` (${(c.difference_pct * 100).toFixed(1)}%)` : ''} · </span>}
                  {c.detail}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {chain.reconciliation_vs_previous && (() => { const r = chain.reconciliation_vs_previous!; return (
        <div data-testid="vs-previous">
          <div className="mb-1 font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Against the version this one replaces (v{r.previous_version_number})</div>
          {r.previous_withdrawn && <div className="mb-1 text-red-800">v{r.previous_version_number} was withdrawn from reliance: {r.previous_withdrawal_reason}</div>}
          <table className="w-full"><tbody>
            {r.inputs_changed.map(row => (
              <tr key={row.item} className="border-t border-[var(--border)]">
                <td className="py-1 pr-2 font-mono">{row.item}</td><td className="pr-2 font-mono">{fmtVal(row.previous)}</td>
                <td className="pr-2">→</td><td className="font-mono">{fmtVal(row.this)}</td></tr>))}
            <tr className="border-t border-[var(--border)]"><td className="py-1 pr-2 font-mono">previous unlevered IRR</td>
              <td className="font-mono" colSpan={3}>{r.previous_results.unlevered_irr == null ? '—' : `${(Number(r.previous_results.unlevered_irr) * 100).toFixed(1)} %`}</td></tr>
          </tbody></table>
        </div>) })()}
      <div>
        <div className="mb-1 font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Remaining assumptions — not verified</div>
        <table className="w-full">
          <tbody>
            {chain.remaining_assumptions.map(a => (
              <tr key={a.name} className="border-t border-[var(--border)]">
                <td className="py-1 pr-2 font-mono">{a.name}</td>
                <td className="py-1 pr-2 font-mono">{fmtVal(a.value)}</td>
                <td className="py-1 pr-2">{a.source}</td>
                <td className="py-1">{a.verification_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
