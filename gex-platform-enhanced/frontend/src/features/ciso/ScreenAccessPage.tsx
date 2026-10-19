// Screen: CISO screen access tailoring (/ciso-screen-access)
/**
 * Screen Access by Role — a client CISO tailors, for their own company, which
 * screens each business function may open.
 *
 * Default: menuArchitecture.ts `visible_to` + the executive default (an EXECUTIVE
 * sees every screen of its company type). A rule flips one cell:
 *   ALLOW — open a screen the function does not have by default,
 *   DENY  — close a screen it does have.
 * Only screens within the company's scope are listed (open by default to some
 * function of the same company type), so a company cannot open itself a screen
 * meant for another kind of party. Navigation only — data access is unchanged.
 *
 * Backend: GET/PUT /api/v1/ciso/screen-access (governance domain: EXECUTIVE writes;
 * company taken from the token). Schema: alembic 060.
 */
import { useEffect, useMemo, useState } from 'react'
import { ShieldCheck, Save, RotateCcw, AlertTriangle, CheckCircle2, Lock } from 'lucide-react'
import { useUserRole } from '@/contexts/UserRoleContext'
import {
  MENU_TABS, defaultVisible, inCompanyScope,
  type BusinessFunction, type MenuItem,
} from '@/config/menuArchitecture'
import {
  fetchScreenAccessRules, saveScreenAccessRules, setScreenAccessRules,
  type ScreenRule, type ScreenRuleEffect,
} from '@/lib/screenAccess'

const FUNCTION_LABELS: Record<BusinessFunction, string> = {
  EXECUTIVE: 'Executive',
  FINANCE_TREASURY: 'Finance',
  COMMERCIAL: 'Commercial',
  ENGINEERING: 'Engineering',
  OPERATIONS: 'Operations',
  COMPLIANCE_LEGAL: 'Compliance & Legal',
}
const COLUMN_ORDER: BusinessFunction[] = [
  'EXECUTIVE', 'FINANCE_TREASURY', 'COMMERCIAL', 'ENGINEERING', 'OPERATIONS', 'COMPLIANCE_LEGAL',
]

const k = (screenId: string, fn: string) => `${screenId}|${fn}`

