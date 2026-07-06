// Screen: Shared component — Main dashboard screen
/**
 * GreenFuelThread — Hidalgo "Crystallized Imagination" visualization
 *
 * Shows each visible project as an information-maturity pipeline:
 *   Phase 1 (high entropy)  → raw engineering data, specs, permits
 *   Phase 2 (crystallizing) → finance/insurance signatures lock structure
 *   Phase 3 (low entropy)   → bankable asset, ready for offtake
 *
 * Key design principles (César Hidalgo):
 *   - Information is NOT displayed, it is GROWN. Each person-byte
 *     (Olaf → Henrik → Florian → Frank) adds structure.
 *   - Permissioned visibility = invisible pruning, not graying.
 *     If you can't see it, the node doesn't exist in your universe.
 *   - The "thread" shows transformation: e-Methanol → SAF is a
 *     visible state change in the molecule's digital twin.
 *
 * Roles see different depths:
 *   PRODUCER   → full thread from engineering to settlement
 *   OFFTAKER   → Phase 2-3 only (from contract to delivery)
 *   BANK       → Gatekeeper view: provenance trail with signatures
 *   INSURER    → Gatekeeper view: risk events + coverage confirmations
 *   ENGINEER   → Phase 1 only (specs, plant builder, OT data)
 */

import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ChevronRight, Zap, ShieldCheck, FileCheck2,
  Landmark, PackageCheck, Truck, Award,
} from 'lucide-react'
import { type CustomerProject } from '@/data/customerProjects'
import { useUserRole } from '@/contexts/UserRoleContext'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

/** A single "person-byte" — someone who added information to the thread */
interface PersonByte {
  actor: string        // name or role label
  company: string
  action: string       // what they crystallized
  gate?: string        // bankability gate this relates to
  timestamp: string    // display date
  phase: 1 | 2 | 3
  link?: string        // navigate to this screen
  /** If this person-byte is visible to current user */
  visible: boolean
}

/** Entropy level for the maturity visualization */
type EntropyLevel = 'high' | 'medium' | 'low' | 'settled'

interface ProjectThread {
  project: CustomerProject
  entropy: EntropyLevel
  entropyPct: number           // 0-100 where 100 = fully crystallized
  personBytes: PersonByte[]
  transformation?: string      // e.g. "e-Methanol → SAF" if applicable
}

// ═══════════════════════════════════════════════════════════════
// PERSON-BYTE BUILDER — derives the information trail from real data
// ═══════════════════════════════════════════════════════════════

