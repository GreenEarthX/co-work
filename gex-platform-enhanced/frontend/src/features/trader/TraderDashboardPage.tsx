import { useState } from 'react'
import { TrendingUp, Zap, FileText, Package, BarChart3, AlertTriangle } from 'lucide-react'
import { ProductionRoadmapGantt } from '@/components/gantt/ProductionRoadmapGantt'

export function TraderDashboardPage() {
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
          <p className="text-sm text-gray-500 mt-1">Market pulse · open positions · commercial milestones</p>
        </div>
        <span className="px-3 py-1 bg-purple-100 text-purple-700 text-xs font-bold rounded-full uppercase tracking-wide">
          Trader Workspace
        </span>
      </div>

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
