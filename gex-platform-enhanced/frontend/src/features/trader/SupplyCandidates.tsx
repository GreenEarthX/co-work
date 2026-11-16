// Screen part: the supply that meets one of my RFQs, and Compare (discovery Phase 1, R7).
// Eligibility first, then price: the server (core/compatibility) decides each requirement as
// Compatible, Incompatible (with the reason) or Needs evidence (with what is missing); a listing
// failing a requirement the buyer made "required" is excluded whatever its price. This screen only
// shows those words; it never computes them.
import { useEffect, useState } from 'react'

import { marketAPI, type Assessment, type Candidate, type Outcome } from '@/api'
import { useMarketPolicy } from '@/lib/marketPolicy'
import { CarbonCell, CounterpartyBadge, EvidenceCell, ProductCell } from './ListingParts'

const WORD: Record<Outcome['outcome'], { label: string; cls: string; mark: string }> = {
  compatible: { label: 'Compatible', cls: 'bg-emerald-50 text-emerald-800', mark: '✓' },
  needs_evidence: { label: 'Needs evidence', cls: 'bg-amber-50 text-amber-800', mark: '?' },
  incompatible: { label: 'Incompatible', cls: 'bg-red-50 text-red-700', mark: '✕' },
}

export function OutcomeChip({ outcome }: { outcome: Outcome['outcome'] }) {
  const w = WORD[outcome]
  return <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold ${w.cls}`}>
    <span aria-hidden>{w.mark}</span>{w.label}
  </span>
}

function Summary({ a }: { a: Assessment }) {
  const blocking = a.outcomes.filter(o => o.mandatory && o.outcome === 'incompatible')
  return (
    <div className="space-y-1">
      <OutcomeChip outcome={a.status} />
      <div className="text-[11px] text-gray-500">
        {a.counts.compatible} compatible · {a.counts.needs_evidence} need evidence · {a.counts.incompatible} not met
      </div>
      {blocking.map(o => <div key={o.requirement} className="text-xs text-red-700">Excluded: {o.reason}</div>)}
    </div>
  )
}

export function CompareTable({ candidates }: { candidates: Candidate[] }) {
  const keys: { requirement: string; label: string; mandatory: boolean }[] = []
  for (const c of candidates) for (const o of c.assessment.outcomes)
    if (!keys.some(k => k.requirement === o.requirement)) keys.push(o)
  return (
    <div className="overflow-x-auto rounded-md border border-gray-200" data-testid="compare">
      <table className="w-full text-left text-xs">
        <thead className="bg-gray-50 text-gray-500"><tr>
          <th className="px-3 py-2">Requirement</th>
          {candidates.map((c, i) => <th key={c.listing.id} className="px-3 py-2">Listing {i + 1} · €{c.listing.price_eur_kg}/kg</th>)}
        </tr></thead>
        <tbody>
          {keys.map(k => (
            <tr key={k.requirement} className="border-t border-gray-100 align-top">
              <td className="px-3 py-2 font-medium text-gray-800">{k.label}{k.mandatory ? ' · required' : ''}</td>
              {candidates.map(c => {
                const o = c.assessment.outcomes.find(x => x.requirement === k.requirement)
                return <td key={c.listing.id} className="px-3 py-2">
                  {o ? <><OutcomeChip outcome={o.outcome} /><div className="mt-1 text-gray-600">{o.reason}</div></> : '—'}
                </td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SupplyCandidates({ rfqId, onClose }: { rfqId: string; onClose: () => void }) {
  const { can } = useMarketPolicy()
  const [rows, setRows] = useState<Candidate[] | null>(null)
  const [error, setError] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [compared, setCompared] = useState<Candidate[] | null>(null)
  const [proposed, setProposed] = useState<Record<string, string>>({})
  const [confirming, setConfirming] = useState<string | null>(null)

  useEffect(() => {
    marketAPI.rfqCompatibility(rfqId).then(r => setRows(r.candidates)).catch(e => setError(e.message))
  }, [rfqId])

  const toggle = (id: string) => setPicked(p => p.includes(id) ? p.filter(x => x !== id) : p.length < 4 ? [...p, id] : p)
  async function compare() {
    try { setCompared((await marketAPI.rfqCompatibility(rfqId, picked)).candidates) } catch (e) { setError((e as Error).message) }
  }
  async function propose(offerId: string) {
    try {
      const m = await marketAPI.proposeMatch(offerId, rfqId)
      setProposed(p => ({ ...p, [offerId]: m.id })); setConfirming(null)
    } catch (e) { setError((e as Error).message) }
  }

  return (
    <div className="mt-4 space-y-3 rounded-lg border border-gray-200 bg-gray-50/50 p-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-900">Supply for this RFQ</h4>
        <button className="text-xs text-gray-500 hover:text-gray-800" onClick={onClose}>Close</button>
      </div>
      <p className="text-xs text-gray-600">
        Sorted by eligibility, then price. A listing that fails a requirement you marked <em>required</em> is excluded,
        whatever its price. Sellers stay anonymous until a match.
      </p>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {rows === null && !error && <p className="text-sm text-gray-500">Assessing…</p>}
      {rows?.length === 0 && <p className="text-sm text-gray-500">No open listing of this molecule.</p>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-gray-500"><tr>
              {['', 'Assessment', 'Product', 'Carbon intensity', 'Evidence', 'Volume', 'Price', 'Delivery', 'Seller', ''].map((h, i) =>
                <th key={i} className="px-2 py-2">{h}</th>)}
            </tr></thead>
            <tbody>
              {rows.map(c => (
                <tr key={c.listing.id} data-testid={`candidate-${c.listing.id}`}
                    className={`border-t border-gray-100 align-top ${c.assessment.eligible ? '' : 'opacity-70'}`}>
                  <td className="px-2 py-2"><input type="checkbox" aria-label={`Compare listing ${c.listing.id}`}
                    checked={picked.includes(c.listing.id)} onChange={() => toggle(c.listing.id)}
                    disabled={!picked.includes(c.listing.id) && picked.length >= 4} /></td>
                  <td className="px-2 py-2"><Summary a={c.assessment} /></td>
                  <td className="px-2 py-2"><ProductCell product={c.listing.product} /></td>
                  <td className="px-2 py-2"><CarbonCell product={c.listing.product} /></td>
                  <td className="px-2 py-2"><EvidenceCell product={c.listing.product} /></td>
                  <td className="px-2 py-2">{c.listing.volume_mtpd} MTPD</td>
                  <td className="px-2 py-2">€{c.listing.price_eur_kg}/kg</td>
                  <td className="px-2 py-2">{c.listing.incoterm ? `${c.listing.incoterm} ${c.listing.named_place ?? ''}`.trim() : '—'}</td>
                  <td className="px-2 py-2"><CounterpartyBadge role={c.listing.seller_role} vetting={c.listing.seller_vetting} /></td>
                  <td className="px-2 py-2">
                    {proposed[c.listing.id] ? <span className="text-emerald-700">Proposed</span>
                      : !c.assessment.eligible || !can('proposal.create') ? null
                      : confirming === c.listing.id ? (
                        <span className="flex flex-col gap-1">
                          <span className="text-gray-700">A firm offer to buy at €{c.listing.price_eur_kg}/kg. It binds when the seller accepts.</span>
                          <span className="flex gap-1">
                            <button className="rounded bg-gray-900 px-2 py-1 font-semibold text-white" onClick={() => propose(c.listing.id)}>Confirm proposal</button>
                            <button className="rounded border px-2 py-1" onClick={() => setConfirming(null)}>Cancel</button>
                          </span>
                        </span>)
                      : <button className="rounded border px-2 py-1 font-semibold hover:bg-white" onClick={() => setConfirming(c.listing.id)}>
                          Propose (binding)</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows && rows.length > 1 && (
        <button className="rounded-md border bg-white px-3 py-1.5 text-xs font-semibold disabled:opacity-40"
                disabled={picked.length < 2} onClick={compare}>Compare selected ({picked.length}/4)</button>
      )}
      {compared && <CompareTable candidates={compared} />}
    </div>
  )
}
