/**
 * ClientCISODashboard — Per-company CISO workspace.
 *
 * Route: /ciso/client/:companyId
 *
 * Architecture:
 *  - useParams<{ companyId }> scopes ALL API calls to one company
 *  - Every fetch passes x-demo-company: companyId  (→ JWT sub after Phase 2A)
 *  - 9 tabs, each lazy-loaded on first activation
 *  - Real API first; company-specific demo data as fallback
 *
 * Security domains covered:
 *  Tab 1 monitoring   — overview, score, access log, OT gateways
 *  Tab 2 wae          — WAE approval queue (per company) + policies
 *  Tab 3 users        — User attribute + desk config (ABAC attributes)
 *  Tab 4 sod          — SoD violation history + active conflict pairs
 *  Tab 5 barriers     — Information barriers (create, view violations)
 *  Tab 6 residency    — DRPL policies + audit log
 *  Tab 7 commitments  — CSS commitment records (initiator & counterparty)
 *  Tab 8 compliance   — ISO 27001, GDPR, eIDAS posture
 *  Tab 9 config       — WAE thresholds, retention, contacts
 */

import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Shield, ShieldCheck, ArrowLeft, AlertTriangle, Activity,
  CheckCircle, XCircle, Users, Lock, Eye, Globe, Workflow,
  Split, Columns, MapPin, Fingerprint, FileCheck, Settings,
  UserCog, Wifi, WifiOff, Radio, Ban, Hash, Clock, Save,
  Pencil, Plus, ChevronDown, ChevronUp, Timer, FileSignature,
} from 'lucide-react'

// ─── Constants ────────────────────────────────────────────────────────────────

const API_BASE = 'http://localhost:8000/api/v1'

const ACTOR_TYPES = [
  'PRODUCER', 'OFFTAKER', 'COMMERCIAL_BANKER', 'DFI', 'INSURER',
  'REGULATOR', 'GOV_AGENCY', 'CERTIFIER', 'EPC_CONTRACTOR',
  'LOGISTICS_OPERATOR', 'TECHNOLOGY_PROVIDER', 'EXECUTIVE',
]
const CLEARANCE_LEVELS = ['STANDARD', 'CONFIDENTIAL', 'RESTRICTED']
const DESK_SUFFIXES = [
  'PROCUREMENT', 'PROJECT_FINANCE', 'TRADING', 'CORPORATE_FINANCE',
  'LEGAL', 'COMPLIANCE', 'EXECUTIVE', 'OPERATIONS', 'RISK',
]
const DATA_CATEGORIES = [
  'PERSONAL', 'CONTRACT', 'FINANCIAL_MODEL', 'CERTIFICATION',
  'COMMS_METADATA', 'PLANT_DATA', 'AUDIT_LOG',
]
const ALWAYS_EU = new Set(['AUDIT_LOG', 'COMMS_METADATA'])

// ─── Company registry ────────────────────────────────────────────────────────

const COMPANY_REGISTRY: Record<string, {
  name: string; ciso: string; jurisdiction: string; iso27001: boolean; projects: string[]
}> = {
  bp_global_energy:  { name: 'BP Global Energy',   ciso: 'Marcus Webb',      jurisdiction: 'EU / GB', iso27001: true,  projects: ['proj_breizh_saf', 'proj_north_sea_h2'] },
  shell_energy:      { name: 'Shell Energy',        ciso: 'Anna Broersen',    jurisdiction: 'EU / NL', iso27001: true,  projects: ['proj_rotterdam_h2', 'proj_ijssel_wind'] },
  bnp_paribas:       { name: 'BNP Paribas',         ciso: 'Henri Leconte',    jurisdiction: 'EU / FR', iso27001: true,  projects: [] },
  rwe_renewables:    { name: 'RWE Renewables',      ciso: 'Klaus Fischer',    jurisdiction: 'EU / DE', iso27001: false, projects: ['proj_ruhr_wind', 'proj_baltic_offshore'] },
  total_energies:    { name: 'TotalEnergies',       ciso: 'Claire Moreau',    jurisdiction: 'EU / FR', iso27001: true,  projects: ['proj_provence_solar'] },
}

// ─── Demo data factory ───────────────────────────────────────────────────────

function demoOverview(companyId: string, info: typeof COMPANY_REGISTRY[string]) {
  const score = companyId === 'bnp_paribas' ? 88 : companyId === 'rwe_renewables' ? 61 : 76
  return {
    company_name: info.name,
    security_score: score,
    score_label: score >= 80 ? 'Strong' : score >= 65 ? 'Good' : 'Needs attention',
    kpis: {
      total_users: companyId === 'bnp_paribas' ? 12 : companyId === 'shell_energy' ? 9 : 5,
      mfa_enabled_pct: score >= 80 ? 100 : score >= 65 ? 80 : 60,
      kyc_verified: 4,
      kyc_pending: 1,
      abac_assigned: 4,
      abac_unassigned: 1,
    },
    events_24h: { total: 28, allow: 22, deny: 6, deny_rate_pct: 21 },
    abac_phase: {
      current: 2,
      phases: [
        { phase: 1, label: 'R1–R3: Stakeholder + Evidence', status: 'active' },
        { phase: 2, label: 'R4–R6: Financial + Export + Write', status: 'active' },
        { phase: 3, label: 'R7: Desk-level Chinese Walls', status: companyId === 'bnp_paribas' ? 'active' : 'planned' },
      ],
    },
    alerts: [
      { id: 'a1', severity: 'high',   message: `${Math.round(100 - score + 20)}% MFA adoption — ensure all users enrol`, ts: '2026-03-16T06:00:00Z' },
      { id: 'a2', severity: 'medium', message: '1 user with KYC status PENDING', ts: '2026-03-15T14:00:00Z' },
    ],
  }
}

function demoAccessLog(companyId: string) {
  const actions = ['READ', 'WRITE', 'EXPORT', 'VERIFY', 'SHARE']
  const resources = ['FINANCIAL_MODEL', 'CONTRACT', 'CERTIFICATION', 'PLANT_DATA', 'AUDIT_LOG']
  const decisions: ('ALLOW' | 'DENY')[] = ['ALLOW', 'ALLOW', 'ALLOW', 'DENY', 'ALLOW']
  return Array.from({ length: 20 }, (_, i) => ({
    id: `ev-${i}`,
    timestamp: new Date(Date.now() - i * 180_000).toISOString(),
    user_id: `user_${(i % 3) + 1}`,
    user_name: ['Alice Chen', 'Bob Muller', 'Claire Martin'][i % 3],
    company_id: companyId,
    project_id: 'proj_001',
    project_name: 'Project Alpha',
    resource_type: resources[i % resources.length],
    action: actions[i % actions.length],
    decision: decisions[i % decisions.length],
    rule_triggered: decisions[i % decisions.length] === 'DENY' ? 'R4_FINANCIAL_READ' : null,
    denial_reason: decisions[i % decisions.length] === 'DENY' ? 'Clearance level insufficient' : null,
  }))
}

