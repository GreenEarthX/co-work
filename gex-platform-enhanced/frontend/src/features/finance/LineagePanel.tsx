// Screen: Information lineage panel (/finance/lineage)
/**
 * LineagePanel — wraps the LineageTrail primitive with mock/seed data
 * and expandable detail cards for each lineage node.
 */
import { useState } from 'react'
import { GitBranch, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { LineageTrail, type LineageNode } from '@/components/primitives'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

interface LineageDetail {
  nodeId: string
  title: string
  value: string
  subItems: { label: string; value: string }[]
  source?: string
  updatedAt?: string
}

// ═══════════════════════════════════════════════════════════════
// MOCK DATA — ETFuels Pecos I lineage
// ═══════════════════════════════════════════════════════════════

const MOCK_NODES: Record<string, LineageNode[]> = {
  proj_etf_pecos1: [
    { id: 'price',   label: 'Offtake price assumption',           layer: 'BRIDGE', state: 'PRICE LOCKED',         verified: true,  timestamp: '2026-03-15', actor: 'Commercial', hash: 'a3f1' },
    { id: 'wacc',    label: 'Weighted average cost of capital',    layer: 'BRIDGE', state: 'WACC COMPUTED',         verified: true,  timestamp: '2026-04-02', actor: 'Finance',    hash: 'b7c2' },
    { id: 'mol',     label: 'Molecule origin & pathway',          layer: 'BRIDGE', state: 'PATHWAY CONFIRMED',     verified: true,  timestamp: '2026-02-20', actor: 'Engineering', hash: 'c4d9' },
    { id: 'ci',      label: 'Carbon intensity assessment',        layer: 'TOKEN',  state: 'CI MEASURED',           verified: true,  timestamp: '2026-04-10', actor: 'Sustainability', hash: 'e2a5' },
    { id: 'cert',    label: 'Certification status',               layer: 'TOKEN',  state: 'RFNBO CERTIFIED',       verified: true,  timestamp: '2026-04-18', actor: 'DNV',         hash: 'f8b3' },
    { id: 'bank',    label: 'Bankability effective score',         layer: 'TOKEN',  state: 'SCORE COMPUTED',        verified: false, timestamp: '2026-05-01', actor: 'Finance',    hash: 'g1d7' },
    { id: 'esg',     label: 'ESG eligibility tier',               layer: 'TRADE',  state: 'TIER VERIFIED',         verified: true,  timestamp: '2026-05-05', actor: 'Compliance', hash: 'h9e4' },
  ],
  default: [
    { id: 'price',   label: 'Offtake price assumption',           layer: 'BRIDGE', state: 'PRICE ESTIMATED',       verified: false, timestamp: '2026-01-10', actor: 'Commercial' },
    { id: 'wacc',    label: 'Weighted average cost of capital',    layer: 'BRIDGE', state: 'WACC DRAFT',            verified: false, timestamp: '2026-02-15', actor: 'Finance' },
    { id: 'mol',     label: 'Molecule origin & pathway',          layer: 'BRIDGE', state: 'PATHWAY IDENTIFIED',    verified: false, timestamp: '2026-01-20', actor: 'Engineering' },
    { id: 'ci',      label: 'Carbon intensity assessment',        layer: 'TOKEN',  state: 'CI PENDING',            verified: false, timestamp: '2026-03-01', actor: 'Sustainability' },
    { id: 'cert',    label: 'Certification status',               layer: 'TOKEN',  state: 'NOT CERTIFIED',         verified: false },
    { id: 'bank',    label: 'Bankability effective score',         layer: 'TOKEN',  state: 'SCORE PENDING',         verified: false },
    { id: 'esg',     label: 'ESG eligibility tier',               layer: 'TRADE',  state: 'TIER PENDING',          verified: false },
  ],
}

const MOCK_DETAILS: Record<string, LineageDetail[]> = {
  proj_etf_pecos1: [
    {
      nodeId: 'price', title: 'Price', value: '1,420/tonne',
      subItems: [
        { label: 'Currency', value: 'EUR' },
        { label: 'Basis', value: 'CIF Rotterdam' },
        { label: 'Escalation', value: '2.0% p.a.' },
        { label: 'Contract type', value: '10-year take-or-pay' },
        { label: 'Buyer', value: 'Maersk Green Fuels' },
      ],
      source: 'Offtake HoT v3.2', updatedAt: '2026-03-15',
    },
    {
      nodeId: 'wacc', title: 'WACC', value: '5.8%',
      subItems: [
        { label: 'Equity cost', value: '12.0%' },
        { label: 'Debt cost (blended)', value: '3.9%' },
        { label: 'Equity share', value: '35%' },
        { label: 'Debt share', value: '65%' },
        { label: 'Tax shield', value: 'Included (21% US federal)' },
      ],
      source: 'Capital Stack v2.1', updatedAt: '2026-04-02',
    },
    {
      nodeId: 'mol', title: 'Molecule Origin', value: 'e-Methanol',
      subItems: [
        { label: 'Feedstock', value: 'Green H2 + biogenic CO2' },
        { label: 'Electrolyser', value: 'PEM 340 MW' },
        { label: 'Pathway', value: 'Wind-to-H2-to-MeOH' },
        { label: 'Location', value: 'Pecos County, TX' },
        { label: 'Capacity', value: '165 kt/yr' },
      ],
      source: 'FEED Study Class 3', updatedAt: '2026-02-20',
    },
    {
      nodeId: 'ci', title: 'Carbon Intensity', value: '12.3 gCO2e/MJ',
      subItems: [
        { label: 'Scope 1', value: '1.8 gCO2e/MJ' },
        { label: 'Scope 2', value: '8.2 gCO2e/MJ' },
        { label: 'Scope 3 upstream', value: '2.3 gCO2e/MJ' },
        { label: 'RED III threshold', value: '28.2 gCO2e/MJ' },
        { label: 'Margin to threshold', value: '-56%' },
      ],
      source: 'LCA v1.4 (DNV)', updatedAt: '2026-04-10',
    },
    {
      nodeId: 'cert', title: 'Certification', value: 'RFNBO (DNV, valid 2027)',
      subItems: [
        { label: 'Standard', value: 'EU RFNBO / Delegated Act' },
        { label: 'Certifier', value: 'DNV GL' },
        { label: 'Valid from', value: '2027-01-01' },
        { label: 'US 45V status', value: 'Pending (IRS guidance)' },
        { label: 'Dual cert conflict', value: 'Amber — temporal overlap' },
      ],
      source: 'CertReadiness v2', updatedAt: '2026-04-18',
    },
    {
      nodeId: 'bank', title: 'Bankability', value: '72% effective score',
      subItems: [
        { label: 'Raw score', value: '78%' },
        { label: 'Verification weight', value: '0.92' },
        { label: 'Effective', value: '72%' },
        { label: 'Gates complete', value: '6 / 11' },
        { label: 'Next gate', value: 'G8 Audit-Grade Model' },
      ],
      source: 'Bankability Engine v3', updatedAt: '2026-05-01',
    },
    {
      nodeId: 'esg', title: 'ESG Eligibility', value: 'Tier VERIFIED',
      subItems: [
        { label: 'EU Taxonomy', value: 'Aligned (CCM)' },
        { label: 'SFDR classification', value: 'Article 9' },
        { label: 'Green Bond eligible', value: 'Yes' },
        { label: 'Social safeguards', value: 'IFC PS 1-8 compliant' },
        { label: 'Governance score', value: '85/100' },
      ],
      source: 'ESG Module v1.2', updatedAt: '2026-05-05',
    },
  ],
  default: [
    { nodeId: 'price', title: 'Price', value: 'TBD', subItems: [{ label: 'Status', value: 'Awaiting offtake' }] },
    { nodeId: 'wacc', title: 'WACC', value: 'TBD', subItems: [{ label: 'Status', value: 'Capital stack incomplete' }] },
    { nodeId: 'mol', title: 'Molecule Origin', value: 'TBD', subItems: [{ label: 'Status', value: 'Pathway under review' }] },
    { nodeId: 'ci', title: 'Carbon Intensity', value: 'TBD', subItems: [{ label: 'Status', value: 'LCA not started' }] },
    { nodeId: 'cert', title: 'Certification', value: 'Not certified', subItems: [{ label: 'Status', value: 'Pre-application' }] },
    { nodeId: 'bank', title: 'Bankability', value: 'Pending', subItems: [{ label: 'Status', value: 'Gates incomplete' }] },
    { nodeId: 'esg', title: 'ESG Eligibility', value: 'Pending', subItems: [{ label: 'Status', value: 'Assessment not started' }] },
  ],
}

// ═══════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════

export function LineagePanel() {
  const { selectedProjectId } = useSelectedProject()
  const [expandedNode, setExpandedNode] = useState<string | null>(null)

  const nodes = MOCK_NODES[selectedProjectId] ?? MOCK_NODES['default']
  const details = MOCK_DETAILS[selectedProjectId] ?? MOCK_DETAILS['default']

  const verifiedCount = nodes.filter(n => n.verified).length
  const projectName = selectedProjectId === 'proj_etf_pecos1' ? 'ETFuels Rattlesnake Gap' : 'Project'

  return (
    <div className="space-y-4 max-w-5xl mx-auto pb-8">

      {/* Header */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="flex items-start justify-between px-6 py-4 bg-gradient-to-r from-gray-900 to-gray-800">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <GitBranch className="w-4 h-4 text-gray-400" />
              <span className="text-xs font-bold uppercase tracking-widest text-gray-400">Information Lineage</span>
            </div>
            <h1 className="text-2xl font-black text-white">{projectName}</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Provenance chain: Price, WACC, Molecule, CI, Certification, Bankability, ESG
            </p>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-700 text-white text-xs font-bold">
              {verifiedCount}/{nodes.length} verified
            </span>
          </div>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
          <div className="text-2xl font-black tabular-nums text-gray-900">{nodes.length}</div>
          <div className="text-xs font-semibold text-gray-500 mt-1">Lineage Nodes</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
          <div className={`text-2xl font-black tabular-nums ${verifiedCount === nodes.length ? 'text-green-600' : 'text-amber-600'}`}>
            {verifiedCount}
          </div>
          <div className="text-xs font-semibold text-gray-500 mt-1">Verified</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
          <div className="text-2xl font-black tabular-nums text-gray-900">
            {new Set(nodes.map(n => n.layer)).size}
          </div>
          <div className="text-xs font-semibold text-gray-500 mt-1">Layers Spanned</div>
        </div>
      </div>

      {/* LineageTrail primitive */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 flex items-center gap-2">
          <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">
            Provenance Chain
          </h3>
          <InfoTooltip text="Vertical lineage trail across BRIDGE, TOKEN, and TRADE layers. Each node carries a verification state and content hash for audit. Click detail cards below for full data." />
        </div>
        <div className="px-6 py-4">
          <LineageTrail
            nodes={nodes}
            highlight_id={expandedNode ?? undefined}
          />
        </div>
      </div>

      {/* Detail cards */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50">
          <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">
            Node Details
          </h3>
        </div>
        <div className="divide-y divide-gray-100">
          {details.map(detail => {
            const node = nodes.find(n => n.id === detail.nodeId)
            const isOpen = expandedNode === detail.nodeId
            return (
              <div key={detail.nodeId}>
                <button
                  type="button"
                  onClick={() => setExpandedNode(isOpen ? null : detail.nodeId)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full shrink-0 ${node?.verified ? 'bg-green-500' : 'bg-amber-400'}`} />
                    <div className="text-left">
                      <div className="text-sm font-semibold text-gray-800">{detail.title}</div>
                      <div className="text-xs text-gray-500">{detail.value}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {node?.verified && (
                      <span className="px-1.5 py-0.5 rounded bg-green-100 text-green-700 text-[10px] font-bold">VERIFIED</span>
                    )}
                    {isOpen ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                  </div>
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 pt-1 bg-gray-50/50 animate-fade-in">
                    <div className="grid grid-cols-2 gap-2">
                      {detail.subItems.map(si => (
                        <div key={si.label} className="flex justify-between text-xs px-2 py-1.5 rounded bg-white border border-gray-100">
                          <span className="text-gray-500">{si.label}</span>
                          <span className="font-semibold text-gray-800 tabular-nums">{si.value}</span>
                        </div>
                      ))}
                    </div>
                    {(detail.source || detail.updatedAt) && (
                      <div className="flex items-center gap-3 mt-2 text-[10px] text-gray-400">
                        {detail.source && (
                          <span className="flex items-center gap-1">
                            <ExternalLink className="w-2.5 h-2.5" />
                            {detail.source}
                          </span>
                        )}
                        {detail.updatedAt && <span>Updated {detail.updatedAt}</span>}
                        {node?.hash && <span className="font-mono">#{node.hash}</span>}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
