import { NavLink } from 'react-router-dom'
import {
  LayoutGrid,
  BarChart2,
  Building2,
  FileText,
  Settings,
  type LucideIcon,
} from 'lucide-react'

interface NavItem {
  to: string
  icon: LucideIcon
  label: string
}

const NAV_ITEMS: NavItem[] = [
  { to: '/capacity',    icon: LayoutGrid,  label: 'INVENTORY' },
  { to: '/marketplace', icon: BarChart2,   label: 'TRADE'     },
  { to: '/matching',    icon: Building2,   label: 'COMPANY'   },
  { to: '/reports',     icon: FileText,    label: 'REPORTS'   },
  { to: '/settings',    icon: Settings,    label: 'SETTINGS'  },
]

export function Sidebar() {
  return (
    <aside
      style={{ width: 'var(--sidebar-w)', minHeight: 'calc(100vh - var(--header-h))' }}
      className="bg-white border-r border-[#e2e8f0] flex flex-col items-center pt-2 pb-4 shrink-0"
    >
      {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex flex-col items-center gap-1 w-full py-3 px-1 cursor-pointer
             transition-colors duration-150 group
             ${isActive
               ? 'text-[#0ea5a0]'
               : 'text-[#94a3b8] hover:text-[#0ea5a0]'
             }`
          }
        >
          {({ isActive }) => (
            <>
              <span
                className={`flex items-center justify-center w-9 h-9 rounded-lg transition-colors
                  ${isActive
                    ? 'bg-[#f0fdf9] text-[#0ea5a0]'
                    : 'text-[#94a3b8] group-hover:bg-[#f0fdf9] group-hover:text-[#0ea5a0]'
                  }`}
              >
                <Icon size={18} strokeWidth={isActive ? 2 : 1.75} />
              </span>
              <span
                style={{ fontSize: '0.58rem', letterSpacing: '0.08em' }}
                className={`font-bold uppercase tracking-widest
                  ${isActive ? 'text-[#0ea5a0]' : 'text-[#94a3b8] group-hover:text-[#0ea5a0]'}`}
              >
                {label}
              </span>
            </>
          )}
        </NavLink>
      ))}
    </aside>
  )
}
