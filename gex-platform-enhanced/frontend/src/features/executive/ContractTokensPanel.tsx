// Screen: Panel on the project report (/project-report)
/**
 * Contract tokens (JML 2026-10-28; /api/v1/contract-tokens). The terms the
 * cross-contract checks compare reach the engine only once the other party has
 * confirmed them on the contract's token — the counterparty for a contract, an
 * appointed reviewer for the producer's own plan. A confirmation also verifies
 * the contract's instrument evidence. Every version, confirmation and dispute is
 * an event on the token, chained by hash.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link2, ShieldCheck, ShieldAlert } from 'lucide-react'
import { getAuthHeader } from '@/lib/authToken'

interface TokenEvent { seq: number; event_type: string; terms_sha256: string | null; actor: string; company_id: string | null; note: string | null; at: string }
interface Token {
  kind: string; counterparty_company_id: string | null; confirmed_by: string
  latest_version_sha256: string | null; confirmed: boolean; held_back_fields: string[]
  verifies_evidence: string[]; chain_intact: boolean; events: TokenEvent[]
}
interface Tokens { tokens: Token[]; possible_counterparties: string[]; you: { company_id: string | null; is_gex: boolean; is_owner_executive: boolean } }

export function ContractTokensPanel({ projectId, onChanged }: { projectId: string; onChanged: () => void }) {
  const [data, setData] = useState<Tokens | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  const load = useCallback(() => {
    fetch(`/api/v1/contract-tokens/${encodeURIComponent(projectId)}`, { headers: getAuthHeader() })
      .then(async r => { if (!r.ok) throw new Error(`The server answered ${r.status}.`); return r.json() })
      .then(setData).catch(e => setError(e.message))
  }, [projectId])
  useEffect(load, [load])

  const call = async (method: string, path: string, body: object) => {
    setError(null)
    const r = await fetch(`/api/v1/contract-tokens/${encodeURIComponent(projectId)}${path}`, {
      method, headers: { ...getAuthHeader(), 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    const j = await r.json().catch(() => ({}))
    if (!r.ok) { setError(j?.detail?.message ?? `Refused (${r.status}).`); return }
    load(); onChanged()
  }

  if (!data) return <p className="px-5 py-4 text-sm text-gray-400">{error ?? 'Loading contracts…'}</p>
  return (
    <div className="rounded-2xl border border-gray-200 bg-white">
      <h2 className="flex items-center gap-2 border-b border-gray-100 px-5 py-3 text-sm font-bold text-gray-900">
        <Link2 className="h-4 w-4" /> Contract terms — confirmed by the other party before they count
      </h2>
      {error && <p className="mx-5 mt-2 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">{error}</p>}
      <div className="divide-y divide-gray-100">
        {data.tokens.map(t => {
          const isCounterparty = t.counterparty_company_id && t.counterparty_company_id === data.you.company_id
          return (
            <div key={t.kind} className="px-5 py-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold capitalize">{t.kind}</span>
                {t.confirmed
                  ? <span className="flex items-center gap-1 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800"><ShieldCheck className="h-3 w-3" /> confirmed</span>
                  : t.latest_version_sha256
                    ? <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">awaiting confirmation</span>
                    : <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-bold text-gray-500">no terms recorded</span>}
                {!t.chain_intact && <span className="flex items-center gap-1 text-[10px] font-bold text-red-700"><ShieldAlert className="h-3 w-3" /> chain broken</span>}
                <span className="text-xs text-gray-500">
                  {t.kind === 'technical' || t.kind === 'model' ? `by the ${t.confirmed_by}`
                    : `counterparty: ${t.counterparty_company_id ?? 'not registered'}`}
                </span>
                <button className="ml-auto text-xs text-gray-500 underline" onClick={() => setOpen(open === t.kind ? null : t.kind)}>
                  {open === t.kind ? 'hide' : 'history'}
                </button>
              </div>
              {t.held_back_fields.length > 0 && (
                <div className="mt-1 text-xs text-amber-700">Held back from the engine until confirmed: {t.held_back_fields.join(', ')}</div>
              )}
              <div className="mt-1 flex flex-wrap gap-2">
                {data.you.is_owner_executive && !(t.kind === 'technical' || t.kind === 'model') && (
                  <select className="rounded border px-1 py-0.5 text-xs" value={t.counterparty_company_id ?? ''}
                    onChange={e => e.target.value && call('PUT', `/${t.kind}/counterparty`, { company_id: e.target.value })}>
                    <option value="">Register counterparty…</option>
                    {data.possible_counterparties.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                )}
                {(isCounterparty || t.kind === 'technical' || t.kind === 'model') && !data.you.is_gex && !t.confirmed
                  && (t.latest_version_sha256 || t.kind === 'licence') && (
                  <button className="rounded bg-teal-700 px-2 py-1 text-xs font-semibold text-white"
                    onClick={() => call('POST', `/${t.kind}/confirm`, { terms_sha256: t.latest_version_sha256 })}>
                    Confirm these terms
                  </button>
                )}
                {(isCounterparty || t.kind === 'technical' || t.kind === 'model') && !data.you.is_gex && t.confirmed && (
                  <button className="rounded border border-amber-400 px-2 py-1 text-xs text-amber-800"
                    onClick={() => { const note = window.prompt('Why do you dispute these terms?'); if (note) call('POST', `/${t.kind}/dispute`, { note }) }}>
                    Dispute
                  </button>
                )}
              </div>
              {open === t.kind && (
                <div className="mt-2 space-y-0.5 font-mono text-[11px] text-gray-500">
                  {t.events.map(e => (
                    <div key={e.seq}>#{e.seq} {e.event_type} · {e.actor}{e.company_id ? ` (${e.company_id})` : ''}
                      {e.terms_sha256 ? ` · ${e.terms_sha256.slice(0, 12)}…` : ''}{e.note ? ` — ${e.note}` : ''}</div>
                  ))}
                  {t.verifies_evidence.length > 0 && <div>Confirmation verifies: {t.verifies_evidence.join(', ')}</div>}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
