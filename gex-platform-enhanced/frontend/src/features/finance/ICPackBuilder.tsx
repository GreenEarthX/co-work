// Screen: IC pack builder screen (/ic-pack, /finance/ic-pack)
/**
 * ICPackBuilder — Investment Committee Pack assembly tool.
 * Assembles and previews IC packs for lender submission, with section
 * completeness tracking, readiness scoring, and export controls.
 */
import { useState, useRef, useMemo, useEffect } from 'react'
import { useProjectDataset, UnverifiedBadge } from './useProjectDataset'
import {
  FileText, Download, Eye, AlertCircle, CheckCircle, XCircle,
  ChevronDown, ChevronUp, Zap, Clock, Lock, Share2, Hash,
} from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'

// ─────────────────────────────── Types ───────────────────────────────────────

type SectionStatus = 'AUTO' | 'PARTIAL' | 'MISSING'

interface SubItem {
  label: string
  done: boolean
}

interface ICSection {
  id: string
  number: string
  name: string
  description: string
  status: SectionStatus
  subItems: SubItem[]
}

// ─────────────────────────────── Section definitions ─────────────────────────

const BASE_SECTIONS: Omit<ICSection, 'status' | 'subItems'>[] = [
  {
    id: 'S1', number: 'S1',
    name: "Banker's Snapshot",
    description: "Auto-generated 1-pager: project summary, key metrics, financing ask, timeline at a glance.",
  },
  {
    id: 'S2', number: 'S2',
    name: 'Financial Model Summary',
    description: 'DSCR series, LLCR, covenant package, reserve account sizing, break-even analysis, sensitivity heatmap.',
  },
  {
    id: 'S3', number: 'S3',
    name: 'Offtake Analysis',
    description: 'Five-test scorecard, per-contract summary table, counterparty credit ratings, red flag register.',
  },
  {
    id: 'S4', number: 'S4',
    name: 'Certification Status',
    description: 'RFNBO gate status, LCA protocol sign-off, GoO issuance plan, independent verifier memo.',
  },
  {
    id: 'S5', number: 'S5',
    name: 'Contracts & Permits',
    description: 'EPC contract summary, grid connection agreement, land/lease instruments, planning permits matrix.',
  },
  {
    id: 'S6', number: 'S6',
    name: 'Insurance Program',
    description: 'CAR/DSU cover, performance bond, marine transit, business interruption schedule by lender.',
  },
  {
    id: 'S7', number: 'S7',
    name: 'Financing Structure',
    description: 'Term sheet summary, conditions precedent tracker, capital stack diagram, security package.',
  },
  {
    id: 'S8', number: 'S8',
    name: 'Risk & Sensitivity',
    description: 'Top-10 risk register, change-in-law exposure, contingency budget, sponsor support mechanisms.',
  },
  {
    id: 'S9', number: 'S9',
    name: 'Evidence Index',
    description: 'Data room table of contents, SHA-256 hash chain verification, version control log.',
  },
]

function buildSubItems(sectionId: string, status: SectionStatus, note?: string): SubItem[] {
  const maps: Record<string, string[]> = {
    S1: ['Project overview', 'Key financial metrics', 'Financing ask summary', 'Executive timeline'],
    S2: ['DSCR model output', 'LLCR calculation', 'Covenant matrix', 'Reserve sizing', 'Break-even table', 'Sensitivity heatmap'],
    S3: ['Five-test scorecard', 'Per-contract summary', 'Counterparty ratings', 'Red flag register'],
    S4: ['RFNBO gate status', 'LCA protocol lock', 'GoO issuance plan', 'Verifier memo'],
    S5: ['EPC contract summary', 'Grid connection agreement', 'Land/lease instruments', 'Planning permits'],
    S6: ['CAR/DSU placement', 'Performance bond', 'Marine transit cover', 'BI schedule'],
    S7: ['Term sheet summary', 'CPs tracker', 'Capital stack diagram', 'Security package'],
    S8: ['Top-10 risk register', 'Change-in-law analysis', 'Contingency budget', 'Sponsor support memo'],
    S9: ['Data room ToC', 'SHA-256 hash chain', 'Version control log'],
  }
  const labels = maps[sectionId] ?? []
  if (status === 'AUTO') return labels.map(l => ({ label: l, done: true }))
  if (status === 'MISSING') return labels.map(l => ({ label: l, done: false }))
  // PARTIAL — mark first half done, rest pending (plus optional note item)
  const result = labels.map((l, i) => ({ label: l, done: i < Math.ceil(labels.length / 2) }))
  if (note) result.push({ label: note, done: false })
  return result
}

