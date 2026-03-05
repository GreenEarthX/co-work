import { FileText, BarChart3, Shield, Download, Clock } from 'lucide-react'

const PLANNED_REPORTS = [
  {
    category: 'Production',
    icon: BarChart3,
    color: 'bg-blue-50 text-blue-600 border-blue-200',
    reports: [
      { name: 'Production Summary', desc: 'Monthly/quarterly output per project, molecule, and facility', priority: 'HIGH' },
      { name: 'Capacity Utilization', desc: 'Actual vs. nameplate capacity over time', priority: 'HIGH' },
      { name: 'Quality & Purity Log', desc: 'Batch-level purity, certification compliance per delivery', priority: 'MEDIUM' },
    ],
  },
  {
    category: 'Commercial',
    icon: FileText,
    color: 'bg-green-50 text-green-600 border-green-200',
    reports: [
      { name: 'Offtake Pipeline', desc: 'All offers, RFQs, matches with status and conversion rates', priority: 'HIGH' },
      { name: 'Contract Portfolio', desc: 'Active contracts, volumes, pricing, counterparty exposure', priority: 'HIGH' },
      { name: 'Delivery Performance', desc: 'On-time delivery rate, shortfall tracking, penalty exposure', priority: 'MEDIUM' },
      { name: 'Revenue Forecast', desc: 'Projected revenue from contracted volumes at current prices', priority: 'MEDIUM' },
    ],
  },
  {
    category: 'Finance & Banking',
    icon: Download,
    color: 'bg-emerald-50 text-emerald-600 border-emerald-200',
    reports: [
      { name: 'Bankability Package', desc: 'Consolidated gate status, evidence completion, capital unlocks for lenders', priority: 'HIGH' },
      { name: 'DSCR & Covenant Report', desc: 'Current DSCR, covenant compliance, breach alerts', priority: 'HIGH' },
      { name: 'Capital Stack Status', desc: 'Equity, debt, grants — drawn vs committed vs available', priority: 'MEDIUM' },
      { name: 'Financial Model Output', desc: 'Base case + stress test results from gex_pf_engine', priority: 'MEDIUM' },
    ],
  },
  {
    category: 'Compliance & Certification',
    icon: Shield,
    color: 'bg-purple-50 text-purple-600 border-purple-200',
    reports: [
      { name: 'Certification Status', desc: 'RFNBO/ISCC/GoO status per project and batch', priority: 'HIGH' },
      { name: 'MRV Reporting', desc: 'Measurement, Reporting, Verification data for regulators', priority: 'MEDIUM' },
      { name: 'Audit Trail', desc: 'Full event log: evidence submissions, state changes, approvals', priority: 'LOW' },
    ],
  },
]

const PRIORITY_COLORS: Record<string, string> = {
  HIGH: 'bg-red-50 text-red-600 border-red-200',
  MEDIUM: 'bg-yellow-50 text-yellow-600 border-yellow-200',
  LOW: 'bg-gray-50 text-gray-500 border-gray-200',
}

export function ReportsPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Reports</h1>
          <p className="text-sm text-gray-600 mt-1">Reporting module — planned capabilities</p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-lg">
          <Clock className="w-4 h-4 text-amber-600" />
          <span className="text-xs font-bold text-amber-700">Under Development</span>
        </div>
      </div>

      {/* Report Categories */}
      {PLANNED_REPORTS.map(category => {
        const Icon = category.icon
        return (
          <div key={category.category} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 bg-gray-50 border-b border-gray-100 flex items-center gap-3">
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${category.color} border`}>
                <Icon className="w-4 h-4" />
              </div>
              <h2 className="font-bold text-gray-900">{category.category}</h2>
              <span className="text-xs text-gray-400 ml-auto">{category.reports.length} reports planned</span>
            </div>
            <div className="divide-y divide-gray-50">
              {category.reports.map(report => (
                <div key={report.name} className="px-6 py-3 flex items-center justify-between hover:bg-gray-50">
                  <div>
                    <div className="text-sm font-semibold text-gray-900">{report.name}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{report.desc}</div>
                  </div>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${PRIORITY_COLORS[report.priority]}`}>{report.priority}</span>
                </div>
              ))}
            </div>
          </div>
        )
      })}

      {/* Implementation Note */}
      <div className="bg-blue-50 rounded-xl border border-blue-200 p-5">
        <h3 className="font-bold text-blue-900 mb-2">Implementation Plan</h3>
        <div className="text-sm text-blue-800 space-y-1">
          <p>Phase 1: Production Summary + Offtake Pipeline (data already available from existing APIs)</p>
          <p>Phase 2: Bankability Package + DSCR Report (integrates with gex_pf_engine bankability module)</p>
          <p>Phase 3: Certification + MRV + Audit Trail (requires regulator workspace completion)</p>
          <p>Export formats: PDF (credit committee packages), Excel (financial data), CSV (raw data)</p>
        </div>
      </div>
    </div>
  )
}
