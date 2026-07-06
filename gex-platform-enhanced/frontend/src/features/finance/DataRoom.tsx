// Screen: Data room screen (/data-room, /finance/data-room)
/**
 * DataRoom — Virtual data room with indexed Table of Contents following Playbook Annex E.
 * 11 categories with document completeness, SHA-256 hashes, and download links.
 */

import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  FolderOpen, FileText, Download, CheckCircle2, Clock, AlertCircle,
  XCircle, ChevronRight, Hash, ArrowLeft,
} from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { WorkflowBadge } from '@/components/workflow/WorkflowBadge'
import { WorkflowActions } from '@/components/workflow/WorkflowActions'

// ─────────────────────────────── Types ───────────────────────────────────────

type DocStatus = 'VERIFIED' | 'UPLOADED' | 'PENDING' | 'MISSING'

interface DataRoomDoc {
  name: string
  gateRef: string
  version: string
  uploadDate: string
  status: DocStatus
  sha256: string
}

interface DocCategory {
  id: number
  name: string
  docs: DataRoomDoc[]
}

// ─────────────────────────────── Helpers ─────────────────────────────────────

function fakeHash(seed: string): string {
  let h = 0
  for (let i = 0; i < seed.length; i++) {
    h = (Math.imul(31, h) + seed.charCodeAt(i)) | 0
  }
  const base = Math.abs(h).toString(16).padStart(8, '0')
  const ext = Math.abs(h * 0x9e3779b9).toString(16).padStart(56, '0')
  return (base + ext).slice(0, 64)
}

// ─────────────────────────────── Data ────────────────────────────────────────