/** Map gate completion to actors who contributed */
function buildPersonBytes(
  project: CustomerProject,
  companyType: string,
  serviceType: string | null,
  businessFunction: string,
): PersonByte[] {
  const gates = project.bankability.gates
  const bytes: PersonByte[] = []

  // ── Phase 1: Engineering person-bytes ──────────────────────
  const g0 = gates.find(g => g.id === 'G0_SITE_RIGHTS')
  if (g0 && g0.completion_pct > 0) {
    bytes.push({
      actor: 'Project Developer',
      company: project.owner_company,
      action: `Site rights secured (${g0.completion_pct}%)`,
      gate: 'G0',
      timestamp: 'Q1 2025',
      phase: 1,
      link: '/stage-gates',
      visible: companyType === 'PRODUCER' || serviceType === 'ENGINEER' || serviceType === 'BANK',
    })
  }

  const g1 = gates.find(g => g.id === 'G1_GRID_UTILITIES')
  if (g1 && g1.completion_pct > 0) {
    bytes.push({
      actor: 'Siemens Energy (Olaf Jacques)',
      company: 'Siemens Energy',
      action: `Grid connection ${g1.is_complete ? 'confirmed' : `at ${g1.completion_pct}%`}`,
      gate: 'G1',
      timestamp: 'Q2 2025',
      phase: 1,
      link: '/stage-gates',
      visible: companyType === 'PRODUCER' || serviceType === 'ENGINEER' || serviceType === 'BANK',
    })
  }

  const g5 = gates.find(g => g.id === 'G5_EPC_RISK_PRICED')
  if (g5 && g5.completion_pct > 0) {
    bytes.push({
      actor: 'EPC Contractor',
      company: 'Siemens Energy',
      action: `EPC risk priced (${g5.completion_pct}%)`,
      gate: 'G5',
      timestamp: 'Q3 2025',
      phase: 1,
      link: '/finance-plant-builder',
      visible: companyType === 'PRODUCER' || serviceType === 'ENGINEER' || serviceType === 'BANK',
    })
  }

  // ── Phase 2: Finance & Insurance crystallization ───────────
  const g4 = gates.find(g => g.id === 'G4_OFFTAKE_BANKABLE')
  if (g4 && g4.completion_pct > 0) {
    bytes.push({
      actor: 'Commercial Team',
      company: project.owner_company,
      action: `Offtake ${g4.is_complete ? 'bankable' : `at ${g4.completion_pct}%`}`,
      gate: 'G4',
      timestamp: 'Q4 2025',
      phase: 2,
      link: '/offtake-quality',
      visible: true, // all roles see offtake status
    })
  }

  const g8 = gates.find(g => g.id === 'G8_AUDIT_GRADE_MODEL')
  if (g8 && g8.completion_pct > 0) {
    bytes.push({
      actor: 'NordLB (Henrik Vost)',
      company: 'NordLB',
      action: `Model audit ${g8.is_complete ? 'signed off' : `at ${g8.completion_pct}%`}`,
      gate: 'G8',
      timestamp: 'Q1 2026',
      phase: 2,
      link: '/dscr-sensitivity',
      visible: companyType !== 'OFFTAKER' || businessFunction === 'FINANCE_TREASURY',
    })
  }

  // Insurance signature
  if (project.molecule_gating?.molecule_insurance_placed) {
    bytes.push({
      actor: 'Allianz (Florian Schmidt)',
      company: 'Allianz',
      action: 'Molecule insurance placed',
      gate: 'G7',
      timestamp: 'Q1 2026',
      phase: 2,
      link: '/insurance-schedule',
      visible: serviceType === 'INSURER' || serviceType === 'BANK' || companyType === 'PRODUCER',
    })
  } else {
    // Show pending state for insurer/bank
    bytes.push({
      actor: 'Insurer',
      company: project.associated_companies.find(c => c.includes('Allianz') || c.includes('Zürich')) ?? 'Pending',
      action: 'Insurance programme pending',
      gate: 'G7',
      timestamp: '—',
      phase: 2,
      link: '/insurance-schedule',
      visible: serviceType === 'INSURER' || serviceType === 'BANK' || companyType === 'PRODUCER',
    })
  }

  // Capital commitment signatures
  const capitalSigned = project.bankability.capital_status.filter(
    c => c.commitment_status === 'DRAWN' || c.commitment_status === 'LEGAL_COMPLETE' || c.commitment_status === 'CREDIT_APPROVED',
  )
  if (capitalSigned.length > 0) {
    bytes.push({
      actor: `${capitalSigned.length} capital line${capitalSigned.length > 1 ? 's' : ''} committed`,
      company: 'Multiple',
      action: capitalSigned.map(c => `${c.name} (${c.amount})`).join(', '),
      timestamp: 'Q2 2026',
      phase: 2,
      link: '/capital-stack',
      visible: serviceType === 'BANK' || companyType === 'PRODUCER' || businessFunction === 'FINANCE_TREASURY',
    })
  }

  // ── Phase 3: Low-entropy asset (offtake ready) ─────────────
  if (project.bankability.overall_completion >= 70) {
    bytes.push({
      actor: 'Asset Crystallized',
      company: '—',
      action: `${project.molecule} at ${project.capacity_mtpd} MTPD — bankable asset`,
      timestamp: project.completion_date.slice(0, 7).replace('-', ' Q'),
      phase: 3,
      link: '/commitment-signing',
      visible: true,
    })
  }

  // Settlement / carbon credit
  if (project.status === 'operating') {
    bytes.push({
      actor: 'Settlement',
      company: '—',
      action: `Production active — carbon credits generating`,
      timestamp: 'Ongoing',
      phase: 3,
      link: '/production',
      visible: true,
    })
  }

  return bytes
}

function deriveEntropy(project: CustomerProject): { level: EntropyLevel; pct: number } {
  const c = project.bankability.overall_completion
  if (c >= 85) return { level: 'settled', pct: c }
  if (c >= 65) return { level: 'low', pct: c }
  if (c >= 40) return { level: 'medium', pct: c }
  return { level: 'high', pct: c }
}

// ═══════════════════════════════════════════════════════════════
// PHASE INDICATOR — the entropy-to-crystal visual
// ═══════════════════════════════════════════════════════════════

const ENTROPY_STYLES: Record<EntropyLevel, { bg: string; border: string; label: string; icon: typeof Zap }> = {
  high:    { bg: 'bg-amber-50', border: 'border-amber-200', label: 'High Entropy', icon: Zap },
  medium:  { bg: 'bg-blue-50',  border: 'border-blue-200',  label: 'Crystallizing', icon: ShieldCheck },
  low:     { bg: 'bg-emerald-50', border: 'border-emerald-200', label: 'Low Entropy', icon: PackageCheck },
  settled: { bg: 'bg-gray-50',  border: 'border-gray-300',  label: 'Settled Asset', icon: Award },
}

