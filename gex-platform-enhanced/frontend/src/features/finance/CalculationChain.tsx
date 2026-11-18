// Screen: Calculation chain (/finance/calculation-chain)
/**
 * Plant -> economics -> financing -> returns, for one project (JML, 18 Nov 2026).
 *
 *   1 Cost Basis   versions saved on the Cost Basis screen (configuration + server result)
 *   2 TEA          run FROM one saved version; reviewed by someone other than who ran it
 *   3 Financing    debt, rate, tenor, grant and their sources, on ONE reviewed TEA
 *   4 Returns      published from the chain: FCI, OPEX, life and debt come from 1-3;
 *                  the owner states only the remaining assumptions, each with a source
 *
 * The owner's screen. A bank never reads it: it reads the shared returns version,
 * which cites these records by id and hash (ChainTrace on the Returns screen).
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { getAuthHeader } from '@/lib/authToken'
import { ChainTrace, reviewLabel, type Chain, type ChainCheck } from './ChainTrace'

/* eslint-disable @typescript-eslint/no-explicit-any */
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...getAuthHeader() } })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const d = body?.detail
    throw new Error(typeof d === 'string' ? d : d?.message ?? `The server answered ${res.status}.`)
  }
  return body as T
}

const card = 'rounded border border-[var(--border)] bg-[var(--surface)] p-4 space-y-3'
const button = 'rounded border border-[var(--border)] px-2 py-1 text-xs hover:bg-[var(--surface-hover,#f8fafc)] disabled:opacity-40'
const eur = (n: number | null | undefined) => n == null ? '—' : `€${(n / 1e6).toLocaleString('en-GB', { maximumFractionDigits: 1 })}M`

function Checks({ checks }: { checks: ChainCheck[] }) {
  const tone: Record<string, string> = { PASS: 'text-emerald-800', FAIL: 'text-red-800', REPORTED: 'text-amber-800', MISSING: 'text-slate-600' }
  return (
    <ul className="space-y-0.5 text-xs">
      {checks.map(c => (
        <li key={c.check}><span className={`font-semibold ${tone[c.result]}`}>{c.result}</span> {c.check}
          {c.difference !== undefined && <span className="font-mono"> · Δ {eur(c.difference as number)}{c.difference_pct != null ? ` (${(c.difference_pct * 100).toFixed(0)}%)` : ''}</span>}
          {(c.result === 'FAIL' || (c.result === 'REPORTED' && c.difference === undefined)) && c.detail ? <span> · {c.detail}</span> : null}
        </li>
      ))}
    </ul>
  )
}

function Step({ n, name, why, children }: { n: number; name: string; why: string; children: React.ReactNode }) {
  return (
    <section className={card} data-testid={`chain-step-${n}`}>
      <div className="flex items-baseline gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-teal-700 text-xs font-bold text-white">{n}</span>
        <h2 className="text-sm font-semibold">{name}</h2>
      </div>
      <p className="text-xs text-[var(--text-secondary)]">{why}</p>
      {children}
    </section>
  )
}

function TermInput({ label, k, terms, setTerms, unit }: { label: string; k: string; unit: string
  terms: Record<string, { value: string; source: string }>; setTerms: (t: any) => void }) {
  const t = terms[k] ?? { value: '', source: '' }
  return (
    <div className="grid grid-cols-[10rem_8rem_1fr] items-center gap-2 text-xs">
      <span>{label} <span className="text-[var(--text-muted)]">({unit})</span></span>
      <input aria-label={`${label} value`} className="rounded border px-2 py-1 font-mono" value={t.value}
        onChange={e => setTerms({ ...terms, [k]: { ...t, value: e.target.value } })} />
      <input aria-label={`${label} source`} placeholder="source (required)" className="rounded border px-2 py-1" value={t.source}
        onChange={e => setTerms({ ...terms, [k]: { ...t, source: e.target.value } })} />
    </div>
  )
}

const toTerms = (t: Record<string, { value: string; source: string }>) =>
  Object.fromEntries(Object.entries(t).filter(([, v]) => v.value !== '').map(([k, v]) => [k, { value: Number(v.value), source: v.source }]))