function demoUsers(companyId: string) {
  const perCompany: Record<string, any[]> = {
    bp_global_energy: [
      { user_id: 'u1', name: 'James Walker',    email: 'j.walker@bp.com',         role: 'EXECUTIVE',         clearance_level: 'RESTRICTED',   desk_id: 'BP_EXECUTIVE',       kyc_status: 'VERIFIED', mfa_enabled: true },
      { user_id: 'u2', name: 'Sarah Chen',       email: 's.chen@bp.com',            role: 'PRODUCER',          clearance_level: 'CONFIDENTIAL', desk_id: 'BP_PROJECT_FINANCE', kyc_status: 'VERIFIED', mfa_enabled: true },
      { user_id: 'u3', name: 'Ahmed Al-Rashid',  email: 'a.alrashid@bp.com',        role: 'OFFTAKER',          clearance_level: 'STANDARD',     desk_id: 'BP_PROCUREMENT',    kyc_status: 'VERIFIED', mfa_enabled: false },
      { user_id: 'u4', name: 'Emma Taylor',      email: 'e.taylor@bp.com',          role: 'PRODUCER',          clearance_level: 'CONFIDENTIAL', desk_id: 'BP_TRADING',        kyc_status: 'PENDING',  mfa_enabled: true },
      { user_id: 'u5', name: 'David Kim',        email: 'd.kim@bp.com',             role: 'CERTIFIER',         clearance_level: 'CONFIDENTIAL', desk_id: 'BP_COMPLIANCE',     kyc_status: 'VERIFIED', mfa_enabled: true },
    ],
    bnp_paribas: [
      { user_id: 'u1', name: 'Marie Dupont',      email: 'm.dupont@bnpparibas.com', role: 'COMMERCIAL_BANKER', clearance_level: 'RESTRICTED',   desk_id: 'BNP_STRUCTURED_FINANCE', kyc_status: 'VERIFIED', mfa_enabled: true },
      { user_id: 'u2', name: 'Jean-Pierre Martin', email: 'jp.martin@bnpparibas.com',role: 'COMMERCIAL_BANKER', clearance_level: 'CONFIDENTIAL', desk_id: 'BNP_PROJECT_FINANCE',    kyc_status: 'VERIFIED', mfa_enabled: true },
      { user_id: 'u3', name: 'Isabelle Blanc',    email: 'i.blanc@bnpparibas.com',  role: 'DFI',               clearance_level: 'CONFIDENTIAL', desk_id: 'BNP_COMPLIANCE',         kyc_status: 'VERIFIED', mfa_enabled: true },
    ],
    shell_energy: [
      { user_id: 'u1', name: 'Pieter de Jong',   email: 'p.dejong@shell.com',      role: 'EXECUTIVE',         clearance_level: 'RESTRICTED',   desk_id: 'SHELL_EXECUTIVE',    kyc_status: 'VERIFIED', mfa_enabled: true },
      { user_id: 'u2', name: 'Lisa van Houten',  email: 'l.vanhouten@shell.com',   role: 'PRODUCER',          clearance_level: 'CONFIDENTIAL', desk_id: 'SHELL_PROCUREMENT',  kyc_status: 'VERIFIED', mfa_enabled: true },
      { user_id: 'u3', name: 'Tom Bakker',        email: 't.bakker@shell.com',      role: 'OFFTAKER',          clearance_level: 'STANDARD',     desk_id: 'SHELL_TRADING',      kyc_status: 'PENDING',  mfa_enabled: false },
    ],
  }
  return perCompany[companyId] ?? perCompany.bp_global_energy
}

function demoApprovals(companyId: string) {
  const companyName = COMPANY_REGISTRY[companyId]?.name ?? companyId
  return [
    {
      request_id: 'req-001',
      action_type: 'SIGN_OFFTAKE_CONTRACT',
      status: 'PENDING_APPROVAL',
      initiator_user_id: 'sarah.chen',
      project_id: 'proj_breizh_saf',
      company: companyName,
      amount: 2_500_000,
      required_roles: ['CFO', 'LEGAL'],
      min_approvers: 2,
      approvals_received: 1,
      expires_at: new Date(Date.now() + 86_400_000).toISOString(),
      payload: { description: 'Sign 10-year offtake agreement — Projet Breizh SAF' },
    },
    {
      request_id: 'req-002',
      action_type: 'RELEASE_DRAWDOWN',
      status: 'PENDING_APPROVAL',
      initiator_user_id: 'james.walker',
      project_id: 'proj_breizh_saf',
      company: companyName,
      amount: 8_000_000,
      required_roles: ['CFO', 'CEO', 'LEGAL'],
      min_approvers: 3,
      approvals_received: 0,
      expires_at: new Date(Date.now() + 172_800_000).toISOString(),
      payload: { description: 'First drawdown — construction phase funding' },
    },
    {
      request_id: 'req-003',
      action_type: 'SUBMIT_CERTIFICATION',
      status: 'APPROVED',
      initiator_user_id: 'david.kim',
      project_id: 'proj_breizh_saf',
      company: companyName,
      amount: null,
      required_roles: ['TECHNICAL_LEAD'],
      min_approvers: 1,
      approvals_received: 1,
      expires_at: new Date(Date.now() - 3_600_000).toISOString(),
      payload: { description: 'RED III certification submission' },
    },
  ]
}

function demoSodViolations(companyId: string) {
  const companyName = COMPANY_REGISTRY[companyId]?.name ?? companyId
  return [
    {
      id: 'sod-001',
      conflict_pair_id: 'SoD-01',
      user_name: 'Sarah Chen',
      action_performed: 'SUBMIT_CERTIFICATION',
      blocked_action: 'VERIFY_CERTIFICATION',
      project_name: 'Breizh SAF',
      company_name: companyName,
      resolution: 'BLOCKED',
      timestamp: new Date(Date.now() - 7_200_000).toISOString(),
    },
    {
      id: 'sod-002',
      conflict_pair_id: 'SoD-03',
      user_name: 'James Walker',
      action_performed: 'INITIATE_DRAWDOWN',
      blocked_action: 'APPROVE_DRAWDOWN',
      project_name: 'Breizh SAF',
      company_name: companyName,
      resolution: 'BLOCKED',
      timestamp: new Date(Date.now() - 28_800_000).toISOString(),
    },
  ]
}

function demoBarriers(companyId: string) {
  return [
    { id: 'ib-01', company_id: companyId, side_a: `${companyId.toUpperCase().split('_')[0]}_TRADING`, side_b: `${companyId.toUpperCase().split('_')[0]}_ORIGINATION`, barrier_type: 'HARD', applies_to_data: ['FINANCIAL_MODEL', 'CONTRACT'], description: 'Trading desk isolated from deal origination', active: true, created_at: '2026-01-15T10:00:00Z', recent_violations: [{ user: 'Emma Taylor', action: 'READ_ORIGINATION_MODEL', ts: '2026-03-10T14:22:00Z' }] },
    { id: 'ib-02', company_id: companyId, side_a: `${companyId.toUpperCase().split('_')[0]}_LEGAL`, side_b: `${companyId.toUpperCase().split('_')[0]}_TRADING`, barrier_type: 'SOFT', applies_to_data: ['CONTRACT'], description: 'Legal cannot access live trading positions', active: true, created_at: '2026-01-20T09:00:00Z', recent_violations: [] },
  ]
}

function demoResidency(companyId: string) {
  const jur = COMPANY_REGISTRY[companyId]?.jurisdiction.split(' / ')[0] ?? 'EU'
  return DATA_CATEGORIES.map((cat, i) => ({
    id: `rp-${i}`,
    data_category: cat,
    required_jurisdiction: ALWAYS_EU.has(cat) ? 'EU' : jur,
    storage_zone: ALWAYS_EU.has(cat) ? 'eu-west-1' : i % 3 === 0 ? 'eu-central-1' : 'eu-west-1',
    active: true,
    locked: ALWAYS_EU.has(cat),
    status: 'COMPLIANT',
  }))
}

function demoCommitments(companyId: string) {
  const name = COMPANY_REGISTRY[companyId]?.name ?? companyId
  return [
    {
      id: 'css-001',
      action_type: 'SIGN_OFFTAKE_CONTRACT',
      status: 'FULLY_SIGNED',
      project_name: 'Breizh SAF',
      initiator: { userName: 'Sarah Chen', companyName: name, signed: true, timestamp: '2026-02-14T10:30:00Z' },
      approvers: [{ role: 'CFO', userName: 'James Walker', signed: true, timestamp: '2026-02-14T11:00:00Z' }],
      counterparty: { userName: 'Pieter de Jong', companyName: 'Shell Energy', signed: true, timestamp: '2026-02-15T09:15:00Z' },
      payloadHash: 'a3f8e1…c22d',
      recordHash: 'd9b47f…0a91',
    },
    {
      id: 'css-002',
      action_type: 'RELEASE_DRAWDOWN',
      status: 'PENDING_COUNTERSIGN',
      project_name: 'Breizh SAF',
      initiator: { userName: 'James Walker', companyName: name, signed: true, timestamp: '2026-03-10T14:00:00Z' },
      approvers: [
        { role: 'CFO',   userName: 'James Walker', signed: true,  timestamp: '2026-03-10T14:30:00Z' },
        { role: 'LEGAL', userName: 'Emma Taylor',  signed: false, timestamp: '2026-03-10T15:00:00Z' },
      ],
      counterparty: null,
      payloadHash: 'b7c92a…f34e',
      recordHash: 'e1a05b…8c72',
    },
  ]
}

