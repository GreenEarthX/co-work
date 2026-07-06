// Screen: Insurance schedule screen (/insurance-schedule, /finance/insurance-schedule)
/**
 * InsuranceSchedule — Structured insurance program schedule following Playbook §12A.
 * G7 gate evidence with lines, deductibles, endorsements, and completeness tracking.
 */

import { useState } from 'react'
import {
  ShieldCheck, AlertTriangle, CheckCircle2, Clock, XCircle,
  Building2, ChevronDown, ChevronUp,
} from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { WorkflowBadge } from '@/components/workflow/WorkflowBadge'
import { WorkflowActions } from '@/components/workflow/WorkflowActions'

// ─────────────────────────────── Types ───────────────────────────────────────

type LineStatus = 'PLACED' | 'QUOTED' | 'REQUIRED' | 'PENDING'

interface InsuranceLine {
  line: string
  insurer: string
  limit: string
  deductible: string
  trigger: string
  status: LineStatus
  renewal: string
  endorsements: string[]
}

interface EndorsementItem {
  name: string
  status: 'PLACED' | 'PENDING' | 'REQUIRED'
  note: string
}

interface G7EvidenceItem {
  item: string
  satisfied: boolean
}

interface InsuranceScheduleData {
  linesActive: number
  totalLimit: string
  annualPremium: string
  nextRenewal: string
  lines: InsuranceLine[]
  endorsements: EndorsementItem[]
  g7Evidence: G7EvidenceItem[]
}

// ─────────────────────────────── Demo data ────────────────────────────────────

