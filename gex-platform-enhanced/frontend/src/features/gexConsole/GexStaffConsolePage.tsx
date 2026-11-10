// Screen: GEX staff console (/gex-console)
/**
 * GEX's own security and permissions screen (JML, 2026-11-03). The CISO pages
 * are a client company's view of itself; this one is GEX's: who administers the
 * platform, which companies are on it, what GEX staff may do, and where each
 * client's onboarding stands — with the vetting actions where GEX is the actor.
 *
 * Reads: GET /api/v1/gex-console/summary, /onboarding/{company}, /ledger-anchor
 * and /api/v1/account/vetting-queue. Every action posts to /api/v1/account/{id}/…,
 * which enforces the rule (activator ≠ the employee who made the call, both
 * pieces of vetting on file). The screen greys out what the server would
 * refuse; it never decides alone.
 */
import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Circle, ShieldCheck, XCircle } from 'lucide-react'
import { cisoCall } from '@/features/ciso/cisoApi'

const DEFAULT_ONBOARDING = 'mohring_energie'

interface Admin { user_id: string; email: string; user_name: string; account_state: string; activated_by: string | null; last_sign_in: string | null }
interface Company { company_id: string; company_name: string; company_type: string; is_test: boolean; accounts: Record<string, number>; projects_owned: number; test_projects_owned: number }
interface Summary {
  caller_user_id: string
  administrators: Admin[]
  companies: Company[]
  vetting_queue_count: number
  staff_rights: { readable_on_every_project: string[]; may: string[]; may_not: string[]; reviewer_gates: Record<string, string[]> }
}
export interface Account {
  user_id: string; email: string; user_name: string; account_state: string
  phone_verified_by: string | null; agreement_ref: string | null; company_name?: string
  /** The account's current number (alembic 081); its owner may change it. */
  telephone?: string | null
}
interface Step { key: string; label: string; actor: string; status: 'done' | 'waiting' | 'blocked'; detail: string }
interface Onboarding { company_id: string; company_name: string; accounts: Account[]; steps: Step[] }

const card = 'rounded-2xl border border-[var(--border)] bg-[var(--surface)]'
const th = 'px-3 py-2 text-left font-semibold text-[var(--text-muted)]'
const td = 'px-3 py-2 align-top'
const btn = 'rounded-md border border-[var(--border)] px-2 py-1 text-[11px] font-semibold hover:bg-[var(--surface-hover,rgba(0,0,0,0.04))] disabled:cursor-not-allowed disabled:opacity-40'

const fmt = (v: string | null) => (v ? v.slice(0, 16).replace('T', ' ') : '—')

function StepIcon({ status }: { status: Step['status'] }) {
  if (status === 'done') return <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-label="done" />
  if (status === 'blocked') return <XCircle className="h-4 w-4 text-red-600" aria-label="blocked" />
  return <Circle className="h-4 w-4 text-[var(--text-muted)]" aria-label="waiting" />
}

// ── One vetting action: a small form posted to /api/v1/account/{id}/{path} ──
interface Field { name: string; label: string; type?: 'text' | 'date' | 'checkbox'; initial?: string }
interface ActionSpec { key: string; label: string; path: string; fields: Field[]; disabled?: string }

