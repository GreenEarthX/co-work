import { TrendingUp, Zap, FileText, Package, BarChart3, AlertTriangle, ArrowRight, LineChart, Layers3, FileCheck2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { ProductionRoadmapGantt } from '@/components/gantt/ProductionRoadmapGantt'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { getProjectById, CUSTOMER_PROJECTS } from '@/data/customerProjects'
import { AdversarialReviewEntryCard } from '@/components/AdversarialReviewEntryCard'

export function TraderDashboardPage() {
  const navigate = useNavigate()
  const { selectedProjectId } = useSelectedProject()
  const project = getProjectById(selectedProjectId) ?? CUSTOMER_PROJECTS[0]
  const riskAlerts = project.bankability.risk_alerts ?? []
  const hasPricingTrustGap = riskAlerts.some(alert =>
    /gabillon|spot reference|pricing reference/i.test(alert),
  )
  const hasOfftakeGap = project.bankability.gates.some(g => g.id === 'G4_OFFTAKE_BANKABLE' && !g.is_complete)

  const closePath = [
    {
      title: 'Define mandate',
      detail: 'Target molecule, 10,000 MT/month, certifications, first delivery window',
      cta: 'Set demand',
      route: '/onboarding',
      Icon: FileText,
      tone: 'bg-blue-50 text-blue-700 border-blue-200',
    },
    {
      title: 'Pool supply',
      detail: 'Aggregate at least 4 producer offers through GreenMesh / FlowFusion',
      cta: 'Open marketplace',
      route: '/marketplace',
      Icon: Layers3,
      tone: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    },
    {
      title: 'Justify price',
      detail: 'Use clean token lead spot reference plus Gabillon forward curve',
      cta: 'Open pricing',
      route: '/pricing-curves',
      Icon: LineChart,
      tone: 'bg-amber-50 text-amber-700 border-amber-200',
    },
    {
      title: 'Close contract',
      detail: 'Issue RFQ and move to term sheet with LC-ready price rationale',
      cta: 'Run matching',
      route: '/matching',
      Icon: FileCheck2,
      tone: 'bg-violet-50 text-violet-700 border-violet-200',
    },
  ]

  const kpis = [
    { label: 'Active Positions',   value: '3',        sub: '2 H₂ · 1 NH₃',         icon: Package,     color: 'text-purple-600', bg: 'bg-purple-50' },
    { label: 'Open RFQs',          value: '7',        sub: '3 closing this week',    icon: FileText,    color: 'text-blue-600',   bg: 'bg-blue-50'   },
    { label: 'Matched Volume',     value: '12,400 t', sub: 'MTD vs 15,000 t target', icon: Zap,         color: 'text-amber-600',  bg: 'bg-amber-50'  },
    { label: 'Portfolio DSCR',     value: '1.28x',    sub: 'Weighted avg',           icon: TrendingUp,  color: 'text-emerald-600',bg: 'bg-emerald-50'},
    { label: 'Expiring Contracts', value: '2',        sub: 'Within 90 days',         icon: AlertTriangle,color:'text-red-600',   bg: 'bg-red-50'    },
    { label: 'P&L MTD',            value: '+€1.4M',   sub: '+8.2% vs last month',    icon: BarChart3,   color: 'text-green-600',  bg: 'bg-green-50'  },
  ]

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Trader Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">Market pulse · contract close path · commercial milestones</p>
        </div>
        <span className="px-3 py-1 bg-purple-100 text-purple-700 text-xs font-bold rounded-full uppercase tracking-wide">
          Trader Workspace
        </span>
      </div>

      <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <div className="text-xs font-black uppercase tracking-widest text-gray-500">Objective</div>
            <h2 className="text-lg font-bold text-gray-900 mt-1">Close a defensible Q1 2027 contract path</h2>
            <p className="text-sm text-gray-500 mt-1">
              Turn pooled producer volume into a buyer-ready contract with reference pricing that treasury, banks, and ratings teams can defend.
            </p>
          </div>
          <button
            onClick={() => navigate('/matching')}
            className="shrink-0 inline-flex items-center gap-2 rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-gray-800"
          >
            Continue path <ArrowRight className="w-4 h-4" />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {closePath.map(step => (
            <button
              key={step.title}
              type="button"
              onClick={() => navigate(step.route)}
              className="rounded-xl border border-gray-200 p-4 text-left hover:shadow-sm transition-shadow bg-gray-50"
            >
              <div className={`inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 text-xs font-bold ${step.tone}`}>
                <step.Icon className="w-3.5 h-3.5" />
                {step.title}
              </div>
              <p className="mt-3 text-sm font-semibold text-gray-900">{step.cta}</p>
              <p className="mt-1 text-xs leading-relaxed text-gray-500">{step.detail}</p>
            </button>
          ))}
        </div>
      </div>

      {(hasPricingTrustGap || hasOfftakeGap) && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-bold text-amber-900">Current blocker to contract close</h3>
              <p className="mt-1 text-sm text-amber-800">
                Counterparties do not yet have a defensible price backbone. GEX must show a clean spot reference and Gabillon-based forward curve before RotterdamOfftake4 can justify LOIs, LC-backed pricing, or credit committee discussion.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  onClick={() => navigate('/pricing-curves')}
                  className="inline-flex items-center gap-2 rounded-lg bg-amber-600 px-3 py-2 text-xs font-bold text-white hover:bg-amber-700"
                >
                  Open price reference <ArrowRight className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => navigate('/marketplace')}
                  className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-bold text-amber-900 hover:bg-amber-100"
                >
                  Aggregate supply
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {kpis.map(kpi => (
          <div key={kpi.label} className={`${kpi.bg} rounded-xl border border-gray-100 p-4`}>
            <div className="flex items-center gap-2 mb-2">
              <kpi.icon className={`w-4 h-4 ${kpi.color}`} />
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{kpi.label}</span>
            </div>
            <div className={`text-xl font-black ${kpi.color}`}>{kpi.value}</div>
            <div className="text-xs text-gray-500 mt-1">{kpi.sub}</div>
          </div>
        ))}
      </div>

      <AdversarialReviewEntryCard
        projectId={project.id}
        actorType="OFFTAKER"
        title="Offtaker challenge review"
      />

      {/* Market Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-bold text-gray-900 mb-4">Active Offtake Positions</h2>
          <div className="space-y-3">
            {[
              { project:'Le Havre e-NG', product:'e-NG', buyer:'GRTgaz', volume:'92%', tenor:'20y', status:'SIGNED',  statusColor:'bg-green-100 text-green-700' },
              { project:'Bremen H₂',     product:'H₂',   buyer:'Vattenfall',volume:'78%',tenor:'15y', status:'PARTIAL', statusColor:'bg-amber-100 text-amber-700' },
              { project:'Helios MeOH',   product:'MeOH', buyer:'Maersk',   volume:'60%',tenor:'12y', status:'PARTIAL', statusColor:'bg-amber-100 text-amber-700' },
            ].map(row => (
              <div key={row.project} className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                <div>
                  <div className="font-semibold text-gray-900 text-sm">{row.project}</div>
                  <div className="text-xs text-gray-500">{row.product} · {row.buyer} · {row.tenor}</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-gray-700">{row.volume}</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${row.statusColor}`}>{row.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-bold text-gray-900 mb-4">Open RFQs</h2>
          <div className="space-y-3">
            {[
              { id:'RFQ-2026-014', product:'NH₃ 500t/mo', deadline:'25 Mar', status:'BIDS_IN',    bids:4 },
              { id:'RFQ-2026-015', product:'H₂ 120t/mo',  deadline:'28 Mar', status:'OPEN',       bids:1 },
              { id:'RFQ-2026-016', product:'SAF 200t/mo', deadline:'02 Apr', status:'OPEN',       bids:0 },
              { id:'RFQ-2026-017', product:'H₂ 80t/mo',   deadline:'05 Apr', status:'DRAFTING',   bids:0 },
            ].map(rfq => (
              <div key={rfq.id} className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                <div>
                  <div className="font-semibold text-gray-900 text-sm">{rfq.id}</div>
                  <div className="text-xs text-gray-500">{rfq.product} · closes {rfq.deadline}</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-600">{rfq.bids} bid{rfq.bids !== 1 ? 's' : ''}</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${rfq.status === 'BIDS_IN' ? 'bg-blue-100 text-blue-700' : rfq.status === 'OPEN' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600'}`}>
                    {rfq.status.replace('_', ' ')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Production Roadmap Gantt — commercial milestones only */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <ProductionRoadmapGantt workspaceId="trader" compact />
      </div>
    </div>
  )
}
