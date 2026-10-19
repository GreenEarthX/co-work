// Screen: route guard — a screen listed in the menu opens only for roles it is listed for
//
// The menu's `visible_to` is the ACCESS list (see menuArchitecture.ts: "Full ACCESS
// check — may the role reach this screen at all?"). Until 16 Oct 2026 it only
// governed what the menu showed: a user who typed a URL reached any screen, which
// let a bank open the internal CEO portfolio report. This guard applies the same
// rule to the address bar. Routes not listed in the menu are left to their own
// guards (GatedRoute, FinanceRouteGuard, the backend's 403).
import type { ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ShieldAlert, ArrowLeft } from 'lucide-react'
import { useUserRole } from '@/contexts/UserRoleContext'
import { MENU_TABS, isVisible, type MenuItem } from '@/config/menuArchitecture'

function normalise(path: string): string {
  return path.length > 1 ? path.replace(/\/+$/, '') : path
}

// The same screen is often reachable under a second address: App.tsx mounts most
// finance screens again under /finance/* for deep links. Those aliases must obey
// the same access list, or the second address becomes a way round the first.
const EXPLICIT_ALIASES: Record<string, string[]> = {
  '/finance': ['/finance-dashboard'],
  '/finance/dashboard': ['/finance-dashboard'],
  '/finance/bankers-snapshot': ['/bankability-snapshot'],
}

function candidatePaths(pathname: string): string[] {
  const p = normalise(pathname)
  // An explicit alias wins outright: /finance/dashboard is the finance dashboard,
  // not the project overview at /dashboard.
  if (EXPLICIT_ALIASES[p]) return [p, ...EXPLICIT_ALIASES[p]]
  const m = p.match(/^\/finance\/([^/]+)$/)
  return m ? [p, `/${m[1]}`, `/finance-${m[1]}`] : [p]
}

/** Menu items registered for this path or one of its aliases (several items may share one screen). */
export function menuItemsForPath(pathname: string): MenuItem[] {
  const candidates = new Set(candidatePaths(pathname))
  return MENU_TABS.flatMap(t => t.items).filter(i => candidates.has(normalise(i.path)))
}

export function MenuAccessGuard({ children, rulesReady = true }: { children: ReactNode; rulesReady?: boolean }) {
  const { pathname } = useLocation()
  const { role } = useUserRole()
  const navigate = useNavigate()
  const items = menuItemsForPath(pathname)

  // Not a menu screen, or at least one menu entry for it is open to this role.
  if (items.length === 0) return <>{children}</>
  // Wait for the company's CISO rules before deciding a menu screen, so a screen the
  // CISO closed never flashes open during loading. On a load failure the hook
  // reports ready and the platform defaults apply.
  if (!rulesReady) return null
  if (items.some(i => isVisible(i, role))) return <>{children}</>

  return (
    <div className="mx-auto mt-10 max-w-md border border-l-2 border-slate-300 border-l-red-700 bg-white dark:bg-slate-950 px-5 py-6">
      <div className="flex items-center gap-2 text-red-700 dark:text-red-300">
        <ShieldAlert className="h-4 w-4" />
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.12em]">Not part of your role</span>
      </div>
      <p className="mt-3 text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
        <span className="font-semibold">{items[0].label}</span> is not open to {role.company_name || 'your organisation'} in its
        current role. Screens are opened by role and by your company's security settings, not by address, so typing the address does not grant access.
      </p>
      <button
        type="button"
        onClick={() => navigate('/projects')}
        className="mt-4 inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to projects
      </button>
    </div>
  )
}