export function ScreenAccessPage() {
  const { role } = useUserRole()
  const cisoSession = typeof window !== 'undefined' && sessionStorage.getItem('gex_ciso_session') === 'true'

  const [saved, setSaved] = useState<Map<string, ScreenRuleEffect>>(new Map())
  const [draft, setDraft] = useState<Map<string, ScreenRuleEffect>>(new Map())
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // Screens within the company's scope, grouped by menu tab, each listed once.
  const groups = useMemo(() => {
    const seen = new Set<string>()
    return MENU_TABS.map(tab => ({
      label: tab.label,
      items: tab.items.filter(i => {
        if (seen.has(i.id) || !inCompanyScope(i, role)) return false
        seen.add(i.id)
        return true
      }),
    })).filter(g => g.items.length > 0)
  }, [role])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchScreenAccessRules()
      .then(rules => {
        if (cancelled) return
        const m = new Map(rules.map(r => [k(r.screen_id, r.business_function), r.effect]))
        setSaved(m); setDraft(new Map(m)); setError(null)
      })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [role.company_name])

  const isDefault = (item: MenuItem, fn: BusinessFunction) =>
    defaultVisible(item, { ...role, business_function: fn })

  const toggle = (item: MenuItem, fn: BusinessFunction) => {
    setNotice(null)
    setDraft(prev => {
      const next = new Map(prev)
      const id = k(item.id, fn)
      if (next.has(id)) next.delete(id)                       // back to the default
      else next.set(id, isDefault(item, fn) ? 'DENY' : 'ALLOW') // flip the default
      return next
    })
  }

  const changes = useMemo(() => {
    const keys = new Set([...saved.keys(), ...draft.keys()])
    let n = 0
    keys.forEach(id => { if (saved.get(id) !== draft.get(id)) n += 1 })
    return n
  }, [saved, draft])

  const save = async () => {
    setBusy(true); setError(null); setNotice(null)
    try {
      const rules: ScreenRule[] = [...draft.entries()].map(([id, effect]) => {
        const [screen_id, business_function] = id.split('|')
        return { screen_id, business_function, effect }
      })
      const result = await saveScreenAccessRules(rules)
      const m = new Map(result.map(r => [k(r.screen_id, r.business_function), r.effect]))
      setSaved(m); setDraft(new Map(m))
      setScreenAccessRules(role.company_name, result)   // the menu follows at once
      setNotice(`Saved. ${result.length} rule${result.length === 1 ? '' : 's'} now apply to everyone at ${role.company_name}.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (!cisoSession) {
    return (
      <div className="mx-auto max-w-xl rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-sm">
        <div className="flex items-center gap-2 font-bold text-[var(--text-primary)]"><Lock className="h-4 w-4" /> CISO administration</div>
        <p className="mt-2 text-[var(--text-secondary)]">Open this screen from the CISO menu after entering the company security password.</p>
      </div>
    )
  }

  const overrides = draft.size

  return (
    <div className="mx-auto max-w-[1280px] space-y-5">
      <div>
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-indigo-700 dark:text-indigo-300">
          <ShieldCheck className="h-4 w-4" /> CISO · {role.company_name}
        </div>
        <h1 className="mt-1 text-2xl font-black text-[var(--text-primary)]">Screen access by role</h1>
        <p className="mt-1 max-w-4xl text-sm text-[var(--text-secondary)]">
          The platform default decides which screens each department of {role.company_name} can open; executives see every
          screen of the company by default. Here you can open a screen to a department that does not have it, or close one
          it has. A second click on a changed cell returns it to the default. Only screens that some department of this kind
          of company can open are listed. Changes apply to everyone at {role.company_name}, in the menu and in the address bar.
          They do not widen data access: each screen still shows only what the project rights allow.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-xs text-[var(--text-secondary)]">
        <span className="flex items-center gap-1.5"><Cell state="default-on" /> Open by default</span>
        <span className="flex items-center gap-1.5"><Cell state="default-off" /> Closed by default</span>
        <span className="flex items-center gap-1.5"><Cell state="allow" /> Opened by the CISO</span>
        <span className="flex items-center gap-1.5"><Cell state="deny" /> Closed by the CISO</span>
        <span className="ml-auto">{overrides} rule{overrides === 1 ? '' : 's'} in force{changes > 0 ? ` · ${changes} unsaved change${changes === 1 ? '' : 's'}` : ''}</span>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-900/20 dark:text-red-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
        </div>
      )}
      {notice && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-900/20 dark:text-emerald-200">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> {notice}
        </div>
      )}

      <div className="overflow-x-auto rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[var(--border)]">
              <th className="px-4 py-3 text-left font-semibold text-[var(--text-muted)]">Screen</th>
              {COLUMN_ORDER.map(fn => (
                <th key={fn} className="px-2 py-3 text-center font-semibold text-[var(--text-muted)]">{FUNCTION_LABELS[fn]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={COLUMN_ORDER.length + 1} className="px-4 py-6 text-center text-[var(--text-muted)]">Loading the company's rules…</td></tr>
            ) : groups.map(g => (
              <Group key={g.label} label={g.label} items={g.items}
                     isDefault={isDefault} draft={draft} saved={saved} onToggle={toggle} />
            ))}
          </tbody>
        </table>
      </div>

      <div className="sticky bottom-3 flex items-center justify-end gap-2">
        <button
          onClick={() => { setDraft(new Map(saved)); setNotice(null) }}
          disabled={changes === 0 || busy}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-secondary)] disabled:opacity-40"
        >
          <RotateCcw className="h-4 w-4" /> Discard changes
        </button>
        <button
          onClick={save}
          disabled={changes === 0 || busy}
          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-40"
        >
          <Save className="h-4 w-4" /> {busy ? 'Saving…' : 'Save rules'}
        </button>
      </div>
    </div>
  )
}

type CellState = 'default-on' | 'default-off' | 'allow' | 'deny'

function Cell({ state, pending }: { state: CellState; pending?: boolean }) {
  const base = 'inline-flex h-6 min-w-[2.25rem] items-center justify-center rounded-md border px-1.5 text-[11px] font-bold'
  const cls: Record<CellState, string> = {
    'default-on':  'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-900/20 dark:text-emerald-300',
    'default-off': 'border-[var(--border)] bg-transparent text-[var(--text-muted)]',
    allow:         'border-emerald-600 bg-emerald-600 text-white',
    deny:          'border-red-600 bg-red-600 text-white',
  }
  const text: Record<CellState, string> = { 'default-on': '✓', 'default-off': '–', allow: 'Open', deny: 'Closed' }
  return <span className={`${base} ${cls[state]} ${pending ? 'ring-2 ring-indigo-400 ring-offset-1' : ''}`}>{text[state]}</span>
}

function Group({ label, items, isDefault, draft, saved, onToggle }: {
  label: string
  items: MenuItem[]
  isDefault: (item: MenuItem, fn: BusinessFunction) => boolean
  draft: Map<string, ScreenRuleEffect>
  saved: Map<string, ScreenRuleEffect>
  onToggle: (item: MenuItem, fn: BusinessFunction) => void
}) {
  return (
    <>
      <tr className="bg-[var(--surface-muted,#f5f5f4)]">
        <td colSpan={COLUMN_ORDER.length + 1} className="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">{label}</td>
      </tr>
      {items.map(item => (
        <tr key={item.id} className="border-t border-[var(--border)]">
          <td className="px-4 py-2">
            <div className="font-semibold text-[var(--text-primary)]">{item.label}</div>
            <div className="font-mono text-[10px] text-[var(--text-muted)]">{item.path}</div>
          </td>
          {COLUMN_ORDER.map(fn => {
            const id = k(item.id, fn)
            const rule = draft.get(id)
            const state: CellState = rule === 'ALLOW' ? 'allow' : rule === 'DENY' ? 'deny' : isDefault(item, fn) ? 'default-on' : 'default-off'
            const pending = saved.get(id) !== rule
            return (
              <td key={fn} className="px-2 py-2 text-center">
                <button
                  onClick={() => onToggle(item, fn)}
                  title={`${item.label} · ${FUNCTION_LABELS[fn]}: ${rule ? 'changed by the CISO — click to return to the default' : 'platform default — click to change'}`}
                  aria-label={`${item.label}, ${FUNCTION_LABELS[fn]}`}
                >
                  <Cell state={state} pending={pending} />
                </button>
              </td>
            )
          })}
        </tr>
      ))}
    </>
  )
}
