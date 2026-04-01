/**
 * InsuranceAssetRegister — asset & exposure register for insurers.
 * Molecule-specific hazard classification. Route: /insurance-assets
 * Visible to: INSURER (TP) and PRODUCER FINANCE_TREASURY
 */
import { useState } from 'react'
import { Building2, AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Flame } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { CUSTOMER_PROJECTS } from '@/data/customerProjects'

// ─── Types ───────────────────────────────────────────────────────────────────

type HazardClass = 'HIGH' | 'MEDIUM' | 'LOW' | 'N/A'
type AssetCategory = 'PROCESS' | 'STORAGE' | 'ELECTRICAL' | 'CIVIL' | 'DIGITAL' | 'LOGISTICS'

interface AssetItem {
  id: string
  name: string
  category: AssetCategory
  replacementValue: string
  hazardClass: HazardClass
  hazardNotes?: string
  location: string
  insuredUnder?: string
  isMoleculeSpecific?: boolean
}

// ─── Demo data ────────────────────────────────────────────────────────────────

const ASSET_REGISTERS: Record<string, AssetItem[]> = {
  proj_lehavre_eng: [
    { id: 'A1', name: 'PEM Electrolyser Stack (2 × 50 MW)', category: 'PROCESS',    replacementValue: '€82M',  hazardClass: 'MEDIUM', location: 'Module A, Zone 1', insuredUnder: 'EAR' },
    { id: 'A2', name: 'Rectifier / Power Electronics',       category: 'ELECTRICAL', replacementValue: '€24M',  hazardClass: 'MEDIUM', location: 'Electrical Room A', insuredUnder: 'CAR' },
    { id: 'A3', name: 'H₂ Compression & Drying',             category: 'PROCESS',    replacementValue: '€18M',  hazardClass: 'HIGH',   hazardNotes: 'High-pressure H₂ — ATEX Zone 1', location: 'Process Area B', insuredUnder: 'EAR' },
    { id: 'A4', name: 'H₂ Storage Cavern Rights',            category: 'STORAGE',    replacementValue: '€12M',  hazardClass: 'HIGH',   hazardNotes: 'Underground storage — special conditions apply', location: 'Le Havre Port Zone', insuredUnder: 'CAR' },
    { id: 'A5', name: 'Grid Connection Substation',          category: 'ELECTRICAL', replacementValue: '€35M',  hazardClass: 'MEDIUM', location: 'Site perimeter', insuredUnder: 'CAR' },
    { id: 'A6', name: 'GEX Digital Twin / MRV Stack',        category: 'DIGITAL',    replacementValue: '€4M',   hazardClass: 'LOW',    location: 'Cloud / on-prem', insuredUnder: 'Cyber' },
    { id: 'A7', name: 'Civils & Foundations',                category: 'CIVIL',      replacementValue: '€28M',  hazardClass: 'LOW',    location: 'Full site', insuredUnder: 'CAR' },
    { id: 'A8', name: 'Logistics Pipeline Connection',       category: 'LOGISTICS',  replacementValue: '€9M',   hazardClass: 'MEDIUM', location: 'Port offtake connection', insuredUnder: 'Marine' },
  ],
  proj_rotterdam_nh3: [
    { id: 'A1', name: 'Haber-Bosch Synthesis Loop',          category: 'PROCESS',    replacementValue: '€110M', hazardClass: 'HIGH',   hazardNotes: 'Seveso III Upper Tier — ammonia inventory > 500 t', location: 'Process Island 1', insuredUnder: 'EAR', isMoleculeSpecific: true },
    { id: 'A2', name: 'NH₃ Refrigerated Storage Tank (3×)',  category: 'STORAGE',    replacementValue: '€42M',  hazardClass: 'HIGH',   hazardNotes: 'Cryogenic ammonia — EIL/PLL specialist required', location: 'Storage Farm', insuredUnder: 'EAR / PLL', isMoleculeSpecific: true },
    { id: 'A3', name: 'NH₃ Loading Arm & Jetty',             category: 'LOGISTICS',  replacementValue: '€28M',  hazardClass: 'HIGH',   hazardNotes: 'Marine NH₃ transfer — Seveso III boundary', location: 'Port Terminal', insuredUnder: 'Marine', isMoleculeSpecific: true },
    { id: 'A4', name: 'PEM Electrolyser Stack (3 × 50 MW)',  category: 'PROCESS',    replacementValue: '€118M', hazardClass: 'MEDIUM', location: 'Module A', insuredUnder: 'EAR' },
    { id: 'A5', name: 'N₂ Separation Unit (ASU)',            category: 'PROCESS',    replacementValue: '€18M',  hazardClass: 'LOW',    location: 'Utilities Zone', insuredUnder: 'EAR' },
    { id: 'A6', name: 'Emergency Scrubber System',           category: 'PROCESS',    replacementValue: '€8M',   hazardClass: 'HIGH',   hazardNotes: 'Seveso III mandatory — must be confirmed in HAZOP', location: 'NH₃ boundary', insuredUnder: 'CAR', isMoleculeSpecific: true },
    { id: 'A7', name: 'Grid Connection & Transformers',      category: 'ELECTRICAL', replacementValue: '€22M',  hazardClass: 'MEDIUM', location: 'North perimeter', insuredUnder: 'CAR' },
    { id: 'A8', name: 'Control Room & SCADA',                category: 'DIGITAL',    replacementValue: '€5M',   hazardClass: 'MEDIUM', hazardNotes: 'Process safety critical — SIL 2/3 classification', location: 'Central Control', insuredUnder: 'EAR' },
  ],
}

