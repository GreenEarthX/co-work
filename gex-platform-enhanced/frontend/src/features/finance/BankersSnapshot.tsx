// Screen: Banker's snapshot screen (/bankability-snapshot, /finance/bankers-snapshot)
import { Printer, MapPin, Calendar, TrendingUp, AlertTriangle, XCircle, CheckCircle2, Zap } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { useProjectDataset, DatasetNotice } from './useProjectDataset'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

type BankabilityState = 'BANKABLE' | 'BUILDABLE' | 'FUNDABLE' | 'CERTIFIABLE' | 'EARLY_DEV'
type GateStatus = 'PASS' | 'IN_PROGRESS' | 'PENDING' | 'NOT_STARTED'

interface GateEntry {
  id: string
  name: string
  status: GateStatus
  score: number
}

interface SnapshotData {
  bankabilityState: BankabilityState
  trustScore: number
  technology: string
  financials: {
    capex: number
    dscrP50: number
    dscrP90: number
    llcr: number
    wacc: number
    breakeven: number
  }
  offtake: {
    contracted: number
    tenor: number
    buyerCredit: string
    index: string
    score: number
  }
  financing: {
    seniorDebt: number
    ecaDfi: string
    equity: number
    mezzEur: number
    termSheetTarget: string
    fidTarget: string
    codTarget: string
    concessionalShare?: number  // 0-1
    blendedDebtCost?: number   // %
    catalyticRatio?: number    // x:1
    maxGracePeriod?: number    // years
  }
  gates: GateEntry[]
  certReadiness: number
  criticalPath: string[]
  killSwitches: string[]
}

const GATE_STATUS_STYLES: Record<GateStatus, { bar: string; text: string }> = {
  PASS:        { bar: 'bg-green-500', text: 'text-green-700' },
  IN_PROGRESS: { bar: 'bg-amber-400', text: 'text-amber-700' },
  PENDING:     { bar: 'bg-gray-400',  text: 'text-gray-600'  },
  NOT_STARTED: { bar: 'bg-gray-200',  text: 'text-gray-400'  },
}

const MOLECULE_STYLES: Record<string, { bg: string; text: string }> = {
  H2:          { bg: 'bg-sky-100',    text: 'text-sky-800'    },
  NH3:         { bg: 'bg-violet-100', text: 'text-violet-800' },
  'e-Methanol':{ bg: 'bg-teal-100',   text: 'text-teal-800'   },
  SAF:         { bg: 'bg-orange-100', text: 'text-orange-800' },
  'e-NG':      { bg: 'bg-cyan-100',   text: 'text-cyan-800'   },
}

function dscrColor(val: number): string {
  if (val >= 1.30) return 'text-green-700'
  if (val >= 1.20) return 'text-amber-600'
  return 'text-red-600'
}

function dscrBg(val: number): string {
  if (val >= 1.30) return 'bg-green-50 border-green-200'
  if (val >= 1.20) return 'bg-amber-50 border-amber-200'
  return 'bg-red-50 border-red-200'
}

function trustArcPath(score: number): string {
  // 270-degree arc, starting from bottom-left (225°), going clockwise to bottom-right (315° = -45°)
  const cx = 60, cy = 65, r = 50
  const startDeg = 135
  const totalDeg = 270
  const endDeg = startDeg + (totalDeg * score) / 100
  const toRad = (d: number) => (d * Math.PI) / 180
  const sx = cx + r * Math.cos(toRad(startDeg))
  const sy = cy + r * Math.sin(toRad(startDeg))
  const ex = cx + r * Math.cos(toRad(endDeg))
  const ey = cy + r * Math.sin(toRad(endDeg))
  const largeArc = totalDeg * score / 100 > 180 ? 1 : 0
  return `M ${sx} ${sy} A ${r} ${r} 0 ${largeArc} 1 ${ex} ${ey}`
}

function trustArcTrackPath(): string {
  const cx = 60, cy = 65, r = 50
  const toRad = (d: number) => (d * Math.PI) / 180
  const sx = cx + r * Math.cos(toRad(135))
  const sy = cy + r * Math.sin(toRad(135))
  const ex = cx + r * Math.cos(toRad(405))
  const ey = cy + r * Math.sin(toRad(405))
  return `M ${sx} ${sy} A ${r} ${r} 0 1 1 ${ex} ${ey}`
}

