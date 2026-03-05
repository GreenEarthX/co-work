import { Outlet } from 'react-router-dom'
import { WorkspaceSwitcher } from './WorkspaceSwitcher'
import { useWorkspace } from '@/contexts/WorkspaceContext'

export function Layout() {
  const { currentWorkspace } = useWorkspace()

  return (
    <div className="min-h-screen bg-[#f5f6f8]">
      {/* Top Bar */}
      <header className="h-[56px] bg-white border-b border-[#e2e8f0] px-6 flex items-center justify-between sticky top-0 z-40">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-[#0ea5a0] flex items-center justify-center">
            <span className="text-white font-black text-base tracking-tight">GEX</span>
          </div>
          <div>
            <div className="font-bold text-[#0f172a] text-sm leading-tight">GreenEarthX</div>
            <div className="text-[0.65rem] text-[#64748b] leading-tight">Orchestrator OS</div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Search */}
          <div className="hidden md:block">
            <input
              type="search"
              placeholder="Search..."
              className="w-56 px-3 py-1.5 border border-[#e2e8f0] rounded text-sm text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:ring-2 focus:ring-[#0ea5a0]/20 focus:border-[#0ea5a0] transition-colors"
            />
          </div>

          {/* Workspace Switcher */}
          <WorkspaceSwitcher />

          {/* User avatar */}
          <div className="w-8 h-8 rounded-full bg-[#0ea5a0] text-white flex items-center justify-center text-xs font-bold">
            JM
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Left Sidebar - Dynamic based on workspace */}
        <aside className="w-56 bg-white border-r border-[#e2e8f0] min-h-[calc(100vh-56px)] sticky top-[56px]">
          <div className="p-3">
            <div className="text-[0.6rem] font-bold text-[#94a3b8] uppercase tracking-widest mb-2 px-2">
              OS Menu
            </div>

            <nav className="space-y-0.5">
              {currentWorkspace.navigation.map((item) => {
                const Icon = item.icon
                const isActive = window.location.pathname === item.path

                return (
                  <a
                    key={item.path}
                    href={item.path}
                    className={`flex items-center gap-3 px-3 py-2 rounded transition-colors ${
                      isActive
                        ? 'bg-[#f0fdf9] text-[#0ea5a0] font-semibold'
                        : 'text-[#475569] hover:bg-[#f8fafc] hover:text-[#0f172a]'
                    }`}
                  >
                    <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-[#0ea5a0]' : 'text-[#94a3b8]'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-[0.8125rem] truncate leading-tight">{item.name}</div>
                      {item.description && (
                        <div className="text-[0.65rem] text-[#94a3b8] truncate leading-tight mt-0.5">
                          {item.description}
                        </div>
                      )}
                    </div>
                    {item.badge && (
                      <span className="px-1.5 py-0.5 bg-red-100 text-red-600 text-[0.6rem] font-bold rounded-full">
                        {item.badge}
                      </span>
                    )}
                  </a>
                )
              })}
            </nav>
          </div>

          {/* Workspace Indicator */}
          <div className="absolute bottom-0 left-0 right-0 p-3 border-t border-[#e2e8f0] bg-white">
            <div className="text-[0.65rem] text-[#94a3b8] uppercase tracking-widest font-bold">
              Current Workspace
            </div>
            <div className="mt-0.5 text-sm text-[#0f172a] font-bold">{currentWorkspace.name}</div>
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 p-5">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
