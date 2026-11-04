// Screen: Change your password (/account/password)
/**
 * The owner changes their own password (JML, 2026-11-03) — in particular a
 * temporary one chosen by GEX at registration, which until changed lets anyone
 * at GEX who knows it act as the owner.
 *
 * Backend: GET /api/v1/auth/password-status (the rule, and whether a temporary
 * password is in force), POST /api/v1/auth/change-password (current password
 * required; the policy's refusal comes back as its reason; every other session
 * is signed out and this one receives a new refresh token).
 */
import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, KeyRound } from 'lucide-react'
import { replaceRefreshToken } from '@/lib/authToken'

export interface PasswordStatus {
  temporary: boolean
  policy: { min_length: number; max_length: number; note: string }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api/v1/auth${path}`, {
    ...init, headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = body?.detail
    throw new Error(typeof detail === 'string' ? detail : `The server answered ${res.status}.`)
  }
  return body as T
}

export const fetchPasswordStatus = () => call<PasswordStatus>('/password-status')

export function ChangePasswordPage() {
  const [status, setStatus] = useState<PasswordStatus | null>(null)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { fetchPasswordStatus().then(setStatus).catch(e => setError(e.message)) }, [])

  const min = status?.policy.min_length ?? 12
  const mismatch = again.length > 0 && next !== again
  const canSubmit = !busy && current.length > 0 && next.length >= min && next === again

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setError(null); setDone(null)
    try {
      const r = await call<{ message: string; refresh_token: string }>('/change-password', {
        method: 'POST', body: JSON.stringify({ current_password: current, new_password: next }),
      })
      replaceRefreshToken(r.refresh_token)
      setCurrent(''); setNext(''); setAgain('')
      setDone(r.message)
      setStatus(s => (s ? { ...s, temporary: false } : s))
      window.dispatchEvent(new Event('gex-password-changed'))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally { setBusy(false) }
  }

  const input = 'w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm'
  return (
    <div className="mx-auto max-w-lg space-y-4">
      <div>
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-indigo-700 dark:text-indigo-300">
          <KeyRound className="h-4 w-4" /> Your account
        </div>
        <h1 className="mt-1 text-2xl font-black text-[var(--text-primary)]">Change your password</h1>
      </div>

      {status?.temporary && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-900/20 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          You are signed in with a temporary password chosen by GEX. Until you change it, GEX staff who
          know it could act as you, and the record could not tell you apart.
        </div>
      )}
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-900/20 dark:text-red-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
        </div>
      )}
      {done && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-900/20 dark:text-emerald-200">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> {done}
        </div>
      )}

      <form onSubmit={submit} className="space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <label className="block space-y-1 text-xs font-semibold text-[var(--text-secondary)]">
          <span>Current password</span>
          <input type="password" autoComplete="current-password" className={input} value={current} onChange={e => setCurrent(e.target.value)} />
        </label>
        <label className="block space-y-1 text-xs font-semibold text-[var(--text-secondary)]">
          <span>New password</span>
          <input type="password" autoComplete="new-password" className={input} value={next} onChange={e => setNext(e.target.value)} />
        </label>
        <label className="block space-y-1 text-xs font-semibold text-[var(--text-secondary)]">
          <span>New password again</span>
          <input type="password" autoComplete="new-password" className={input} value={again} onChange={e => setAgain(e.target.value)} />
        </label>
        <p className="text-[11px] text-[var(--text-muted)]">
          At least {min} characters. {status?.policy.note ?? ''}
          {mismatch && <span className="ml-1 font-semibold text-red-700 dark:text-red-300">The two entries differ.</span>}
        </p>
        <p className="text-[11px] text-[var(--text-muted)]">Changing it signs you out everywhere else.</p>
        <button type="submit" disabled={!canSubmit}
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">
          Change password
        </button>
      </form>
    </div>
  )
}
