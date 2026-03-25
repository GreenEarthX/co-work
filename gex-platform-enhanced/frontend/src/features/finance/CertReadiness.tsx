import { useState, useEffect } from 'react'
import { CheckCircle2, XCircle, AlertTriangle, Clock, Award, Zap } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { HELP, TAB_DESCRIPTIONS } from '@/config/helpText'
import { CUSTOMER_PROJECTS } from '@/data/customerProjects'
import { useSelectedProject } from '@/contexts/ProjectContext'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

type GateStatus = 'PASS' | 'PARTIAL' | 'FAIL'

type CertTrack =
  | 'NOT_STARTED'
  | 'PRE_ASSESSMENT'
  | 'LCA_COMMISSION'
  | 'PRE_AUDIT'
  | 'CERTIFICATION'
  | 'GOO_ISSUANCE'

interface GateEvidence {
  text: string
  pass: boolean
}

interface CertGate {
  id: string
  name: string
  description: string
  status: GateStatus
  score: number
  evidence: GateEvidence[]
}

interface GapRow {
  gate: string
  missing: string
  action: string
  timeToClose: string
}

interface ProjectCert {
  overall: number
  additionality: CertGate
  temporal: CertGate
  geographical: CertGate
  lca: CertGate
  track: CertTrack
  verifier: string
  nextAction: string
  gaps: GapRow[]
}

// ═══════════════════════════════════════════════════════════════
// DEMO DATA
// ═══════════════════════════════════════════════════════════════

function makeGate(
  id: string,
  name: string,
  description: string,
  status: GateStatus,
  score: number,
  rawItems: string[]
): CertGate {
  return {
    id,
    name,
    description,
    status,
    score,
    evidence: rawItems.map(item => ({
      text: item.replace(/^[✓✗] /, ''),
      pass: item.startsWith('✓'),
    })),
  }
}