const SCHEDULE_DATA: Record<string, InsuranceScheduleData> = {

  proj_lehavre_eng: {
    linesActive: 4,
    totalLimit: '€485M',
    annualPremium: '€4.2M',
    nextRenewal: '2026-11-01',
    lines: [
      {
        line: 'Construction All-Risk (CAR)',
        insurer: 'AXA XL',
        limit: '€195M',
        deductible: '€250K',
        trigger: 'Physical damage during construction',
        status: 'PLACED',
        renewal: '2026-11-01',
        endorsements: ['Lender Loss Payee', 'Waiver of Subrogation'],
      },
      {
        line: 'Delay in Start-Up (DSU)',
        insurer: 'Zurich Insurance',
        limit: '€80M',
        deductible: '30-day waiting period',
        trigger: 'Construction delay causing revenue loss',
        status: 'PLACED',
        renewal: '2026-11-01',
        endorsements: ['Lender Loss Payee'],
      },
      {
        line: 'Performance Bond',
        insurer: 'Euler Hermes (Allianz Trade)',
        limit: '€25M',
        deductible: '€0',
        trigger: 'EPC/OEM non-performance vs. guaranteed output',
        status: 'PLACED',
        renewal: '2027-06-30',
        endorsements: ['Assignment on Financial Close'],
      },
      {
        line: 'Marine Cargo',
        insurer: 'Lloyd\'s of London (Syndicate 4472)',
        limit: '€35M',
        deductible: '€50K per occurrence',
        trigger: 'Loss or damage during equipment transit',
        status: 'PLACED',
        renewal: '2026-08-15',
        endorsements: [],
      },
      {
        line: 'Third Party Liability',
        insurer: 'AXA XL',
        limit: '€50M',
        deductible: '€100K per occurrence',
        trigger: 'Bodily injury or property damage to third parties',
        status: 'QUOTED',
        renewal: '2026-11-01',
        endorsements: ['Additional Named Insured (lender)'],
      },
      {
        line: 'Pollution Liability',
        insurer: 'Chubb European Group',
        limit: '€30M',
        deductible: '€200K',
        trigger: 'Sudden and accidental pollution event',
        status: 'QUOTED',
        renewal: '2026-11-01',
        endorsements: [],
      },
      {
        line: 'Business Interruption (ops phase)',
        insurer: 'Swiss Re Corporate Solutions',
        limit: '€60M',
        deductible: '45-day waiting period',
        trigger: 'Operational revenue loss from insured peril',
        status: 'QUOTED',
        renewal: '2026-11-01',
        endorsements: ['Lender Loss Payee', 'Assignment on Financial Close'],
      },
      {
        line: 'Lender Loss Payee Endorsement',
        insurer: 'All insurers (endorsement)',
        limit: '—',
        deductible: '—',
        trigger: 'Claims proceeds paid directly to lender group',
        status: 'REQUIRED',
        renewal: '2026-11-01',
        endorsements: ['Required on all property lines'],
      },
    ],
    endorsements: [
      { name: 'Additional Named Insured (Senior Lender)', status: 'PLACED', note: 'BNP Paribas as ANI on CAR, DSU and BI policies.' },
      { name: 'Waiver of Subrogation', status: 'PLACED', note: 'In favour of lender group on all property damage policies.' },
      { name: 'Assignment on Financial Close', status: 'PLACED', note: 'Policies assigned to lender group on drawdown date.' },
      { name: 'Lender Loss Payee', status: 'PENDING', note: 'Awaiting final wording approval from lender insurance counsel.' },
    ],
    g7Evidence: [
      { item: 'CAR policy placed and bound', satisfied: true },
      { item: 'DSU policy placed with ≥18 months cover', satisfied: true },
      { item: 'Performance bond in place for EPC and OEM', satisfied: true },
      { item: 'Marine cargo policy placed', satisfied: true },
      { item: 'Third party liability ≥€50M placed', satisfied: false },
      { item: 'Pollution liability placed', satisfied: false },
      { item: 'Business interruption placed (ops phase)', satisfied: false },
      { item: 'All lender endorsements confirmed', satisfied: false },
    ],
  },

  proj_bremen_h2: {
    linesActive: 2,
    totalLimit: '€280M',
    annualPremium: '€2.6M',
    nextRenewal: '2027-03-01',
    lines: [
      {
        line: 'Construction All-Risk (CAR)',
        insurer: 'Munich Re',
        limit: '€220M',
        deductible: '€300K',
        trigger: 'Physical damage during construction',
        status: 'PLACED',
        renewal: '2027-03-01',
        endorsements: ['Lender Loss Payee'],
      },
      {
        line: 'Performance Bond',
        insurer: 'Allianz Trade',
        limit: '€18M',
        deductible: '€0',
        trigger: 'EPC non-performance',
        status: 'PLACED',
        renewal: '2027-09-30',
        endorsements: [],
      },
      {
        line: 'Delay in Start-Up (DSU)',
        insurer: 'Zurich Insurance',
        limit: '€40M',
        deductible: '45-day waiting period',
        trigger: 'Construction delay causing revenue loss',
        status: 'QUOTED',
        renewal: '2027-03-01',
        endorsements: [],
      },
      {
        line: 'Marine Cargo',
        insurer: 'Generali',
        limit: '€22M',
        deductible: '€75K',
        trigger: 'Equipment transit damage',
        status: 'QUOTED',
        renewal: '2026-12-01',
        endorsements: [],
      },
      {
        line: 'Third Party Liability',
        insurer: 'AXA',
        limit: '€30M',
        deductible: '€150K',
        trigger: 'Third party bodily injury / property damage',
        status: 'QUOTED',
        renewal: '2027-03-01',
        endorsements: [],
      },
      {
        line: 'Pollution Liability',
        insurer: 'Not yet selected',
        limit: '€20M',
        deductible: 'TBD',
        trigger: 'Pollution event',
        status: 'QUOTED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Business Interruption (ops phase)',
        insurer: 'Not yet selected',
        limit: '€50M',
        deductible: 'TBD',
        trigger: 'Operational revenue loss',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Lender Loss Payee Endorsement',
        insurer: 'All insurers',
        limit: '—',
        deductible: '—',
        trigger: 'Claims proceeds to lender',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
    ],
    endorsements: [
      { name: 'Additional Named Insured (Senior Lender)', status: 'PENDING', note: 'Lender group to be confirmed at financial close.' },
      { name: 'Waiver of Subrogation', status: 'PENDING', note: 'Required on CAR policy — wording in review.' },
      { name: 'Assignment on Financial Close', status: 'PENDING', note: 'Draft assignment clause agreed in principle.' },
      { name: 'Lender Loss Payee', status: 'REQUIRED', note: 'Not yet agreed. Broker mandate to issue by Q2 2026.' },
    ],
    g7Evidence: [
      { item: 'CAR policy placed and bound', satisfied: true },
      { item: 'DSU policy placed with ≥18 months cover', satisfied: false },
      { item: 'Performance bond in place for EPC and OEM', satisfied: true },
      { item: 'Marine cargo policy placed', satisfied: false },
      { item: 'Third party liability ≥€50M placed', satisfied: false },
      { item: 'Pollution liability placed', satisfied: false },
      { item: 'Business interruption placed (ops phase)', satisfied: false },
      { item: 'All lender endorsements confirmed', satisfied: false },
    ],
  },

  proj_sansebastian_emethanol: {
    linesActive: 1,
    totalLimit: '€165M',
    annualPremium: '€1.4M',
    nextRenewal: '2027-09-01',
    lines: [
      {
        line: 'Construction All-Risk (CAR)',
        insurer: 'Mapfre Re',
        limit: '€165M',
        deductible: '€400K',
        trigger: 'Physical damage during construction',
        status: 'PLACED',
        renewal: '2027-09-01',
        endorsements: [],
      },
      {
        line: 'Delay in Start-Up (DSU)',
        insurer: 'Zurich',
        limit: '€30M',
        deductible: '60-day waiting period',
        trigger: 'Revenue loss from construction delay',
        status: 'QUOTED',
        renewal: '2027-09-01',
        endorsements: [],
      },
      {
        line: 'Performance Bond',
        insurer: 'Not selected',
        limit: 'TBD',
        deductible: 'TBD',
        trigger: 'EPC non-performance',
        status: 'QUOTED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Marine Cargo',
        insurer: 'Not selected',
        limit: '€15M',
        deductible: 'TBD',
        trigger: 'Equipment transit',
        status: 'QUOTED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Third Party Liability',
        insurer: 'Not yet selected',
        limit: '€25M',
        deductible: 'TBD',
        trigger: 'Third party liability',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Pollution Liability',
        insurer: 'Not yet selected',
        limit: 'TBD',
        deductible: 'TBD',
        trigger: 'Pollution event',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Business Interruption (ops phase)',
        insurer: 'Not yet selected',
        limit: 'TBD',
        deductible: 'TBD',
        trigger: 'Operational revenue loss',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Lender Loss Payee Endorsement',
        insurer: 'All insurers',
        limit: '—',
        deductible: '—',
        trigger: 'Claims to lender',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
    ],
    endorsements: [
      { name: 'Additional Named Insured (Senior Lender)', status: 'REQUIRED', note: 'Lender not yet confirmed.' },
      { name: 'Waiver of Subrogation', status: 'REQUIRED', note: 'Not yet placed on any policy.' },
      { name: 'Assignment on Financial Close', status: 'REQUIRED', note: 'Pre-FID — financial close not imminent.' },
      { name: 'Lender Loss Payee', status: 'REQUIRED', note: 'Outstanding. Required for G7 gate.' },
    ],
    g7Evidence: [
      { item: 'CAR policy placed and bound', satisfied: true },
      { item: 'DSU policy placed with ≥18 months cover', satisfied: false },
      { item: 'Performance bond in place for EPC and OEM', satisfied: false },
      { item: 'Marine cargo policy placed', satisfied: false },
      { item: 'Third party liability ≥€50M placed', satisfied: false },
      { item: 'Pollution liability placed', satisfied: false },
      { item: 'Business interruption placed (ops phase)', satisfied: false },
      { item: 'All lender endorsements confirmed', satisfied: false },
    ],
  },

  proj_rotterdam_nh3: {
    linesActive: 0,
    totalLimit: '—',
    annualPremium: '—',
    nextRenewal: '—',
    lines: [
      {
        line: 'Construction All-Risk (CAR)',
        insurer: 'Not selected',
        limit: '€380M (target)',
        deductible: 'TBD',
        trigger: 'Physical damage during construction',
        status: 'QUOTED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Delay in Start-Up (DSU)',
        insurer: 'Not selected',
        limit: 'TBD',
        deductible: 'TBD',
        trigger: 'Revenue loss from delay',
        status: 'QUOTED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Performance Bond',
        insurer: 'Not selected',
        limit: 'TBD',
        deductible: 'TBD',
        trigger: 'EPC non-performance',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Marine Cargo',
        insurer: 'Not selected',
        limit: 'TBD',
        deductible: 'TBD',
        trigger: 'Equipment transit',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Third Party Liability',
        insurer: 'Not selected',
        limit: 'TBD',
        deductible: 'TBD',
        trigger: 'Third party liability',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Pollution Liability',
        insurer: 'Not selected',
        limit: 'TBD',
        deductible: 'TBD',
        trigger: 'Pollution event',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Business Interruption (ops phase)',
        insurer: 'Not selected',
        limit: 'TBD',
        deductible: 'TBD',
        trigger: 'Operational revenue loss',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
      {
        line: 'Lender Loss Payee Endorsement',
        insurer: 'All insurers',
        limit: '—',
        deductible: '—',
        trigger: 'Claims to lender',
        status: 'REQUIRED',
        renewal: 'TBD',
        endorsements: [],
      },
    ],
    endorsements: [
      { name: 'Additional Named Insured (Senior Lender)', status: 'REQUIRED', note: 'Lender group TBD.' },
      { name: 'Waiver of Subrogation', status: 'REQUIRED', note: 'No policies placed.' },
      { name: 'Assignment on Financial Close', status: 'REQUIRED', note: 'Pre-FID.' },
      { name: 'Lender Loss Payee', status: 'REQUIRED', note: 'Required — no policies placed yet.' },
    ],
    g7Evidence: [
      { item: 'CAR policy placed and bound', satisfied: false },
      { item: 'DSU policy placed with ≥18 months cover', satisfied: false },
      { item: 'Performance bond in place for EPC and OEM', satisfied: false },
      { item: 'Marine cargo policy placed', satisfied: false },
      { item: 'Third party liability ≥€50M placed', satisfied: false },
      { item: 'Pollution liability placed', satisfied: false },
      { item: 'Business interruption placed (ops phase)', satisfied: false },
      { item: 'All lender endorsements confirmed', satisfied: false },
    ],
  },

  proj_wales_saf: {
    linesActive: 0,
    totalLimit: '—',
    annualPremium: '—',
    nextRenewal: '—',
    lines: [
      { line: 'Construction All-Risk (CAR)', insurer: 'Not selected', limit: '€290M (target)', deductible: 'TBD', trigger: 'Physical damage during construction', status: 'REQUIRED', renewal: 'TBD', endorsements: [] },
      { line: 'Delay in Start-Up (DSU)', insurer: 'Not selected', limit: 'TBD', deductible: 'TBD', trigger: 'Revenue loss from delay', status: 'REQUIRED', renewal: 'TBD', endorsements: [] },
      { line: 'Performance Bond', insurer: 'Not selected', limit: 'TBD', deductible: 'TBD', trigger: 'EPC non-performance', status: 'REQUIRED', renewal: 'TBD', endorsements: [] },
      { line: 'Marine Cargo', insurer: 'Not selected', limit: 'TBD', deductible: 'TBD', trigger: 'Equipment transit', status: 'REQUIRED', renewal: 'TBD', endorsements: [] },
      { line: 'Third Party Liability', insurer: 'Not selected', limit: 'TBD', deductible: 'TBD', trigger: 'Third party liability', status: 'REQUIRED', renewal: 'TBD', endorsements: [] },
      { line: 'Pollution Liability', insurer: 'Not selected', limit: 'TBD', deductible: 'TBD', trigger: 'Pollution event', status: 'REQUIRED', renewal: 'TBD', endorsements: [] },
      { line: 'Business Interruption (ops phase)', insurer: 'Not selected', limit: 'TBD', deductible: 'TBD', trigger: 'Operational revenue loss', status: 'REQUIRED', renewal: 'TBD', endorsements: [] },
      { line: 'Lender Loss Payee Endorsement', insurer: 'All insurers', limit: '—', deductible: '—', trigger: 'Claims to lender', status: 'REQUIRED', renewal: 'TBD', endorsements: [] },
    ],
    endorsements: [
      { name: 'Additional Named Insured (Senior Lender)', status: 'REQUIRED', note: 'Pre-FID — not applicable yet.' },
      { name: 'Waiver of Subrogation', status: 'REQUIRED', note: 'Not placed.' },
      { name: 'Assignment on Financial Close', status: 'REQUIRED', note: 'Not placed.' },
      { name: 'Lender Loss Payee', status: 'REQUIRED', note: 'Not placed.' },
    ],
    g7Evidence: [
      { item: 'CAR policy placed and bound', satisfied: false },
      { item: 'DSU policy placed with ≥18 months cover', satisfied: false },
      { item: 'Performance bond in place for EPC and OEM', satisfied: false },
      { item: 'Marine cargo policy placed', satisfied: false },
      { item: 'Third party liability ≥€50M placed', satisfied: false },
      { item: 'Pollution liability placed', satisfied: false },
      { item: 'Business interruption placed (ops phase)', satisfied: false },
      { item: 'All lender endorsements confirmed', satisfied: false },
    ],
  },
}

// ─────────────────────────────── Status helpers ───────────────────────────────

function lineStatusBadge(status: LineStatus) {
  switch (status) {
    case 'PLACED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-100 border border-green-300 text-green-700 text-xs font-semibold"><CheckCircle2 className="w-3 h-3" /> PLACED</span>
    case 'QUOTED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 border border-amber-300 text-amber-700 text-xs font-semibold"><Clock className="w-3 h-3" /> QUOTED</span>
    case 'PENDING':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-100 border border-blue-300 text-blue-700 text-xs font-semibold"><Clock className="w-3 h-3" /> PENDING</span>
    case 'REQUIRED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-100 border border-red-300 text-red-700 text-xs font-semibold"><XCircle className="w-3 h-3" /> REQUIRED</span>
  }
}

function endorsementStatusBadge(status: 'PLACED' | 'PENDING' | 'REQUIRED') {
  switch (status) {
    case 'PLACED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-100 border border-green-300 text-green-700 text-[10px] font-semibold"><CheckCircle2 className="w-3 h-3" /> PLACED</span>
    case 'PENDING':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 border border-amber-300 text-amber-700 text-[10px] font-semibold"><Clock className="w-3 h-3" /> PENDING</span>
    case 'REQUIRED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-100 border border-red-300 text-red-700 text-[10px] font-semibold"><AlertTriangle className="w-3 h-3" /> REQUIRED</span>
  }
}

// ─────────────────────────────── Component ───────────────────────────────────

export function InsuranceSchedule() {
  const { selectedProjectId } = useSelectedProject()
  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId) ?? visibleProjects[0]
  const data = SCHEDULE_DATA[project.id] ?? SCHEDULE_DATA['proj_wales_saf']
  const [showEndorsements, setShowEndorsements] = useState(true)

  const placedCount = data.lines.filter(l => l.status === 'PLACED').length
  const quotedCount = data.lines.filter(l => l.status === 'QUOTED').length
  const requiredCount = data.lines.filter(l => l.status === 'REQUIRED' || l.status === 'PENDING').length

  const g7Satisfied = data.g7Evidence.filter(e => e.satisfied).length
  const g7Total = data.g7Evidence.length
  const g7Pct = Math.round((g7Satisfied / g7Total) * 100)

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-6 py-4 shadow-card">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="font-display text-2xl font-bold text-[var(--text-primary)] flex items-center gap-2">
              <ShieldCheck className="w-6 h-6 text-[var(--brand)]" />
              Insurance Schedule
            </h1>
            <WorkflowBadge state="COMPUTED" />
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{project.name} · Playbook §12A · G7 Gate Evidence</p>
        </div>
        <WorkflowActions
          state="COMPUTED"
          objectType="Insurance Schedule"
          userRole="analyst"
          projectId={project.id}
          workflowObjectType="InsuranceSchedule"
          workflowObjectId={`insurance-schedule-${project.id}`}
        />
      </div>

      {/* ── Program Summary strip ── */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-card">
          <div className="flex items-center gap-2 mb-1">
            <Building2 className="w-4 h-4 text-[var(--brand)]" />
            <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-[0.1em]">Lines Active</span>
          </div>
          <div className="text-3xl font-black text-[var(--text-primary)]">{data.linesActive}</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">of {data.lines.length} required</div>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-card">
          <div className="flex items-center gap-2 mb-1">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-[0.1em]">Total Limit</span>
          </div>
          <div className="text-3xl font-black text-[var(--text-primary)]">{data.totalLimit}</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">Aggregate placed cover</div>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-card">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle2 className="w-4 h-4 text-blue-600" />
            <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-[0.1em]">Annual Premium</span>
          </div>
          <div className="text-3xl font-black text-[var(--text-primary)]">{data.annualPremium}</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">Total insurance cost</div>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-card">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-4 h-4 text-amber-600" />
            <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-[0.1em]">Next Renewal</span>
          </div>
          <div className="text-2xl font-black text-[var(--text-primary)]">{data.nextRenewal}</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">Earliest policy renewal date</div>
        </div>
      </div>

      {/* ── Insurance lines table ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
        <div className="border-b border-[var(--border)] px-5 py-3 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[var(--text-primary)]">Insurance Program Lines</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              <span className="text-green-600 font-semibold">{placedCount} Placed</span>
              {' · '}
              <span className="text-amber-600 font-semibold">{quotedCount} Quoted</span>
              {' · '}
              <span className="text-red-600 font-semibold">{requiredCount} Required</span>
            </p>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--surface-hover)]">
                <th className="text-left py-2.5 px-4 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Line</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Insurer</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Limit</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Deductible</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Trigger</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Status</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Renewal</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Endorsements</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {data.lines.map((line, idx) => (
                <tr key={idx} className="hover:bg-[var(--surface-hover)] transition-colors">
                  <td className="py-3 px-4 font-medium text-[var(--text-primary)]">{line.line}</td>
                  <td className="py-3 px-3 text-[var(--text-secondary)]">{line.insurer}</td>
                  <td className="py-3 px-3 font-mono text-[var(--text-primary)] font-semibold">{line.limit}</td>
                  <td className="py-3 px-3 text-[var(--text-secondary)]">{line.deductible}</td>
                  <td className="py-3 px-3 text-[var(--text-muted)] max-w-[160px]">{line.trigger}</td>
                  <td className="py-3 px-3">{lineStatusBadge(line.status)}</td>
                  <td className="py-3 px-3 font-mono text-[var(--text-muted)]">{line.renewal}</td>
                  <td className="py-3 px-3">
                    {line.endorsements.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {line.endorsements.map((e, i) => (
                          <span key={i} className="inline-block px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--text-muted)] text-[10px]">{e}</span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-[var(--text-muted)]">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Endorsements panel ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
        <button
          onClick={() => setShowEndorsements(v => !v)}
          className="w-full border-b border-[var(--border)] px-5 py-3 flex items-center justify-between hover:bg-[var(--surface-hover)] transition-colors"
        >
          <div>
            <h2 className="text-sm font-bold text-[var(--text-primary)] text-left">Lender Endorsement Requirements</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5 text-left">Key endorsements required by senior lender group for financial close</p>
          </div>
          {showEndorsements ? <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />}
        </button>
        {showEndorsements && (
          <div className="divide-y divide-[var(--border)]">
            {data.endorsements.map((end, idx) => (
              <div key={idx} className="px-5 py-3.5 flex items-start gap-4">
                <div className="shrink-0 pt-0.5">{endorsementStatusBadge(end.status)}</div>
                <div>
                  <div className="text-xs font-semibold text-[var(--text-primary)]">{end.name}</div>
                  <div className="text-xs text-[var(--text-muted)] mt-0.5">{end.note}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── G7 Gate Completeness ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-5 py-5 shadow-card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">G7 Gate Completeness</h2>
          <span className={`text-sm font-bold font-mono ${g7Pct >= 75 ? 'text-emerald-600' : g7Pct >= 40 ? 'text-amber-600' : 'text-red-600'}`}>
            {g7Pct}% ({g7Satisfied}/{g7Total})
          </span>
        </div>
        <div className="h-2.5 rounded-full bg-[var(--border)] overflow-hidden mb-3">
          <div
            className={`h-full rounded-full transition-all duration-700 ${g7Pct >= 75 ? 'bg-emerald-500' : g7Pct >= 40 ? 'bg-amber-400' : 'bg-red-500'}`}
            style={{ width: `${g7Pct}%` }}
          />
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {data.g7Evidence.map((item, idx) => (
            <div key={idx} className="flex items-center gap-2 text-xs">
              {item.satisfied
                ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                : <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />}
              <span className={item.satisfied ? 'text-[var(--text-secondary)]' : 'text-[var(--text-muted)]'}>
                {item.item}
              </span>
            </div>
          ))}
        </div>
        {g7Pct < 100 && (
          <div className="mt-3 p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800">
            <AlertTriangle className="w-3.5 h-3.5 inline mr-1.5 text-amber-600" />
            <strong>{g7Total - g7Satisfied} item{g7Total - g7Satisfied !== 1 ? 's' : ''}</strong> outstanding before G7 gate can be confirmed as complete.
          </div>
        )}
      </div>

    </div>
  )
}