type Feed = { stream: string; onSite: string; basis: string; price: string; unit: string; perDay: string; source: string }
const blankFeed = (stream = ''): Feed => ({ stream, onSite: '', basis: '', price: '', unit: 'kg/day', perDay: '', source: '' })

/** What the person running the TEA states, each with its basis. Everything else comes from the saved cost basis. */
function TeaRunForm({ cb, busy, onRun }: { cb: any; busy: boolean; onRun: (stated: any) => void }) {
  const [ptype, setPtype] = useState({ value: 'Fluids', basis: '' })
  const [loc, setLoc] = useState({ value: '', basis: '' })
  const [feeds, setFeeds] = useState<Feed[]>([blankFeed('hydrogen'), blankFeed('co2')])
  const set = (i: number, k: keyof Feed, v: string) => setFeeds(feeds.map((f, j) => (j === i ? { ...f, [k]: v } : f)))
  const stated = () => ({
    process_type: ptype, loc_factor: { value: Number(loc.value), basis: loc.basis },
    feedstocks: Object.fromEntries(feeds.filter(f => f.stream && (f.onSite || f.price)).map(f => [f.stream, {
      ...(f.onSite ? { on_site_t_per_year: Number(f.onSite), basis: f.basis } : {}),
      ...(f.price ? { price_eur_per_unit: Number(f.price), unit: f.unit, consumption_per_day: Number(f.perDay), source: f.source } : {}),
    }])),
  })
  const outputs = Object.entries(cb.outputs_by_molecule || {})
  return (
    <div className="space-y-2 rounded border border-[var(--border)] p-2 text-xs" data-testid="tea-run-form">
      <div className="font-semibold">Run the TEA from cost basis v{cb.version_number}: state what the cost basis does not</div>
      {outputs.length > 0 && <div className="text-[var(--text-muted)]">This plant makes, at its run time: {outputs.map(([m, t]) => `${m} ${Math.round(Number(t)).toLocaleString('en-GB')} t/yr`).join(' · ')}</div>}
      <div className="grid grid-cols-[9rem_8rem_1fr] items-center gap-2">
        <span>Process type</span>
        <select aria-label="Process type" className="rounded border px-1 py-1" value={ptype.value} onChange={e => setPtype({ ...ptype, value: e.target.value })}>
          {['Fluids', 'Solids', 'Mixed'].map(v => <option key={v}>{v}</option>)}</select>
        <input aria-label="Process type basis" placeholder="basis (required)" className="rounded border px-2 py-1" value={ptype.basis} onChange={e => setPtype({ ...ptype, basis: e.target.value })} />
        <span>Location factor</span>
        <input aria-label="Location factor" className="rounded border px-2 py-1 font-mono" value={loc.value} onChange={e => setLoc({ ...loc, value: e.target.value })} />
        <input aria-label="Location factor basis" placeholder="basis (required)" className="rounded border px-2 py-1" value={loc.basis} onChange={e => setLoc({ ...loc, basis: e.target.value })} />
      </div>
      <table className="w-full">
        <thead><tr className="text-left text-[var(--text-muted)]"><th>Feedstock</th><th>On site t/yr</th><th>Basis</th><th>Bought: price €/unit</th><th>unit</th><th>per day</th><th>Source</th></tr></thead>
        <tbody>{feeds.map((f, i) => (
          <tr key={i}>
            {(['stream', 'onSite', 'basis', 'price'] as const).map(k => <td key={k}><input aria-label={`${f.stream || 'feedstock'} ${k}`} className="w-full rounded border px-1 py-0.5" value={f[k]} onChange={e => set(i, k, e.target.value)} /></td>)}
            <td><select aria-label={`${f.stream} unit`} className="rounded border px-1 py-0.5" value={f.unit} onChange={e => set(i, 'unit', e.target.value)}>{['kg/day', 't/day', 'Nm3/day', 'MWh/day', 'm3/day'].map(u => <option key={u}>{u}</option>)}</select></td>
            {(['perDay', 'source'] as const).map(k => <td key={k}><input aria-label={`${f.stream || 'feedstock'} ${k}`} className="w-full rounded border px-1 py-0.5" value={f[k]} onChange={e => set(i, k, e.target.value)} /></td>)}
          </tr>))}</tbody>
      </table>
      <div className="flex gap-2">
        <button type="button" className={button} onClick={() => setFeeds([...feeds, blankFeed()])}>Add feedstock</button>
        <button type="button" className={button} disabled={busy} onClick={() => onRun(stated())}>Run TEA from v{cb.version_number}</button>
      </div>
      <div className="text-[var(--text-muted)]">A feedstock neither made on site nor bought fails the balance check; a shortfall fails too. Every OpenPyTEA default that still applies is listed with the run.</div>
    </div>
  )
}