function buildCategories(projectId: string): DocCategory[] {
  const isLeHavre = projectId === 'proj_lehavre_eng'
  const isBremen = projectId === 'proj_bremen_h2'
  const isHelios = projectId === 'proj_sansebastian_emethanol'
  const isRotterdam = projectId === 'proj_rotterdam_nh3'

  function doc(
    name: string,
    gateRef: string,
    version: string,
    uploadDate: string,
    status: DocStatus,
  ): DataRoomDoc {
    return { name, gateRef, version, uploadDate, status, sha256: fakeHash(name + projectId) }
  }

  function degrade(s: DocStatus): DocStatus {
    if (isLeHavre) return s
    if (isBremen) {
      if (s === 'VERIFIED') return Math.random() > 0.4 ? 'UPLOADED' : 'VERIFIED'
      if (s === 'UPLOADED') return 'UPLOADED'
      return 'PENDING'
    }
    if (isHelios) {
      if (s === 'VERIFIED') return 'UPLOADED'
      if (s === 'UPLOADED') return 'PENDING'
      return 'MISSING'
    }
    if (isRotterdam) {
      if (s === 'VERIFIED') return 'PENDING'
      if (s === 'UPLOADED') return 'MISSING'
      return 'MISSING'
    }
    // Wales SAF — mostly missing
    if (s === 'VERIFIED') return 'MISSING'
    if (s === 'UPLOADED') return 'MISSING'
    return 'MISSING'
  }

  return [
    {
      id: 1,
      name: 'Corporate & Structure',
      docs: [
        doc('Corporate Structure Chart v2.pdf', 'G0', 'v2', '2025-10-12', degrade('VERIFIED')),
        doc('Certificate of Incorporation - SPV.pdf', 'G0', 'v1', '2025-09-01', degrade('VERIFIED')),
        doc('Shareholders Agreement - Signed.pdf', 'G0', 'v3', '2025-11-05', degrade('UPLOADED')),
      ],
    },
    {
      id: 2,
      name: 'Technical Documentation',
      docs: [
        doc('FEED Study Report - Technip Energies.pdf', 'G3', 'v2', '2025-08-20', degrade('VERIFIED')),
        doc('Electrolyser Technology Spec - ITM Power.pdf', 'G3', 'v1', '2025-07-15', degrade('VERIFIED')),
        doc('RFNBO Pre-audit Report - DNV.pdf', 'G11', 'v1', '2025-12-01', degrade('VERIFIED')),
        doc('Process Flow Diagram Rev C.pdf', 'G3', 'v3', '2026-01-10', degrade('UPLOADED')),
        doc('Hazard Identification (HAZID) Report.pdf', 'G5', 'v1', '2025-10-30', degrade('PENDING')),
      ],
    },
    {
      id: 3,
      name: 'Financial Model',
      docs: [
        doc('Financial Model - PF Engine Run 2026-03-15.xlsx', 'G8', 'v7', '2026-03-15', degrade('VERIFIED')),
        doc('Independent Engineer Report - Mott MacDonald.pdf', 'G8', 'v2', '2026-01-22', degrade('VERIFIED')),
        doc('Base Case Sensitivity Analysis.xlsx', 'G8', 'v4', '2026-02-10', degrade('UPLOADED')),
        doc('Debt Sizing Memo - BNP Paribas.pdf', 'G10', 'v1', '2025-12-18', degrade('PENDING')),
      ],
    },
    {
      id: 4,
      name: 'Offtake & Commercial',
      docs: [
        doc('Offtake Agreement - TOTSA TotalEnergies v3.pdf', 'G4', 'v3', '2025-09-30', degrade('VERIFIED')),
        doc('Credit Support Deed - BNP Guarantee.pdf', 'G4', 'v2', '2025-10-15', degrade('VERIFIED')),
        doc('Price Floor Mechanism Annex.pdf', 'G4', 'v1', '2025-11-01', degrade('UPLOADED')),
      ],
    },
    {
      id: 5,
      name: 'EPC & Construction',
      docs: [
        doc('EPC Contract - Technip Energies v3.pdf', 'G5', 'v3', '2025-10-05', degrade('VERIFIED')),
        doc('EPC Performance Bond - Euler Hermes.pdf', 'G5', 'v1', '2025-10-20', degrade('VERIFIED')),
        doc('Construction Programme & Milestones.pdf', 'G5', 'v2', '2025-11-15', degrade('UPLOADED')),
        doc('Contractor Completion Guarantee.pdf', 'G5', 'v1', '2025-12-01', degrade('PENDING')),
      ],
    },
    {
      id: 6,
      name: 'Grid & Power',
      docs: [
        doc('Grid Connection Agreement - RTE v2.pdf', 'G1', 'v2', '2025-08-12', degrade('VERIFIED')),
        doc('Power Purchase Agreement - EDF Renouvelables.pdf', 'G1', 'v2', '2025-07-28', degrade('VERIFIED')),
        doc('Capacity Reservation Confirmation - RTE.pdf', 'G1', 'v1', '2025-09-05', degrade('UPLOADED')),
      ],
    },
    {
      id: 7,
      name: 'Permits & Environmental',
      docs: [
        doc('Environmental Impact Assessment - Artelia.pdf', 'G0', 'v2', '2025-06-15', degrade('VERIFIED')),
        doc('ICPE Operating Permit - Prefecture du Havre.pdf', 'G0', 'v1', '2025-05-20', degrade('VERIFIED')),
        doc('Port Concession Agreement - Grand Port Maritime.pdf', 'G0', 'v1', '2025-07-01', degrade('VERIFIED')),
        doc('Biodiversity Offset Plan.pdf', 'G0', 'v1', '2025-08-10', degrade('UPLOADED')),
      ],
    },
    {
      id: 8,
      name: 'Insurance',
      docs: [
        doc('Construction All-Risk Policy - AXA XL.pdf', 'G7', 'v2', '2025-10-01', degrade('VERIFIED')),
        doc('Business Interruption Policy - Zurich.pdf', 'G7', 'v1', '2025-10-01', degrade('VERIFIED')),
        doc('Lender Loss Payee Endorsement.pdf', 'G7', 'v1', '2026-01-15', degrade('UPLOADED')),
      ],
    },
    {
      id: 9,
      name: 'Certification & GoOs',
      docs: [
        doc('RFNBO Certification - TÜV Rheinland.pdf', 'G11', 'v1', '2026-01-30', degrade('VERIFIED')),
        doc('Guarantees of Origin Registry Enrolment - AIB.pdf', 'G11', 'v1', '2026-02-10', degrade('VERIFIED')),
        doc('GHG Audit Report - ISO 14064 - Bureau Veritas.pdf', 'G11', 'v2', '2026-02-28', degrade('UPLOADED')),
      ],
    },
    {
      id: 10,
      name: 'Legal & Regulatory',
      docs: [
        doc('Legal Due Diligence Report - Linklaters.pdf', 'G10', 'v1', '2025-12-10', degrade('VERIFIED')),
        doc('Finance Law Opinion - Clifford Chance.pdf', 'G10', 'v2', '2026-01-08', degrade('VERIFIED')),
        doc('Regulatory Compliance Matrix - France H2.pdf', '—', 'v1', '2026-01-20', degrade('UPLOADED')),
      ],
    },
    {
      id: 11,
      name: 'Evidence Index',
      docs: [
        doc('GEX Evidence Index - Verified Hashes v4.pdf', '—', 'v4', '2026-03-10', degrade('VERIFIED')),
        doc('Playbook Annex E Checklist - Completion Summary.xlsx', '—', 'v2', '2026-03-12', degrade('UPLOADED')),
      ],
    },
  ]
}

// ─────────────────────────────── Status helpers ───────────────────────────────

