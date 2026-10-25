// Screen: Certification readiness screen (/cert-readiness, /finance/cert-readiness)
import { useState, useEffect } from 'react'
import { CheckCircle2, XCircle, Clock, Award, Zap, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { HELP, TAB_DESCRIPTIONS } from '@/config/helpText'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { fetchCertificationGate, type CertificationGateResult } from '@/lib/certificationGateApi'
import { useProjectDataset, UnverifiedBadge } from './useProjectDataset'

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
// US 45V SECTION (shown only when project.country === 'US')
// ═══════════════════════════════════════════════════════════════

function V45Section({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(true)
  // project_dataset cert_45v (PostgreSQL since 2026-10-25), UNVERIFIED.
  const gates = useProjectDataset<CertGate[]>('cert_45v', projectId).data

  // Compute overall 45V score
  const overall45v = gates
    ? Math.round(gates.reduce((sum, g) => sum + g.score, 0) / gates.length)
    : null

  return (
    <div className="mb-6">
      {/* Amber conflict banner */}
      <div className="mb-4 flex items-start gap-3 p-4 rounded-xl border border-amber-300 bg-amber-50">
        <AlertTriangle size={16} className="shrink-0 mt-0.5 text-amber-600" />
        <div>
          <p className="text-xs font-bold text-amber-800 mb-0.5">45V + RFNBO: Double-Claim Risk</p>
          <p className="text-xs text-amber-700">
            Claiming both certifications on the same renewable energy attributes creates a double-claim risk.
            If 45V is primary, RFNBO can only apply to EU-destination volumes using separate energy attribute accounting.
            GEX recommendation: elect <strong>45V as primary</strong> for all US-produced hydrogen;
            apply RFNBO as secondary pathway for CIF Rotterdam offtake volumes only.
          </p>
        </div>
      </div>

      {/* Section header with toggle */}
      <button
        className="w-full flex items-center justify-between mb-3 group"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex items-center gap-2">
          <h2
            className="text-sm font-bold uppercase tracking-wide"
            style={{ color: '#1d4ed8' }}
          >
            US 45V Clean Hydrogen Track
          </h2>
          {overall45v !== null && (
            <span
              className="px-2 py-0.5 rounded-full text-xs font-bold"
              style={{
                backgroundColor: overall45v >= 70 ? '#dcfce7' : overall45v >= 50 ? '#fef3c7' : '#fee2e2',
                color: overall45v >= 70 ? '#15803d' : overall45v >= 50 ? '#92400e' : '#991b1b',
              }}
            >
              {overall45v}/100
            </span>
          )}
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
            $3/kg PTC (Tier 1 pathway)
          </span>
        </div>
        {open
          ? <ChevronUp size={16} className="text-slate-400 group-hover:text-slate-600" />
          : <ChevronDown size={16} className="text-slate-400 group-hover:text-slate-600" />
        }
      </button>

      {open && (
        <>
          {gates ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {gates.map(g => <GateCard key={g.id} gate={g} />)}
            </div>
          ) : (
            <div className="rounded-xl p-4 border border-slate-200 bg-slate-50 text-sm text-slate-500">
              No 45V gate data available for this project.
            </div>
          )}

          {/* Recommendation */}
          <div className="mt-4 flex items-start gap-2 p-3 rounded-lg border border-blue-200 bg-blue-50">
            <Zap size={14} className="mt-0.5 shrink-0 text-blue-600" />
            <p className="text-xs text-blue-700">
              <span className="font-semibold">Recommendation: </span>
              Elect 45V primary. Prevailing wage filing (Q2 2026) is the next gating action — clears Tier 1 credit
              at ~$170/t e-methanol equivalent. RFNBO secondary: apply only to EU-destination volumes (CIF Rotterdam
              offtake) once IRS temporal rule is finalised.
            </p>
          </div>
        </>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════
// LIVE regime-forked certification gate (backend /api/v1/tea/certification-gate)
// Reads the project's PERSISTED ledger claims and shows whether the gate is open
// for the fuel's pathway_class — RFNBO vs advanced biofuel require DIFFERENT claims.
// ═══════════════════════════════════════════════════════════════

// Map a project's molecule label → a process-function fuel_id.
function moleculeToFuelId(molecule: string | undefined): string {
  const m = (molecule ?? '').toLowerCase()
  if (m.includes('methanol')) return 'E_METHANOL'
  if (m.includes('methane') || m.includes('e-ng')) return 'E_METHANE'
  if (m.includes('ammonia')) return 'E_AMMONIA'
  if (m.includes('hydrogen') || m === 'h2') return 'GREEN_H2'
  if (m.includes('saf') || m.includes('jet') || m.includes('aviation')) return 'E_SAF'
  return 'E_SAF'
}

function LiveCertGatePanel({ projectId, molecule }: { projectId: string; molecule?: string }) {
  const [data, setData] = useState<CertificationGateResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const fuelId = moleculeToFuelId(molecule)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    setLoading(true); setError(null)
    fetchCertificationGate(projectId, fuelId)
      .then(r => { if (!cancelled) setData(r) })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [projectId, fuelId])

  const claimRow = (c: string, waived: boolean) => {
    const state = data?.claim_states_from_ledger?.[c]
    const ok = state === 'verified' || state === 'satisfied' || state === 'waived'
    return (
      <div key={c} className="flex items-center gap-2 text-xs py-0.5">
        {waived
          ? <Clock size={13} className="text-slate-400" />
          : ok ? <CheckCircle2 size={13} className="text-emerald-600" />
               : <XCircle size={13} className="text-rose-500" />}
        <span className={waived ? 'text-slate-400 line-through' : 'text-slate-700'}>{c}</span>
        {!waived && <span className="text-slate-400">· {state ?? 'absent'}</span>}
      </div>
    )
  }

  return (
    <div className="mb-6 rounded-xl border border-slate-200 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Award size={16} className="text-blue-600" />
        <h2 className="text-sm font-bold uppercase tracking-wide text-blue-700">
          Certification gate (regime-forked · live)
        </h2>
        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{fuelId}</span>
      </div>
      {loading && <p className="text-xs text-slate-500">Evaluating gate from ledger…</p>}
      {error && (
        <p className="text-xs text-amber-700">
          Gate unavailable ({error}). Requires the TEA engine + backend running with persisted claims.
        </p>
      )}
      {data && (
        <>
          <div className="flex items-center gap-2 mb-2">
            <span
              className="px-2 py-0.5 rounded-full text-xs font-bold"
              style={data.gate.gate_open
                ? { backgroundColor: '#dcfce7', color: '#15803d' }
                : { backgroundColor: '#fee2e2', color: '#991b1b' }}
            >
              {data.gate.gate_open ? 'GATE OPEN' : 'GATE CLOSED'}
            </span>
            <span className="text-xs text-slate-500">{data.gate.pathway_class}</span>
          </div>
          <p className="text-xs text-slate-600 mb-2">{data.gate.certification_scheme}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">Required claims</p>
              {data.gate.required_cert_claims.map(c => claimRow(c, false))}
            </div>
            <div>
              <p className="text-xs font-semibold text-slate-400 mb-1">Waived for this regime</p>
              {data.gate.waived_cert_claims.map(c => claimRow(c, true))}
            </div>
          </div>
          {data.gate.missing_claims.length > 0 && (
            <p className="text-xs text-rose-600 mt-2">
              Missing: {data.gate.missing_claims.join(', ')}
            </p>
          )}
          <p className="text-xs text-slate-400 mt-2">
            GHG method: {data.gate.ghg_method ?? '—'} · credit: {data.gate.us_credit ?? '—'}
          </p>
        </>
      )}
    </div>
  )
}

export function CertReadiness() {
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject()
  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId) ?? visibleProjects[0]

  // project_dataset cert_readiness (PostgreSQL since 2026-10-25), UNVERIFIED.
  // It used to fall back to the FIRST visible project's dataset — another
  // project's readiness shown under this one's name.
  const ds = useProjectDataset<ProjectCert>('cert_readiness', selectedProjectId)
  const data = ds.data

  // No sample dataset for this project — still render the LIVE panel. The
  // ledger-derived gate must never be hidden behind demo-data availability.
  if (!data) {
    return (
      <div className="min-h-screen p-6" style={{ backgroundColor: 'var(--surface, #f8fafc)', color: 'var(--text, #0f172a)' }}>
        <div className="mb-6">
          <h1 className="text-xl font-bold mb-1">Certification Readiness</h1>
          <p className="text-sm" style={{ color: 'var(--text-muted, #64748b)' }}>
            {TAB_DESCRIPTIONS.CERT_READINESS}
          </p>
        </div>
        {selectedProjectId || project ? (
          <LiveCertGatePanel
            projectId={selectedProjectId || project?.id || ''}
            molecule={project?.molecule}
          />
        ) : (
          <p className="text-sm" style={{ color: 'var(--text-muted, #64748b)' }}>
            No visible projects for this role.
          </p>
        )}
        <p className="text-xs" style={{ color: 'var(--text-muted, #94a3b8)' }}>
          {ds.loading ? 'Loading the recorded readiness…' : ds.error ? `Recorded readiness unavailable: ${ds.error}`
            : 'No readiness assessment is recorded for this project — only the live, ledger-derived certification gate is shown.'}
        </p>
      </div>
    )
  }

  const readinessLabel =
    data.overall >= 80 ? 'Ready for verifier engagement' :
    data.overall >= 50 ? 'Partial readiness — gaps to close' :
    data.overall >= 25 ? 'Significant gaps — certification not imminent' :
    'Not cert-ready — foundational issues to resolve'

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: 'var(--surface, #f8fafc)', color: 'var(--text, #0f172a)' }}>

      {/* ── Header ──────────────────────────────────────────── */}
      <div className="mb-6">
        <h1 className="text-xl font-bold mb-1 flex items-center gap-2">Certification Readiness <UnverifiedBadge verification={ds.verification} /></h1>
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
            {visibleProjects.map(p => (
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

      {/* ── SAMPLE-DATA FENCE — evidence-grade platforms must never mix demo
             and live numbers without saying so. Only the "Certification gate
             (regime-forked · live)" panel below reads the real ledger. ── */}
      <div className="mb-4 flex items-start gap-2 p-3 rounded-lg border border-amber-300 bg-amber-50">
        <AlertTriangle size={14} className="text-amber-600 mt-0.5 shrink-0" />
        <p className="text-xs text-amber-800">
          <span className="font-bold">SAMPLE DATA — </span>
          the readiness score, certification track, four-pillar gates, 45V track and
          gap table on this screen are illustrative demo values, not ledger-derived.
          Only the <span className="font-semibold">“Certification gate (regime-forked · live)”</span> panel
          reads the project’s persisted claims.
        </p>
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

      {/* ── RFNBO / RED III Gate Cards (2×2 grid) ───────────── */}
      <div className="mb-6">
        <h2 className="text-sm font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--brand, #0ea5e9)' }}>
          RFNBO / RED III Gates
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <GateCard gate={data.additionality} />
          <GateCard gate={data.temporal} />
          <GateCard gate={data.geographical} />
          <GateCard gate={data.lca} />
        </div>
      </div>

      {/* ── Certification gate (regime-forked, live — all projects) ── */}
      <LiveCertGatePanel projectId={selectedProjectId} molecule={project.molecule} />

      {/* ── US 45V Track (shown for US-jurisdiction projects) ── */}
      {project?.country === 'US' && (
        <V45Section projectId={selectedProjectId} />
      )}

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
