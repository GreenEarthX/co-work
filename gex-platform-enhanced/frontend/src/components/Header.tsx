import { LogOut } from 'lucide-react'

interface HeaderProps {
  companyName?: string
  userName?: string
  profileCompletion?: number
  onLogout?: () => void
}

export function Header({
  companyName = 'GreenEarthX Platform',
  userName = 'User',
  profileCompletion = 0,
  onLogout,
}: HeaderProps) {
  return (
    <header
      style={{ height: 'var(--header-h)' }}
      className="bg-white border-b border-[#e2e8f0] px-5 flex items-center justify-between sticky top-0 z-50 shrink-0"
    >
      {/* ── Left: Company · User · Profile Completion ── */}
      <div className="flex items-center gap-0 min-w-0">
        {/* Company Name */}
        <span className="font-bold text-[#0ea5a0] text-[0.9375rem] whitespace-nowrap">
          {companyName}
        </span>

        {/* Pipe divider */}
        <span className="mx-4 text-[#e2e8f0] select-none">|</span>

        {/* User Name */}
        <span className="text-[#0f172a] text-sm font-medium whitespace-nowrap">
          {userName}
        </span>

        {/* Pipe divider */}
        <span className="mx-4 text-[#e2e8f0] select-none">|</span>

        {/* Profile Completion */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#64748b] whitespace-nowrap">
            Profile Completion {profileCompletion}%
          </span>
          <div className="gex-progress w-24 hidden sm:block">
            <div
              className="gex-progress-bar"
              style={{ width: `${profileCompletion}%` }}
            />
          </div>
        </div>
      </div>

      {/* ── Right: Logout + Logo ── */}
      <div className="flex items-center gap-3 shrink-0 ml-4">
        <button
          onClick={onLogout}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0ea5a0] text-white text-xs font-bold rounded tracking-wide uppercase hover:bg-[#0d9488] transition-colors"
        >
          <LogOut size={12} strokeWidth={2.5} />
          LOGOUT
        </button>

        {/* GEX Logo mark */}
        <div className="flex items-center gap-1 pl-1 border-l border-[#e2e8f0]">
          <svg width="34" height="24" viewBox="0 0 34 24" fill="none">
            {/* Leaf / G mark */}
            <circle cx="12" cy="12" r="10" fill="#0ea5a0" opacity="0.15" />
            <path
              d="M8 12 C8 8.686 10.686 6 14 6 L14 12 L8 12Z"
              fill="#0ea5a0"
            />
            <path
              d="M8 12 C8 15.314 10.686 18 14 18 L14 12 L8 12Z"
              fill="#0d9488"
            />
            {/* GEX text */}
            <text x="18" y="16" fontFamily="Inter,sans-serif" fontSize="9" fontWeight="800" fill="#0f172a">
              GE
            </text>
            <text x="27.5" y="16" fontFamily="Inter,sans-serif" fontSize="9" fontWeight="800" fill="#0ea5a0">
              X
            </text>
          </svg>
        </div>
      </div>
    </header>
  )
}
