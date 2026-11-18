// Screen: Returns — published cases panel (/finance/returns)
/**
 * Published returns cases (handoff v4, tasks 8 and 10).
 *
 *  Owner's finance: publish the calculator's inputs as a named case version
 *  (either boundary), list every version with its identity and "needs review",
 *  export one, and share a version (or "this case and later versions") per user,
 *  read-only. Audience templates are shown as suggestions; they grant nothing.
 *
 *  A shared reader: sees the versions shared with them, with the owner's figures
 *  as published. Without a share: told so; the calculator below is their own.
 *
 *  Every figure is the stored version's. Nothing here recomputes a case.
 */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getAuthHeader } from '@/lib/authToken'
import { BOUNDARY_LABEL, fmtEur, fmtPct, type Boundary, type ReturnsInputs } from './returnsModel'
import { DebtMetricsPanel, DownsideTable, ProvenancePanel } from './ReturnsDetail'
import { ChainTrace, type Chain } from './ChainTrace'

interface Identity {
  version_id: string; case_id: string; case_name: string; version_number: number; scenario: string
  valuation_boundary: Boundary; model_version: string; rules_version: string | null
  evidence_fingerprint: string | null; tea_case: Record<string, unknown> | null; published_at: string
  content_sha256: string; supersedes_version_id: string | null
  input_versions?: { chain?: Chain } | null; chain_traced?: boolean
}
interface Review { needs_review: boolean; changes: { what: string; detail?: string }[] }
interface Withdrawal { reason: string; withdrawn_by: string; withdrawn_at: string; shares_revoked: { user_id: string }[] }
interface CaseRow extends Identity { review: Review; withdrawal?: Withdrawal | null }
interface CaseList { project_id: string; disclosure: 'OWNER' | 'RETURNS_SHARE'; versions: CaseRow[] }
interface ShareRow { entitlement_id: string; user_id: string; version_id: string | null; case_id: string | null;
  status: string; expires_at: string | null }

class HttpError extends Error { constructor(msg: string, public status: number) { super(msg) } }

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...getAuthHeader() } })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const d = body?.detail
    throw new HttpError(typeof d === 'string' ? d : d?.message ?? `The server answered ${res.status}.`, res.status)
  }
  return body as T
}

const card = 'rounded border border-[var(--border)] bg-[var(--surface)]'
const title = 'mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]'
const button = 'rounded border border-[var(--border)] px-2 py-1 text-xs hover:bg-[var(--surface-hover,#f8fafc)]'

function IdentityLine({ v }: { v: Identity }) {
  return (
    <div className="text-xs text-[var(--text-secondary)]">
      {v.case_name} v{v.version_number} · {v.scenario} · {BOUNDARY_LABEL[v.valuation_boundary]} · model {v.model_version}
      {' '}· rules {v.rules_version ?? '—'} · evidence {v.evidence_fingerprint?.slice(0, 10) ?? '—'}
      {' '}· TEA {String((v.tea_case as { claim_id?: string })?.claim_id ?? 'not named')}
      {' '}· published {new Date(v.published_at).toLocaleString('en-GB')} · sha256 {v.content_sha256.slice(0, 12)}
      {' '}· {v.chain_traced ? <span className="font-semibold text-emerald-800">traced to a saved chain</span>
        : <span className="text-amber-800">inputs typed, not traced</span>}
    </div>
  )
}

