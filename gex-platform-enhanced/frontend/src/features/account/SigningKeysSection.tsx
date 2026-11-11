/**
 * Your company's signing keys (Phase 5 of "One contract record"). A party signs its
 * own confirmations and disputes with a key registered here, so a confirmation does
 * not rest on a session GEX signs. GET/POST /api/v1/trading-book/party-keys.
 *
 * The server holds the rule: an executive proposes a public key, a SECOND executive
 * activates it, any executive revokes it with a reason; every step is in the ledger.
 * This section shows what the server answers and never decides alone. GEX stores the
 * public key only — the private key never leaves the company.
 */
import { useCallback, useEffect, useState } from 'react'
import { KeyRound } from 'lucide-react'

interface PartyKey {
  key_ref: string; scheme: string; public_key: string; label: string | null; status: string
  proposed_by: string; proposed_at: string; approved_by: string | null; revoked_by: string | null
  revoke_reason: string | null
}

async function call<T>(path = '', init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api/v1/trading-book/party-keys${path}`, {
    ...init, headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const d = body?.detail
    throw new Error((d && typeof d === 'object' && d.message) || (typeof d === 'string' && d)
      || `The server answered ${res.status}.`)
  }
  return body as T
}

const btn = 'rounded-md border border-[var(--border)] px-2 py-1 text-[11px] font-semibold disabled:opacity-40'

export function SigningKeysSection() {
  const [keys, setKeys] = useState<PartyKey[] | null>(null)
  const [publicKey, setPublicKey] = useState('')
  const [label, setLabel] = useState('')
  const [reason, setReason] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    call<{ keys: PartyKey[] }>().then(r => { setKeys(r.keys); setError(null) })
      .catch(e => { setKeys(null); setError(e.message) })
  }, [])
  useEffect(() => { load() }, [load])

  const act = async (path: string, body?: unknown): Promise<boolean> => {
    setBusy(true)
    try {
      await call(path, { method: 'POST', body: JSON.stringify(body ?? {}) })
      setError(null)
      load()
      return true
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); return false }
    finally { setBusy(false) }
  }

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4" data-testid="signing-keys">
      <h2 className="flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
        <KeyRound className="h-4 w-4" /> Your company's signing keys
      </h2>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">
        Sign your confirmations with your own key (ed25519). An executive proposes a public key; a second
        executive activates it. GEX keeps the public key only.
      </p>
      {error && <p className="mt-2 text-xs text-red-700 dark:text-red-300" role="alert">{error}</p>}
      {keys && keys.length === 0 && <p className="mt-2 text-xs text-[var(--text-muted)]">No key registered.</p>}
      {keys && keys.length > 0 && (
        <ul className="mt-3 space-y-2 text-xs">
          {keys.map(k => (
            <li key={k.key_ref} data-testid={`key-${k.key_ref}`} className="rounded border border-[var(--border)] p-2">
              <div><code>{k.key_ref}</code> · <span className="font-semibold">{k.status.toLowerCase()}</span>
                {k.label ? ` · ${k.label}` : ''}</div>
              <div className="text-[var(--text-muted)]">
                proposed by {k.proposed_by}{k.approved_by ? `, ${k.status === 'REJECTED' ? 'rejected' : 'activated'} by ${k.approved_by}` : ''}
                {k.revoked_by ? `, revoked by ${k.revoked_by}: ${k.revoke_reason}` : ''}
              </div>
              {k.status === 'PROPOSED' && (
                <div className="mt-1 flex gap-2">
                  <button className={btn} disabled={busy} onClick={() => act(`/${encodeURIComponent(k.key_ref)}/activate`)}>Activate</button>
                  <button className={btn} disabled={busy} onClick={() => act(`/${encodeURIComponent(k.key_ref)}/reject`)}>Reject</button>
                  <span className="self-center text-[var(--text-muted)]">a second executive, not the one who proposed it</span>
                </div>
              )}
              {k.status === 'ACTIVE' && (
                <div className="mt-1 flex gap-2">
                  <input aria-label={`Reason to revoke ${k.key_ref}`} placeholder="Reason to revoke"
                         value={reason[k.key_ref] ?? ''} onChange={e => setReason({ ...reason, [k.key_ref]: e.target.value })}
                         className="flex-1 rounded border border-[var(--border)] bg-transparent px-2 py-1" />
                  <button className={btn} disabled={busy || !(reason[k.key_ref] ?? '').trim()}
                          onClick={() => act(`/${encodeURIComponent(k.key_ref)}/revoke`, { reason: reason[k.key_ref] })}>Revoke</button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {keys && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <input aria-label="Public key (base64)" placeholder="ed25519 public key, base64" value={publicKey}
                 onChange={e => setPublicKey(e.target.value)}
                 className="min-w-[18rem] flex-1 rounded border border-[var(--border)] bg-transparent px-2 py-1 font-mono" />
          <input aria-label="Label" placeholder="Label (optional)" value={label} onChange={e => setLabel(e.target.value)}
                 className="rounded border border-[var(--border)] bg-transparent px-2 py-1" />
          <button className={btn} disabled={busy || !publicKey.trim()}
                  onClick={() => act('', { public_key: publicKey.trim(), label: label.trim() || null })
                    .then(ok => { if (ok) { setPublicKey(''); setLabel('') } })}>Propose key</button>
        </div>
      )}
    </section>
  )
}
