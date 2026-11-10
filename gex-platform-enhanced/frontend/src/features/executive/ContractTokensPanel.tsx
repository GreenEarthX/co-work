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

interface TokenEvent {
  seq: number; event_type: string; terms_sha256: string | null; actor: string; company_id: string | null; note: string | null; at: string
  /** Phase 5: on a CONFIRMED or DISPUTED event — "signed by the party" or "confirmed in GEX, not signed by the party". */
  signed_by_party?: boolean; signature_label?: string; signer_key_ref?: string | null
}
// The offtake frame (contract record Phase 3, Q2): one sub-leg per buyer, each confirmed by that buyer.
interface FrameBuyer { company_id: string; sub_leg_hash: string; confirmed: boolean; locked?: boolean }
interface Frame { version: number; shared_hash: string; buyers: FrameBuyer[] }
interface Token {
  kind: string; counterparty_company_id: string | null; confirmed_by: string; frame?: Frame | null
  latest_version_sha256: string | null; confirmed: boolean; held_back_fields: string[]
  verifies_evidence: string[]; chain_intact: boolean; events: TokenEvent[]
}
// Adverse facts are events on the contract (Q10): reported with a document, they apply at once;
// two other companies clear one. A novation (Q13) hands a buyer's sub-leg over with three confirmations.
interface Fact { kind: string; fact: string; subject_company_id: string | null; report_event_hash: string
  reported_by: string; reporter_company_id: string; open: boolean; cleared_by: { company_id: string }[] }
interface Novation { proposal_event_hash: string; outgoing_company_id: string; incoming_company_id: string
  confirmed_by: string[]; awaiting: string[]; state: 'pending' | 'completed' | 'lapsed' }
interface Tokens { tokens: Token[]; possible_counterparties: string[]; adverse_facts?: Fact[]; novations?: Novation[]
  you: { company_id: string | null; is_gex: boolean; is_owner_executive: boolean } }
const FACT_LABELS: Record<string, string> = {
  COUNTERPARTY_INSOLVENT: 'EPC contractor insolvent', SUPPORT_OR_PPA_REVOKED: 'Support or PPA revoked',
  CERTIFICATION_SUSPENDED: 'Certification suspended', BUYER_INSOLVENT: 'Buyer insolvent',
}

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
              {t.frame && (
                <div className="mt-1 space-y-1">
                  {t.frame.buyers.map(b => (
                    <div key={b.company_id} className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="text-gray-700">{b.company_id}</span>
                      {b.confirmed
                        ? <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">confirmed its sub-leg</span>
                        : <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">awaiting its confirmation</span>}
                      {b.locked && <span className="text-[10px] text-gray-500">market trade · confirmed on the trade, with four eyes</span>}
                      {b.company_id === data.you.company_id && !data.you.is_gex && !b.confirmed && !b.locked && (
                        <button className="rounded bg-teal-700 px-2 py-0.5 text-[11px] font-semibold text-white"
                          onClick={() => call('POST', `/offtake/buyers/${encodeURIComponent(b.company_id)}/confirm`, { sub_leg_hash: b.sub_leg_hash })}>
                          Confirm my sub-leg
                        </button>
                      )}
                      {b.company_id && !b.locked && (b.company_id === data.you.company_id || data.you.is_owner_executive) && !data.you.is_gex && (
                        <button className="rounded border border-gray-300 px-2 py-0.5 text-[11px] text-gray-700"
                          onClick={() => { const incoming = window.prompt('Hand this sub-leg over to which company (its id)?'); if (incoming) call('POST', `/offtake/buyers/${encodeURIComponent(b.company_id!)}/novation`, { incoming_company_id: incoming }) }}>
                          Hand over…
                        </button>
                      )}
                      {b.company_id === data.you.company_id && !data.you.is_gex && b.confirmed && (
                        <button className="rounded border border-amber-400 px-2 py-0.5 text-[11px] text-amber-800"
                          onClick={() => { const note = window.prompt('Why do you dispute your sub-leg?'); if (note) call('POST', `/offtake/buyers/${encodeURIComponent(b.company_id)}/dispute`, { note }) }}>
                          Dispute
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {t.held_back_fields.length > 0 && (
                <div className="mt-1 text-xs text-amber-700">Held back from the engine until confirmed: {t.held_back_fields.join(', ')}</div>
              )}
              <div className="mt-1 flex flex-wrap gap-2">
                {data.you.is_owner_executive && !t.frame && !(t.kind === 'technical' || t.kind === 'model') && (
                  <select className="rounded border px-1 py-0.5 text-xs" value={t.counterparty_company_id ?? ''}
                    onChange={e => e.target.value && call('PUT', `/${t.kind}/counterparty`, { company_id: e.target.value })}>
                    <option value="">Register counterparty…</option>
                    {data.possible_counterparties.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                )}
                {!t.frame && (isCounterparty || t.kind === 'technical' || t.kind === 'model') && !data.you.is_gex && !t.confirmed
                  && (t.latest_version_sha256 || t.kind === 'licence') && (
                  <button className="rounded bg-teal-700 px-2 py-1 text-xs font-semibold text-white"
                    onClick={() => call('POST', `/${t.kind}/confirm`, { terms_sha256: t.latest_version_sha256 })}>
                    Confirm these terms
                  </button>
                )}
                {!t.frame && (isCounterparty || t.kind === 'technical' || t.kind === 'model') && !data.you.is_gex && t.confirmed && (
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
                      {e.terms_sha256 ? ` · ${e.terms_sha256.slice(0, 12)}…` : ''}{e.note ? ` — ${e.note}` : ''}
                      {e.signature_label && (
                        <span data-testid={`signature-${e.seq}`}
                              className={e.signed_by_party ? 'ml-1 text-emerald-700 dark:text-emerald-300' : 'ml-1 text-amber-700 dark:text-amber-300'}>
                          · {e.signature_label}{e.signed_by_party && e.signer_key_ref ? ` (${e.signer_key_ref})` : ''}
                        </span>
                      )}</div>
                  ))}
                  {t.verifies_evidence.length > 0 && <div>Confirmation verifies: {t.verifies_evidence.join(', ')}</div>}
                </div>
              )}
            </div>
          )
        })}
      </div>
      {!data.you.is_gex && <FactsAndNovations data={data} call={call} />}
    </div>
  )
}

