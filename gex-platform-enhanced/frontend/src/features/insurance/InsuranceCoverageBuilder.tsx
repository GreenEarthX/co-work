/**
 * InsuranceCoverageBuilder — insurer-facing coverage line builder.
 * Shows CAR/EAR/DSU/BI/Marine/Liability lines with gap flags and molecule-specific overlays.
 * Route: /insurance-coverage
 * Visible to: INSURER (TP) and PRODUCER FINANCE_TREASURY
 */
import { useState } from 'react'
import { ShieldCheck, AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Plus, Info } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { CUSTOMER_PROJECTS } from '@/data/customerProjects'
import { MoleculeGatingAlert } from '@/components/finance/MoleculeGatingAlert'

// ─── Types ───────────────────────────────────────────────────────────────────

type CoverageStatus = 'PLACED' | 'QUOTED' | 'PENDING' | 'GAP' | 'EXCLUDED'
type CoverageLineId = 'CAR' | 'EAR' | 'DSU' | 'BI' | 'MARINE' | 'LIABILITY' | 'PLL'

interface CoverageLine {
  id: CoverageLineId
  name: string
  description: string
  insuredValue: string
  deductible: string
  premium: string
  status: CoverageStatus
  insurer?: string
  notes?: string
  moleculeRequired?: ('NH3' | 'SAF' | 'H2' | 'E_METHANOL')[]
}

// ─── Demo data ────────────────────────────────────────────────────────────────

const BASE_LINES: Record<string, CoverageLine[]> = {
  proj_lehavre_eng: [
    { id: 'CAR',       name: 'Construction All Risk (CAR)',          description: 'Material damage & third-party liability during construction', insuredValue: '€350M', deductible: '€500K', premium: '0.18%', status: 'PLACED',  insurer: 'Munich Re / AXA XL', notes: 'Includes LEG 3/96 defects cover' },
    { id: 'EAR',       name: 'Erection All Risk (EAR)',              description: 'Mechanical & electrical plant erection risk', insuredValue: '€210M', deductible: '€250K', premium: '0.22%', status: 'PLACED',  insurer: 'Zurich Engineering', notes: 'Electrolyser stack coverage confirmed' },
    { id: 'DSU',       name: 'Delay in Start-Up (DSU)',              description: 'Revenue loss from construction delay', insuredValue: '€24M/yr', deductible: '90 days', premium: '0.35%', status: 'QUOTED',  insurer: 'Scor SE', notes: 'Quote valid 90 days; waiting FC docs' },
    { id: 'BI',        name: 'Business Interruption (BI)',           description: 'Operating revenue loss following insured event', insuredValue: '€18M/yr', deductible: '30 days', premium: '0.28%', status: 'PENDING', notes: 'Requires completed DSCR model' },
    { id: 'MARINE',    name: 'Marine Cargo',                         description: 'Electrolyser stack & key equipment transit', insuredValue: '€120M', deductible: '€50K', premium: '0.09%', status: 'PLACED',  insurer: 'Lloyd\'s Syndicate 2791' },
    { id: 'LIABILITY', name: 'General & Product Liability',          description: 'Third-party bodily injury and property damage', insuredValue: '€50M', deductible: '€25K', premium: '€85K/yr', status: 'PLACED',  insurer: 'AXA XL' },
  ],
  proj_rotterdam_nh3: [
    { id: 'CAR',       name: 'Construction All Risk (CAR)',          description: 'Material damage & TP liability during construction', insuredValue: '€280M', deductible: '€500K', premium: '0.21%', status: 'QUOTED',  insurer: 'TBC — market approach Q2 2026', notes: 'HAZOP must complete before bind' },
    { id: 'EAR',       name: 'Erection All Risk (EAR)',              description: 'Haber-Bosch synthesis loop and compressors', insuredValue: '€155M', deductible: '€350K', premium: '0.26%', status: 'PENDING', notes: 'Process hazard review required' },
    { id: 'DSU',       name: 'Delay in Start-Up (DSU)',              description: 'Revenue loss from construction delay', insuredValue: '€20M/yr', deductible: '60 days', premium: '0.40%', status: 'GAP',     notes: 'No DSU market appetite until Seveso tier confirmed' },
    { id: 'BI',        name: 'Business Interruption (BI)',           description: 'NH₃ production revenue loss', insuredValue: '€15M/yr', deductible: '30 days', premium: '—', status: 'GAP',     notes: 'DSU must place first; NH₃ BI is technically complex' },
    { id: 'PLL',       name: 'Pollution & Environmental Liability',  description: 'NH₃ accidental release — Seveso III obligation', insuredValue: '€100M', deductible: '€100K', premium: '0.55%', status: 'PENDING', moleculeRequired: ['NH3'], notes: 'EIL/PLL specialist required: AIG, Zurich, Chubb' },
    { id: 'MARINE',    name: 'Marine Cargo',                         description: 'Ammonia tanker & terminal cargo risk', insuredValue: '€60M', deductible: '€75K', premium: '0.12%', status: 'PLACED',  insurer: 'Lloyd\'s NH₃ specialist' },
    { id: 'LIABILITY', name: 'General & Product Liability',          description: 'TP / Employers liability', insuredValue: '€30M', deductible: '€25K', premium: '€72K/yr', status: 'PLACED', insurer: 'AXA XL' },
  ],
}