function statusBadge(status: DocStatus) {
  switch (status) {
    case 'VERIFIED':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-100 border border-green-300 text-green-700 text-xs font-semibold">
          <CheckCircle2 className="w-3 h-3" /> VERIFIED
        </span>
      )
    case 'UPLOADED':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-100 border border-blue-300 text-blue-700 text-xs font-semibold">
          <FileText className="w-3 h-3" /> UPLOADED
        </span>
      )
    case 'PENDING':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 border border-amber-300 text-amber-700 text-xs font-semibold">
          <Clock className="w-3 h-3" /> PENDING
        </span>
      )
    case 'MISSING':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-100 border border-red-300 text-red-700 text-xs font-semibold">
          <XCircle className="w-3 h-3" /> MISSING
        </span>
      )
  }
}

function completenessColor(pct: number): string {
  if (pct >= 75) return 'bg-green-500'
  if (pct >= 40) return 'bg-amber-400'
  return 'bg-red-500'
}

function completenessTextColor(pct: number): string {
  if (pct >= 75) return 'text-green-600'
  if (pct >= 40) return 'text-amber-600'
  return 'text-red-500'
}

function computeCompleteness(docs: DataRoomDoc[]): number {
  if (docs.length === 0) return 0
  const present = docs.filter(d => d.status === 'VERIFIED' || d.status === 'UPLOADED').length
  return Math.round((present / docs.length) * 100)
}

// ─────────────────────────────── Component ───────────────────────────────────