const CERT_DATA: Record<string, ProjectCert> = {
  proj_le_havre_eng: {
    overall: 96,
    additionality: makeGate(
      'additionality', 'Additionality', 'Is the renewable power source new and additional capacity?',
      'PASS', 98,
      ['✓ Dedicated 200MW offshore wind farm (new capacity)', '✓ PPA signed with commissioning date 2024', '✓ Additionality declaration from RTE confirmed', '✓ No grid injection — direct connection']
    ),
    temporal: makeGate(
      'temporal', 'Temporal Correlation', 'Is H₂ production correlated hourly with renewable generation?',
      'PASS', 95,
      ['✓ Hourly matching protocol in place', '✓ SOEC can modulate down to 15% in <5min', '✓ Smart charging controller installed', '✓ Data logger: 15-min intervals, 99.7% uptime']
    ),
    geographical: makeGate(
      'geographical', 'Geographical Correlation', 'Same bidding zone or direct physical connection?',
      'PASS', 98,
      ['✓ Same bidding zone (FR)', '✓ Direct cable connection confirmed', '✓ No cross-zone transfer required']
    ),
    lca: makeGate(
      'lca', 'LCA Intensity', 'Lifecycle CO₂ below 3.4 kgCO₂e/kgH₂ threshold (RFNBO/RED III)?',
      'PASS', 92,
      ['✓ LCA: 0.82 kgCO₂e/kgH₂ (well below 3.4 threshold)', '✓ DNV LCA report completed', '✓ Methane slip: <0.1%', '✓ Electrolysis: SOEC 82% efficiency']
    ),
    track: 'PRE_AUDIT',
    verifier: 'DNV — pre-audit scheduled Q2-2026',
    nextAction: 'Submit pre-audit documentation package to DNV',
    gaps: [],
  },
  proj_bremen_h2: {
    overall: 74,
    additionality: makeGate(
      'additionality', 'Additionality', 'Is the renewable power source new and additional capacity?',
      'PASS', 85,
      ['✓ PPA with Vattenfall offshore wind (new build)', '✓ PPA commissioning date 2023', '✗ Additionality declaration from BNetzA pending', '✓ Grid-connected but RFNBO hourly rule applies']
    ),
    temporal: makeGate(
      'temporal', 'Temporal Correlation', 'Is H₂ production correlated hourly with renewable generation?',
      'PARTIAL', 72,
      ['✓ Hourly matching controller installed', '✗ Periods of grid draw during low-wind — 12% of hours in Q1 2025', '✓ Dynamic modulation protocol in operation', '✗ Backup grid use not yet excluded from LCA boundary']
    ),
    geographical: makeGate(
      'geographical', 'Geographical Correlation', 'Same bidding zone or direct physical connection?',
      'PASS', 88,
      ['✓ Same bidding zone (DE-LU)', '✓ Wind farm within 50km', '✓ No cross-zone transfer']
    ),
    lca: makeGate(
      'lca', 'LCA Intensity', 'Lifecycle CO₂ below 3.4 kgCO₂e/kgH₂ threshold (RFNBO/RED III)?',
      'PARTIAL', 65,
      ['✓ Preliminary LCA: 2.1 kgCO₂e/kgH₂ (below 3.4)', '✗ Full LCA not yet commissioned', '✗ Backup grid emissions not excluded', '✓ PEM efficiency 68% confirmed by commissioning test']
    ),
    track: 'LCA_COMMISSION',
    verifier: 'TÜV Rheinland — engagement letter under review',
    nextAction: 'Commission full LCA study and exclude backup grid use from boundary',
    gaps: [
      { gate: 'Additionality', missing: 'BNetzA declaration pending', action: 'File additionality declaration with BNetzA', timeToClose: '4–6 weeks' },
      { gate: 'Temporal',      missing: '12% grid draw hours unaccounted', action: 'Implement dynamic curtailment to eliminate grid draw', timeToClose: '2–3 months' },
      { gate: 'LCA',           missing: 'Full LCA not commissioned', action: 'Commission TÜV Rheinland LCA — exclude backup grid boundary', timeToClose: '3–4 months' },
    ],
  },
  proj_helios_emethanol: {
    overall: 58,
    additionality: makeGate(
      'additionality', 'Additionality', 'Is the renewable power source new and additional capacity?',
      'PARTIAL', 65,
      ['✓ PPA with Iberdrola solar (new capacity)', '✗ Additionality confirmation from CNMC pending', '✗ PPA covers 80% of demand — 20% grid top-up not yet addressed', '✓ Direct connection planned for 2027']
    ),
    temporal: makeGate(
      'temporal', 'Temporal Correlation', 'Is production correlated hourly with renewable generation?',
      'PARTIAL', 55,
      ['✗ Hourly matching protocol not yet implemented', '✓ Electrolyser can modulate to 20%', '✗ Control system upgrade needed for RFNBO compliance', '✗ 15-min data logging not yet operational']
    ),
    geographical: makeGate(
      'geographical', 'Geographical Correlation', 'Same bidding zone or direct physical connection?',
      'PASS', 82,
      ['✓ Same bidding zone (ES)', '✓ Wind/solar within 100km', '✓ No cross-zone transfer']
    ),
    lca: makeGate(
      'lca', 'LCA Intensity', 'Lifecycle CO₂ below 3.4 kgCO₂e/kgH₂ threshold (RFNBO/RED III)?',
      'PARTIAL', 48,
      ['✗ LCA not yet commissioned', '✓ Expected intensity: ~1.8 kgCO₂e/kgH₂ (estimate only)', '✗ CO₂ feedstock chain LCA required (methanol pathway)', '✗ No verifier engaged']
    ),
    track: 'PRE_ASSESSMENT',
    verifier: 'None engaged',
    nextAction: 'Commission LCA study and implement hourly matching protocol',
    gaps: [
      { gate: 'Additionality',  missing: 'CNMC declaration missing; 20% grid top-up not addressed', action: 'File with CNMC; negotiate additional PPA capacity', timeToClose: '4–8 weeks' },
      { gate: 'Temporal',       missing: 'No hourly matching; control system upgrade required', action: 'Install 15-min data logger and dynamic control system', timeToClose: '3–5 months' },
      { gate: 'LCA',            missing: 'LCA not commissioned; CO₂ feedstock chain missing', action: 'Engage verifier and scope full methanol pathway LCA', timeToClose: '5–7 months' },
    ],
  },
  proj_rotterdam_nh3: {
    overall: 22,
    additionality: makeGate(
      'additionality', 'Additionality', 'Is the renewable power source new and additional capacity?',
      'FAIL', 20,
      ['✗ No PPA signed', '✗ No additionality plan', '✗ Grid power only — disqualified for RFNBO under current structure', '✗ Wind farm site not identified']
    ),
    temporal: makeGate(
      'temporal', 'Temporal Correlation', 'Is production correlated hourly with renewable generation?',
      'FAIL', 10,
      ['✗ No renewable power agreement', '✗ No modulation protocol', '✗ Grid-only operation not RFNBO compliant']
    ),
    geographical: makeGate(
      'geographical', 'Geographical Correlation', 'Same bidding zone or direct physical connection?',
      'FAIL', 15,
      ['✗ No dedicated renewable generation', '✗ Grid power from NL bidding zone — mixed origin']
    ),
    lca: makeGate(
      'lca', 'LCA Intensity', 'Lifecycle CO₂ below 3.4 kgCO₂e/kgH₂ threshold (RFNBO/RED III)?',
      'FAIL', 18,
      ['✗ No LCA commissioned', '✗ Grid power LCA: ~18 kgCO₂e/kgH₂ (well above 3.4 limit)', '✗ Project structurally non-compliant until power sourcing resolved']
    ),
    track: 'NOT_STARTED',
    verifier: 'None',
    nextAction: 'CRITICAL: Secure dedicated renewable PPA before any certification pathway can begin',
    gaps: [
      { gate: 'Additionality',  missing: 'No PPA, no additionality plan, grid-only structure', action: 'CRITICAL: Source and execute dedicated renewable PPA', timeToClose: '6–12 months' },
      { gate: 'Temporal',       missing: 'No renewable agreement, no modulation', action: 'Cannot proceed until power sourcing resolved', timeToClose: '12+ months' },
      { gate: 'Geographical',   missing: 'No dedicated generation in zone', action: 'Identify wind/solar asset within NL bidding zone', timeToClose: '6–12 months' },
      { gate: 'LCA',            missing: 'LCA would fail (18 kgCO₂e/kgH₂ grid intensity)', action: 'LCA cannot pass until renewable power secured', timeToClose: '12+ months' },
    ],
  },
  proj_wales_saf: {
    overall: 18,
    additionality: makeGate(
      'additionality', 'Additionality', 'Is the renewable power source new and additional capacity?',
      'FAIL', 15,
      ['✗ No PPA executed', '✗ LOI with grid-balancing wind only', '✗ Additionality not established']
    ),
    temporal: makeGate(
      'temporal', 'Temporal Correlation', 'Is production correlated hourly with renewable generation?',
      'FAIL', 12,
      ['✗ No hourly matching', '✗ Fischer-Tropsch cannot modulate on hourly basis', '✗ SAF pathway requires upstream H₂ hourly matching']
    ),
    geographical: makeGate(
      'geographical', 'Geographical Correlation', 'Same bidding zone or direct physical connection?',
      'PARTIAL', 35,
      ['✓ Welsh offshore wind in same GB zone', '✗ No direct connection or firm capacity', '✗ Transmission constraints in Welsh grid identified']
    ),
    lca: makeGate(
      'lca', 'LCA Intensity', 'Lifecycle CO₂ below 3.4 kgCO₂e/kgH₂ threshold (RFNBO/RED III)?',
      'FAIL', 10,
      ['✗ No LCA commissioned', '✗ F-T SAF pathway LCA complex — needs verifier', '✗ No efficiency data available']
    ),
    track: 'NOT_STARTED',
    verifier: 'None',
    nextAction: 'Project not cert-ready. Resolve power sourcing and offtake before certification planning.',
    gaps: [
      { gate: 'Additionality',  missing: 'No executed PPA; LOI insufficient', action: 'Execute dedicated offshore wind PPA', timeToClose: '9–12 months' },
      { gate: 'Temporal',       missing: 'F-T process cannot hourly-match; no upstream H₂ matching', action: 'Redesign process to enable H₂ buffer and hourly matching', timeToClose: '12+ months' },
      { gate: 'Geographical',   missing: 'No firm capacity; transmission constraint identified', action: 'Secure firm grid connection and resolve transmission constraint', timeToClose: '12–18 months' },
      { gate: 'LCA',            missing: 'No data; F-T SAF LCA scope undefined', action: 'Commission verifier for SAF LCA once power sourcing resolved', timeToClose: '12+ months' },
    ],
  },
}

