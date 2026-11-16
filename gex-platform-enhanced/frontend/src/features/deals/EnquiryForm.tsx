// Screen part: send a non-binding enquiry about one listing or one RFQ (R9, decision D-D).
// It binds nothing. Neither side learns who the other is until the receiving party shares contact.
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { marketAPI } from '@/api'

export function EnquiryForm({ subject, myRfqs, onClose }: {
  subject: { kind: 'listing' | 'rfq'; id: string; label: string }
  myRfqs?: { id: string; label: string }[]
  onClose: () => void
}) {
  const [body, setBody] = useState('')
  const [evidence, setEvidence] = useState('')
  const [about, setAbout] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState<string | null>(null)
  const key = useRef(crypto.randomUUID())

  async function send() {
    setBusy(true); setError('')
    try {
      const e = await marketAPI.sendEnquiry({
        ...(subject.kind === 'listing' ? { listing_id: subject.id } : { rfq_id: subject.id }),
        ...(about ? { about_rfq_id: about } : {}),
        body: body.trim(), ...(evidence.trim() ? { evidence_request: evidence.trim() } : {}),
      }, key.current)
      setSent(e.id)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  if (sent) {
    return (
      <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm">
        Enquiry sent. It binds nothing. <Link className="font-semibold underline" to={`/deals/${sent}`}>Continue in Deals</Link>
        <button className="ml-3 text-xs text-gray-600" onClick={onClose}>Close</button>
      </div>
    )
  }
  return (
    <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4" aria-label="Send enquiry">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Enquiry about {subject.label}</h3>
          <p className="text-xs text-gray-600">
            Non-binding. The other side sees your role and vetting badge, not your name. If they choose
            <em> Share contact</em>, both companies and the people on this thread are revealed to each other; if they
            decline, nothing is.
          </p>
        </div>
        <button className="text-xs text-gray-500" onClick={onClose}>Cancel</button>
      </div>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <label className="block text-sm"><span className="mb-1 block font-medium text-gray-700">Message</span>
        <textarea className="w-full rounded-md border border-gray-300 p-2 text-sm" rows={3} maxLength={4000}
                  value={body} onChange={e => setBody(e.target.value)} /></label>
      <label className="block text-sm"><span className="mb-1 block font-medium text-gray-700">Evidence you would like to see (optional)</span>
        <input className="w-full rounded-md border border-gray-300 p-2 text-sm" maxLength={1000}
               placeholder="e.g. the ISCC EU certificate covering 2028-Q1" value={evidence} onChange={e => setEvidence(e.target.value)} /></label>
      {subject.kind === 'listing' && myRfqs && myRfqs.length > 0 && (
        <label className="block text-sm"><span className="mb-1 block font-medium text-gray-700">For my RFQ (optional)</span>
          <select className="w-full rounded-md border border-gray-300 p-2 text-sm" value={about} onChange={e => setAbout(e.target.value)}>
            <option value="">None</option>
            {myRfqs.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
          <span className="mt-1 block text-xs text-gray-500">Records how this listing met your requirements when you asked. Not shown to the seller.</span>
        </label>
      )}
      <button className="rounded-md bg-gray-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
              disabled={busy || !body.trim()} onClick={send}>Send enquiry</button>
    </div>
  )
}