export function DataRoom() {
  const { selectedProjectId } = useSelectedProject()
  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId) ?? visibleProjects[0]
  const [selectedCategoryId, setSelectedCategoryId] = useState(1)
  const [hoveredHash, setHoveredHash] = useState<string | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()

  // Deep-link from Bankability "Missing evidence" buttons:
  //   ?gate=G0_SITE_RIGHTS&evidence=land_option_or_lease_executed
  // Resolves the gate prefix (G0) and auto-selects the first category
  // containing a matching document so the user lands on the right page.
  const deepLinkGate     = searchParams.get('gate') ?? ''
  const deepLinkEvidence = searchParams.get('evidence') ?? ''
  const gatePrefix       = (deepLinkGate.match(/^G\d+/) ?? [''])[0]
  const evidenceHuman    = deepLinkEvidence.replace(/_/g, ' ')

  const categories = buildCategories(project.id)
  const selectedCategory = categories.find(c => c.id === selectedCategoryId) ?? categories[0]

  useEffect(() => {
    if (!gatePrefix) return
    const target = categories.find(c => c.docs.some(d => d.gateRef === gatePrefix))
    if (target) setSelectedCategoryId(target.id)
    // intentionally not depending on `categories` (recomputed each render)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gatePrefix, project.id])

  const clearDeepLink = () => setSearchParams({})

  // Overall completeness across all docs
  const allDocs = categories.flatMap(c => c.docs)
  const overallPct = computeCompleteness(allDocs)

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-6 py-4 shadow-card">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="font-display text-2xl font-bold text-[var(--text-primary)] flex items-center gap-2">
              <FolderOpen className="w-6 h-6 text-[var(--brand)]" />
              Data Room
            </h1>
            <WorkflowBadge state="REVIEWED" />
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{project.name} · Playbook Annex E</p>
        </div>
        <WorkflowActions
          state="REVIEWED"
          objectType="Data Room"
          userRole="analyst"
          projectId={project.id}
          workflowObjectType="DataRoom"
          workflowObjectId={`data-room-${project.id}`}
        />
      </div>

      {/* ── Deep-link context banner ── */}
      {deepLinkGate && (
        <div className="flex items-start gap-3 rounded-xl border border-[var(--brand)]/40 bg-[var(--brand-light)] px-4 py-3">
          <FileText className="mt-0.5 w-4 h-4 shrink-0 text-[var(--brand)]" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-[var(--text-primary)]">
              Looking for evidence: <span className="font-mono">{evidenceHuman || '(unspecified)'}</span>
            </p>
            <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
              Required by gate <span className="font-mono font-semibold">{deepLinkGate}</span>. The category
              {gatePrefix ? ` containing ${gatePrefix} documents` : ''} has been auto-selected below.
            </p>
          </div>
          <button
            onClick={clearDeepLink}
            className="flex items-center gap-1 text-[11px] text-[var(--brand)] hover:underline"
          >
            <ArrowLeft className="w-3 h-3" /> Clear filter
          </button>
        </div>
      )}

      {/* ── Overall completeness bar ── */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4 shadow-card">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-[var(--text-primary)]">Overall Data Room Completeness</span>
          <span className={`text-sm font-bold font-mono ${completenessTextColor(overallPct)}`}>{overallPct}%</span>
        </div>
        <div className="h-2.5 rounded-full bg-[var(--border)] overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${completenessColor(overallPct)}`}
            style={{ width: `${overallPct}%` }}
          />
        </div>
        <div className="flex gap-4 mt-2 text-xs text-[var(--text-muted)]">
          <span className="text-green-600 font-semibold">{allDocs.filter(d => d.status === 'VERIFIED').length} Verified</span>
          <span className="text-blue-600 font-semibold">{allDocs.filter(d => d.status === 'UPLOADED').length} Uploaded</span>
          <span className="text-amber-600 font-semibold">{allDocs.filter(d => d.status === 'PENDING').length} Pending</span>
          <span className="text-red-600 font-semibold">{allDocs.filter(d => d.status === 'MISSING').length} Missing</span>
        </div>
      </div>

      {/* ── Main layout: ToC + Table ── */}
      <div className="flex gap-4">

        {/* ToC Sidebar — 30% */}
        <div className="w-[30%] shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
          <div className="border-b border-[var(--border)] px-4 py-3">
            <h2 className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Table of Contents</h2>
          </div>
          <div className="divide-y divide-[var(--border)]">
            {categories.map(cat => {
              const pct = computeCompleteness(cat.docs)
              const isSelected = cat.id === selectedCategoryId
              return (
                <button
                  key={cat.id}
                  onClick={() => setSelectedCategoryId(cat.id)}
                  className={`w-full text-left px-4 py-3 flex items-center gap-3 transition-colors ${
                    isSelected
                      ? 'bg-[var(--brand-light)] border-l-2 border-l-[var(--brand)]'
                      : 'hover:bg-[var(--surface-hover)]'
                  }`}
                >
                  <span className="text-xs text-[var(--text-muted)] font-mono w-4 shrink-0">{cat.id}</span>
                  <div className="flex-1 min-w-0">
                    <div className={`text-xs font-semibold truncate ${isSelected ? 'text-[var(--brand)]' : 'text-[var(--text-primary)]'}`}>
                      {cat.name}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                      <div
                        className={`w-1.5 h-1.5 rounded-full shrink-0 ${completenessColor(pct)}`}
                      />
                      <span className="text-[10px] text-[var(--text-muted)]">{pct}% · {cat.docs.length} docs</span>
                    </div>
                  </div>
                  {isSelected && <ChevronRight className="w-3 h-3 text-[var(--brand)] shrink-0" />}
                </button>
              )
            })}
          </div>
        </div>

        {/* Document table — 70% */}
        <div className="flex-1 rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-[var(--text-primary)]">
                {selectedCategory.id}. {selectedCategory.name}
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                {selectedCategory.docs.length} documents · {computeCompleteness(selectedCategory.docs)}% complete
              </p>
            </div>
            <AlertCircle className="w-4 h-4 text-[var(--text-muted)]" />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--surface-hover)]">
                  <th className="text-left py-2.5 px-4 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Document</th>
                  <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Gate</th>
                  <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Ver</th>
                  <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Uploaded</th>
                  <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Status</th>
                  <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">SHA-256</th>
                  <th className="py-2.5 px-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {selectedCategory.docs.map((doc, idx) => (
                  <tr key={idx} className="hover:bg-[var(--surface-hover)] transition-colors">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <FileText className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
                        <span className="font-medium text-[var(--text-primary)] break-all">{doc.name}</span>
                      </div>
                    </td>
                    <td className="py-3 px-3 font-mono text-[var(--text-secondary)]">{doc.gateRef}</td>
                    <td className="py-3 px-3 font-mono text-[var(--text-muted)]">{doc.version}</td>
                    <td className="py-3 px-3 text-[var(--text-muted)]">{doc.uploadDate}</td>
                    <td className="py-3 px-3">{statusBadge(doc.status)}</td>
                    <td className="py-3 px-3">
                      {doc.status !== 'MISSING' ? (
                        <div className="relative">
                          <button
                            className="flex items-center gap-1 font-mono text-[10px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                            onMouseEnter={() => setHoveredHash(doc.sha256)}
                            onMouseLeave={() => setHoveredHash(null)}
                          >
                            <Hash className="w-3 h-3 shrink-0" />
                            {doc.sha256.slice(0, 8)}…
                          </button>
                          {hoveredHash === doc.sha256 && (
                            <div className="absolute bottom-full left-0 mb-1 z-10 bg-gray-900 text-white text-[10px] font-mono rounded-md px-2.5 py-1.5 shadow-lg whitespace-nowrap">
                              {doc.sha256}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-[var(--text-muted)] text-[10px]">—</span>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      {doc.status !== 'MISSING' && (
                        <button
                          onClick={() => window.alert('Demo: download')}
                          className="flex items-center gap-1 px-2 py-1 rounded-md border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-hover)] text-[var(--text-secondary)] transition-colors"
                          title="Download"
                        >
                          <Download className="w-3 h-3" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