const DEFAULT_REGISTER = ASSET_REGISTERS.proj_lehavre_eng

const HAZARD_COLORS: Record<HazardClass, string> = {
  HIGH:   'bg-red-100 text-red-800 border-red-300',
  MEDIUM: 'bg-amber-50 text-amber-700 border-amber-200',
  LOW:    'bg-green-50 text-green-700 border-green-200',
  'N/A':  'bg-gray-100 text-gray-500 border-gray-200',
}

const CATEGORY_LABELS: Record<AssetCategory, string> = {
  PROCESS:   'Process',
  STORAGE:   'Storage',
  ELECTRICAL:'Electrical',
  CIVIL:     'Civil',
  DIGITAL:   'Digital / IT',
  LOGISTICS: 'Logistics',
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function AssetRow({ asset }: { asset: AssetItem }) {
  const [open, setOpen] = useState(false)

  return (
    <div className={`rounded-xl border overflow-hidden ${asset.isMoleculeSpecific ? 'border-orange-200 bg-orange-50' : 'border-gray-200 bg-white'}`}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between p-3.5 text-left hover:bg-gray-50/50 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          {asset.isMoleculeSpecific && <Flame className="w-4 h-4 text-orange-500 shrink-0" />}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-gray-400">{asset.id}</span>
              <span className="text-sm font-bold text-gray-900">{asset.name}</span>
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-gray-400">{CATEGORY_LABELS[asset.category]}</span>
              <span className="text-gray-300">·</span>
              <span className="text-xs text-gray-500">{asset.location}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-4">
          <span className="text-xs tabular-nums font-semibold text-gray-700 hidden md:block">{asset.replacementValue}</span>
          <span className={`inline-flex items-center px-2 py-0.5 rounded-md border text-xs font-bold ${HAZARD_COLORS[asset.hazardClass]}`}>
            {asset.hazardClass}
          </span>
          {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-gray-100 mt-0">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-3 text-xs">
            <div>
              <div className="text-gray-500 font-semibold uppercase tracking-wide mb-1">Replacement Value</div>
              <div className="font-bold text-gray-900">{asset.replacementValue}</div>
            </div>
            <div>
              <div className="text-gray-500 font-semibold uppercase tracking-wide mb-1">Insured Under</div>
              <div className="font-bold text-gray-900">{asset.insuredUnder ?? '—'}</div>
            </div>
            <div>
              <div className="text-gray-500 font-semibold uppercase tracking-wide mb-1">Hazard Class</div>
              <div className={`inline-flex items-center px-2 py-0.5 rounded-md border text-xs font-bold ${HAZARD_COLORS[asset.hazardClass]}`}>
                {asset.hazardClass}
              </div>
            </div>
          </div>
          {asset.hazardNotes && (
            <div className={`mt-3 px-3 py-2 rounded-lg text-xs ${asset.hazardClass === 'HIGH' ? 'bg-red-100 text-red-700' : 'bg-amber-50 text-amber-700'}`}>
              <AlertTriangle className="w-3.5 h-3.5 inline mr-1" />
              {asset.hazardNotes}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function InsuranceAssetRegister() {
  const { selectedProjectId } = useSelectedProject()
  const project = CUSTOMER_PROJECTS.find(p => p.id === selectedProjectId)
  const assets = ASSET_REGISTERS[selectedProjectId] ?? DEFAULT_REGISTER

  const totalRV = assets.reduce((sum, a) => {
    const num = parseFloat(a.replacementValue.replace(/[^0-9.]/g, ''))
    return isNaN(num) ? sum : sum + num
  }, 0)

  const highHazard = assets.filter(a => a.hazardClass === 'HIGH').length
  const moleculeSpecific = assets.filter(a => a.isMoleculeSpecific).length

  const [filterHazard, setFilterHazard] = useState<HazardClass | 'ALL'>('ALL')

  const displayed = filterHazard === 'ALL'
    ? assets
    : assets.filter(a => a.hazardClass === filterHazard)

  return (
    <div className="space-y-5 max-w-5xl mx-auto pb-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Building2 className="w-4 h-4 text-sky-600" />
            <span className="text-xs font-bold uppercase tracking-widest text-gray-500">Insurance Workspace</span>
          </div>
          <h1 className="text-xl font-black text-gray-900">Asset & Exposure Register</h1>
          <p className="text-sm text-gray-500 mt-0.5">{project?.name ?? 'Selected Project'} — Replacement values & hazard classification</p>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total Replacement Value', value: `€${totalRV.toFixed(0)}M`, color: 'text-gray-900', bg: 'bg-white border-gray-200' },
          { label: 'High Hazard Assets', value: highHazard, color: highHazard > 0 ? 'text-red-700' : 'text-gray-500', bg: highHazard > 0 ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200' },
          { label: 'Molecule-Specific Assets', value: moleculeSpecific, color: moleculeSpecific > 0 ? 'text-orange-700' : 'text-gray-500', bg: moleculeSpecific > 0 ? 'bg-orange-50 border-orange-200' : 'bg-gray-50 border-gray-200' },
        ].map(kpi => (
          <div key={kpi.label} className={`rounded-xl border p-4 ${kpi.bg}`}>
            <div className="text-xs font-bold text-gray-500 uppercase">{kpi.label}</div>
            <div className={`text-3xl font-black ${kpi.color} mt-1`}>{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-500">Filter by hazard:</span>
        {(['ALL', 'HIGH', 'MEDIUM', 'LOW'] as const).map(h => (
          <button
            key={h}
            type="button"
            onClick={() => setFilterHazard(h)}
            className={`px-3 py-1 rounded-lg text-xs font-bold border transition-colors ${
              filterHazard === h
                ? 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
            }`}
          >
            {h}
          </button>
        ))}
      </div>

      {/* Asset list — HIGH hazard first */}
      <div className="space-y-3">
        {displayed
          .sort((a, b) => {
            const order: Record<HazardClass, number> = { HIGH: 0, MEDIUM: 1, LOW: 2, 'N/A': 3 }
            return order[a.hazardClass] - order[b.hazardClass]
          })
          .map(asset => (
            <AssetRow key={asset.id} asset={asset} />
          ))
        }
      </div>

      {moleculeSpecific > 0 && (
        <div className="flex items-start gap-2 px-4 py-3 bg-orange-50 border border-orange-200 rounded-xl text-xs text-orange-700">
          <Flame className="w-4 h-4 text-orange-500 shrink-0 mt-0.5" />
          <span>
            <strong>Molecule-specific assets</strong> (highlighted in orange) require specialist underwriting and may impose
            conditions on the main CAR/EAR policy. Confirm with Lloyd's / specialist market.
          </span>
        </div>
      )}
    </div>
  )
}