const DEFAULT_LINES = BASE_LINES.proj_lehavre_eng

const STATUS_CONFIG: Record<CoverageStatus, { label: string; bg: string; text: string; border: string; icon: React.ElementType }> = {
  PLACED:   { label: 'Placed',   bg: 'bg-green-100',  text: 'text-green-800',  border: 'border-green-300',  icon: CheckCircle2 },
  QUOTED:   { label: 'Quoted',   bg: 'bg-blue-100',   text: 'text-blue-800',   border: 'border-blue-300',   icon: Info },
  PENDING:  { label: 'Pending',  bg: 'bg-amber-50',   text: 'text-amber-700',  border: 'border-amber-200',  icon: ChevronDown },
  GAP:      { label: 'GAP',      bg: 'bg-red-100',    text: 'text-red-800',    border: 'border-red-300',    icon: AlertTriangle },
  EXCLUDED: { label: 'Excluded', bg: 'bg-gray-100',   text: 'text-gray-600',   border: 'border-gray-300',   icon: AlertTriangle },
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: CoverageStatus }) {
  const cfg = STATUS_CONFIG[status]
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-xs font-bold ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  )
}

function CoverageRow({ line }: { line: CoverageLine }) {
  const [open, setOpen] = useState(false)
  const isGap = line.status === 'GAP'

  return (
    <div className={`rounded-xl border overflow-hidden ${isGap ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-white'}`}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className={`w-full flex items-center justify-between p-4 text-left hover:bg-gray-50/50 transition-colors ${isGap ? 'hover:bg-red-50' : ''}`}
      >
        <div className="flex items-center gap-3 min-w-0">
          {isGap && <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-gray-400">{line.id}</span>
              <span className="text-sm font-bold text-gray-900">{line.name}</span>
              {line.moleculeRequired && (
                <span className="text-xs px-1.5 py-0.5 bg-sky-100 text-sky-700 rounded font-semibold">
                  {line.moleculeRequired.join('/')}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 truncate">{line.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-4">
          <span className="text-xs tabular-nums text-gray-600 hidden md:block">{line.insuredValue}</span>
          <StatusBadge status={line.status} />
          {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-gray-100">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3 text-xs">
            <div>
              <div className="text-gray-500 font-semibold uppercase tracking-wide mb-1">Insured Value</div>
              <div className="font-bold text-gray-900">{line.insuredValue}</div>
            </div>
            <div>
              <div className="text-gray-500 font-semibold uppercase tracking-wide mb-1">Deductible</div>
              <div className="font-bold text-gray-900">{line.deductible}</div>
            </div>
            <div>
              <div className="text-gray-500 font-semibold uppercase tracking-wide mb-1">Indicative Premium</div>
              <div className="font-bold text-gray-900">{line.premium}</div>
            </div>
            <div>
              <div className="text-gray-500 font-semibold uppercase tracking-wide mb-1">Lead Insurer</div>
              <div className="font-bold text-gray-900">{line.insurer ?? '—'}</div>
            </div>
          </div>
          {line.notes && (
            <div className={`mt-3 px-3 py-2 rounded-lg text-xs ${isGap ? 'bg-red-100 text-red-700' : 'bg-gray-50 text-gray-600'}`}>
              {line.notes}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function InsuranceCoverageBuilder() {
  const { selectedProjectId } = useSelectedProject()
  const project = CUSTOMER_PROJECTS.find(p => p.id === selectedProjectId)
  const lines = BASE_LINES[selectedProjectId] ?? DEFAULT_LINES

  const placed  = lines.filter(l => l.status === 'PLACED').length
  const gaps    = lines.filter(l => l.status === 'GAP').length
  const pending = lines.filter(l => l.status === 'PENDING' || l.status === 'QUOTED').length

  const [showAddForm, setShowAddForm] = useState(false)

  return (
    <div className="space-y-5 max-w-5xl mx-auto pb-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <ShieldCheck className="w-4 h-4 text-sky-600" />
            <span className="text-xs font-bold uppercase tracking-widest text-gray-500">Insurance Workspace</span>
          </div>
          <h1 className="text-xl font-black text-gray-900">Coverage Lines</h1>
          <p className="text-sm text-gray-500 mt-0.5">{project?.name ?? 'Selected Project'} — CAR / EAR / DSU / BI / Marine / Liability</p>
        </div>
        <button
          type="button"
          onClick={() => setShowAddForm(v => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-sky-600 text-white text-xs font-bold rounded-lg hover:bg-sky-700"
        >
          <Plus className="w-3.5 h-3.5" />
          Add Line
        </button>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Lines Placed', value: placed, color: 'text-green-700', bg: 'bg-green-50 border-green-200' },
          { label: 'Coverage Gaps', value: gaps,   color: gaps > 0 ? 'text-red-700' : 'text-gray-500', bg: gaps > 0 ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200' },
          { label: 'Pending / Quoted', value: pending, color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200' },
        ].map(kpi => (
          <div key={kpi.label} className={`rounded-xl border p-4 ${kpi.bg}`}>
            <div className="text-xs font-bold text-gray-500 uppercase">{kpi.label}</div>
            <div className={`text-3xl font-black ${kpi.color} mt-1`}>{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* Molecule gating alert — NH3/SAF specific */}
      {project && <MoleculeGatingAlert project={project} />}

      {/* Add line stub */}
      {showAddForm && (
        <div className="rounded-xl border border-dashed border-sky-300 bg-sky-50 p-5 text-center">
          <p className="text-sm text-sky-700 font-semibold">Coverage line builder form — connect to insurer API or upload slip PDF.</p>
          <p className="text-xs text-sky-600 mt-1">Integration point: Lloyd's Whitespace, RIMS, or manual entry.</p>
          <button
            type="button"
            onClick={() => setShowAddForm(false)}
            className="mt-3 text-xs text-sky-600 hover:underline"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Coverage lines list */}
      <div className="space-y-3">
        {/* Gaps first */}
        {lines.filter(l => l.status === 'GAP').map(line => (
          <CoverageRow key={line.id} line={line} />
        ))}
        {/* Then rest */}
        {lines.filter(l => l.status !== 'GAP').map(line => (
          <CoverageRow key={line.id} line={line} />
        ))}
      </div>

      {/* Note for insurers */}
      <div className="flex items-start gap-2 px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-xs text-gray-600">
        <Info className="w-4 h-4 text-gray-400 shrink-0 mt-0.5" />
        <span>
          Coverage placement status is updated by the project's insurance broker. Insurer sign-off triggers the
          <strong> INSURANCE_REVIEWED</strong> workflow state required before financial close approval.
        </span>
      </div>
    </div>
  )
}