type ProjectSectionConfig = Record<string, { status: SectionStatus; note?: string }>

const READINESS_WEIGHTS: Record<SectionStatus, number> = {
  AUTO: 1,
  PARTIAL: 0.5,
  MISSING: 0,
}

function computeReadiness(override: number | null, sections: ICSection[]): number {
  if (override !== null) return override
  const score = sections.reduce((s, sec) => s + READINESS_WEIGHTS[sec.status], 0)
  return Math.round((score / sections.length) * 100)
}

// The section states and readiness live in PostgreSQL since 2026-10-25
// (project_dataset ic_pack_config / ic_pack_readiness), UNVERIFIED. Nothing
// recorded → every section MISSING; the "early stage" default is gone.
function buildSections(cfg: ProjectSectionConfig): ICSection[] {
  return BASE_SECTIONS.map(base => {
    const c = cfg[base.id] ?? { status: 'MISSING' as SectionStatus }
    return {
      ...base,
      status: c.status,
      subItems: buildSubItems(base.id, c.status, c.note),
    }
  })
}

function lenderTier(readiness: number): { label: string; color: string; bg: string } {
  if (readiness > 75) return { label: 'Tier 1 Bank IC submission', color: 'text-green-700', bg: 'bg-green-50 border-green-200' }
  if (readiness >= 50) return { label: 'DFI/ECA initial engagement', color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200' }
  if (readiness >= 25) return { label: 'Advisory bank qualification', color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200' }
  return { label: 'Internal review only', color: 'text-gray-600', bg: 'bg-gray-50 border-gray-200' }
}

// ─────────────────────────────── Sub-components ──────────────────────────────

const STATUS_CFG: Record<SectionStatus, { label: string; bg: string; text: string; icon: React.ReactNode }> = {
  AUTO:    { label: 'AUTO',    bg: 'bg-green-100',  text: 'text-green-700',  icon: <Zap size={11} /> },
  PARTIAL: { label: 'PARTIAL', bg: 'bg-amber-100',  text: 'text-amber-700',  icon: <Clock size={11} /> },
  MISSING: { label: 'MISSING', bg: 'bg-red-100',    text: 'text-red-700',    icon: <XCircle size={11} /> },
}

function SectionBadge({ status }: { status: SectionStatus }) {
  const cfg = STATUS_CFG[status]
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${cfg.bg} ${cfg.text}`}>
      {cfg.icon}
      {cfg.label}
    </span>
  )
}

function CircularProgress({ pct }: { pct: number }) {
  const r = 52
  const circ = 2 * Math.PI * r
  const offset = circ - (pct / 100) * circ
  const color = pct > 75 ? '#22c55e' : pct >= 50 ? '#3b82f6' : pct >= 25 ? '#f59e0b' : '#9ca3af'
  return (
    <svg width="136" height="136" viewBox="0 0 136 136">
      <circle cx="68" cy="68" r={r} fill="none" stroke="#e5e7eb" strokeWidth="10" />
      <circle
        cx="68" cy="68" r={r}
        fill="none"
        stroke={color}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={offset}
        transform="rotate(-90 68 68)"
      />
      <text x="68" y="62" textAnchor="middle" fontSize="26" fontWeight="700" fill={color}>{pct}%</text>
      <text x="68" y="80" textAnchor="middle" fontSize="11" fill="#6b7280">Ready</text>
    </svg>
  )
}

// ─────────────────────────────── Main component ──────────────────────────────

export function ICPackBuilder() {
  const { selectedProjectId } = useSelectedProject()
  const [expandedSection, setExpandedSection] = useState<string | null>(null)
  const [generated, setGenerated] = useState(false)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const previewRef = useRef<HTMLDivElement>(null)

  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId)
  const projectId = selectedProjectId ?? 'unknown'

  const cfgDs = useProjectDataset<ProjectSectionConfig>('ic_pack_config', selectedProjectId)
  const readinessDs = useProjectDataset<number>('ic_pack_readiness', selectedProjectId)
  const sections = useMemo(() => buildSections(cfgDs.data ?? {}), [cfgDs.data])
  const readiness = useMemo(() => computeReadiness(readinessDs.data ?? null, sections), [readinessDs.data, sections])
  const tier = lenderTier(readiness)
  // A real SHA-256 of the pack's section contents. It used to be hex generated
  // from the project id that only looked like a hash.
  const [packHash, setPackHash] = useState('')
  useEffect(() => {
    const bytes = new TextEncoder().encode(JSON.stringify({ projectId, sections }))
    crypto.subtle.digest('SHA-256', bytes)
      .then(d => setPackHash(Array.from(new Uint8Array(d)).map(b => b.toString(16).padStart(2, '0')).join('')))
      .catch(() => setPackHash(''))
  }, [projectId, sections])

  const missingSections = sections.filter(s => s.status === 'MISSING')

  function handleGenerate() {
    setGenerated(true)
    setGeneratedAt(new Date().toLocaleString())
  }

  function handlePreview() {
    setShowPreview(true)
    setTimeout(() => previewRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">IC Pack Builder <UnverifiedBadge verification={cfgDs.verification} /></h1>
          {cfgDs.notRecorded && !cfgDs.loading && (
            <p className="mt-1 text-xs text-amber-700">No section assessment is recorded for this project — every section shows as missing.</p>
          )}
          <p className="text-sm text-gray-500 mt-1">
            {project?.name ?? projectId} — Investment Committee Pack Assembly
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <button
            onClick={handleGenerate}
            className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg shadow transition-colors"
          >
            <FileText size={16} />
            Generate IC Pack
          </button>
          {generated && (
            <div className="text-right space-y-0.5">
              <div className="flex items-center gap-1.5 text-xs text-gray-500">
                <Hash size={12} />
                <span className="font-mono text-gray-600 truncate max-w-xs">{packHash.slice(0, 16)}…{packHash.slice(-8)}</span>
              </div>
              <div className="text-xs text-gray-400">Generated {generatedAt}</div>
            </div>
          )}
        </div>
      </div>

      {/* Main two-column layout */}
      <div className="flex gap-6 items-start">
        {/* Left: section checklist (65%) */}
        <div className="flex-1 min-w-0 space-y-3">
          {sections.map(sec => {
            const isOpen = expandedSection === sec.id
            const doneCount = sec.subItems.filter(i => i.done).length
            const totalCount = sec.subItems.length

            return (
              <div
                key={sec.id}
                className={`border rounded-lg overflow-hidden ${
                  sec.status === 'MISSING' ? 'border-red-200' :
                  sec.status === 'PARTIAL' ? 'border-amber-200' :
                  'border-green-200'
                }`}
              >
                {/* Card header */}
                <div
                  className={`flex items-center gap-3 px-4 py-3 cursor-pointer select-none ${
                    sec.status === 'MISSING' ? 'bg-red-50/40' :
                    sec.status === 'PARTIAL' ? 'bg-amber-50/40' :
                    'bg-green-50/40'
                  }`}
                  onClick={() => setExpandedSection(isOpen ? null : sec.id)}
                >
                  <span className="text-xs font-bold text-gray-400 w-6 shrink-0">{sec.number}</span>
                  <span className="font-semibold text-gray-800 flex-1 text-sm">{sec.name}</span>
                  <SectionBadge status={sec.status} />
                  <span className="text-xs text-gray-400 ml-1">
                    {doneCount}/{totalCount}
                  </span>
                  <div className="text-gray-400 shrink-0">
                    {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>
                </div>

                {/* Description (always visible) */}
                <div className="px-4 py-2 bg-white border-t border-gray-100">
                  <p className="text-xs text-gray-500">{sec.description}</p>
                </div>

                {/* Expanded sub-items */}
                {isOpen && (
                  <div className="bg-white border-t border-gray-100 px-4 py-3">
                    <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
                      {sec.subItems.map(item => (
                        <div key={item.label} className="flex items-center gap-2 text-xs">
                          {item.done ? (
                            <CheckCircle size={13} className="text-green-500 shrink-0" />
                          ) : (
                            <XCircle size={13} className="text-red-400 shrink-0" />
                          )}
                          <span className={item.done ? 'text-gray-700' : 'text-gray-400'}>{item.label}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Right sidebar (35%) */}
        <div className="w-80 shrink-0 space-y-4 sticky top-6">
          {/* Readiness meter */}
          <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
            <div className="text-sm font-semibold text-gray-700 mb-3">Pack Readiness</div>
            <div className="flex justify-center">
              <CircularProgress pct={readiness} />
            </div>
            <div className={`mt-3 text-xs font-medium px-3 py-1.5 rounded border ${tier.bg} ${tier.color}`}>
              {tier.label}
            </div>
          </div>

          {/* Blocking items */}
          {missingSections.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <div className="flex items-center gap-1.5 text-sm font-semibold text-red-700 mb-2">
                <AlertCircle size={14} />
                What's blocking generation?
              </div>
              <ul className="space-y-1.5">
                {missingSections.map(s => (
                  <li key={s.id} className="flex items-start gap-1.5 text-xs text-red-600">
                    <XCircle size={12} className="mt-0.5 shrink-0" />
                    <span>{s.number} — {s.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {missingSections.length === 0 && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4">
              <div className="flex items-center gap-1.5 text-sm font-semibold text-green-700">
                <CheckCircle size={14} />
                No blocking items
              </div>
              <p className="text-xs text-green-600 mt-1">All required sections have sufficient data.</p>
            </div>
          )}

          {/* Ready to share */}
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="flex items-center gap-1.5 text-sm font-semibold text-gray-700 mb-3">
              <Share2 size={14} />
              Ready to share with:
            </div>
            <div className={`text-sm font-medium px-3 py-2 rounded border ${tier.bg} ${tier.color}`}>
              {tier.label}
            </div>
            <div className="mt-2 text-xs text-gray-400">{readiness}% section readiness</div>
          </div>

          {/* Export options */}
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="text-sm font-semibold text-gray-700 mb-3">Export Options</div>
            <div className="space-y-2">
              <button
                onClick={handlePreview}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm border border-blue-200 text-blue-600 rounded-lg hover:bg-blue-50 transition-colors"
              >
                <Eye size={14} />
                Preview Pack
              </button>
              <button
                onClick={() => window.alert('Coming soon')}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <Download size={14} />
                Export PDF
              </button>
              <button
                onClick={() => window.alert('Coming soon')}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <Lock size={14} />
                Export Evidence JSON
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Pack Preview Section */}
      {showPreview && (
        <div ref={previewRef} className="mt-10">
          <div className="border-t border-gray-200 pt-8">
            <h2 className="text-lg font-bold text-gray-800 mb-4">Pack Preview</h2>

            {/* S1 Banker's Snapshot mini-preview */}
            <div className="bg-white border border-gray-200 rounded-xl p-6 max-w-3xl shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded bg-blue-600 flex items-center justify-center">
                  <FileText size={16} className="text-white" />
                </div>
                <div>
                  <div className="text-sm font-bold text-gray-800">S1 — Banker's Snapshot</div>
                  <div className="text-xs text-gray-500">Auto-generated · 1-pager</div>
                </div>
                <SectionBadge status={sections[0].status} />
              </div>

              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Project</div>
                  <div className="text-sm font-semibold text-gray-800">{project?.name ?? projectId}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Pack Readiness</div>
                  <div className="text-sm font-semibold text-gray-800">{readiness}%</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Sections</div>
                  <div className="text-sm font-semibold text-gray-800">
                    {sections.filter(s => s.status === 'AUTO').length} AUTO ·{' '}
                    {sections.filter(s => s.status === 'PARTIAL').length} PARTIAL ·{' '}
                    {sections.filter(s => s.status === 'MISSING').length} MISSING
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Lender Tier</div>
                  <div className={`text-sm font-semibold ${tier.color}`}>{tier.label}</div>
                </div>
              </div>

              {/* Hash + timestamp */}
              <div className="bg-gray-50 rounded-lg p-3 space-y-1.5">
                <div className="flex items-center gap-2 text-xs">
                  <Hash size={11} className="text-gray-400" />
                  <span className="text-gray-500">SHA-256:</span>
                  <span className="font-mono text-gray-700 text-xs break-all">{packHash}</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <Clock size={11} className="text-gray-400" />
                  Generated: {generatedAt ?? new Date().toLocaleString()}
                </div>
              </div>

              <button
                onClick={() => window.alert('Coming soon')}
                className="mt-4 flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
              >
                <Download size={14} />
                Download PDF
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
