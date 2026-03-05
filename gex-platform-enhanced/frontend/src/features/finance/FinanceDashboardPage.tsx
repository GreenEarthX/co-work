import { TrendingUp, DollarSign, Shield, AlertTriangle, FileCheck, Activity } from 'lucide-react'

interface StatusCardProps {
  title: string
  description: string
  status: 'at-risk' | 'watch' | 'on-track' | 'compliant'
  actionLabel: string
  actionHref: string
  icon: any
}

function StatusCard({ title, description, status, actionLabel, actionHref, icon: Icon }: StatusCardProps) {
  const statusConfig = {
    'at-risk': { bg: 'bg-red-50', text: 'text-red-700', label: 'At risk' },
    'watch': { bg: 'bg-yellow-50', text: 'text-yellow-700', label: 'Watch' },
    'on-track': { bg: 'bg-green-50', text: 'text-green-700', label: 'On track' },
    'compliant': { bg: 'bg-emerald-50', text: 'text-emerald-700', label: 'Compliant' },
  }

  const config = statusConfig[status]

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-lg transition-shadow">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
            <Icon className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-900">{title}</h3>
            <p className="text-sm text-gray-600 mt-1">{description}</p>
          </div>
        </div>
        <span className={`px-3 py-1 ${config.bg} ${config.text} text-xs font-bold rounded-full whitespace-nowrap`}>
          {config.label}
        </span>
      </div>

      <a
        href={actionHref}
        className="text-sm text-gray-900 hover:text-brand font-semibold underline"
      >
        {actionLabel}
      </a>
    </div>
  )
}