// ─── API helpers ─────────────────────────────────────────────────────────────

function apiCall(path: string, companyId: string, options: RequestInit = {}) {
  return fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'x-demo-company': companyId,
      ...options.headers,
    },
    ...options,
  })
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
}

// ─── Helper components ────────────────────────────────────────────────────────

function ScoreGauge({ score, label }: { score: number; label: string }) {
  const color = score >= 75 ? 'text-emerald-600 dark:text-emerald-400'
    : score >= 50 ? 'text-amber-500' : 'text-red-500'
  const ring  = score >= 75 ? 'stroke-emerald-500' : score >= 50 ? 'stroke-amber-400' : 'stroke-red-500'
  const r = 38, circ = 2 * Math.PI * r
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-24 h-24">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r={r} fill="none" strokeWidth="8" className="stroke-[var(--border)]" />
          <circle cx="50" cy="50" r={r} fill="none" strokeWidth="8" strokeLinecap="round"
            className={ring} strokeDasharray={circ}
            strokeDashoffset={circ - (score / 100) * circ}
            style={{ transition: 'stroke-dashoffset 0.8s ease' }} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`font-display text-2xl font-extrabold leading-none ${color}`}>{score}</span>
          <span className="text-[9px] text-[var(--text-muted)] font-semibold uppercase">/100</span>
        </div>
      </div>
      <span className={`text-xs font-bold ${color}`}>{label}</span>
    </div>
  )
}

function Kpi({ label, value, sub, accent, Icon }: { label: string; value: string | number; sub?: string; accent?: string; Icon?: any }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 shadow-card">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">{label}</span>
        {Icon && <Icon className="w-3 h-3 text-[var(--text-muted)]" />}
      </div>
      <div className={`mt-0.5 font-display text-xl font-extrabold leading-none ${accent ?? 'text-[var(--text-primary)]'}`}>{value}</div>
      {sub && <div className="text-[10px] text-[var(--text-muted)] mt-0.5">{sub}</div>}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    PENDING_APPROVAL: 'gex-badge gex-badge-amber',
    APPROVED:         'gex-badge gex-badge-green',
    REJECTED:         'gex-badge gex-badge-red',
    EXPIRED:          'gex-badge gex-badge-default',
    BLOCKED:          'gex-badge gex-badge-red',
    FULLY_SIGNED:     'gex-badge gex-badge-green',
    PENDING_COUNTERSIGN: 'gex-badge gex-badge-amber',
    OVERRIDE_APPROVED:   'gex-badge gex-badge-amber',
    COMPLIANT:        'gex-badge gex-badge-green',
    MISMATCHED:       'gex-badge gex-badge-red',
    PENDING_REVIEW:   'gex-badge gex-badge-amber',
    ONLINE:           'gex-badge gex-badge-green',
    OFFLINE:          'gex-badge gex-badge-red',
    DEGRADED:         'gex-badge gex-badge-amber',
  }
  return <span className={map[status] ?? 'gex-badge gex-badge-default'}>{status.replace(/_/g, ' ')}</span>
}

// ─── Tab types ────────────────────────────────────────────────────────────────

type TabKey = 'monitoring' | 'wae' | 'users' | 'sod' | 'barriers' | 'residency' | 'commitments' | 'compliance' | 'config'

// ─── Main component ───────────────────────────────────────────────────────────