function trustColor(score: number): string {
  if (score >= 70) return '#16a34a'
  if (score >= 45) return '#d97706'
  return '#dc2626'
}

// ═══════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════════════

function MetricRow({ label, value, valueClass = 'text-gray-900' }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex items-baseline justify-between py-1 border-b border-gray-100 last:border-0">
      <span className="text-xs text-gray-500 font-medium">{label}</span>
      <span className={`text-sm font-bold tabular-nums ${valueClass}`}>{value}</span>
    </div>
  )
}

function SectionCard({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-gray-200 bg-white shadow-sm ${className}`}>
      <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 rounded-t-xl">
        <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">{title}</h3>
      </div>
      <div className="px-4 py-3">{children}</div>
    </div>
  )
}

function GateBar({ gate }: { gate: GateEntry }) {
  const style = GATE_STATUS_STYLES[gate.status]
  const width = gate.status === 'PASS' ? 100 : gate.score
  return (
    <div className="flex items-center gap-2 py-0.5">
      <span className="text-xs font-mono text-gray-400 w-7 shrink-0">{gate.id}</span>
      <span className="text-xs text-gray-700 w-28 shrink-0 truncate">{gate.name}</span>
      <div className="flex-1 h-4 bg-gray-100 rounded-sm overflow-hidden relative">
        <div
          className={`h-full rounded-sm transition-all ${style.bar}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <span className={`text-xs font-semibold w-8 text-right tabular-nums ${style.text}`}>
        {gate.status === 'NOT_STARTED' ? '—' : `${gate.score}%`}
      </span>
    </div>
  )
}