function actionsFor(a: Account, callerId: string, companyId?: string): ActionSpec[] {
  const s = a.account_state
  const vetting = s === 'PENDING' || s === 'IN_VETTING'
  const out: ActionSpec[] = []
  if (s === 'PENDING') out.push({ key: 'claim', label: 'Take on', path: 'claim', fields: [{ name: 'note', label: 'Note' }] })
  if (vetting) {
    out.push({ key: 'call', label: 'Record call', path: 'telephone-verification', fields: [
      { name: 'telephone_called', label: 'Number called', initial: a.telephone ?? '' },
      { name: 'spoke_with', label: 'Spoke with' },
      { name: 'identity_confirmed', label: 'Identity confirmed', type: 'checkbox' },
      { name: 'organisation_confirmed', label: 'Organisation confirmed', type: 'checkbox' },
      { name: 'notes', label: 'Notes' },
    ] })
    out.push({ key: 'agreement', label: 'Record agreement', path: 'usage-agreement', fields: [
      { name: 'agreement_ref', label: 'Agreement reference' },
      { name: 'agreement_version', label: 'Version' },
      { name: 'signed_by', label: 'Signed by' },
      { name: 'signed_on', label: 'Signed on', type: 'date' },
    ] })
    const missing = !(a.phone_verified_by && a.agreement_ref)
    out.push({
      key: 'activate', label: 'Activate', path: 'activate',
      fields: [{ name: 'company_id', label: 'Company id', initial: companyId ?? '' }, { name: 'note', label: 'Note' }],
      disabled: missing ? 'Needs the verification call and the signed agreement on file first'
        : a.phone_verified_by === callerId ? 'You made the verification call: another GEX admin must activate'
        : undefined,
    })
    out.push({ key: 'reject', label: 'Reject', path: 'reject', fields: [{ name: 'reason', label: 'Reason (10+ characters)' }] })
  }
  if (s === 'ACTIVE') out.push({ key: 'suspend', label: 'Suspend', path: 'suspend', fields: [{ name: 'reason', label: 'Reason (10+ characters)' }] })
  return out
}