export function ClientCISODashboard() {
  const { companyId = 'bp_global_energy' } = useParams<{ companyId: string }>()
  const navigate = useNavigate()

  const info = COMPANY_REGISTRY[companyId] ?? { name: companyId, ciso: 'Unknown', jurisdiction: 'EU', iso27001: false, projects: [] }

  // ── Per-tab state ──────────────────────────────────────────────────────────
  const [tab, setTab] = useState<TabKey>('monitoring')

  const [overview, setOverview]       = useState<any>(null)
  const [accessLog, setAccessLog]     = useState<any[]>([])
  const [gateways, setGateways]       = useState<any[]>([])
  const [approvals, setApprovals]     = useState<any[]>([])
  const [policies, setPolicies]       = useState<any[]>([])
  const [sodPairs, setSodPairs]       = useState<any[]>([])
  const [sodViolations, setSodViolations] = useState<any[]>([])
  const [users, setUsers]             = useState<any[]>([])
  const [barriers, setBarriers]       = useState<any[]>([])
  const [residency, setResidency]     = useState<any[]>([])
  const [resAudit, setResAudit]       = useState<any[]>([])
  const [commitments, setCommitments] = useState<any[]>([])
  const [compliance, setCompliance]   = useState<any>(null)

  const [loadedTabs, setLoadedTabs]   = useState<Set<TabKey>>(new Set())
  const [loading, setLoading]         = useState<TabKey | null>('monitoring')

  // ── UI state ───────────────────────────────────────────────────────────────
  const [editingUser, setEditingUser] = useState<string | null>(null)
  const [editForm, setEditForm]       = useState<any>({})
  const [showBarrierForm, setShowBarrierForm] = useState(false)
  const [barrierForm, setBarrierForm] = useState({ side_a: '', side_b: '', barrier_type: 'HARD', applies_to_data: [] as string[], description: '' })
  const [expandedItem, setExpandedItem] = useState<string | null>(null)
  const [resEditingId, setResEditingId] = useState<string | null>(null)
  const [resEditForm, setResEditForm] = useState<any>({})

  // ── Data loaders ───────────────────────────────────────────────────────────

  const loadMonitoring = useCallback(async () => {
    setLoading('monitoring')
    try {
      const [ov, log, gw] = await Promise.all([
        apiCall('/ciso/overview', companyId),
        apiCall('/ciso/access-log?limit=30', companyId),
        apiCall('/ciso/gateways', companyId),
      ])
      setOverview(ov)
      setAccessLog(log.events || log.items || [])
      setGateways(gw.gateways || [])
    } catch {
      setOverview(demoOverview(companyId, info))
      setAccessLog(demoAccessLog(companyId))
      setGateways([])
    }
    setLoading(null)
  }, [companyId])

  const loadWae = useCallback(async () => {
    setLoading('wae')
    try {
      const [pend, pol] = await Promise.all([
        apiCall('/approvals/pending', companyId),
        apiCall('/approvals/policies/list', companyId),
      ])
      setApprovals(pend.items || [])
      setPolicies(pol.policies || [])
    } catch {
      setApprovals(demoApprovals(companyId))
      setPolicies([])
    }
    setLoading(null)
  }, [companyId])

  const loadUsers = useCallback(async () => {
    setLoading('users')
    try {
      const data = await apiCall('/ciso/users', companyId)
      setUsers(data.users || data.items || [])
    } catch {
      setUsers(demoUsers(companyId))
    }
    setLoading(null)
  }, [companyId])

  const loadSod = useCallback(async () => {
    setLoading('sod')
    try {
      const data = await apiCall('/approvals/sod/pairs', companyId)
      setSodPairs(data.pairs || [])
    } catch {
      setSodPairs([])
    }
    setSodViolations(demoSodViolations(companyId))
    setLoading(null)
  }, [companyId])

  const loadBarriers = useCallback(async () => {
    setLoading('barriers')
    try {
      const data = await apiCall('/ciso/barriers', companyId)
      setBarriers(data.barriers || [])
    } catch {
      setBarriers(demoBarriers(companyId))
    }
    setLoading(null)
  }, [companyId])

  const loadResidency = useCallback(async () => {
    setLoading('residency')
    try {
      const [pols, audit] = await Promise.all([
        apiCall('/ciso/residency/policies', companyId),
        apiCall('/ciso/residency/audit', companyId),
      ])
      setResidency(pols.policies || [])
      setResAudit(audit.entries || [])
    } catch {
      setResidency(demoResidency(companyId))
      setResAudit([])
    }
    setLoading(null)
  }, [companyId])

  const loadCommitments = useCallback(async () => {
    setLoading('commitments')
    const fetches = info.projects.length
      ? info.projects.map(pid => apiCall(`/commitments/project/${pid}`, companyId).catch(() => ({ commitments: [] })))
      : [Promise.resolve({ commitments: demoCommitments(companyId) })]
    try {
      const results = await Promise.all(fetches)
      const all = results.flatMap((r: any) => r.commitments || [])
      setCommitments(all.length ? all : demoCommitments(companyId))
    } catch {
      setCommitments(demoCommitments(companyId))
    }
    setLoading(null)
  }, [companyId])

  const loadCompliance = useCallback(async () => {
    setLoading('compliance')
    try {
      const data = await apiCall('/ciso/compliance', companyId)
      setCompliance(data)
    } catch {
      setCompliance(null)
    }
    setLoading(null)
  }, [companyId])

  // ── Tab switching ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (loadedTabs.has(tab)) return
    setLoadedTabs(prev => new Set([...prev, tab]))
    const loaders: Partial<Record<TabKey, () => void>> = {
      monitoring:  loadMonitoring,
      wae:         loadWae,
      users:       loadUsers,
      sod:         loadSod,
      barriers:    loadBarriers,
      residency:   loadResidency,
      commitments: loadCommitments,
      compliance:  loadCompliance,
    }
    loaders[tab]?.()
  }, [tab])

  // ── Badge counts ───────────────────────────────────────────────────────────

  const pendingCount    = approvals.filter(a => a.status === 'PENDING_APPROVAL' || a.status === 'ESCALATED').length
  const sodCount        = sodViolations.length
  const activeBarriers  = barriers.filter(b => b.active).length
  const pendingCommit   = commitments.filter(c => c.status !== 'FULLY_SIGNED').length

  const tabs: { key: TabKey; label: string; Icon: any; badge?: number }[] = [
    { key: 'monitoring',  label: 'Monitoring',   Icon: Activity },
    { key: 'wae',         label: 'WAE Approvals', Icon: Workflow,     badge: pendingCount },
    { key: 'users',       label: 'Users & Desks', Icon: UserCog },
    { key: 'sod',         label: 'SoD',           Icon: Split,        badge: sodCount },
    { key: 'barriers',    label: 'Barriers',      Icon: Columns,      badge: activeBarriers },
    { key: 'residency',   label: 'Residency',     Icon: MapPin },
    { key: 'commitments', label: 'Commitments',   Icon: Fingerprint,  badge: pendingCommit },
    { key: 'compliance',  label: 'Compliance',    Icon: FileCheck },
    { key: 'config',      label: 'Config',        Icon: Settings },
  ]

  const ov = overview ?? demoOverview(companyId, info)

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-center gap-4 mb-5">
        <button
          onClick={() => navigate('/ciso-dashboard')}
          className="flex items-center justify-center h-8 w-8 rounded-lg border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-hover)] transition-colors"
        >
          <ArrowLeft className="w-4 h-4 text-[var(--text-muted)]" />
        </button>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-900/30">
            <Shield className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display font-bold text-lg text-[var(--text-primary)]">
                {info.name} — CISO Dashboard
              </h1>
              {info.iso27001 && (
                <span className="gex-badge gex-badge-green text-[9px]">
                  <ShieldCheck className="w-2.5 h-2.5 mr-0.5 inline" /> ISO 27001
                </span>
              )}
            </div>
            <p className="text-xs text-[var(--text-muted)]">CISO: {info.ciso} · {info.jurisdiction}</p>
          </div>
        </div>
        {ov.alerts?.some((a: any) => a.severity === 'high') && (
          <span className="ml-auto gex-badge gex-badge-red">
            <AlertTriangle className="w-3 h-3 mr-1 inline" /> Active Alert
          </span>
        )}
      </div>

      {/* ── Tab bar ── */}
      <div className="flex gap-1 overflow-x-auto pb-1 mb-5">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg whitespace-nowrap transition-colors ${
              tab === t.key
                ? 'bg-[var(--brand)] text-white'
                : 'text-[var(--text-muted)] hover:bg-[var(--surface-hover)]'
            }`}
          >
            <t.Icon className="w-3.5 h-3.5" />
            {t.label}
            {!!t.badge && t.badge > 0 && (
              <span className="ml-0.5 h-4 min-w-[16px] px-1 rounded-full bg-red-500 text-white text-[9px] flex items-center justify-center">
                {t.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* TAB: MONITORING                                                       */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'monitoring' && (
        <div className="space-y-5">

          {/* Alerts */}
          {ov.alerts?.length > 0 && (
            <div className="space-y-2">
              {ov.alerts.map((a: any) => (
                <div key={a.id} className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${
                  a.severity === 'high' ? 'border-red-200 bg-red-50 dark:border-red-800/40 dark:bg-red-900/10'
                  : 'border-amber-200 bg-amber-50 dark:border-amber-800/40 dark:bg-amber-900/10'
                }`}>
                  <AlertTriangle className={`w-4 h-4 mt-0.5 shrink-0 ${a.severity === 'high' ? 'text-red-600' : 'text-amber-500'}`} />
                  <div className="flex-1">
                    <p className="text-sm text-[var(--text-primary)]">{a.message}</p>
                    <p className="text-xs text-[var(--text-muted)]">{new Date(a.ts).toLocaleString('en-GB')}</p>
                  </div>
                  <span className={a.severity === 'high' ? 'gex-badge gex-badge-red' : 'gex-badge gex-badge-amber'}>{a.severity}</span>
                </div>
              ))}
            </div>
          )}

          {/* Score + KPIs */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-[auto_1fr]">
            <div className="flex items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-8 py-5 shadow-card">
              <div className="flex flex-col items-center gap-3">
                <ScoreGauge score={ov.security_score} label={ov.score_label} />
                <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Security Score</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Kpi label="Total Users"   value={ov.kpis.total_users}           Icon={Users} />
              <Kpi label="MFA Adoption"  value={`${ov.kpis.mfa_enabled_pct}%`}
                accent={ov.kpis.mfa_enabled_pct === 100 ? 'text-emerald-600' : 'text-amber-500'}
                sub="of users enrolled" Icon={Lock} />
              <Kpi label="KYC Verified"  value={ov.kpis.kyc_verified}
                sub={`${ov.kpis.kyc_pending} pending`} accent="text-[var(--brand)]" Icon={CheckCircle} />
              <Kpi label="ABAC Assigned" value={ov.kpis.abac_assigned}
                sub={`${ov.kpis.abac_unassigned} unassigned`} accent="text-[var(--brand)]" Icon={Shield} />
              <Kpi label="Events (24 h)" value={ov.events_24h.total}
                sub={`${ov.events_24h.allow} allow / ${ov.events_24h.deny} deny`} Icon={Activity} />
              <Kpi label="Deny Rate"     value={`${ov.events_24h.deny_rate_pct}%`}
                accent={ov.events_24h.deny_rate_pct > 30 ? 'text-red-500' : undefined}
                sub="of requests" Icon={XCircle} />
            </div>
          </div>

          {/* ABAC phases */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
            <div className="border-b border-[var(--border)] px-5 py-3.5">
              <h2 className="text-sm font-bold text-[var(--text-primary)]">ABAC Policy Deployment</h2>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {ov.abac_phase.phases.map((p: any) => (
                <div key={p.phase} className="flex items-center gap-4 px-5 py-3">
                  <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                    p.status === 'active' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                    : 'bg-[var(--surface-hover)] text-[var(--text-muted)]'}`}>
                    {p.phase}
                  </div>
                  <span className="flex-1 text-sm text-[var(--text-primary)]">{p.label}</span>
                  <span className={p.status === 'active' ? 'gex-badge gex-badge-green' : 'gex-badge gex-badge-default'}>
                    {p.status}
                  </span>
                  {p.phase === ov.abac_phase.current && (
                    <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">current</span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Access log */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
            <div className="border-b border-[var(--border)] px-5 py-3.5 flex items-center gap-2">
              <Eye className="w-4 h-4 text-[var(--text-muted)]" />
              <h2 className="text-sm font-bold text-[var(--text-primary)]">Recent Access Events</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[var(--text-muted)]">
                    {['Time', 'User', 'Action', 'Resource', 'Decision', 'Reason'].map(h => (
                      <th key={h} className="text-left py-2 px-3 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {accessLog.slice(0, 25).map((e: any, i: number) => (
                    <tr key={e.id ?? i} className="border-b border-[var(--border)]/40 hover:bg-[var(--surface-hover)]">
                      <td className="py-1.5 px-3 text-[var(--text-muted)] whitespace-nowrap">
                        {new Date(e.timestamp).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </td>
                      <td className="py-1.5 px-3 font-medium text-[var(--text-primary)]">{e.user_name}</td>
                      <td className="py-1.5 px-3"><span className="gex-badge gex-badge-default">{e.action}</span></td>
                      <td className="py-1.5 px-3 text-[var(--text-muted)]">{e.resource_type}</td>
                      <td className="py-1.5 px-3">
                        <span className={e.decision === 'ALLOW' ? 'gex-badge gex-badge-green' : 'gex-badge gex-badge-red'}>{e.decision}</span>
                      </td>
                      <td className="py-1.5 px-3 text-[var(--text-muted)] max-w-[180px] truncate">{e.denial_reason || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* OT Gateways */}
          {gateways.length > 0 && (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
              <div className="border-b border-[var(--border)] px-5 py-3.5 flex items-center gap-2">
                <Wifi className="w-4 h-4 text-[var(--text-muted)]" />
                <h2 className="text-sm font-bold text-[var(--text-primary)]">OT Gateways</h2>
              </div>
              <div className="divide-y divide-[var(--border)]">
                {gateways.map((gw: any) => (
                  <div key={gw.gateway_id ?? gw.id} className="flex items-center gap-3 px-5 py-3">
                    {gw.status === 'ONLINE' ? <Wifi className="w-4 h-4 text-emerald-500 shrink-0" />
                     : gw.status === 'DEGRADED' ? <Radio className="w-4 h-4 text-amber-500 shrink-0" />
                     : <WifiOff className="w-4 h-4 text-red-500 shrink-0" />}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-[var(--text-primary)]">{gw.gateway_name ?? gw.project_id}</p>
                      <p className="text-xs text-[var(--text-muted)]">{gw.data_points_24h?.toLocaleString() ?? '—'} data points · {gw.integrity_failures ?? 0} integrity failures</p>
                    </div>
                    <StatusBadge status={gw.status ?? 'ONLINE'} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* TAB: WAE APPROVALS                                                    */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'wae' && (
        <div className="space-y-5">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
            <div className="border-b border-[var(--border)] px-5 py-3.5">
              <h2 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                <Workflow className="w-4 h-4 text-amber-500" /> Approval Queue — {info.name}
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                WAE requests initiated by {info.name} personnel. ABAC confirms WRITE access → WAE evaluates countersignature quorum.
              </p>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {approvals.length === 0 ? (
                <div className="flex items-center gap-2 px-5 py-4 text-sm text-[var(--text-muted)]">
                  <CheckCircle className="w-4 h-4 text-emerald-500" /> No approval requests
                </div>
              ) : approvals.map((req: any) => (
                <div key={req.request_id ?? req.id} className={`px-5 py-4 ${
                  (req.status === 'PENDING_APPROVAL' || req.status === 'ESCALATED')
                    ? 'bg-amber-50/40 dark:bg-amber-900/5' : ''
                }`}>
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-[var(--text-primary)]">
                          {(req.action_type ?? '').replace(/_/g, ' ')}
                        </span>
                        <StatusBadge status={req.status} />
                      </div>
                      <p className="text-xs text-[var(--text-muted)] mt-0.5">{req.payload?.description}</p>
                    </div>
                    <div className="text-right shrink-0">
                      {req.amount && (
                        <p className="text-sm font-bold text-[var(--text-primary)]">
                          €{Number(req.amount).toLocaleString()}
                        </p>
                      )}
                      <p className="text-[10px] text-[var(--text-muted)]">{req.project_id}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[10px]">
                    <div className="flex items-center gap-3">
                      <span className="text-[var(--text-muted)]">By: <span className="text-[var(--text-primary)] font-medium">{req.initiator_user_id}</span></span>
                      {(req.status === 'PENDING_APPROVAL') && req.expires_at && (
                        <span className="flex items-center gap-1 text-amber-600">
                          <Timer className="w-3 h-3" />
                          Expires {new Date(req.expires_at).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1 flex-wrap">
                      {Array.from({ length: req.approvals_received ?? 0 }).map((_, i) => (
                        <span key={i} className="gex-badge gex-badge-green text-[9px]">✓ Approved</span>
                      ))}
                      {(req.required_roles ?? []).slice(req.approvals_received ?? 0).map((r: string) => (
                        <span key={r} className="gex-badge gex-badge-amber text-[9px]">⏳ {r}</span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Policies table */}
          {policies.length > 0 && (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
              <div className="border-b border-[var(--border)] px-5 py-3.5">
                <h2 className="text-sm font-bold text-[var(--text-primary)]">Platform WAE Policies</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border)] text-[var(--text-muted)]">
                      {['Action Type', 'Threshold', 'Required Approvers', 'Escalation'].map(h => (
                        <th key={h} className="text-left py-2 px-4 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {policies.map((p: any) => (
                      <tr key={p.action_type} className="border-b border-[var(--border)]/40 hover:bg-[var(--surface-hover)]">
                        <td className="py-1.5 px-4 font-mono text-[10px] text-[var(--text-primary)]">{p.action_type}</td>
                        <td className="py-1.5 px-4 text-[var(--text-muted)]">{p.threshold_amount ? `> €${(p.threshold_amount / 1000).toFixed(0)}K` : 'Any'}</td>
                        <td className="py-1.5 px-4">
                          <div className="flex flex-wrap gap-0.5">
                            {(p.required_roles ?? []).map((r: string) => <span key={r} className="gex-badge gex-badge-default text-[9px]">{r}</span>)}
                          </div>
                        </td>
                        <td className="py-1.5 px-4 text-[var(--text-muted)]">{p.escalation_role ? `${p.escalation_role} (${p.escalation_timeout_hours}h)` : `${p.timeout_hours ?? 48}h`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* TAB: USERS & DESKS                                                    */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'users' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-[var(--text-primary)]">User Attributes & Desk Configuration</h2>
            <p className="text-xs text-[var(--text-muted)]">ABAC attributes + desk_id for info barrier enforcement (R7)</p>
          </div>
          {users.map((u: any) => (
            <div key={u.user_id ?? u.email} className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3.5">
                <div className="flex items-center gap-3">
                  <div className="h-9 w-9 rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center shrink-0">
                    <Users className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-[var(--text-primary)]">{u.name}</span>
                      {u.desk_id && <span className="gex-badge gex-badge-default text-[9px] font-mono">{u.desk_id}</span>}
                    </div>
                    <p className="text-xs text-[var(--text-muted)]">{u.email}</p>
                  </div>
                </div>
                <button
                  className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                    editingUser === (u.user_id ?? u.email)
                      ? 'bg-[var(--brand)] text-white border-[var(--brand)]'
                      : 'border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]'
                  }`}
                  onClick={() => {
                    if (editingUser === (u.user_id ?? u.email)) {
                      setEditingUser(null)
                    } else {
                      setEditingUser(u.user_id ?? u.email)
                      setEditForm({ role: u.role, clearance_level: u.clearance_level, desk_id: u.desk_id ?? '' })
                    }
                  }}
                >
                  {editingUser === (u.user_id ?? u.email)
                    ? <><Save className="w-3 h-3" /> Save</>
                    : <><Pencil className="w-3 h-3" /> Edit</>}
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3 px-5 pb-4 md:grid-cols-4">
                {/* Actor Type */}
                <div>
                  <p className="text-[10px] font-medium text-[var(--text-muted)] mb-1">Actor Type</p>
                  {editingUser === (u.user_id ?? u.email) ? (
                    <select
                      value={editForm.role}
                      onChange={e => setEditForm((f: any) => ({ ...f, role: e.target.value }))}
                      className="w-full h-7 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-[var(--text-primary)]"
                    >
                      {ACTOR_TYPES.map(at => <option key={at} value={at}>{at.replace(/_/g, ' ')}</option>)}
                    </select>
                  ) : (
                    <span className="gex-badge gex-badge-default">{(u.role ?? '').replace(/_/g, ' ')}</span>
                  )}
                </div>

                {/* Clearance */}
                <div>
                  <p className="text-[10px] font-medium text-[var(--text-muted)] mb-1">Clearance Level</p>
                  {editingUser === (u.user_id ?? u.email) ? (
                    <select
                      value={editForm.clearance_level}
                      onChange={e => setEditForm((f: any) => ({ ...f, clearance_level: e.target.value }))}
                      className="w-full h-7 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-[var(--text-primary)]"
                    >
                      {CLEARANCE_LEVELS.map(cl => <option key={cl} value={cl}>{cl}</option>)}
                    </select>
                  ) : (
                    <span className={`gex-badge ${u.clearance_level === 'RESTRICTED' ? 'gex-badge-red' : u.clearance_level === 'CONFIDENTIAL' ? 'gex-badge-amber' : 'gex-badge-default'}`}>
                      <Lock className="w-2.5 h-2.5 mr-1 inline" />{u.clearance_level ?? 'STANDARD'}
                    </span>
                  )}
                </div>

                {/* Desk ID */}
                <div>
                  <p className="text-[10px] font-medium text-[var(--text-muted)] mb-1">Desk ID (R7)</p>
                  {editingUser === (u.user_id ?? u.email) ? (
                    <select
                      value={editForm.desk_id}
                      onChange={e => setEditForm((f: any) => ({ ...f, desk_id: e.target.value }))}
                      className="w-full h-7 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-[var(--text-primary)]"
                    >
                      <option value="">No desk</option>
                      {DESK_SUFFIXES.map(d => {
                        const v = `${info.name.split(' ')[0].toUpperCase()}_${d}`
                        return <option key={v} value={v}>{v}</option>
                      })}
                    </select>
                  ) : (
                    <span className="gex-badge gex-badge-default font-mono">{u.desk_id || '—'}</span>
                  )}
                </div>

                {/* KYC */}
                <div>
                  <p className="text-[10px] font-medium text-[var(--text-muted)] mb-1">KYC / MFA</p>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className={u.kyc_status === 'VERIFIED' ? 'gex-badge gex-badge-green' : 'gex-badge gex-badge-amber'}>
                      {u.kyc_status ?? 'VERIFIED'}
                    </span>
                    {u.mfa_enabled
                      ? <span className="gex-badge gex-badge-green">MFA ✓</span>
                      : <span className="gex-badge gex-badge-red">No MFA</span>}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* TAB: SOD VIOLATIONS                                                   */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'sod' && (
        <div className="space-y-5">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
            <div className="border-b border-[var(--border)] px-5 py-3.5">
              <h2 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                <Ban className="w-4 h-4 text-red-500" /> SoD Violations — {info.name}
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">HTTP 409 returned on conflict. Initiator must be different from verifier for the same resource.</p>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {sodViolations.length === 0 ? (
                <div className="flex items-center gap-2 px-5 py-4">
                  <CheckCircle className="w-4 h-4 text-emerald-500" />
                  <span className="text-sm text-emerald-600 font-medium">No SoD violations for {info.name}</span>
                </div>
              ) : sodViolations.map((v: any) => (
                <div key={v.id} className={`px-5 py-4 ${v.resolution === 'BLOCKED' ? 'bg-red-50/40 dark:bg-red-900/5' : ''}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="gex-badge gex-badge-default font-mono text-[9px]">{v.conflict_pair_id}</span>
                        <span className="text-sm font-medium text-[var(--text-primary)]">{v.user_name}</span>
                        <StatusBadge status={v.resolution} />
                      </div>
                      <p className="text-xs text-[var(--text-muted)] mt-1">
                        Prior: <span className="font-mono">{v.action_performed}</span> → Blocked: <span className="font-mono">{v.blocked_action}</span>
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">Project: {v.project_name}</p>
                    </div>
                    <span className="text-[10px] text-[var(--text-muted)] shrink-0">
                      {new Date(v.timestamp).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Active SoD pairs from engine */}
          {sodPairs.length > 0 && (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
              <div className="border-b border-[var(--border)] px-5 py-3.5">
                <h2 className="text-sm font-bold text-[var(--text-primary)]">Active Conflict Pairs</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border)] text-[var(--text-muted)]">
                      {['ID', 'Action A', 'Action B', 'Scope', 'Description'].map(h => (
                        <th key={h} className="text-left py-2 px-4 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sodPairs.map((p: any) => (
                      <tr key={p.id} className="border-b border-[var(--border)]/40 hover:bg-[var(--surface-hover)]">
                        <td className="py-1.5 px-4 font-mono text-[10px]">{p.id}</td>
                        <td className="py-1.5 px-4 font-mono text-[10px]">{p.action_a}</td>
                        <td className="py-1.5 px-4 font-mono text-[10px]">{p.action_b}</td>
                        <td className="py-1.5 px-4"><span className="gex-badge gex-badge-default">{p.resource_scope}</span></td>
                        <td className="py-1.5 px-4 text-[var(--text-muted)]">{p.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* TAB: INFORMATION BARRIERS                                             */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'barriers' && (
        <div className="space-y-5">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3.5">
              <div>
                <h2 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                  <Columns className="w-4 h-4 text-amber-500" /> Information Barriers — {info.name}
                </h2>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">Desk-level Chinese Walls via ABAC Rule R7. Not NDA — these isolate desks within {info.name}.</p>
              </div>
              <button
                onClick={() => setShowBarrierForm(v => !v)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-[var(--brand)] text-white hover:opacity-90 transition-opacity"
              >
                <Plus className="w-3 h-3" /> New Barrier
              </button>
            </div>

            {/* Create form */}
            {showBarrierForm && (
              <div className="px-5 py-4 border-b border-[var(--border)] bg-[var(--surface-hover)] space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-[10px] font-medium text-[var(--text-muted)] mb-1">Side A (Desk)</p>
                    <input className="w-full h-8 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-[var(--text-primary)]"
                      placeholder="e.g. BP_TRADING"
                      value={barrierForm.side_a}
                      onChange={e => setBarrierForm(f => ({ ...f, side_a: e.target.value }))} />
                  </div>
                  <div>
                    <p className="text-[10px] font-medium text-[var(--text-muted)] mb-1">Side B (Desk)</p>
                    <input className="w-full h-8 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-[var(--text-primary)]"
                      placeholder="e.g. BP_ORIGINATION"
                      value={barrierForm.side_b}
                      onChange={e => setBarrierForm(f => ({ ...f, side_b: e.target.value }))} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-[10px] font-medium text-[var(--text-muted)] mb-1">Barrier Type</p>
                    <select
                      value={barrierForm.barrier_type}
                      onChange={e => setBarrierForm(f => ({ ...f, barrier_type: e.target.value }))}
                      className="w-full h-8 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-[var(--text-primary)]"
                    >
                      {['HARD', 'SOFT', 'CHINESE_WALL'].map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div>
                    <p className="text-[10px] font-medium text-[var(--text-muted)] mb-1">Applies to Data</p>
                    <div className="flex flex-wrap gap-1">
                      {DATA_CATEGORIES.map(cat => (
                        <button key={cat}
                          onClick={() => setBarrierForm(f => ({
                            ...f,
                            applies_to_data: f.applies_to_data.includes(cat)
                              ? f.applies_to_data.filter((c: string) => c !== cat)
                              : [...f.applies_to_data, cat]
                          }))}
                          className={`text-[9px] px-2 py-0.5 rounded border transition-colors ${
                            barrierForm.applies_to_data.includes(cat)
                              ? 'bg-[var(--brand)] text-white border-[var(--brand)]'
                              : 'border-[var(--border)] text-[var(--text-muted)]'
                          }`}
                        >{cat}</button>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={async () => {
                      try {
                        const r = await apiCall('/ciso/barriers', companyId, { method: 'POST', body: JSON.stringify(barrierForm) })
                        if (r.barrier) setBarriers(prev => [...prev, r.barrier])
                      } catch { setBarriers(prev => [...prev, { id: `ib-new-${Date.now()}`, ...barrierForm, company_id: companyId, active: true, created_at: new Date().toISOString(), recent_violations: [] }]) }
                      setShowBarrierForm(false)
                      setBarrierForm({ side_a: '', side_b: '', barrier_type: 'HARD', applies_to_data: [], description: '' })
                    }}
                    className="px-4 py-1.5 text-xs bg-[var(--brand)] text-white rounded-lg hover:opacity-90"
                  >Create</button>
                  <button onClick={() => setShowBarrierForm(false)} className="px-4 py-1.5 text-xs border border-[var(--border)] rounded-lg text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">Cancel</button>
                </div>
              </div>
            )}

            <div className="divide-y divide-[var(--border)]">
              {barriers.map((b: any) => (
                <div key={b.id}>
                  <div
                    className="flex items-center justify-between px-5 py-4 cursor-pointer hover:bg-[var(--surface-hover)]"
                    onClick={() => setExpandedItem(expandedItem === b.id ? null : b.id)}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className={`gex-badge ${b.barrier_type === 'HARD' || b.barrier_type === 'CHINESE_WALL' ? 'gex-badge-red' : 'gex-badge-amber'}`}>
                        {b.barrier_type}
                      </span>
                      <span className="text-sm font-mono font-semibold text-[var(--text-primary)]">{b.side_a ?? b.deskA}</span>
                      <span className="text-xs text-[var(--text-muted)]">⇔</span>
                      <span className="text-sm font-mono font-semibold text-[var(--text-primary)]">{b.side_b ?? b.deskB}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={b.active ? 'gex-badge gex-badge-green' : 'gex-badge gex-badge-default'}>{b.active ? 'Active' : 'Inactive'}</span>
                      {expandedItem === b.id ? <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />}
                    </div>
                  </div>
                  {expandedItem === b.id && (
                    <div className="bg-[var(--surface-hover)] border-t border-[var(--border)] px-5 py-3 space-y-2">
                      <p className="text-xs text-[var(--text-muted)]">{b.description || 'No description'}</p>
                      <div className="flex flex-wrap gap-1">
                        {(b.applies_to_data ?? []).map((d: string) => <span key={d} className="gex-badge gex-badge-default text-[9px]">{d}</span>)}
                      </div>
                      {(b.recent_violations?.length ?? 0) > 0 && (
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-wide text-red-600 mb-1">Recent violations</p>
                          {b.recent_violations.map((v: any, i: number) => (
                            <div key={i} className="flex items-center gap-3 text-[10px] text-[var(--text-muted)]">
                              <Ban className="w-3 h-3 text-red-500 shrink-0" />
                              <span>{v.user}</span>
                              <span className="font-mono">{v.action}</span>
                              <span>{new Date(v.ts).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* TAB: DATA RESIDENCY                                                   */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'residency' && (
        <div className="space-y-5">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
            <div className="border-b border-[var(--border)] px-5 py-3.5">
              <h2 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                <MapPin className="w-4 h-4 text-[var(--brand)]" /> Data Residency Policies — {info.name}
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                DRPL governs WHERE data is stored. HTTP 451 on violation. AUDIT_LOG + COMMS_METADATA are always EU (locked).
              </p>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {residency.map((p: any) => (
                <div key={p.id} className="flex items-center justify-between px-5 py-3.5">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="gex-badge gex-badge-default font-mono text-[9px] shrink-0">{p.data_category}</span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-[var(--text-primary)]">Required: <strong>{p.required_jurisdiction}</strong></span>
                        {(p.locked || ALWAYS_EU.has(p.data_category)) && (
                          <Lock className="w-3 h-3 text-[var(--text-muted)]" title="Locked — always EU" />
                        )}
                      </div>
                      <p className="text-xs text-[var(--text-muted)]">Stored: {p.storage_zone}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {!ALWAYS_EU.has(p.data_category) && resEditingId === p.id ? (
                      <>
                        <select
                          value={resEditForm.required_jurisdiction ?? p.required_jurisdiction}
                          onChange={e => setResEditForm((f: any) => ({ ...f, required_jurisdiction: e.target.value }))}
                          className="h-7 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-1 text-[var(--text-primary)]"
                        >
                          {['EU', 'GB', 'CH', 'US'].map(j => <option key={j} value={j}>{j}</option>)}
                        </select>
                        <button
                          className="flex items-center gap-1 px-2 py-1 text-[10px] bg-[var(--brand)] text-white rounded"
                          onClick={async () => {
                            try {
                              await apiCall('/ciso/residency/policies', companyId, { method: 'POST', body: JSON.stringify({ data_category: p.data_category, required_jurisdiction: resEditForm.required_jurisdiction ?? p.required_jurisdiction, storage_zone: p.storage_zone }) })
                              setResidency(prev => prev.map((x: any) => x.id === p.id ? { ...x, required_jurisdiction: resEditForm.required_jurisdiction ?? p.required_jurisdiction } : x))
                            } catch { /* ignore in demo */ }
                            setResEditingId(null)
                          }}
                        ><Save className="w-3 h-3" /></button>
                        <button className="text-[var(--text-muted)] hover:text-[var(--text-primary)]" onClick={() => setResEditingId(null)}><XCircle className="w-3.5 h-3.5" /></button>
                      </>
                    ) : (
                      <>
                        <StatusBadge status={p.status ?? 'COMPLIANT'} />
                        {!ALWAYS_EU.has(p.data_category) && (
                          <button
                            className="text-[var(--text-muted)] hover:text-[var(--brand)]"
                            onClick={() => { setResEditingId(p.id); setResEditForm({ required_jurisdiction: p.required_jurisdiction }) }}
                          ><Pencil className="w-3.5 h-3.5" /></button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Residency audit */}
          {resAudit.length > 0 && (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
              <div className="border-b border-[var(--border)] px-5 py-3.5">
                <h2 className="text-sm font-bold text-[var(--text-primary)]">Residency Check Audit</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border)] text-[var(--text-muted)]">
                      {['Category', 'Zone', 'Outcome', 'Reason', 'Time'].map(h => (
                        <th key={h} className="text-left py-2 px-4 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {resAudit.slice(0, 15).map((e: any, i: number) => (
                      <tr key={e.id ?? i} className="border-b border-[var(--border)]/40 hover:bg-[var(--surface-hover)]">
                        <td className="py-1.5 px-4 font-mono text-[10px]">{e.data_category}</td>
                        <td className="py-1.5 px-4 text-[var(--text-muted)]">{e.requested_zone}</td>
                        <td className="py-1.5 px-4"><StatusBadge status={e.outcome} /></td>
                        <td className="py-1.5 px-4 text-[var(--text-muted)] max-w-[200px] truncate">{e.reason || '—'}</td>
                        <td className="py-1.5 px-4 text-[var(--text-muted)] whitespace-nowrap">{new Date(e.checked_at).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* TAB: COMMITMENTS (CSS)                                                */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'commitments' && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
            <div className="border-b border-[var(--border)] px-5 py-3.5">
              <h2 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                <Fingerprint className="w-4 h-4 text-[var(--brand)]" /> Commitment Records — {info.name}
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">Non-repudiation records (eIDAS 910/2014). {info.name} as initiator or counterparty. Append-only — no deletion permitted.</p>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {commitments.length === 0 ? (
                <p className="px-5 py-4 text-sm text-[var(--text-muted)]">No commitment records for {info.name}</p>
              ) : commitments.map((c: any) => (
                <div key={c.commitment_id ?? c.id} className="px-5 py-4">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <FileSignature className="w-4 h-4 text-[var(--brand)]" />
                        <span className="text-sm font-semibold text-[var(--text-primary)]">
                          {(c.action_type ?? '').replace(/_/g, ' ')}
                        </span>
                        <StatusBadge status={c.status} />
                      </div>
                      <p className="text-xs text-[var(--text-muted)] mt-0.5">{c.project_name ?? c.project_id}</p>
                    </div>
                    <p className="text-[9px] text-[var(--text-muted)] font-mono shrink-0">{(c.commitment_id ?? c.id ?? '').slice(0, 12)}…</p>
                  </div>

                  {/* Signature chain */}
                  <div className="space-y-2">
                    {[c.initiator].filter(Boolean).map((party: any, i: number) => (
                      <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--surface-hover)]">
                        <div className={`h-5 w-5 rounded-full flex items-center justify-center shrink-0 ${party.signed ? 'bg-emerald-100 text-emerald-700' : 'bg-[var(--border)] text-[var(--text-muted)]'}`}>
                          {party.signed ? <CheckCircle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-[10px] font-medium text-[var(--text-primary)]">Initiator: {party.userName ?? party.user}</span>
                          {party.companyName && <span className="text-[9px] text-[var(--text-muted)] ml-1.5">({party.companyName})</span>}
                        </div>
                        {party.timestamp && <span className="text-[9px] text-[var(--text-muted)] shrink-0">{new Date(party.timestamp).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>}
                      </div>
                    ))}
                    {(c.approvers ?? []).map((a: any, i: number) => (
                      <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--surface-hover)]">
                        <div className={`h-5 w-5 rounded-full flex items-center justify-center shrink-0 ${a.signed ? 'bg-emerald-100 text-emerald-700' : 'bg-[var(--border)] text-[var(--text-muted)]'}`}>
                          {a.signed ? <CheckCircle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                        </div>
                        <span className="flex-1 text-[10px] font-medium text-[var(--text-primary)]">
                          Approver ({a.role}): {a.userName ?? a.user}
                        </span>
                        {a.timestamp && <span className="text-[9px] text-[var(--text-muted)] shrink-0">{new Date(a.timestamp).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>}
                      </div>
                    ))}
                    {c.counterparty ? (
                      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--surface-hover)]">
                        <div className={`h-5 w-5 rounded-full flex items-center justify-center shrink-0 ${c.counterparty.signed ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                          {c.counterparty.signed ? <CheckCircle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-[10px] font-medium text-[var(--text-primary)]">Counterparty: {c.counterparty.userName ?? c.counterparty.user}</span>
                          {c.counterparty.companyName && <span className="text-[9px] text-[var(--text-muted)] ml-1.5">({c.counterparty.companyName})</span>}
                        </div>
                        {c.counterparty.timestamp && <span className="text-[9px] text-[var(--text-muted)] shrink-0">{new Date(c.counterparty.timestamp).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>}
                      </div>
                    ) : c.status === 'PENDING_COUNTERSIGN' && (
                      <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-900/10">
                        <Clock className="w-4 h-4 text-amber-500 shrink-0" />
                        <span className="text-[10px] text-amber-700 dark:text-amber-400 font-medium">Awaiting counterparty signature</span>
                      </div>
                    )}
                  </div>

                  {/* Hashes */}
                  <div className="flex items-center gap-4 mt-3 pt-2 border-t border-[var(--border)]/40">
                    {[['Payload', c.payloadHash ?? c.payload_hash], ['Record', c.recordHash ?? c.record_hash]].filter(([, v]) => v).map(([label, hash]) => (
                      <div key={label as string} className="flex items-center gap-1">
                        <Hash className="w-3 h-3 text-[var(--text-muted)]" />
                        <span className="text-[9px] text-[var(--text-muted)] font-mono">{label}: {String(hash).slice(0, 16)}…</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* TAB: COMPLIANCE                                                        */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'compliance' && (
        <div className="space-y-5">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
            <div className="border-b border-[var(--border)] px-5 py-3.5">
              <h2 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                <FileCheck className="w-4 h-4 text-[var(--brand)]" /> Compliance Posture — {info.name}
              </h2>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {[
                { standard: 'ISO 27001', status: info.iso27001 ? 'CERTIFIED' : 'IN_PROGRESS', detail: info.iso27001 ? 'Annual audit passed · Certificate valid' : 'Gap analysis in progress' },
                { standard: 'GDPR / EU Data Act', status: 'COMPLIANT', detail: 'Data residency policies active · DPA on file' },
                { standard: 'eIDAS 910/2014', status: 'COMPLIANT', detail: 'Commitment records use HMAC-SHA256 (dev) · RSA-2048 in Tier 4' },
                { standard: 'NIS2 Directive', status: 'IN_PROGRESS', detail: 'OT boundary rules active · Incident response policy pending' },
                { standard: 'MiCA (Tokenisation)', status: 'PENDING_REVIEW', detail: 'Applicable when carbon tokens are issued under EU securities framework' },
              ].map(item => (
                <div key={item.standard} className="flex items-center justify-between px-5 py-3.5">
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">{item.standard}</p>
                    <p className="text-xs text-[var(--text-muted)]">{item.detail}</p>
                  </div>
                  <StatusBadge status={item.status} />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* TAB: CONFIG                                                           */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'config' && (
        <div className="space-y-5">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
            <div className="border-b border-[var(--border)] px-5 py-3.5">
              <h2 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                <Settings className="w-4 h-4 text-[var(--text-muted)]" /> Security Configuration — {info.name}
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">Read-only until JWT CISO role authentication is deployed (Phase 2A).</p>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {[
                { key: 'Company ID',         value: companyId },
                { key: 'CISO Contact',        value: info.ciso },
                { key: 'Primary Jurisdiction', value: info.jurisdiction },
                { key: 'ISO 27001',           value: info.iso27001 ? 'Certified' : 'In progress' },
                { key: 'Active Projects',     value: info.projects.length ? info.projects.join(', ') : '—' },
                { key: 'WAE Approval Mode',   value: 'QUORUM (platform-wide policies)' },
                { key: 'CSS Algorithm (dev)', value: 'HMAC-SHA256' },
                { key: 'CSS Algorithm (Tier 4)', value: 'RSA-2048 / Ed25519 via HSM/QTSP' },
                { key: 'DRPL Mode',           value: 'ENFORCE (HTTP 451 on block)' },
                { key: 'Audit Log Retention', value: '7 years (ALWAYS_EU locked)' },
              ].map(({ key, value }) => (
                <div key={key} className="flex items-center justify-between px-5 py-3 text-sm">
                  <span className="text-[var(--text-muted)]">{key}</span>
                  <span className="font-medium text-[var(--text-primary)] font-mono text-xs">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