function TrustArc({ score }: { score: number }) {
  const color = trustColor(score)
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="120" height="110" viewBox="0 0 120 110">
        {/* Track */}
        <path
          d={trustArcTrackPath()}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {/* Fill */}
        <path
          d={trustArcPath(score)}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
        />
        {/* Score text */}
        <text x="60" y="62" textAnchor="middle" fontSize="22" fontWeight="900" fill={color}>{score}</text>
        <text x="60" y="78" textAnchor="middle" fontSize="9" fill="#6b7280" fontWeight="600">/100</text>
      </svg>
      <span className="text-xs text-gray-500 font-medium -mt-2">Trust score (indicative)</span>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

export function BankersSnapshot() {
  const { selectedProjectId } = useSelectedProject()
  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId)
  // Until 16 Oct 2026 any project without a hand-written entry fell back to the
  // Le Havre sample, so a Speculative project was shown as "Bankable 94/100".
  // No entry → say so. An entry → label it as the fixed sample it is.
  // The entries live in PostgreSQL since 2026-10-25 (project_dataset
  // bankers_snapshot), UNVERIFIED.
  const ds = useProjectDataset<SnapshotData>('bankers_snapshot', selectedProjectId)
  const data = ds.data
  if (ds.loading || ds.error) return <DatasetNotice ds={ds} what="banker's snapshot" />
  if (!data) {
    return (
      <div className="mx-auto mt-8 max-w-xl rounded-xl border border-slate-200 bg-white p-6">
        <p className="text-[11px] font-mono font-bold uppercase tracking-[0.12em] text-slate-500">Banker's snapshot</p>
        <h2 className="mt-1 text-lg font-semibold text-slate-900">{project?.name ?? 'This project'}</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-700">
          No decision-grade summary exists for this project yet. This page does not show figures that
          were not produced from the project's own evidence. Its state, its blockers and the capital
          decisions it is eligible for are on <a className="font-medium text-teal-700 underline" href="/bankability-scores">State &amp; Blockers</a>{' '}
          and <a className="font-medium text-teal-700 underline" href="/stage-gates">Gates &amp; Evidence</a>.
        </p>
      </div>
    )
  }

  // State, gates and the verified share are the ENGINE's (2026-10-28). The
  // snapshot dataset's own bankabilityState, gate scores and trust score were
  // typed by hand — Bremen read "BUILDABLE" while the engine said SPECULATIVE —
  // and are not shown.
  const engine = project?.bankability
  const verifiedPct = Math.round(engine?.overall_completion ?? 0)
  const engineGates: GateEntry[] = (engine?.gates ?? []).map(g => ({
    id: g.id, name: g.name, score: Math.round(g.completion_pct),
    status: (g.determination === 'SATISFIED' ? 'PASS'
      : g.verified_count > 0 ? 'IN_PROGRESS'
      : g.determination === 'BLOCKED' || g.determination === 'UNRESOLVED' ? 'PENDING' : 'NOT_STARTED') as GateStatus,
  }))
  const molStyle = MOLECULE_STYLES[project?.molecule ?? 'H2'] ?? MOLECULE_STYLES['H2']
  const today = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })

  const totalInvestment = data.financing.seniorDebt + data.financing.equity + data.financing.mezzEur

  return (
    <>
      {/* Print styles */}
      <style>{`
        @media print {
          .no-print { display: none !important; }
          .print-break { page-break-before: always; }
          body { font-size: 11px; }
          .shadow-sm { box-shadow: none !important; }
        }
      `}</style>

      <div className="space-y-4 max-w-7xl mx-auto pb-8">

        <div className="no-print rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <span className="font-semibold">Unverified figures.</span>{' '}
          This snapshot is recorded for this project but nobody has confirmed it, and it is not computed from
          the project's verified evidence; the gate engine's result is on State &amp; Blockers.
        </div>

        {/* ── HEADER BAR ─────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-gray-900 to-gray-800">
            <div className="flex items-center gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold uppercase tracking-widest text-gray-400">Banker's Snapshot</span>
                  <span className="text-gray-600">·</span>
                  <span className="text-xs text-gray-400">Decision-Grade Summary</span>
                </div>
                <h1 className="text-2xl font-black text-white">{project?.name ?? 'Project'}</h1>
                <div className="flex items-center gap-3 mt-1">
                  <div className="flex items-center gap-1.5 text-gray-300 text-sm">
                    <MapPin className="w-3.5 h-3.5 text-gray-400" />
                    <span>{project?.location ?? '—'}</span>
                  </div>
                  <span className="text-gray-600">·</span>
                  <span className="text-xs text-gray-400">{data.technology}</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-4">
              {/* Molecule badge */}
              <span className={`text-xs font-black px-3 py-1.5 rounded-lg border ${molStyle.bg} ${molStyle.text}`}>
                {project?.molecule ?? '—'}
              </span>

              {/* Bankability state — the engine's */}
              <span className="text-xs font-black px-3 py-1.5 rounded-lg border bg-gray-100 text-gray-800 border-gray-300"
                title={engine?.state_label ?? undefined}>
                {engine?.evaluated === false ? 'NOT YET EVALUATED' : (engine?.state ?? '—').replace(/_/g, ' ')}
              </span>

              {/* Verified share of the evidence — the engine's */}
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 text-gray-200"
                title="Share of the required evidence verified, at the required maturity (GEX engine)">
                <Zap className="w-3.5 h-3.5" />
                <span className="text-sm font-black tabular-nums">{verifiedPct}%</span>
                <span className="text-xs opacity-70">verified</span>
              </div>

              {/* Date */}
              <div className="flex items-center gap-1.5 text-gray-400 text-xs">
                <Calendar className="w-3.5 h-3.5" />
                <span>{today}</span>
              </div>

              {/* Print button */}
              <button
                onClick={() => window.print()}
                className="no-print flex items-center gap-2 px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white text-xs font-semibold rounded-lg transition-colors border border-white/20"
              >
                <Printer className="w-3.5 h-3.5" />
                Print Snapshot
              </button>
            </div>
          </div>
        </div>

        {/* ── TWO-COLUMN BODY ────────────────────────────────────────── */}
        <div className="grid grid-cols-5 gap-4">

          {/* LEFT COLUMN — 40% (2/5) */}
          <div className="col-span-2 space-y-4">

            {/* Financials Card */}
            <SectionCard title="Key Financials">
              <MetricRow label="CapEx" value={`€${data.financials.capex}M`} />
              <div className={`flex items-baseline justify-between py-1.5 px-2 rounded-lg border mt-1 ${dscrBg(data.financials.dscrP50)}`}>
                <span className="text-xs font-bold text-gray-700">DSCR P50</span>
                <span className={`text-base font-black tabular-nums ${dscrColor(data.financials.dscrP50)}`}>
                  {data.financials.dscrP50.toFixed(2)}x
                </span>
              </div>
              <div className={`flex items-baseline justify-between py-1.5 px-2 rounded-lg border mt-1 ${dscrBg(data.financials.dscrP90)}`}>
                <div>
                  <span className="text-xs font-bold text-gray-700">DSCR P90</span>
                  <span className="text-xs text-gray-400 ml-1">(downside)</span>
                </div>
                <span className={`text-base font-black tabular-nums ${dscrColor(data.financials.dscrP90)}`}>
                  {data.financials.dscrP90.toFixed(2)}x
                </span>
              </div>
              <div className="mt-2 space-y-0">
                <MetricRow label="LLCR" value={`${data.financials.llcr.toFixed(2)}x`} valueClass={data.financials.llcr >= 1.4 ? 'text-green-700' : data.financials.llcr >= 1.2 ? 'text-amber-600' : 'text-red-600'} />
                <MetricRow label="WACC" value={`${data.financials.wacc.toFixed(1)}%`} valueClass="text-gray-800" />
                <MetricRow
                  label="Break-even"
                  value={
                    project?.molecule === 'NH3' ? `${data.financials.breakeven} €/t` :
                    project?.molecule === 'e-NG' ? `${data.financials.breakeven} €/MWh` :
                    project?.molecule === 'e-Methanol' ? `${data.financials.breakeven} €/t` :
                    `${data.financials.breakeven} €/kg`
                  }
                />
              </div>
            </SectionCard>

            {/* Offtake Card */}
            <SectionCard title="Offtake">
              <MetricRow label="Contracted capacity" value={`${data.offtake.contracted}%`} valueClass={data.offtake.contracted >= 70 ? 'text-green-700' : data.offtake.contracted >= 50 ? 'text-amber-600' : 'text-red-600'} />
              <MetricRow label="Tenor" value={`${data.offtake.tenor} years`} />
              <div className="py-1 border-b border-gray-100">
                <div className="text-xs text-gray-500 font-medium mb-0.5">Buyer credit</div>
                <div className="text-xs font-semibold text-gray-800 leading-tight">{data.offtake.buyerCredit}</div>
              </div>
              <div className="py-1">
                <div className="text-xs text-gray-500 font-medium mb-0.5">Pricing index</div>
                <div className="text-xs font-semibold text-gray-800 leading-tight">{data.offtake.index}</div>
              </div>
              {/* Offtake score bar */}
              <div className="mt-2 pt-2 border-t border-gray-100">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-gray-500">Offtake bankability score</span>
                  <span className={`font-black ${data.offtake.score >= 70 ? 'text-green-700' : data.offtake.score >= 50 ? 'text-amber-600' : 'text-red-600'}`}>
                    {data.offtake.score}/100
                  </span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${data.offtake.score >= 70 ? 'bg-green-500' : data.offtake.score >= 50 ? 'bg-amber-400' : 'bg-red-500'}`}
                    style={{ width: `${data.offtake.score}%` }}
                  />
                </div>
              </div>
            </SectionCard>

            {/* Financing Ask Card */}
            <SectionCard title="Financing Ask">
              <MetricRow label="Senior debt" value={data.financing.seniorDebt > 0 ? `€${data.financing.seniorDebt}M` : 'Not secured'} />
              <MetricRow label="Equity" value={`€${data.financing.equity}M`} />
              {data.financing.mezzEur > 0 && (
                <MetricRow label="Mezzanine" value={`€${data.financing.mezzEur}M`} />
              )}
              <div className="py-1 border-b border-gray-100">
                <div className="text-xs text-gray-500 font-medium mb-0.5">ECA / DFI status</div>
                <div className="text-xs font-semibold text-gray-800 leading-tight">{data.financing.ecaDfi}</div>
              </div>
              <div className="grid grid-cols-3 gap-2 mt-3">
                {[
                  { label: 'Term Sheet', value: data.financing.termSheetTarget },
                  { label: 'FID',        value: data.financing.fidTarget       },
                  { label: 'COD',        value: data.financing.codTarget       },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-gray-50 rounded-lg border border-gray-200 p-2 text-center">
                    <div className="text-xs text-gray-400 font-medium">{label}</div>
                    <div className="text-xs font-black text-gray-800 mt-0.5">{value}</div>
                  </div>
                ))}
              </div>
              {/* Total investment */}
              <div className="mt-3 pt-2 border-t border-gray-200 flex justify-between items-baseline">
                <span className="text-xs font-bold text-gray-700">Total investment</span>
                <span className="text-base font-black text-gray-900">€{totalInvestment}M</span>
              </div>
              {/* Concessional metrics (when available) */}
              {data.financing.concessionalShare != null && data.financing.concessionalShare > 0 && (
                <div className="mt-3 pt-2 border-t border-teal-200 space-y-1">
                  <div className="text-xs font-black uppercase tracking-widest text-teal-700 mb-1">DFI / Concessional</div>
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Concessional share</span>
                    <span className="font-semibold text-teal-700">{(data.financing.concessionalShare * 100).toFixed(0)}%</span>
                  </div>
                  {data.financing.blendedDebtCost != null && (
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-500">Blended debt cost</span>
                      <span className="font-semibold">{data.financing.blendedDebtCost.toFixed(2)}%</span>
                    </div>
                  )}
                  {data.financing.catalyticRatio != null && (
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-500">Catalytic ratio</span>
                      <span className={`font-semibold ${data.financing.catalyticRatio >= 5 ? 'text-green-600' : 'text-amber-600'}`}>
                        {data.financing.catalyticRatio.toFixed(1)}:1
                      </span>
                    </div>
                  )}
                  {data.financing.maxGracePeriod != null && data.financing.maxGracePeriod > 0 && (
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-500">Max grace period</span>
                      <span className="font-semibold">{data.financing.maxGracePeriod}y</span>
                    </div>
                  )}
                </div>
              )}
            </SectionCard>
          </div>

          {/* RIGHT COLUMN — 60% (3/5) */}
          <div className="col-span-3 space-y-4">

            {/* 12-Gate chart */}
            <SectionCard title="12-Gate Progress — Bankability Pathway">
              <div className="space-y-1">
                {engineGates.length === 0 && (
                  <p className="text-xs text-gray-500">Not yet evaluated by the GEX engine.</p>
                )}
                {engineGates.map(gate => (
                  <GateBar key={gate.id} gate={gate} />
                ))}
                {engine?.scope?.note && <p className="text-[10px] text-gray-400 mt-1">{engine.scope.note}</p>}
              </div>
              {/* Legend */}
              <div className="flex items-center gap-4 mt-3 pt-3 border-t border-gray-100">
                {(['PASS', 'IN_PROGRESS', 'PENDING', 'NOT_STARTED'] as GateStatus[]).map(s => (
                  <div key={s} className="flex items-center gap-1.5">
                    <div className={`w-3 h-3 rounded-sm ${GATE_STATUS_STYLES[s].bar}`} />
                    <span className="text-xs text-gray-500">{s.replace('_', ' ')}</span>
                  </div>
                ))}
              </div>
            </SectionCard>

            {/* Trust score arc + Cert readiness */}
            <div className="grid grid-cols-2 gap-4">
              {/* Trust score arc */}
              <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-4 flex flex-col items-center justify-center">
                <h3 className="text-xs font-black uppercase tracking-widest text-gray-600 mb-2">Evidence verified</h3>
                <TrustArc score={verifiedPct} />
                <div className="text-xs text-gray-400 text-center mt-1">
                  Required evidence verified at the required maturity — GEX engine
                </div>
              </div>

              {/* Cert readiness */}
              <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-4">
                <h3 className="text-xs font-black uppercase tracking-widest text-gray-600 mb-3">Certification Readiness</h3>
                <div className="flex items-center justify-center gap-4 mb-3">
                  <div className={`text-5xl font-black tabular-nums ${data.certReadiness >= 70 ? 'text-green-600' : data.certReadiness >= 45 ? 'text-amber-500' : 'text-red-500'}`}>
                    {data.certReadiness}
                    <span className="text-lg text-gray-400 font-normal">%</span>
                  </div>
                </div>
                <div className="h-3 bg-gray-100 rounded-full overflow-hidden mb-2">
                  <div
                    className={`h-full rounded-full transition-all ${data.certReadiness >= 70 ? 'bg-green-500' : data.certReadiness >= 45 ? 'bg-amber-400' : 'bg-red-500'}`}
                    style={{ width: `${data.certReadiness}%` }}
                  />
                </div>
                <div className="text-xs text-gray-500 text-center">
                  {data.certReadiness >= 80 ? 'RED III / RFNBO pathway clear' :
                   data.certReadiness >= 50 ? 'Partial certification evidence — action needed' :
                   'Certification pathway not established'}
                </div>
                {/* Threshold markers */}
                <div className="relative h-0 mt-1">
                  <div className="absolute text-xs text-amber-500 font-bold" style={{ left: `${50}%`, transform: 'translateX(-50%)' }}>50%</div>
                  <div className="absolute text-xs text-green-600 font-bold" style={{ left: `${80}%`, transform: 'translateX(-50%)' }}>80%</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── BOTTOM STRIP ────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
          <div className="grid grid-cols-3 divide-x divide-gray-200">

            {/* Critical Path */}
            <div className="p-4">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="w-4 h-4 text-amber-500" />
                <h3 className="text-xs font-black uppercase tracking-widest text-amber-700">Critical Path</h3>
              </div>
              <ol className="space-y-2">
                {data.criticalPath.map((item, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-amber-100 text-amber-700 text-xs font-black flex items-center justify-center mt-0.5">{i + 1}</span>
                    <span className="text-xs text-gray-700 leading-tight">{item}</span>
                  </li>
                ))}
              </ol>
            </div>

            {/* Kill Switches */}
            <div className="p-4">
              <div className="flex items-center gap-2 mb-3">
                <XCircle className="w-4 h-4 text-red-500" />
                <h3 className="text-xs font-black uppercase tracking-widest text-red-700">Kill Switches</h3>
              </div>
              <ul className="space-y-2">
                {data.killSwitches.map((item, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 text-red-400 shrink-0 mt-0.5" />
                    <span className="text-xs text-gray-700 leading-tight">{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Investment Ask + Timeline */}
            <div className="p-4">
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle2 className="w-4 h-4 text-gray-500" />
                <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">Investment Ask</h3>
              </div>
              <div className="space-y-2">
                <div className="bg-gray-900 rounded-lg px-3 py-2 flex justify-between items-baseline">
                  <span className="text-xs text-gray-400">Total raise</span>
                  <span className="text-lg font-black text-white">€{totalInvestment}M</span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-blue-50 rounded-lg border border-blue-200 px-2 py-1.5">
                    <div className="text-xs text-blue-500 font-medium">Senior Debt</div>
                    <div className="text-sm font-black text-blue-800">€{data.financing.seniorDebt}M</div>
                  </div>
                  <div className="bg-green-50 rounded-lg border border-green-200 px-2 py-1.5">
                    <div className="text-xs text-green-500 font-medium">Equity</div>
                    <div className="text-sm font-black text-green-800">€{data.financing.equity}M</div>
                  </div>
                </div>
                <div className="border-t border-gray-100 pt-2 space-y-1">
                  {[
                    { label: 'Term Sheet', value: data.financing.termSheetTarget, icon: '→' },
                    { label: 'FID',        value: data.financing.fidTarget,        icon: '⚡' },
                    { label: 'COD',        value: data.financing.codTarget,        icon: '✓' },
                  ].map(({ label, value, icon }) => (
                    <div key={label} className="flex justify-between items-center text-xs">
                      <span className="text-gray-500">{icon} {label}</span>
                      <span className="font-bold text-gray-800">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </>
  )
}