// ═══════════════════════════════════════════════════════════════
// CERTIFICATION TRACK CONFIG
// ═══════════════════════════════════════════════════════════════

const TRACK_MILESTONES: { id: CertTrack; label: string }[] = [
  { id: 'NOT_STARTED',    label: 'Not Started' },
  { id: 'PRE_ASSESSMENT', label: 'Pre-Assessment' },
  { id: 'LCA_COMMISSION', label: 'LCA Commission' },
  { id: 'PRE_AUDIT',      label: 'Pre-Audit' },
  { id: 'CERTIFICATION',  label: 'Certification' },
  { id: 'GOO_ISSUANCE',   label: 'GoO Issuance' },
]

const TRACK_INDEX: Record<CertTrack, number> = {
  NOT_STARTED:    0,
  PRE_ASSESSMENT: 1,
  LCA_COMMISSION: 2,
  PRE_AUDIT:      3,
  CERTIFICATION:  4,
  GOO_ISSUANCE:   5,
}

// ═══════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════

const STATUS_META: Record<GateStatus, { label: string; bg: string; text: string; border: string }> = {
  PASS:    { label: 'PASS',    bg: 'bg-green-50',  text: 'text-green-700',  border: 'border-green-200' },
  PARTIAL: { label: 'PARTIAL', bg: 'bg-amber-50',  text: 'text-amber-700',  border: 'border-amber-200' },
  FAIL:    { label: 'FAIL',    bg: 'bg-red-50',    text: 'text-red-700',    border: 'border-red-200' },
}

