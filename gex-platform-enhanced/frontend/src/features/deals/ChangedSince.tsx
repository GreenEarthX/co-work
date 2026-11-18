// Check 9 (report §6.3): what changed since an enquiry, proposal or acceptance was assessed. The
// server compares the stored assessment (never updated) with the same pair assessed now; this only
// shows its answer.
import type { ChangedSinceAssessed } from '@/api'

const WORD: Record<string, string> = { compatible: 'Compatible', incompatible: 'Incompatible', needs_evidence: 'Needs evidence' }
const FIELD: Record<string, string> = {
  product: 'product evidence', price_eur_kg: 'price', volume_mtpd: 'volume', delivery_start: 'delivery start',
  delivery_end: 'delivery end', offer_type: 'firm or indicative', valid_until: 'validity', incoterm: 'Incoterm',
  named_place: 'named place', availability: 'availability',
}

export function ChangedSince({ change }: { change?: ChangedSinceAssessed | null }) {
  if (!change) return null
  return (
    <div role="status" data-testid="changed-since" className="rounded-md border border-orange-300 bg-orange-50 p-3 text-xs text-orange-900">
      <div className="font-semibold">
        Changed since you looked ({change.purpose}, {change.assessed_at?.slice(0, 10)}):{' '}
        {WORD[change.status_then] ?? change.status_then} → {WORD[change.status_now] ?? change.status_now}
        {!change.eligible_now && ' · now excluded by a required item'}
      </div>
      {change.outcomes.map(o => (
        <div key={o.requirement}>{o.label}: {WORD[o.then ?? ''] ?? '—'} → {WORD[o.now ?? ''] ?? '—'}{o.reason_now ? `. ${o.reason_now}` : ''}</div>
      ))}
      {change.listing_fields.length > 0 && (
        <div>Changed on the listing: {change.listing_fields.map(f => FIELD[f] ?? f).join(', ')}.</div>
      )}
    </div>
  )
}