export function CalculationChain() {
  const { selectedProjectId: pid } = useSelectedProject()
  const qc = useQueryClient()
  const chain = useQuery({ queryKey: ['calc-chain', pid], enabled: !!pid && pid !== 'all', retry: false,
    queryFn: () => api<any>(`/api/v1/calculation-chain/${encodeURIComponent(pid!)}`) })
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [conditions, setConditions] = useState('')
  const [finTerms, setFinTerms] = useState<Record<string, { value: string; source: string }>>({})
  const [stated, setStated] = useState<Record<string, { value: string; source: string }>>({})
  const [caseName, setCaseName] = useState('Base case (chain)')
  const [formFor, setFormFor] = useState<string | null>(null)

  if (!pid || pid === 'all') return <div className="p-6 text-sm">Select a project.</div>
  if (chain.isLoading) return <div className="p-6 text-sm">Loading the calculation chain…</div>
  if (chain.error) return <div className="p-6 text-sm text-red-700">{(chain.error as Error).message}</div>
  const d = chain.data
  const refresh = () => qc.invalidateQueries({ queryKey: ['calc-chain', pid] })
  async function act(fn: () => Promise<unknown>, ok: string): Promise<boolean> {
    setBusy(true); setMsg(null)
    try { await fn(); setMsg(ok); refresh(); return true }
    catch (e) { setMsg((e as Error).message); return false } finally { setBusy(false) }
  }
  const P = encodeURIComponent(pid)
  const isReviewer = !!d.viewer?.is_appointed_reviewer
  const reviewed = d.tea_base_cases.filter((b: any) => b.state === 'verified' && b.review_basis === 'INDEPENDENT')
  const latestFin = d.financing_cases[d.financing_cases.length - 1]

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <header>
        <h1 className="text-lg font-semibold">Calculation chain — {d.project_name}</h1>
        <p className="text-sm text-[var(--text-secondary)]">
          Plant → economics → financing → returns. Each step cites the exact saved version before it. No figure is
          carried by hand: what the chain sets cannot be typed, and what it does not set is listed as an assumption
          with its source.
        </p>
        {msg && <div role="status" className="mt-2 rounded bg-[var(--surface-hover,#f8fafc)] px-3 py-2 text-xs">{msg}</div>}
      </header>

      <Step n={1} name="Cost Basis — saved versions" why="Why: the plant and its cost build-up, fixed. The server recomputes the result from the saved configuration and hashes both, so a later change cannot alter what was saved.">
        {d.cost_bases.length === 0 && <div className="text-xs">No cost basis saved. <Link className="text-[var(--brand)] underline" to="/finance-plant-builder">Open Cost Basis</Link> and save one.</div>}
        <table className="w-full text-xs">
          <tbody>
            {d.cost_bases.map((c: any) => (
              <tr key={c.version_id} className="border-t border-[var(--border)]">
                <td className="py-1 font-semibold">v{c.version_number}</td>
                <td>{c.molecule} · {c.result.product.nameplate_t_per_year.toLocaleString('en-GB')} t/yr nameplate · run time {c.configuration.capacity_factor}</td>
                <td>CAPEX {eur(c.result.capex.total_capex_eur)} · OPEX {eur(c.result.opex.total_annual_opex_eur)}/yr</td>
                <td>saved by {c.saved_by}</td>
                <td className="font-mono">{c.content_sha256.slice(0, 10)}</td>
                <td>{!isReviewer && <button type="button" className={button} disabled={busy}
                  onClick={() => setFormFor(formFor === c.version_id ? null : c.version_id)}>Run TEA from v{c.version_number}…</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {formFor && <TeaRunForm cb={d.cost_bases.find((c: any) => c.version_id === formFor)} busy={busy}
          onRun={stated => act(() => api(`/api/v1/cost-basis/${P}/${formFor}/tea`, { method: 'POST', body: JSON.stringify({ stated }) }),
            'TEA run from the saved cost basis. It awaits review.').then(done => { if (done) setFormFor(null) })} />}
        {!isReviewer && <Link className="text-xs text-[var(--brand)] underline" to="/finance-plant-builder">Open Cost Basis to save a new version</Link>}
      </Step>

      <Step n={2} name="TEA — run from a saved cost basis, then reviewed" why="Why: the TEA prices the same plant with published cost correlations (OpenPyTEA). Its inputs are derived from the saved cost basis, not typed. A run counts only once someone other than who ran it has reviewed it, and the review says whether it was independent.">
        {d.tea_base_cases.length === 0 && <div className="text-xs">No TEA run from a saved cost basis yet.</div>}
        {d.tea_base_cases.map((b: any) => {
          const cb = d.cost_bases.find((c: any) => c.version_id === b.cost_basis_version_id)
          return (
            <div key={b.claim_id} className="border-t border-[var(--border)] pt-2 text-xs space-y-1" data-testid="tea-run">
              <div className="font-semibold">{b.claim_id} · from cost basis v{cb?.version_number} · <span className="uppercase">{b.state}</span>
                {b.review_basis && <> · {reviewLabel(b.review_basis)} by {b.approved_by}</>}</div>
              <div>{b.engine} {b.engine_version} · {b.result_status} · CAPEX {eur(b.capex_eur)} · OPEX {eur(b.opex_eur_per_year)}/yr · LCOP {b.lcop?.toFixed?.(2)} · run by {b.run_by}</div>
              {!!b.review_conditions?.length && <div>Review conditions: {b.review_conditions.join(' · ')}</div>}
              <Checks checks={b.reconciliation} />
              {(b.tea_inputs?.defaults_used || []).length > 0 && (
                <details><summary className="cursor-pointer">OpenPyTEA defaults this run still used ({b.tea_inputs.defaults_used.length}) — listed as assumptions</summary>
                  <ul className="ml-4 list-disc">{b.tea_inputs.defaults_used.map((x: any) => <li key={x.name}><span className="font-mono">{x.name}</span> = {JSON.stringify(x.value)} — {x.basis}</li>)}</ul>
                </details>)}
              {!b.tea_inputs && <div className="text-red-800">This run priced a generic train, not this cost basis's lines: it cannot feed a financing case.</div>}
              {b.can_review && (
                <div className="flex flex-wrap items-end gap-2 pt-1">
                  <div className="w-full font-semibold">Your review will be recorded as: {reviewLabel(b.review_would_be)}{b.failed_checks?.length ? ` · plain approval refused while ${b.failed_checks.length} check(s) fail` : ''}</div>
                  <label>Conditions (one per line)<textarea aria-label="Review conditions" className="ml-1 block w-96 rounded border px-2 py-1" rows={2} value={conditions} onChange={e => setConditions(e.target.value)} /></label>
                  {(['approve', 'approve_with_conditions', 'reject'] as const).map(o => (
                    <button key={o} type="button" className={button} disabled={busy}
                      onClick={() => act(() => api(`/api/v1/tea-review/${P}/${b.claim_id}`, { method: 'POST',
                        body: JSON.stringify({ outcome: o, conditions: conditions.split('\n').filter(Boolean) }) }), `Review recorded: ${o}.`)}>
                      {o.replace(/_/g, ' ')}</button>
                  ))}
                </div>
              )}
              {b.state === 'submitted' && !b.can_review && <div className="text-[var(--text-muted)]">Awaiting review by an appointed independent engineer or the owner's finance or executive function (not {b.run_by}).</div>}
            </div>
          )
        })}
      </Step>

      {isReviewer ? <div className="rounded border border-[var(--border)] p-3 text-xs text-[var(--text-secondary)]">{d.withheld}</div> : <>
      <Step n={3} name="Financing case — on one independently reviewed TEA" why="Why: debt is sized against the reviewed CAPEX, not a typed figure. Only a TEA reviewed by an appointed independent engineer qualifies. Each term states its source; none is verified until a lender confirms it.">
        {d.financing_cases.map((f: any) => (
          <div key={f.version_id} className="text-xs border-t border-[var(--border)] pt-1">
            <span className="font-semibold">v{f.version_number}</span> on {f.tea_claim_id} · FCI {eur(f.fci_eur)} · debt {eur(f.debt_eur)} ({(f.debt_eur / f.fci_eur * 100).toFixed(0)}%) · {(f.interest_rate * 100).toFixed(2)}% · {f.debt_tenor_years} yr · grant {eur(f.grant_eur)} · <span className="font-mono">{f.content_sha256.slice(0, 10)}</span>
          </div>
        ))}
        {reviewed.length === 0 ? <div className="text-xs text-[var(--text-muted)]">Needs a TEA base case reviewed by an appointed independent engineer first.</div> : (
          <div className="space-y-1">
            <div className="text-xs">On <span className="font-semibold">{reviewed[reviewed.length - 1].claim_id}</span> (CAPEX {eur(reviewed[reviewed.length - 1].capex_eur)})</div>
            <TermInput label="Debt" k="debt_eur" unit="EUR" terms={finTerms} setTerms={setFinTerms} />
            <TermInput label="Interest rate" k="interest_rate" unit="fraction" terms={finTerms} setTerms={setFinTerms} />
            <TermInput label="Debt tenor" k="debt_tenor_years" unit="years" terms={finTerms} setTerms={setFinTerms} />
            <TermInput label="Grant" k="grant_eur" unit="EUR" terms={finTerms} setTerms={setFinTerms} />
            <button type="button" className={button} disabled={busy} onClick={() => act(() => api(`/api/v1/calculation-chain/${P}/financing`, {
              method: 'POST', body: JSON.stringify({ tea_claim_id: reviewed[reviewed.length - 1].claim_id, terms: toTerms(finTerms) }) }), 'Financing case saved.')}>Save financing case</button>
          </div>
        )}
      </Step>

      <Step n={4} name="Returns — published from the chain" why="Why: FCI and OPEX are the reviewed TEA's, operating life the cost basis's, debt the financing case's. You state only what the chain does not hold, each with a source; the version stores the source versions, every check and every remaining assumption.">
        {!latestFin ? <div className="text-xs text-[var(--text-muted)]">Needs a financing case first.</div> : (
          <div className="space-y-1">
            <div className="text-xs">From financing case v{latestFin.version_number}</div>
            <label className="text-xs">Case name<input className="ml-1 rounded border px-2 py-1" value={caseName} onChange={e => setCaseName(e.target.value)} /></label>
            <TermInput label="Product price" k="product_price_eur_t" unit="EUR/t" terms={stated} setTerms={setStated} />
            <TermInput label="Tax rate" k="tax_rate" unit="fraction" terms={stated} setTerms={setStated} />
            <TermInput label="Depreciation" k="depreciation_years" unit="years" terms={stated} setTerms={setStated} />
            <TermInput label="Cost of equity" k="cost_of_equity" unit="fraction" terms={stated} setTerms={setStated} />
            <button type="button" className={button} disabled={busy} onClick={() => act(() => api(`/api/v1/calculation-chain/${P}/returns`, {
              method: 'POST', body: JSON.stringify({ financing_version_id: latestFin.version_id, case_name: caseName, stated: toTerms(stated) }) }),
              'Published. Share it from the Returns screen.')}>Publish returns version from the chain</button>
          </div>
        )}
        {d.returns_versions.map((v: any) => (
          <div key={v.version_id} className="border-t border-[var(--border)] pt-2 space-y-2">
            <div className="text-xs font-semibold">{v.case_name} v{v.version_number} · published {new Date(v.published_at).toLocaleString('en-GB')} · sha256 {v.content_sha256.slice(0, 12)}
              {' '}· <Link className="text-[var(--brand)] underline" to="/finance/returns">open and share on Returns</Link></div>
            {v.withdrawal && <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">WITHDRAWN from reliance {v.withdrawal.withdrawn_at?.slice(0, 16)} by {v.withdrawal.withdrawn_by}: {v.withdrawal.reason}</div>}
            <ChainTrace chain={v.chain as Chain} />
          </div>
        ))}
      </Step>
      </>}
    </div>
  )
}