function EntropyBadge({ level, pct }: { level: EntropyLevel; pct: number }) {
  const s = ENTROPY_STYLES[level]
  const Icon = s.icon
  return (
    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold ${s.bg} ${s.border} border`}>
      <Icon size={12} className="opacity-70" />
      {s.label} · {pct}%
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// CRYSTALLIZATION BAR — the 3-phase maturity gradient
// ═══════════════════════════════════════════════════════════════

function CrystallizationBar({ project }: { project: CustomerProject }) {
  const gates = project.bankability.gates
  // Phase 1 score: avg of engineering gates (G0, G1, G5)
  const engGates = gates.filter(g => ['G0_SITE_RIGHTS', 'G1_GRID_UTILITIES', 'G5_EPC_RISK_PRICED'].includes(g.id))
  const phase1 = engGates.length > 0
    ? Math.round(engGates.reduce((s, g) => s + g.completion_pct, 0) / engGates.length)
    : 0

  // Phase 2 score: avg of finance gates (G4, G8)
  const finGates = gates.filter(g => ['G4_OFFTAKE_BANKABLE', 'G8_AUDIT_GRADE_MODEL'].includes(g.id))
  const phase2 = finGates.length > 0
    ? Math.round(finGates.reduce((s, g) => s + g.completion_pct, 0) / finGates.length)
    : 0

  // Phase 3: overall > 70% = settled
  const phase3 = project.bankability.overall_completion >= 70 ? 100 : Math.max(0, (project.bankability.overall_completion - 50) * 5)

  return (
    <div className="flex items-center gap-0.5 h-2.5 w-full">
      {/* Phase 1: amber/warm = high entropy */}
      <div className="h-full rounded-l-full bg-gray-100 flex-1 overflow-hidden" title={`Engineering: ${phase1}%`}>
        <div
          className="h-full rounded-l-full transition-all duration-700"
          style={{ width: `${phase1}%`, background: 'linear-gradient(90deg, #f59e0b, #fbbf24)' }}
        />
      </div>
      {/* Phase 2: blue = crystallizing */}
      <div className="h-full bg-gray-100 flex-1 overflow-hidden" title={`Finance: ${phase2}%`}>
        <div
          className="h-full transition-all duration-700"
          style={{ width: `${phase2}%`, background: 'linear-gradient(90deg, #3b82f6, #60a5fa)' }}
        />
      </div>
      {/* Phase 3: teal = low entropy / settled */}
      <div className="h-full rounded-r-full bg-gray-100 flex-1 overflow-hidden" title={`Settlement: ${phase3}%`}>
        <div
          className="h-full rounded-r-full transition-all duration-700"
          style={{ width: `${phase3}%`, background: 'linear-gradient(90deg, #0ea5a0, #14b8a6)' }}
        />
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// PERSON-BYTE NODE — one actor's contribution to the thread
// ═══════════════════════════════════════════════════════════════

const PHASE_COLORS: Record<number, string> = {
  1: 'border-l-amber-400',
  2: 'border-l-blue-400',
  3: 'border-l-teal-500',
}

const PHASE_ICONS: Record<number, typeof Zap> = {
  1: Zap,
  2: Landmark,
  3: PackageCheck,
}

function PersonByteNode({ pb, navigate }: { pb: PersonByte; navigate: (path: string) => void }) {
  const Icon = PHASE_ICONS[pb.phase] ?? FileCheck2
  return (
    <button
      className={`w-full text-left border-l-3 ${PHASE_COLORS[pb.phase]} pl-3 py-1.5 hover:bg-gray-50 rounded-r transition-colors`}
      onClick={() => pb.link && navigate(pb.link)}
    >
      <div className="flex items-start gap-2">
        <Icon size={13} className="mt-0.5 text-gray-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-gray-900 truncate">{pb.action}</div>
          <div className="text-[10px] text-gray-400 truncate">{pb.actor} · {pb.company} · {pb.timestamp}</div>
        </div>
        {pb.gate && (
          <span className="text-[10px] font-bold text-gray-300 shrink-0">{pb.gate}</span>
        )}
      </div>
    </button>
  )
}

// ═══════════════════════════════════════════════════════════════
// GATEKEEPER VIEW — provenance trail for bankers & insurers
// ═══════════════════════════════════════════════════════════════

function GatekeeperSummary({ project, bytes }: { project: CustomerProject; bytes: PersonByte[] }) {
  const gatedBytes = bytes.filter(b => b.gate)
  const signedGates = project.bankability.gates.filter(g => g.is_complete).length
  const totalGates = project.bankability.gates.length

  return (
    <div className="mt-3 px-3 py-2.5 bg-gray-50 rounded-lg border border-gray-100">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-bold text-gray-500 uppercase tracking-wide flex items-center gap-1.5">
          <FileCheck2 size={12} />
          Provenance Chain
        </div>
        <div className="text-xs text-gray-400">
          {signedGates}/{totalGates} gates verified
        </div>
      </div>
      <div className="flex gap-1">
        {project.bankability.gates.map(g => (
          <div
            key={g.id}
            className={`h-1.5 flex-1 rounded-full ${g.is_complete ? 'bg-teal-500' : g.completion_pct > 0 ? 'bg-blue-300' : 'bg-gray-200'}`}
            title={`${g.name}: ${g.completion_pct}%`}
          />
        ))}
      </div>
      <div className="mt-2 text-[10px] text-gray-400">
        {gatedBytes.length} actor signatures in chain · {project.bankability.unlocked_capital.length} capital lines unlocked
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// TRANSFORMATION BADGE — shows molecule conversion
// ═══════════════════════════════════════════════════════════════

function TransformationBadge({ from, to }: { from: string; to: string }) {
  return (
    <div className="inline-flex items-center gap-1 px-2 py-0.5 bg-violet-50 border border-violet-200 rounded text-[10px] font-bold text-violet-700">
      {from} <Truck size={10} /> {to}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

interface Props {
  projects: CustomerProject[]
}

export function GreenFuelThread({ projects }: Props) {
  const navigate = useNavigate()
  const { role } = useUserRole()

  const threads: ProjectThread[] = useMemo(() => {
    return projects.map(project => {
      const { level, pct } = deriveEntropy(project)
      const allBytes = buildPersonBytes(
        project,
        role.company_type,
        role.service_type ?? null,
        role.business_function,
      )

      // INVISIBLE PRUNING — Hidalgo principle: don't gray out, remove entirely.
      // This keeps the system's entropy low for each user.
      const visibleBytes = allBytes.filter(b => b.visible)

      // Detect molecule transformation potential (prosumer)
      const transformation = project.molecule === 'e-Methanol'
        ? 'e-Methanol → SAF'
        : project.molecule === 'H2'
          ? 'H2 → e-Methanol / NH3'
          : undefined

      return { project, entropy: level, entropyPct: pct, personBytes: visibleBytes, transformation }
    })
  }, [projects, role.company_type, role.service_type, role.business_function])

  const isGatekeeper = role.service_type === 'BANK' || role.service_type === 'INSURER'

  if (threads.length === 0) return null

  return (
    <div className="space-y-4">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wide">
            {isGatekeeper ? 'Provenance & Maturity' : 'Green Fuel Thread'}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {isGatekeeper
              ? 'Molecule provenance chain — each signature reduces project entropy'
              : 'Information crystallization from engineering to settlement'}
          </p>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-gray-400">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400" /> Engineering</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-400" /> Finance</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-teal-500" /> Settlement</span>
        </div>
      </div>

      {/* Project threads */}
      {threads.map(({ project, entropy, entropyPct, personBytes, transformation }) => (
        <div
          key={project.id}
          className="bg-white rounded-xl border border-gray-200 overflow-hidden"
        >
          {/* Thread header */}
          <div className="px-4 py-3 flex items-center justify-between border-b border-gray-50">
            <div className="flex items-center gap-3 min-w-0">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-gray-900 truncate">{project.name}</span>
                  <span className="text-xs text-gray-400">{project.molecule}</span>
                  {transformation && <TransformationBadge from={transformation.split(' → ')[0]} to={transformation.split(' → ')[1]} />}
                </div>
                <div className="text-[11px] text-gray-400 mt-0.5">
                  {project.location} · {project.capacity_mtpd} MTPD · {project.status}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <EntropyBadge level={entropy} pct={entropyPct} />
              <button
                onClick={() => navigate(`/projects?name=${encodeURIComponent(project.name)}`)}
                className="p-1.5 hover:bg-gray-100 rounded-lg"
              >
                <ChevronRight size={16} className="text-gray-400" />
              </button>
            </div>
          </div>

          {/* Crystallization bar */}
          <div className="px-4 pt-3">
            <CrystallizationBar project={project} />
            <div className="flex justify-between text-[10px] text-gray-300 mt-1 px-0.5">
              <span>Engineering</span>
              <span>Finance & Insurance</span>
              <span>Settlement</span>
            </div>
          </div>

          {/* Person-byte trail — the information breadcrumbs */}
          <div className="px-4 py-3 space-y-0.5">
            {personBytes.map((pb, i) => (
              <PersonByteNode key={`${pb.gate ?? i}-${pb.actor}`} pb={pb} navigate={navigate} />
            ))}
          </div>

          {/* Gatekeeper provenance summary (bankers & insurers only) */}
          {isGatekeeper && (
            <div className="px-4 pb-3">
              <GatekeeperSummary project={project} bytes={personBytes} />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