function FactsAndNovations({ data, call }: { data: Tokens; call: (m: string, p: string, b: object) => void }) {
  const facts = data.adverse_facts ?? []
  const novations = (data.novations ?? []).filter(n => n.state === 'pending')
  const report = () => {
    const fact = window.prompt(`Which fact? ${Object.keys(FACT_LABELS).join(', ')}`)
    if (!fact) return
    const subject = fact === 'BUYER_INSOLVENT' ? window.prompt('Which buyer (company id)?') : null
    const doc = window.prompt('The sha256 of the document on file that shows it')
    if (doc) call('POST', '/adverse-facts', { fact, document_sha256: doc, subject_company_id: subject })
  }
  return (
    <div className="border-t border-gray-100 px-5 py-3 text-sm">
      <div className="flex items-center gap-2">
        <span className="font-semibold">Adverse facts</span>
        <span className="text-xs text-gray-500">apply at once when reported; two other companies clear one</span>
        <button className="ml-auto rounded border border-red-300 px-2 py-0.5 text-xs text-red-700" onClick={report}>
          Report a fact…
        </button>
      </div>
      {facts.length === 0 && <p className="mt-1 text-xs text-gray-400">None reported.</p>}
      {facts.map(f => (
        <div key={f.report_event_hash} className="mt-1 flex flex-wrap items-center gap-2 text-xs">
          <span className={f.open ? 'font-semibold text-red-700' : 'text-gray-500 line-through'}>
            {FACT_LABELS[f.fact] ?? f.fact}{f.subject_company_id ? ` (${f.subject_company_id})` : ''}
          </span>
          <span className="text-gray-500">reported by {f.reporter_company_id} · {f.cleared_by.length} of 2 clearing confirmations</span>
          {f.open && f.reporter_company_id !== data.you.company_id && (
            <button className="rounded border border-gray-300 px-2 py-0.5 text-[11px]"
              onClick={() => { const doc = window.prompt('The sha256 of the document on file that clears it'); if (doc) call('POST', `/adverse-facts/${f.report_event_hash}/clear`, { document_sha256: doc }) }}>
              Confirm clearing
            </button>
          )}
        </div>
      ))}
      {novations.length > 0 && <div className="mt-3 font-semibold">Novations awaiting confirmation</div>}
      {novations.map(n => (
        <div key={n.proposal_event_hash} className="mt-1 flex flex-wrap items-center gap-2 text-xs">
          <span>{n.outgoing_company_id} → {n.incoming_company_id}</span>
          <span className="text-gray-500">confirmed by {n.confirmed_by.join(', ')}; awaiting {n.awaiting.join(', ')}</span>
          <button className="rounded bg-teal-700 px-2 py-0.5 text-[11px] font-semibold text-white"
            onClick={() => call('POST', `/offtake/novations/${n.proposal_event_hash}/confirm`, {})}>
            Confirm this novation
          </button>
        </div>
      ))}
    </div>
  )
}
