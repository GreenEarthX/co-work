// Screen: Deals (/deals, /deals/:id) — my company's enquiries, sent and received (R9, D-D).
// An enquiry is non-binding. The receiving party chooses Share contact (both companies and the people
// on the thread are revealed to each other, and the consent is recorded) or Decline (nothing is).
// A firm proposal is a separate, binding act: from here it goes through Market Discovery or the RFQ's
// supply list, never by typing in a thread.
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { marketAPI, type Enquiry } from '@/api'
import { useMarketPolicy } from '@/lib/marketPolicy'
import { CounterpartyBadge } from '@/features/trader/ListingParts'

const STATUS: Record<Enquiry['status'], { label: string; cls: string }> = {
  open: { label: 'Open', cls: 'bg-blue-50 text-blue-800' },
  contact_shared: { label: 'Contact shared', cls: 'bg-emerald-50 text-emerald-800' },
  declined: { label: 'Declined', cls: 'bg-gray-100 text-gray-600' },
  withdrawn: { label: 'Withdrawn', cls: 'bg-gray-100 text-gray-600' },
  closed: { label: 'Closed', cls: 'bg-gray-100 text-gray-600' },
}

function StatusChip({ status }: { status: Enquiry['status'] }) {
  const s = STATUS[status]
  return <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${s.cls}`}>{s.label}</span>
}

function subjectLine(e: Enquiry) {
  const s = e.subject
  const price = s.kind === 'listing' ? `€${s.price_eur_kg}/kg` : s.max_price_eur_kg != null ? `up to €${s.max_price_eur_kg}/kg` : ''
  return `${s.kind === 'listing' ? 'Listing' : 'RFQ'} · ${s.molecule} · ${s.volume_mtpd} MTPD${price ? ` · ${price}` : ''} · ${s.delivery_start} to ${s.delivery_end}`
}

function Thread({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { can } = useMarketPolicy()
  const [e, setE] = useState<Enquiry | null>(null)
  const [body, setBody] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { setE(null); marketAPI.enquiry(id).then(setE).catch(x => setError(x.message)) }, [id])

  async function act(f: () => Promise<Enquiry>) {
    setBusy(true); setError('')
    try { setE(await f()); onChanged() } catch (x) { setError((x as Error).message) } finally { setBusy(false) }
  }

  if (error && !e) return <p role="alert" className="text-sm text-red-700">{error}</p>
  if (!e) return <p className="text-sm text-gray-500">Loading…</p>
  const id_ = e.counterparty.identity
  const mayAnswer = e.role === 'received' ? can('enquiry.reply') : can('enquiry.send')
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip status={e.status} />
        <span className="text-sm text-gray-800">{subjectLine(e)}</span>
      </div>
      <div className="rounded-md border border-gray-200 p-3 text-sm" data-testid="counterparty">
        {id_ ? (
          <>
            <div className="font-semibold text-gray-900">{id_.company_name}</div>
            {id_.person && <div>{id_.person.name} · <a className="underline" href={`mailto:${id_.person.email}`}>{id_.person.email}</a></div>}
            {id_.details && Object.entries(id_.details).filter(([, v]) => v).map(([k, v]) =>
              <div key={k} className="text-xs text-gray-600">{k.replace(/_/g, ' ')}: {v}</div>)}
            <div className="mt-1 text-xs text-gray-500">Released by consent on {e.decided_at?.slice(0, 10)}.</div>
          </>
        ) : (
          <>
            <CounterpartyBadge role={e.counterparty.role} vetting={e.counterparty.vetting} />
            <div className="mt-1 text-xs text-gray-500">
              {e.status === 'open' ? 'Identities are revealed to both sides only if the party asked shares contact.'
                : 'No contact was shared.'}
            </div>
          </>
        )}
      </div>

      <ol className="space-y-2" aria-label="Messages">
        {(e.messages ?? []).map((m, i) => (
          <li key={i} className={`max-w-[80%] rounded-lg p-3 text-sm ${m.side === 'you' ? 'ml-auto bg-gray-900 text-white' : 'bg-gray-100 text-gray-900'}`}>
            <div className="mb-1 text-[11px] opacity-70">{m.side === 'you' ? 'You' : 'Them'} · {m.at.slice(0, 16).replace('T', ' ')}</div>
            {m.body}
            {m.evidence_request && <div className="mt-2 text-xs opacity-80">Evidence requested: {m.evidence_request}</div>}
          </li>
        ))}
      </ol>

      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {e.can.reply && mayAnswer && (
        <div className="space-y-2">
          <textarea aria-label="Reply" className="w-full rounded-md border border-gray-300 p-2 text-sm" rows={2}
                    value={body} onChange={x => setBody(x.target.value)} />
          <button className="rounded-md border px-3 py-1.5 text-sm font-semibold disabled:opacity-40" disabled={busy || !body.trim()}
                  onClick={() => act(() => marketAPI.replyEnquiry(e.id, body.trim())).then(() => setBody(''))}>Send reply</button>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {e.can.share_contact && can('enquiry.reply') && (
          <button className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-semibold text-white" disabled={busy}
                  onClick={() => act(() => marketAPI.decideEnquiry(e.id, 'share-contact'))}>Share contact</button>)}
        {e.can.decline && can('enquiry.reply') && (
          <button className="rounded-md border px-3 py-1.5 text-sm font-semibold" disabled={busy}
                  onClick={() => act(() => marketAPI.decideEnquiry(e.id, 'decline'))}>Decline</button>)}
        {e.can.withdraw && can('enquiry.send') && (
          <button className="rounded-md border px-3 py-1.5 text-sm font-semibold" disabled={busy}
                  onClick={() => act(() => marketAPI.decideEnquiry(e.id, 'withdraw'))}>Withdraw</button>)}
        {e.status === 'contact_shared' && e.role === 'sent' && e.subject.kind === 'listing' && (
          <Link className="rounded-md border px-3 py-1.5 text-sm font-semibold" to="/rfqs">Make a firm proposal from your RFQ</Link>)}
      </div>
      {e.can.share_contact && (
        <p className="text-xs text-gray-500">Share contact reveals your company and your name and e-mail to the asker, and theirs to you.
          It is recorded. It commits you to nothing else.</p>)}
    </div>
  )
}

export default function DealsPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [rows, setRows] = useState<Enquiry[] | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(() => {
    marketAPI.myEnquiries().then(r => setRows(r.enquiries)).catch(x => setError(x.message))
  }, [])
  useEffect(() => { load() }, [load])

  return (
    <div className="mx-auto max-w-6xl p-6">
      <h1 className="mb-1 text-xl font-bold text-gray-900">Deals</h1>
      <p className="mb-5 text-sm text-gray-600">Enquiries your company sent and received. Non-binding: nothing here is a commitment.</p>
      {error && <p role="alert" className="mb-3 text-sm text-red-700">{error}</p>}
      <div className="grid gap-6 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <ul className="divide-y rounded-md border border-gray-200" aria-label="Enquiries">
          {rows?.length === 0 && <li className="p-4 text-sm text-gray-500">No enquiry yet. Ask about a listing or an RFQ on Market Discovery.</li>}
          {rows?.map(e => (
            <li key={e.id}>
              <button className={`w-full p-3 text-left text-sm hover:bg-gray-50 ${e.id === id ? 'bg-gray-50' : ''}`}
                      onClick={() => navigate(`/deals/${e.id}`)}>
                <div className="flex items-center gap-2">
                  <StatusChip status={e.status} />
                  <span className="text-xs text-gray-500">{e.role === 'sent' ? 'Sent' : 'Received'}</span>
                </div>
                <div className="mt-1 text-gray-800">{subjectLine(e)}</div>
                <div className="text-xs text-gray-500">{e.counterparty.identity?.company_name
                  ?? <CounterpartyBadge role={e.counterparty.role} vetting={e.counterparty.vetting} />}</div>
              </button>
            </li>
          ))}
        </ul>
        <div>{id ? <Thread id={id} onChanged={load} /> : <p className="text-sm text-gray-500">Choose an enquiry.</p>}</div>
      </div>
    </div>
  )
}