export function AccountActions({ account, callerId, companyId, onDone }:
  { account: Account; callerId: string; companyId?: string; onDone: () => void }) {
  const [open, setOpen] = useState<ActionSpec | null>(null)
  const [values, setValues] = useState<Record<string, string | boolean>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const start = (spec: ActionSpec) => {
    setOpen(spec); setError(null)
    setValues(Object.fromEntries(spec.fields.map(f => [f.name, f.type === 'checkbox' ? false : (f.initial ?? '')])))
  }
  const submit = async () => {
    if (!open) return
    setBusy(true); setError(null)
    try {
      await cisoCall(`/account/${encodeURIComponent(account.user_id)}/${open.path}`, undefined,
        { method: 'POST', body: JSON.stringify(values) })
      setOpen(null); onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {actionsFor(account, callerId, companyId).map(spec => (
          <button key={spec.key} className={btn} disabled={!!spec.disabled} title={spec.disabled}
                  onClick={() => start(spec)}>{spec.label}</button>
        ))}
      </div>
      {open && (
        <div className="space-y-2 rounded-lg border border-[var(--border)] p-3" role="form" aria-label={open.label}>
          <div className="text-[11px] font-bold text-[var(--text-primary)]">{open.label} — {account.user_name || account.email}</div>
          {open.fields.map(f => (
            <label key={f.name} className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">
              <span className="w-40 shrink-0">{f.label}</span>
              {f.type === 'checkbox'
                ? <input type="checkbox" checked={!!values[f.name]} onChange={e => setValues(v => ({ ...v, [f.name]: e.target.checked }))} />
                : <input type={f.type ?? 'text'} value={String(values[f.name] ?? '')}
                         className="flex-1 rounded border border-[var(--border)] bg-transparent px-2 py-1"
                         onChange={e => setValues(v => ({ ...v, [f.name]: e.target.value }))} />}
            </label>
          ))}
          {error && <div className="text-[11px] text-red-700 dark:text-red-300">{error}</div>}
          <div className="flex gap-2">
            <button className={btn} disabled={busy} onClick={submit}>Record</button>
            <button className={btn} disabled={busy} onClick={() => setOpen(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

interface AnchorHealth {
  backend: string
  worker_running: boolean
  worker_refused: string[]
  last_run_at: string | null
  last_error: string | null
  by_status: Record<string, { count: number; without_pseudo_id: number; oldest: string | null }>
  failed: { event_hash: string; event_type: string; attempts: number; last_error: string | null; created_at: string | null }[]
}

const ANCHOR_STATUSES = ['PENDING', 'ANCHORED', 'NOT_ANCHORED', 'FAILED'] as const

/** Phase 4 of "One contract record": the ledger anchor outbox and its worker.
 *  Hashes and statuses only; a read failure says so, never shows zeros. */
export function LedgerAnchorPanel() {
  const [h, setH] = useState<AnchorHealth | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    cisoCall<AnchorHealth>('/gex-console/ledger-anchor')
      .then(r => { setH(r); setError(null) })
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
  }, [])
  const worker = !h ? '' : h.backend === 'none'
    ? 'Off (LEDGER_ANCHOR_BACKEND = none): no event leaves for a ledger'
    : h.worker_running ? `On (${h.backend}), last pass ${fmt(h.last_run_at)}`
      : `Switched on (${h.backend}) but NOT running: ${(h.worker_refused ?? []).join('; ') || 'not started'}`
  return (
    <section className={`${card} p-4`} data-testid="ledger-anchor">
      <h2 className="text-sm font-bold text-[var(--text-primary)]">Ledger anchor</h2>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">
        Each contract event's hash, under a pseudonymous id, for a public ledger. No terms, names or company ids leave.
      </p>
      {error && <p className="mt-2 text-xs text-red-700 dark:text-red-300">The outbox could not be read: {error}</p>}
      {h && (
        <>
          <p className="mt-2 text-xs"><span className="font-semibold">Worker:</span> {worker}</p>
          {h.last_error && <p className="mt-1 text-xs text-red-700 dark:text-red-300">Last pass failed: {h.last_error}</p>}
          <table className="mt-3 w-full text-xs">
            <thead><tr className="border-b border-[var(--border)]">
              {ANCHOR_STATUSES.map(s => <th key={s} className={th}>{s.replace('_', ' ').toLowerCase()}</th>)}
            </tr></thead>
            <tbody><tr>
              {ANCHOR_STATUSES.map(s => <td key={s} className={td} data-testid={`anchor-${s}`}>{h.by_status?.[s]?.count ?? 0}</td>)}
            </tr></tbody>
          </table>
          {(h.failed ?? []).length > 0 && (
            <>
              <h3 className="mt-3 text-xs font-bold text-red-700 dark:text-red-300">Failed after {h.failed[0].attempts} attempts · {h.failed.length}</h3>
              <ul className="mt-1 space-y-1 text-[11px] text-[var(--text-secondary)]">
                {h.failed.map(f => (
                  <li key={f.event_hash}><code>{f.event_hash.slice(0, 16)}…</code> {f.event_type} — {f.last_error ?? 'no error recorded'}</li>
                ))}
              </ul>
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">Requeue with scripts/drain_anchor_outbox.py --requeue-failed once the cause is fixed.</p>
            </>
          )}
        </>
      )}
    </section>
  )
}

export function GexStaffConsolePage() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [queue, setQueue] = useState<Account[]>([])
  const [companyId, setCompanyId] = useState(DEFAULT_ONBOARDING)
  const [onboarding, setOnboarding] = useState<Onboarding | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [s, q] = await Promise.all([
        cisoCall<Summary>('/gex-console/summary'),
        cisoCall<{ applications: Account[] }>('/account/vetting-queue'),
      ])
      setSummary(s); setQueue(q.applications); setError(null)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }, [])

  const loadOnboarding = useCallback(async () => {
    if (!companyId) return
    try { setOnboarding(await cisoCall<Onboarding>(`/gex-console/onboarding/${encodeURIComponent(companyId)}`)) }
    catch (e) { setOnboarding(null); setError(e instanceof Error ? e.message : String(e)) }
  }, [companyId])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadOnboarding() }, [loadOnboarding])
  const refresh = () => { load(); loadOnboarding() }

  if (error && !summary) {
    return (
      <div className="mx-auto max-w-xl rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-900/20 dark:text-red-200">
        <div className="flex items-center gap-2 font-bold"><AlertTriangle className="h-4 w-4" /> GEX staff console</div>
        <p className="mt-2">{error}</p>
      </div>
    )
  }
  if (!summary) return <div className="p-6 text-sm text-[var(--text-muted)]">Loading the staff console…</div>

  const callerId = summary.caller_user_id
  const accountsById = new Map((onboarding?.accounts ?? []).map(a => [a.user_id, a]))

  return (
    <div className="mx-auto max-w-[1280px] space-y-5">
      <div>
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-indigo-700 dark:text-indigo-300">
          <ShieldCheck className="h-4 w-4" /> GEX staff
        </div>
        <h1 className="mt-1 text-2xl font-black text-[var(--text-primary)]">Staff console: permissions and onboarding</h1>
        <p className="mt-1 max-w-4xl text-sm text-[var(--text-secondary)]">
          GEX's own view. Each action goes to the endpoint that enforces its rule; a greyed-out
          button says what the server would refuse.
        </p>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-900/20 dark:text-red-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
        </div>
      )}

      {/* ── Client onboarding ── */}
      <section className={`${card} p-4`}>
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Client onboarding</h2>
          <select aria-label="Company" value={companyId} onChange={e => setCompanyId(e.target.value)}
                  className="rounded border border-[var(--border)] bg-transparent px-2 py-1 text-xs">
            {summary.companies.map(c => (
              <option key={c.company_id} value={c.company_id}>{c.company_name}{c.is_test ? ' (TEST)' : ''}</option>
            ))}
          </select>
        </div>
        <table className="mt-3 w-full text-xs">
          <thead><tr className="border-b border-[var(--border)]">
            <th className={th}></th><th className={th}>Step</th><th className={th}>Who acts</th><th className={th}>Record</th><th className={th}></th>
          </tr></thead>
          <tbody>
            {(onboarding?.steps ?? []).map(s => {
              const uid = s.key.startsWith('claim:') ? s.key.slice(6) : null
              const account = uid ? accountsById.get(uid) : undefined
              return (
                <tr key={s.key} className="border-b border-[var(--border)] last:border-0" data-testid={`step-${s.key}`}>
                  <td className={td}><StepIcon status={s.status} /></td>
                  <td className={`${td} font-semibold text-[var(--text-primary)]`}>{s.label}</td>
                  <td className={`${td} text-[var(--text-secondary)]`}>{s.actor}</td>
                  <td className={`${td} text-[var(--text-secondary)]`}>{s.detail}</td>
                  <td className={td}>
                    {account && <AccountActions account={account} callerId={callerId} companyId={onboarding?.company_id} onDone={refresh} />}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>

      {/* ── Vetting queue ── */}
      <section className={`${card} p-4`}>
        <h2 className="text-sm font-bold text-[var(--text-primary)]">Vetting queue · {queue.length}</h2>
        {queue.length === 0
          ? <p className="mt-2 text-xs text-[var(--text-muted)]">No application is waiting.</p>
          : (
            <table className="mt-3 w-full text-xs">
              <thead><tr className="border-b border-[var(--border)]">
                <th className={th}>Applicant</th><th className={th}>Company (as stated)</th><th className={th}>State</th><th className={th}>Call</th><th className={th}>Agreement</th><th className={th}></th>
              </tr></thead>
              <tbody>
                {queue.map(a => (
                  <tr key={a.user_id} className="border-b border-[var(--border)] last:border-0">
                    <td className={td}>
                      <div className="font-semibold">{a.user_name}</div>
                      <div className="text-[var(--text-muted)]">{a.email}</div>
                      <div className="text-[var(--text-muted)]">{a.telephone ?? 'No telephone recorded'}</div>
                    </td>
                    <td className={td}>{a.company_name}</td>
                    <td className={td}>{a.account_state}</td>
                    <td className={td}>{a.phone_verified_by ?? '—'}</td>
                    <td className={td}>{a.agreement_ref ?? '—'}</td>
                    <td className={td}><AccountActions account={a} callerId={callerId} onDone={refresh} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* ── GEX administrators ── */}
        <section className={`${card} p-4`}>
          <h2 className="text-sm font-bold text-[var(--text-primary)]">GEX administrators · {summary.administrators.length}</h2>
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">Each can read every company's gates and evidence. Suspend one you do not recognise.</p>
          <table className="mt-3 w-full text-xs">
            <thead><tr className="border-b border-[var(--border)]">
              <th className={th}>Account</th><th className={th}>How created</th><th className={th}>Last sign-in</th><th className={th}></th>
            </tr></thead>
            <tbody>
              {summary.administrators.map(a => (
                <tr key={a.user_id} className="border-b border-[var(--border)] last:border-0">
                  <td className={td}><div className="font-semibold">{a.email}</div><div className="text-[var(--text-muted)]">{a.account_state}</div></td>
                  <td className={td}>{a.activated_by ?? 'Not recorded'}</td>
                  <td className={td}>{fmt(a.last_sign_in)}</td>
                  <td className={td}>
                    {a.user_id === callerId
                      ? <span className="text-[var(--text-muted)]">You</span>
                      : <AccountActions account={{ ...a, phone_verified_by: null, agreement_ref: null }} callerId={callerId} onDone={refresh} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {/* ── What GEX staff may do ── */}
        <section className={`${card} p-4`}>
          <h2 className="text-sm font-bold text-[var(--text-primary)]">What GEX staff may do</h2>
          <ul className="mt-2 space-y-1 text-xs text-[var(--text-secondary)]">
            {summary.staff_rights.may.map(m => <li key={m} className="flex gap-2"><CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" />{m}</li>)}
          </ul>
          <h3 className="mt-3 text-xs font-bold text-[var(--text-primary)]">What GEX staff may not do</h3>
          <ul className="mt-2 space-y-1 text-xs text-[var(--text-secondary)]">
            {summary.staff_rights.may_not.map(m => <li key={m} className="flex gap-2"><XCircle className="h-3.5 w-3.5 shrink-0 text-red-600" />{m}</li>)}
          </ul>
          <h3 className="mt-3 text-xs font-bold text-[var(--text-primary)]">Who verifies which gate</h3>
          <ul className="mt-2 space-y-0.5 text-xs text-[var(--text-secondary)]">
            {Object.entries(summary.staff_rights.reviewer_gates).map(([role, gates]) =>
              <li key={role}><span className="font-semibold">{role.replace(/_/g, ' ').toLowerCase()}</span>: {gates.join(', ')}</li>)}
          </ul>
        </section>
      </div>

      {/* ── Companies ── */}
      <section className={`${card} p-4`}>
        <h2 className="text-sm font-bold text-[var(--text-primary)]">Companies · {summary.companies.length}</h2>
        <table className="mt-3 w-full text-xs">
          <thead><tr className="border-b border-[var(--border)]">
            <th className={th}>Company</th><th className={th}>Type</th><th className={th}>Accounts</th><th className={th}>Projects owned</th>
          </tr></thead>
          <tbody>
            {summary.companies.map(c => (
              <tr key={c.company_id} className="border-b border-[var(--border)] last:border-0">
                <td className={td}>
                  <span className="font-semibold">{c.company_name}</span>
                  {c.is_test && <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">TEST</span>}
                  <div className="text-[var(--text-muted)]">{c.company_id}</div>
                </td>
                <td className={td}>{c.company_type}</td>
                <td className={td}>{Object.entries(c.accounts).map(([s, n]) => `${n} ${s.toLowerCase()}`).join(', ') || 'none'}</td>
                <td className={td}>{c.projects_owned}{c.test_projects_owned ? ` (${c.test_projects_owned} TEST)` : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <LedgerAnchorPanel />
    </div>
  )
}