const STATUS_BADGE: Record<GateStatus, string> = {
  PASS:    'bg-green-100 text-green-700',
  PARTIAL: 'bg-amber-100 text-amber-700',
  FAIL:    'bg-red-100 text-red-700',
}

function scoreColor(score: number) {
  if (score >= 70) return '#22c55e'
  if (score >= 40) return '#f59e0b'
  return '#ef4444'
}

// Overall readiness gauge — 270° arc
function ReadinessGauge({ score }: { score: number }) {
  const size = 130
  const cx = size / 2
  const cy = size / 2
  const r = 50
  const toRad = (d: number) => (d * Math.PI) / 180
  const startAngle = 225
  const totalSweep = 270
  const arcFill = startAngle + (score / 100) * totalSweep

  function polar(angle: number) {
    return { x: cx + r * Math.cos(toRad(angle)), y: cy + r * Math.sin(toRad(angle)) }
  }

  const s = polar(startAngle)
  const e = polar(startAngle + totalSweep)
  const f = polar(arcFill)
  const color = scoreColor(score)

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <path
        d={`M ${s.x} ${s.y} A ${r} ${r} 0 1 1 ${e.x} ${e.y}`}
        fill="none" stroke="#e5e7eb" strokeWidth={11} strokeLinecap="round"
      />
      <path
        d={`M ${s.x} ${s.y} A ${r} ${r} 0 ${arcFill - startAngle > 180 ? 1 : 0} 1 ${f.x} ${f.y}`}
        fill="none" stroke={color} strokeWidth={11} strokeLinecap="round"
      />
      <text x={cx} y={cy - 4} textAnchor="middle" fontSize={24} fontWeight="bold" fill={color}>{score}</text>
      <text x={cx} y={cy + 15} textAnchor="middle" fontSize={10} fill="#94a3b8">/100</text>
    </svg>
  )
}

