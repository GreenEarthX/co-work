/**
 * Your telephone number — the account's own, which its owner may change
 * (JML, 2026-11-03). GET/PUT /api/v1/auth/telephone; the server normalises
 * spacing and refuses anything that is not a number. A verification call GEX
 * already recorded stays recorded.
 */
import { useEffect, useState } from 'react'
import { CheckCircle2, Phone } from 'lucide-react'

async function call<T>(init: RequestInit = {}): Promise<T> {
  const res = await fetch('/api/v1/auth/telephone', {
    ...init, headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `The server answered ${res.status}.`)
  return body as T
}

export function TelephoneSection() {
  const [saved, setSaved] = useState<string | null | undefined>(undefined)
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    call<{ telephone: string | null }>()
      .then(r => { setSaved(r.telephone); setValue(r.telephone ?? '') })
      .catch(e => setError(e.message))
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setError(null); setNotice(null)
    try {
      const r = await call<{ telephone: string; changed: boolean }>({ method: 'PUT', body: JSON.stringify({ telephone: value }) })
      setSaved(r.telephone); setValue(r.telephone)
      setNotice(r.changed ? 'Telephone number saved.' : 'That is already your number.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally { setBusy(false) }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
        <Phone className="h-4 w-4" /> Your telephone number
      </div>
      <label className="block space-y-1 text-xs font-semibold text-[var(--text-secondary)]">
        <span>Telephone</span>
        <input type="tel" autoComplete="tel" value={value} onChange={e => setValue(e.target.value)}
               placeholder={saved === null ? 'Not recorded' : ''}
               className="w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm" />
      </label>
      <p className="text-[11px] text-[var(--text-muted)]">
        GEX uses this number to reach you. Changing it does not undo a verification call already made.
      </p>
      {error && <p className="text-[11px] font-semibold text-red-700 dark:text-red-300">{error}</p>}
      {notice && <p className="flex items-center gap-1 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300"><CheckCircle2 className="h-3.5 w-3.5" /> {notice}</p>}
      <button type="submit" disabled={busy || saved === undefined || value.trim() === '' || value.trim() === saved}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">
        Save number
      </button>
    </form>
  )
}