function VersionView({ projectId, versionId }: { projectId: string; versionId: string }) {
  const q = useQuery({
    queryKey: ['returns-case', projectId, versionId],
    queryFn: () => api<any>(`/api/v1/returns-cases/${encodeURIComponent(projectId)}/versions/${versionId}`), // eslint-disable-line @typescript-eslint/no-explicit-any
    retry: false,
  })
  if (q.isLoading) return <div className="text-sm text-[var(--text-muted)]">Loading the case…</div>
  if (q.error) return <div className="text-sm text-red-700">{(q.error as Error).message}</div>
  const v = q.data
  const r = v.results
  return (
    <div className="space-y-3">
      <IdentityLine v={v.identity} />
      {v.withdrawal && <Withdrawn w={v.withdrawal} />}
      {v.review?.needs_review && (
        <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Needs review — {v.review.changes.map((c: { what: string; detail?: string }) => c.detail ?? c.what).join('; ')}.
          The figures below are this version's, unchanged.
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 text-sm">
        <div><div className="text-xs text-[var(--text-muted)]">Unlevered IRR</div><div className="font-mono text-lg">{fmtPct(r.unlevered_irr)}</div></div>
        <div><div className="text-xs text-[var(--text-muted)]">Project NPV</div><div className="font-mono text-lg">{fmtEur(r.npv_unlevered_eur)}</div></div>
        <div><div className="text-xs text-[var(--text-muted)]">Levered IRR</div><div className="font-mono text-lg">{fmtPct(r.levered_irr)}</div></div>
        <div><div className="text-xs text-[var(--text-muted)]">Equity NPV</div><div className="font-mono text-lg">{fmtEur(r.npv_levered_eur)}</div></div>
        <div><div className="text-xs text-[var(--text-muted)]">FCI</div><div className="font-mono">{fmtEur(r.fci_eur)}</div></div>
        <div><div className="text-xs text-[var(--text-muted)]">DEVEX (pre-FID)</div>
          <div className="font-mono">{'devex_eur' in r ? fmtEur(r.devex_eur) : 'not shared'}</div></div>
        <div><div className="text-xs text-[var(--text-muted)]">Payback</div><div className="font-mono">{r.payback_years == null ? '—' : `${r.payback_years.toFixed(1)} yr`}</div></div>
        <div><div className="text-xs text-[var(--text-muted)]">ROE</div><div className="font-mono">{fmtPct(r.roe_avg_annual)}</div></div>
      </div>
      {v.withheld && <div className="text-xs text-[var(--text-muted)]">Withheld from this view: {v.withheld.join('; ')}.</div>}
      <ChainTrace chain={v.identity.input_versions?.chain} />
      <DebtMetricsPanel dm={r.debt_metrics} />
      <DownsideTable d={v.sensitivities ?? r.downside} />
      <ProvenancePanel p={v.provenance} />
      <div className="text-xs text-[var(--text-secondary)]">{v.validity}</div>
      <button type="button" className="text-xs text-[var(--brand)] hover:underline" onClick={async () => {
        const body = await api<unknown>(`/api/v1/returns-cases/${encodeURIComponent(projectId)}/versions/${versionId}/export`)
        const url = URL.createObjectURL(new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' }))
        const a = document.createElement('a'); a.href = url
        a.download = `returns-case-${projectId}-v${v.identity.version_number}.json`; a.click(); URL.revokeObjectURL(url)
      }}>
        Export this version (JSON) — the same disclosure as this screen
      </button>
    </div>
  )
}

function Withdrawn({ w }: { w: Withdrawal }) {
  return (
    <div data-testid="withdrawn" className="rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
      <span className="font-semibold">WITHDRAWN from reliance</span> on {new Date(w.withdrawn_at).toLocaleString('en-GB')} by {w.withdrawn_by}.
      {' '}{w.reason}{w.shares_revoked?.length ? ` Access revoked for: ${w.shares_revoked.map(s => s.user_id).join(', ')}.` : ''}
      {' '}The figures below are kept unchanged as the record; do not rely on them.
    </div>
  )
}

function WithdrawButton({ projectId, versionId, onDone }: { projectId: string; versionId: string; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  if (!open) return <button type="button" className={button} onClick={() => setOpen(true)}>Withdraw from reliance…</button>
  return (
    <div className="space-y-1 text-xs">
      <textarea aria-label="Withdrawal reason" className="w-full rounded border px-2 py-1" rows={2} placeholder="Why (at least 10 characters). Every share of this version is revoked; the version itself is kept." value={reason} onChange={e => setReason(e.target.value)} />
      <button type="button" className={button} disabled={reason.trim().length < 10} onClick={async () => {
        try { await api(`/api/v1/returns-cases/${encodeURIComponent(projectId)}/versions/${versionId}/withdraw`, { method: 'POST', body: JSON.stringify({ reason }) }); onDone() }
        catch (e) { setMsg((e as Error).message) } }}>Withdraw and revoke access</button>
      {msg && <span className="text-red-700"> {msg}</span>}
    </div>
  )
}

function SharePanel({ projectId, versions }: { projectId: string; versions: CaseRow[] }) {
  const qc = useQueryClient()
  const base = `/api/v1/returns-cases/${encodeURIComponent(projectId)}`
  const shares = useQuery({ queryKey: ['returns-shares', projectId], queryFn: () => api<{ shares: ShareRow[] }>(`${base}/shares`), retry: false })
  const templates = useQuery({ queryKey: ['returns-shares', projectId, 'templates'],
    queryFn: () => api<{ status: string; templates: Record<string, { label: string; metrics: string[]; returns: boolean; why: string }> }>(`${base}/audience-templates`), retry: false })
  const [user, setUser] = useState('')
  const [target, setTarget] = useState('')
  const [expires, setExpires] = useState('')
  const [msg, setMsg] = useState<string | null>(null)

  async function share() {
    setMsg(null)
    const [kind, id] = target.split(':')
    try {
      await api(`${base}/shares`, { method: 'POST', body: JSON.stringify({
        user_id: user, ...(kind === 'case' ? { case_id: target.slice(5) } : { version_id: id }),
        expires_at: expires || null }) })
      setUser(''); setMsg('Shared, read-only.')
      qc.invalidateQueries({ queryKey: ['returns-shares', projectId] })
    } catch (e) { setMsg((e as Error).message) }
  }
  async function revoke(id: string) {
    try { await api(`${base}/shares/${id}`, { method: 'DELETE' }); qc.invalidateQueries({ queryKey: ['returns-shares', projectId] }) }
    catch (e) { setMsg((e as Error).message) }
  }

  return (
    <div className={`${card} p-4 space-y-3`}>
      <div className={title}>Share a returns case (RETURNS)</div>
      <div className="text-xs text-[var(--text-secondary)]">
        Per user, read-only, expirable and revocable. A RETURNS share discloses the case's results only: never the
        DEVEX brief, funding, packages or dated pre-FID figures.
      </div>
      <div className="flex flex-wrap items-end gap-2 text-xs">
        <label>User id<input className="ml-1 rounded border px-2 py-1" value={user} onChange={e => setUser(e.target.value)} /></label>
        <label>Case
          <select className="ml-1 rounded border px-2 py-1" value={target} onChange={e => setTarget(e.target.value)}>
            <option value="">choose…</option>
            {versions.filter(v => !v.withdrawal).map(v => <option key={v.version_id} value={`version:${v.version_id}`}>{v.case_name} v{v.version_number} only</option>)}
            {[...new Set(versions.map(v => v.case_id))].map(c => <option key={c} value={`case:${c}`}>{versions.find(v => v.case_id === c)?.case_name} — this case and later versions</option>)}
          </select>
        </label>
        <label>Expires<input type="date" className="ml-1 rounded border px-2 py-1" value={expires} onChange={e => setExpires(e.target.value)} /></label>
        <button type="button" className={button} disabled={!user || !target} onClick={share}>Share</button>
      </div>
      {msg && <div className="text-xs text-[var(--text-secondary)]">{msg}</div>}
      <table className="w-full text-xs">
        <tbody>
          {(shares.data?.shares ?? []).map(s => (
            <tr key={s.entitlement_id} className="border-t border-[var(--border)]">
              <td className="py-1">{s.user_id}</td>
              <td>{s.version_id ? `version ${s.version_id.slice(0, 8)}` : `case ${s.case_id} and later`}</td>
              <td>{s.status}{s.expires_at ? ` · until ${s.expires_at.slice(0, 10)}` : ''}</td>
              <td>{s.status === 'active' && <button type="button" className={button} onClick={() => revoke(s.entitlement_id)}>Revoke</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {templates.data && (
        <details className="text-xs">
          <summary className="cursor-pointer text-[var(--text-secondary)]">Suggestions by audience — {templates.data.status}</summary>
          <ul className="mt-2 space-y-1">
            {Object.entries(templates.data.templates).map(([k, t]) => (
              <li key={k}><span className="font-semibold">{t.label}:</span> {t.returns ? t.metrics.join(', ') : 'no returns case suggested'} — {t.why}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

export function PublishedCases({ projectId, inputs, isOwnerFinance }: {
  projectId: string; inputs: () => ReturnsInputs; isOwnerFinance: boolean
}) {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['returns-cases', projectId],
    queryFn: () => api<CaseList>(`/api/v1/returns-cases/${encodeURIComponent(projectId)}`),
    retry: false,
  })
  const [open, setOpen] = useState<string | null>(null)
  const [name, setName] = useState('Base case')
  const [scenario, setScenario] = useState('BASE')
  const [boundary, setBoundary] = useState<Boundary>('FULL_PROJECT')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  async function publish() {
    setBusy(true); setMsg(null)
    try {
      const v = await api<{ identity: Identity }>(`/api/v1/returns-cases/${encodeURIComponent(projectId)}`, {
        method: 'POST', body: JSON.stringify({ case_name: name, scenario, valuation_boundary: boundary, inputs: inputs() }) })
      setMsg(`Published ${v.identity.case_name} v${v.identity.version_number}.`)
      setOpen(v.identity.version_id)
      qc.invalidateQueries({ queryKey: ['returns-cases', projectId] })
    } catch (e) { setMsg((e as Error).message) } finally { setBusy(false) }
  }

  const status = (list.error as HttpError | null)?.status
  const versions = list.data?.versions ?? []
  return (
    <div className="space-y-3">
      <div className={`${card} p-4 space-y-3`}>
        <div className={title}>Published returns cases</div>
        {list.isLoading && <div className="text-sm text-[var(--text-muted)]">Loading…</div>}
        {status === 403 && (
          <div className="text-sm text-[var(--text-secondary)]">
            No returns case of this project has been shared with you. The calculator below runs on inputs you enter
            yourself: they are not the owner's case.
          </div>
        )}
        {list.error && status !== 403 && <div className="text-sm text-red-700">{(list.error as Error).message}</div>}
        {list.data && versions.length === 0 && <div className="text-sm text-[var(--text-muted)]">No case published yet.</div>}
        {versions.map(v => (
          <div key={v.version_id} className="border-t border-[var(--border)] pt-2">
            <div className="flex items-center justify-between gap-2">
              <button type="button" className="text-left text-sm font-medium text-[var(--brand)] hover:underline"
                onClick={() => setOpen(open === v.version_id ? null : v.version_id)}>
                {v.case_name} v{v.version_number} — {v.valuation_boundary === 'FROM_FID' ? 'from FID' : 'full project'}
              </button>
              {v.withdrawal ? <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-900">withdrawn</span>
                : v.review.needs_review && <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">needs review</span>}
            </div>
            <IdentityLine v={v} />
            {isOwnerFinance && !v.withdrawal && <WithdrawButton projectId={projectId} versionId={v.version_id}
              onDone={() => { qc.invalidateQueries({ queryKey: ['returns-cases', projectId] }); qc.invalidateQueries({ queryKey: ['returns-shares', projectId] }) }} />}
            {open === v.version_id && <div className="mt-3"><VersionView projectId={projectId} versionId={v.version_id} /></div>}
          </div>
        ))}
        {isOwnerFinance && (
          <div className="flex flex-wrap items-end gap-2 border-t border-[var(--border)] pt-3 text-xs">
            <label>Case name<input className="ml-1 rounded border px-2 py-1" value={name} onChange={e => setName(e.target.value)} /></label>
            <label>Scenario<input className="ml-1 rounded border px-2 py-1" value={scenario} onChange={e => setScenario(e.target.value)} /></label>
            <label>Boundary
              <select className="ml-1 rounded border px-2 py-1" value={boundary} onChange={e => setBoundary(e.target.value as Boundary)}>
                {(Object.keys(BOUNDARY_LABEL) as Boundary[]).map(b => <option key={b} value={b}>{BOUNDARY_LABEL[b]}</option>)}
              </select>
            </label>
            <button type="button" className={button} disabled={busy || !name || !scenario} onClick={publish}>
              Publish the calculator's inputs as a new version
            </button>
            {msg && <span className="text-[var(--text-secondary)]">{msg}</span>}
          </div>
        )}
      </div>
      {isOwnerFinance && versions.length > 0 && <SharePanel projectId={projectId} versions={versions} />}
    </div>
  )
}