// Single gate card (2×2 grid)
function GateCard({ gate }: { gate: CertGate }) {
  const meta = STATUS_META[gate.status]
  const color = scoreColor(gate.score)
  return (
    <div
      className={`rounded-xl p-4 flex flex-col gap-3 ${meta.bg} border ${meta.border}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-bold text-sm">{gate.name}</p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted, #64748b)' }}>{gate.description}</p>
        </div>
        <span className={`shrink-0 px-2 py-0.5 rounded-full text-xs font-bold ${STATUS_BADGE[gate.status]}`}>
          {meta.label}
        </span>
      </div>

      {/* Score bar */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-2 rounded-full bg-white/60 overflow-hidden">
          <div className="h-full rounded-full transition-all duration-500" style={{ width: `${gate.score}%`, backgroundColor: color }} />
        </div>
        <span className="text-xs font-bold w-8 text-right" style={{ color }}>{gate.score}</span>
      </div>

      {/* Evidence */}
      <ul className="flex flex-col gap-1">
        {gate.evidence.map((ev, i) => (
          <li key={i} className="flex items-start gap-1.5 text-xs">
            {ev.pass
              ? <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-green-600" />
              : <XCircle size={12} className="mt-0.5 shrink-0 text-red-500" />
            }
            <span style={{ color: ev.pass ? '#166534' : '#991b1b' }}>{ev.text}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// Certification track progress bar
function CertTrackBar({ current }: { current: CertTrack }) {
  const currentIdx = TRACK_INDEX[current]
  return (
    <div className="relative">
      {/* Connecting line */}
      <div
        className="absolute top-4 left-0 right-0 h-0.5 z-0"
        style={{ backgroundColor: '#e5e7eb', margin: '0 20px' }}
      />
      <div className="flex justify-between relative z-10">
        {TRACK_MILESTONES.map((m, i) => {
          const done    = i < currentIdx
          const active  = i === currentIdx
          const pending = i > currentIdx
          return (
            <div key={m.id} className="flex flex-col items-center gap-1" style={{ width: 80 }}>
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center border-2 text-xs font-bold transition-all"
                style={{
                  backgroundColor: done ? '#22c55e' : active ? 'var(--brand, #0ea5e9)' : '#fff',
                  borderColor: done ? '#22c55e' : active ? 'var(--brand, #0ea5e9)' : '#d1d5db',
                  color: done || active ? '#fff' : '#9ca3af',
                }}
              >
                {done ? <CheckCircle2 size={14} /> : i + 1}
              </div>
              <p
                className="text-center font-medium leading-tight"
                style={{
                  fontSize: 9,
                  color: done ? '#15803d' : active ? 'var(--brand, #0ea5e9)' : '#9ca3af',
                  maxWidth: 72,
                }}
              >
                {m.label}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

export function CertReadiness() {
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject()
  const [data, setData] = useState<ProjectCert | null>(null)

  const project = CUSTOMER_PROJECTS.find(p => p.id === selectedProjectId) ?? CUSTOMER_PROJECTS[0]

  useEffect(() => {
    // Demo data fallback — API not available
    const d = CERT_DATA[selectedProjectId] ?? CERT_DATA[CUSTOMER_PROJECTS[0].id]
    setData(d)
  }, [selectedProjectId])

  if (!data) return null

  const readinessLabel =
    data.overall >= 80 ? 'Ready for verifier engagement' :
    data.overall >= 50 ? 'Partial readiness — gaps to close' :
    data.overall >= 25 ? 'Significant gaps — certification not imminent' :
    'Not cert-ready — foundational issues to resolve'

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: 'var(--surface, #f8fafc)', color: 'var(--text, #0f172a)' }}>

      {/* ── Header ──────────────────────────────────────────── */}
      <div className="mb-6">
        <h1 className="text-xl font-bold mb-1">Certification Readiness</h1>
        <p className="text-sm" style={{ color: 'var(--text-muted, #64748b)' }}>
          {TAB_DESCRIPTIONS.CERT_READINESS}
        </p>
      </div>

      {/* ── Project selector + readiness gauge ──────────────── */}
      <div
        className="rounded-xl p-5 mb-6 flex flex-col sm:flex-row items-start sm:items-center gap-6"
        style={{ border: '1px solid var(--border, #e2e8f0)', backgroundColor: 'var(--surface-raised, #f8fafc)' }}
      >
        <div className="flex-1">
          <label className="block text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted, #64748b)' }}>
            Project
          </label>
          <select
            value={selectedProjectId}
            onChange={e => setSelectedProjectId(e.target.value)}
            className="w-full rounded-lg px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2"
            style={{
              border: '1px solid var(--border, #e2e8f0)',
              backgroundColor: 'var(--surface, #fff)',
              color: 'var(--text, #0f172a)',
            }}
          >
            {CUSTOMER_PROJECTS.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <p className="text-xs mt-2" style={{ color: 'var(--text-muted, #64748b)' }}>
            {project.location} · {project.molecule} · {project.phase}
          </p>
          <div className="mt-3 flex items-start gap-2 p-3 rounded-lg" style={{ backgroundColor: 'var(--surface, #f1f5f9)', border: '1px solid var(--border, #e2e8f0)' }}>
            <Zap size={14} className="mt-0.5 shrink-0" style={{ color: 'var(--brand, #0ea5e9)' }} />
            <div>
              <p className="text-xs font-semibold" style={{ color: 'var(--brand, #0ea5e9)' }}>Verifier</p>
              <p className="text-xs" style={{ color: 'var(--text-muted, #64748b)' }}>{data.verifier}</p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <ReadinessGauge score={data.overall} />
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide mb-1 flex items-center gap-1" style={{ color: 'var(--text-muted, #64748b)' }}>
              Overall Cert Readiness <InfoTooltip text={HELP.CERT_READINESS_SCORE} />
            </p>
            <p className="text-2xl font-bold" style={{ color: scoreColor(data.overall) }}>{data.overall}/100</p>
            <p className="text-xs mt-1 max-w-36" style={{ color: 'var(--text-muted, #64748b)' }}>{readinessLabel}</p>
          </div>
        </div>
      </div>

      {/* ── Certification Track ──────────────────────────────── */}
      <div
        className="rounded-xl p-5 mb-6"
        style={{ border: '1px solid var(--border, #e2e8f0)', backgroundColor: 'var(--surface-raised, #f8fafc)' }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Award size={16} style={{ color: 'var(--brand, #0ea5e9)' }} />
          <h2 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--brand, #0ea5e9)' }}>
            Certification Track
          </h2>
        </div>
        <CertTrackBar current={data.track} />
        <div className="mt-4 flex items-start gap-2 p-3 rounded-lg bg-blue-50 border border-blue-200">
          <Clock size={14} className="text-blue-600 mt-0.5 shrink-0" />
          <p className="text-xs text-blue-700">
            <span className="font-semibold">Next action: </span>{data.nextAction}
          </p>
        </div>
      </div>

      {/* ── Four Gate Cards (2×2 grid) ───────────────────────── */}
      <div className="mb-6">
        <h2 className="text-sm font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--brand, #0ea5e9)' }}>
          Four RFNBO Gates
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <GateCard gate={data.additionality} />
          <GateCard gate={data.temporal} />
          <GateCard gate={data.geographical} />
          <GateCard gate={data.lca} />
        </div>
      </div>

      {/* ── Readiness Gap Analysis Table ─────────────────────── */}
      {data.gaps.length > 0 ? (
        <div className="mb-4">
          <h2 className="text-sm font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--brand, #0ea5e9)' }}>
            Readiness Gap Analysis
          </h2>
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--border, #e2e8f0)' }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ backgroundColor: 'var(--surface-raised, #f1f5f9)' }}>
                  {['Gate', 'What\'s Missing', 'Required Action', 'Time to Close'].map(h => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left font-semibold text-xs uppercase tracking-wide"
                      style={{ color: 'var(--text-muted, #64748b)' }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.gaps.map((gap, i) => (
                  <tr key={i} style={{ borderTop: '1px solid var(--border, #e2e8f0)' }}>
                    <td className="px-4 py-3 font-semibold text-xs">{gap.gate}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: '#b45309' }}>{gap.missing}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: 'var(--text-muted, #64748b)' }}>{gap.action}</td>
                    <td className="px-4 py-3 text-xs font-mono font-medium" style={{ color: '#0f172a' }}>{gap.timeToClose}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div
          className="rounded-xl p-4 flex items-center gap-3"
          style={{ border: '1px solid #86efac', backgroundColor: '#f0fdf4' }}
        >
          <CheckCircle2 size={18} className="text-green-600 shrink-0" />
          <p className="text-sm text-green-700 font-medium">
            No material gaps identified. Project is ready for verifier pre-audit engagement.
          </p>
        </div>
      )}
    </div>
  )
}