export function FinanceDashboardPage() {
  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Finance Workspace</h1>
          <p className="text-sm text-gray-500 mt-1">
            Risk, evidence & reporting view (gates → covenants → audit)
          </p>
          <p className="text-xs text-gray-400 mt-1">
            As of: {new Date().toLocaleString('en-GB', { 
              day: '2-digit', 
              month: '2-digit', 
              year: 'numeric', 
              hour: '2-digit', 
              minute: '2-digit', 
              second: '2-digit' 
            })}
          </p>
        </div>

        <div className="flex gap-3">
          <button className="px-6 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 font-semibold">
            Open Risk Pack
          </button>
          <button className="px-6 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-semibold">
            Open Gate Checklist
          </button>
        </div>
      </div>

      {/* Status Cards Grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Stage Gate Status */}
        <StatusCard
          title="Stage Gate Status"
          description="FEL → FEED → FID → Financial Close → COD"
          status="at-risk"
          actionLabel="Open Gate Checklist"
          actionHref="/stage-gates"
          icon={TrendingUp}
        />

        {/* Revenue Coverage */}
        <StatusCard
          title="Revenue Coverage"
          description="Contracted volume, tenor, pricing basis"
          status="watch"
          actionLabel="View Contract Stack"
          actionHref="/revenue"
          icon={DollarSign}
        />

        {/* Compliance Readiness */}
        <StatusCard
          title="Compliance Readiness"
          description="RFNBO / RED / 45V evidence coverage"
          status="at-risk"
          actionLabel="Open Evidence Map"
          actionHref="/compliance"
          icon={Shield}
        />

        {/* Completion Risk */}
        <StatusCard
          title="Completion Risk"
          description="Critical path, contingency, change orders"
          status="watch"
          actionLabel="Review Schedule & CAPEX"
          actionHref="/stage-gates"
          icon={AlertTriangle}
        />

        {/* Insurance & Guarantees */}
        <StatusCard
          title="Insurance & Guarantees"
          description="Coverage status + expiries"
          status="on-track"
          actionLabel="Open Coverage Register"
          actionHref="/insurance"
          icon={FileCheck}
        />

        {/* Covenant Monitor */}
        <StatusCard
          title="Covenant Monitor"
          description="DSCR, LLCR, reserve accounts, reporting deadlines"
          status="compliant"
          actionLabel="Open Monitoring Pack"
          actionHref="/covenants"
          icon={Activity}
        />
      </div>

      {/* Key Financial Metrics */}
      <div className="bg-gradient-to-br from-blue-50 to-white rounded-xl border border-blue-200 p-6">
        <h3 className="text-lg font-bold text-gray-900 mb-4">Key Financial Metrics</h3>
        
        <div className="grid grid-cols-4 gap-6">
          <div>
            <div className="text-sm text-gray-600 mb-2">DSCR (Current)</div>
            <div className="text-3xl font-black text-gray-900">1.35x</div>
            <div className="text-xs text-gray-500 mt-1">Covenant: &gt;1.25x ✓</div>
          </div>

          <div>
            <div className="text-sm text-gray-600 mb-2">LLCR (Projected)</div>
            <div className="text-3xl font-black text-gray-900">1.52x</div>
            <div className="text-xs text-gray-500 mt-1">Covenant: &gt;1.40x ✓</div>
          </div>

          <div>
            <div className="text-sm text-gray-600 mb-2">Debt Service Reserve</div>
            <div className="text-3xl font-black text-gray-900">€8.2M</div>
            <div className="text-xs text-gray-500 mt-1">Target: €7.5M ✓</div>
          </div>

          <div>
            <div className="text-sm text-gray-600 mb-2">Offtake Coverage</div>
            <div className="text-3xl font-black text-gray-900">72%</div>
            <div className="text-xs text-gray-500 mt-1">Bankability: &gt;70% ✓</div>
          </div>
        </div>
      </div>

      {/* Stage Gate Progress */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-bold text-gray-900 mb-4">Stage Gate Progress</h3>
        
        <div className="space-y-4">
          {/* Progress Bar */}
          <div className="relative">
            <div className="flex justify-between mb-2">
              <span className="text-xs font-semibold text-gray-500">FEL</span>
              <span className="text-xs font-semibold text-gray-500">FEED</span>
              <span className="text-xs font-semibold text-gray-500">FID</span>
              <span className="text-xs font-semibold text-gray-500">Financial Close</span>
              <span className="text-xs font-semibold text-gray-500">COD</span>
            </div>
            <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-green-500 via-yellow-500 to-red-500" style={{ width: '65%' }} />
            </div>
            <div className="flex justify-between mt-2">
              <span className="text-xs text-green-700">✓ Complete</span>
              <span className="text-xs text-green-700">✓ Complete</span>
              <span className="text-xs text-yellow-700">⚠ In Progress</span>
              <span className="text-xs text-gray-400">○ Pending</span>
              <span className="text-xs text-gray-400">○ Pending</span>
            </div>
          </div>

          {/* Current Status */}
          <div className="mt-6 p-4 bg-yellow-50 rounded-lg border border-yellow-200">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-yellow-700 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-yellow-900">FID Stage - 3 Critical Items</div>
                <ul className="text-sm text-yellow-800 mt-2 space-y-1">
                  <li>• EPC contract finalization (7 days overdue)</li>
                  <li>• Grid connection agreement pending</li>
                  <li>• Final environmental permit approval needed</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Revenue Stack */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-gray-900">Contract Stack (Revenue Coverage)</h3>
          <span className="text-sm text-gray-500">50.0 MTPD Total Capacity</span>
        </div>
        
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-green-100 h-12 rounded flex items-center px-4">
              <span className="font-bold text-green-900">36 MTPD Contracted (72%)</span>
            </div>
            <span className="text-sm text-gray-600 w-24">5-10 years</span>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex-1 bg-yellow-100 h-12 rounded flex items-center px-4">
              <span className="font-bold text-yellow-900">10 MTPD Active Offers (20%)</span>
            </div>
            <span className="text-sm text-gray-600 w-24">1-3 years</span>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex-1 bg-gray-100 h-12 rounded flex items-center px-4">
              <span className="font-bold text-gray-900">4 MTPD Uncontracted (8%)</span>
            </div>
            <span className="text-sm text-gray-600 w-24">Merchant risk</span>
          </div>
        </div>

        <div className="mt-4 p-3 bg-blue-50 rounded-lg">
          <div className="text-sm text-blue-900">
            <span className="font-semibold">Bankability Assessment:</span> 72% contracted coverage exceeds 70% threshold. 
            Recommend converting 5 MTPD from active offers to firm contracts by Q2 2026.
          </div>
        </div>
      </div>

      {/* Compliance Evidence Dashboard */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-bold text-gray-900 mb-4">Compliance Evidence Coverage</h3>
        
        <div className="grid grid-cols-3 gap-6">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-gray-700">RFNBO (EU)</span>
              <span className="px-2 py-1 bg-red-50 text-red-700 text-xs font-bold rounded">62% Coverage</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3 mb-2">
              <div className="bg-red-500 h-3 rounded-full" style={{ width: '62%' }} />
            </div>
            <div className="text-xs text-gray-600">
              Missing: Hourly RE correlation data for Q3 2025
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-gray-700">45V (US IRA)</span>
              <span className="px-2 py-1 bg-gray-100 text-gray-500 text-xs font-bold rounded">0% Coverage</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3 mb-2">
              <div className="bg-gray-400 h-3 rounded-full" style={{ width: '0%' }} />
            </div>
            <div className="text-xs text-gray-600">
              Not applicable (EU project)
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-gray-700">RED III</span>
              <span className="px-2 py-1 bg-yellow-50 text-yellow-700 text-xs font-bold rounded">78% Coverage</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3 mb-2">
              <div className="bg-yellow-500 h-3 rounded-full" style={{ width: '78%' }} />
            </div>
            <div className="text-xs text-gray-600">
              Missing: Upstream emissions verification
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
