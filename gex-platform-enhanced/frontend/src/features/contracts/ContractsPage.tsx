// Screen: Contracts screen (/contracts)
import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, FileText, Filter, RefreshCw } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { contractsAPI } from '@/lib/api'
import { CUSTOMER_PROJECTS, type CustomerProject } from '@/data/customerProjects'
import { type UserRole, useUserRole } from '@/contexts/UserRoleContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'

type StatusGroup = 'pending_signature' | 'signed' | 'archived'
type StatusFilter = 'all' | Exclude<StatusGroup, 'archived'>
type AgreementType = 'Purchase' | 'Sale'
type AgreementFilter = 'all' | AgreementType
type IssueLevel = 'high' | 'medium' | 'low'
type CreditTone = 'strong' | 'watch' | 'weak' | 'missing'

interface RawContract {
  id: string
  project_id?: string
  project_name?: string
  project?: string
  contract_id_external?: string
  counterparty?: string
  buyer?: string
  seller?: string
  molecule?: string
  product?: string
  volume_mtpd?: number
  volume?: number
  volume_mt?: number
  price_eur_kg?: number
  price?: number
  pricing_basis?: string
  start_date?: string
  end_date?: string
  tenor_years?: number
  credit_rating?: string
  status?: string
}

interface ContractIssue {
  label: string
  level: IssueLevel
}

interface AgreementInference {
  type: AgreementType
  source: 'owner-linked' | 'associated-linked' | 'counterparty-linked' | 'role-inferred'
}

interface ContractView {
  id: string
  externalId: string
  projectName: string
  counterparty: string
  molecule: string
  volumeMtpd: number
  priceEurKg: number | null
  pricingBasis: string
  startDate: string
  endDate: string
  tenorYears: number | null
  creditRating: string
  status: string
  statusGroup: Exclude<StatusGroup, 'archived'>
  agreementType: AgreementType
  inferenceSource: AgreementInference['source']
  qualitySummary: string
  originPrimary: string
  originSecondary: string
  scopeLabel: string
  linkedProject: CustomerProject | null
  issues: ContractIssue[]
  highestIssue: IssueLevel | null
}

const QUALITY_BASELINE: Record<string, string> = {
  H2: 'RFNBO / 99.97% purity target',
  NH3: 'Low-carbon ammonia / terminal controls',
  'e-Methanol': 'ISCC-aligned marine fuel quality',
  SAF: 'ASTM D7566 compliance path',
  'e-NG': 'Grid-spec methane / GoO traceability',
  'e-Methane': 'Grid-spec methane / GoO traceability',
  'e-NH3': 'Low-carbon ammonia / terminal controls',
  HVO: 'Drop-in diesel quality',
  'e-Gasoline': 'Synthetic gasoline blend quality',
  'e-LG': 'Liquefied gas spec to confirm',
  'e-Naphtha': 'Petrochemical feedstock spec to confirm',
}

const STATUS_TONE: Record<Exclude<StatusGroup, 'archived'>, string> = {
  pending_signature: 'bg-amber-50 text-amber-700 border-amber-200',
  signed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

const ISSUE_TONE: Record<IssueLevel, string> = {
  high: 'bg-red-50 text-red-700 border-red-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-slate-100 text-slate-600 border-slate-200',
}

const TYPE_TONE: Record<AgreementType, string> = {
  Purchase: 'bg-blue-50 text-blue-700 border-blue-200',
  Sale: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

const ISSUE_RANK: Record<IssueLevel, number> = {
  high: 0,
  medium: 1,
  low: 2,
}

function normalizeKey(value?: string | null): string {
  return (value ?? '').trim().toLowerCase().replace(/[^a-z0-9]+/g, ' ')
}

function humanize(value?: string | null): string {
  if (!value) return 'Not captured'
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

const PROJECTS_BY_ID = new Map<string, CustomerProject>(
  CUSTOMER_PROJECTS.map(project => [project.id, project]),
)

const PROJECTS_BY_NAME = new Map<string, CustomerProject>(
  CUSTOMER_PROJECTS.map(project => [normalizeKey(project.name), project]),
)

function toStatusGroup(status?: string): StatusGroup {
  const value = (status ?? '').trim().toLowerCase()

  if (!value) return 'pending_signature'
  if (['active', 'executed', 'delivering', 'signed'].includes(value)) return 'signed'
  if (['expired', 'terminated', 'cancelled', 'canceled', 'rejected'].includes(value)) return 'archived'
  return 'pending_signature'
}

function prettyStatus(status?: string): string {
  if (!status) return 'Pending signature'
  return humanize(status)
}

function extractContracts(payload: unknown): RawContract[] {
  if (Array.isArray(payload)) return payload as RawContract[]
  if (!payload || typeof payload !== 'object') return []

  const candidate = payload as { contracts?: unknown; data?: unknown }

  if (Array.isArray(candidate.contracts)) return candidate.contracts as RawContract[]
  if (Array.isArray(candidate.data)) return candidate.data as RawContract[]
  return []
}

function linkProject(contract: RawContract): CustomerProject | null {
  if (contract.project_id && PROJECTS_BY_ID.has(contract.project_id)) {
    return PROJECTS_BY_ID.get(contract.project_id) ?? null
  }

  const byName = PROJECTS_BY_NAME.get(normalizeKey(contract.project_name ?? contract.project))
  return byName ?? null
}

function getCreditTone(rating?: string): CreditTone {
  const value = (rating ?? '').trim().toUpperCase()
  if (!value) return 'missing'
  if (value.startsWith('AAA') || value.startsWith('AA') || value.startsWith('A')) return 'strong'
  if (value.startsWith('BBB')) return 'watch'
  return 'weak'
}

function getCreditClasses(tone: CreditTone): string {
  switch (tone) {
    case 'strong':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200'
    case 'watch':
      return 'bg-amber-50 text-amber-700 border-amber-200'
    case 'weak':
      return 'bg-red-50 text-red-700 border-red-200'
    default:
      return 'bg-slate-100 text-slate-600 border-slate-200'
  }
}

function getCreditDescriptor(tone: CreditTone): string {
  switch (tone) {
    case 'strong':
      return 'Investment grade'
    case 'watch':
      return 'BBB band'
    case 'weak':
      return 'Below investment grade'
    default:
      return 'Not captured'
  }
}

function pushIssue(issues: ContractIssue[], label: string | undefined, level: IssueLevel) {
  if (!label) return
  if (!issues.some(issue => issue.label === label)) {
    issues.push({ label, level })
  }
}

function deriveQuality(contract: RawContract, linkedProject: CustomerProject | null): {
  summary: string
  issues: ContractIssue[]
} {
  const molecule = contract.molecule ?? contract.product ?? 'Unknown'
  const base = QUALITY_BASELINE[molecule] ?? `${molecule} quality to be confirmed`
  const issues: ContractIssue[] = []
  const gating = linkedProject?.molecule_gating
  let summary = base

  if (molecule === 'NH3' || molecule === 'e-NH3') {
    if (gating?.hazop_completed === false) pushIssue(issues, 'HAZOP sign-off still open', 'high')
    if (gating?.seveso_tier === 'PENDING') pushIssue(issues, 'Seveso / COMAH classification pending', 'medium')
    if (gating?.terminal_interface_signed === false) {
      pushIssue(issues, 'Terminal interface agreement not signed', 'medium')
      summary = `${base} · terminal interface open`
    }
  }

  if (molecule === 'SAF') {
    if (gating?.process_hazard_review === false) pushIssue(issues, 'Process hazard review incomplete', 'high')
    if (gating?.astm_cert_status === 'IN_PROGRESS') {
      pushIssue(issues, 'ASTM D7566 certification still in progress', 'medium')
      summary = `${base} · ASTM in progress`
    }
  }

  if (gating?.molecule_insurance_placed === false) pushIssue(issues, 'Molecule-specific insurance still open', 'low')

  return { summary, issues }
}

function deriveAgreementType(
  contract: RawContract,
  linkedProject: CustomerProject | null,
  role: UserRole,
): AgreementInference {
  const capabilities = new Set(role.capabilities ?? [])
  const canBuy = role.company_type === 'OFFTAKER' || capabilities.has('OFFTAKE')
  const canSell = role.company_type === 'PRODUCER' || capabilities.has('PRODUCE') || capabilities.has('SELL')

  if (linkedProject?.owner_company === role.company_name) {
    return { type: 'Sale', source: 'owner-linked' }
  }

  if (linkedProject?.associated_companies.includes(role.company_name)) {
    if (canBuy) return { type: 'Purchase', source: 'associated-linked' }
    return { type: 'Sale', source: 'associated-linked' }
  }

  if (normalizeKey(contract.counterparty) === normalizeKey(role.company_name)) {
    return { type: 'Purchase', source: 'counterparty-linked' }
  }

  if (canBuy && !canSell) return { type: 'Purchase', source: 'role-inferred' }
  if (canSell && !canBuy) return { type: 'Sale', source: 'role-inferred' }

  return {
    type: role.company_type === 'OFFTAKER' ? 'Purchase' : 'Sale',
    source: 'role-inferred',
  }
}

function getScopeLabel(
  linkedProject: CustomerProject | null,
  visibleProjectIds: Set<string>,
  role: UserRole,
): string {
  if (!linkedProject) return 'Contract registry only'
  if (linkedProject.owner_company === role.company_name) return 'Owned portfolio'
  if (visibleProjectIds.has(linkedProject.id)) return 'Shared portfolio'
  return 'Registry linked'
}

function deriveIssues(
  contract: RawContract,
  linkedProject: CustomerProject | null,
  statusGroup: Exclude<StatusGroup, 'archived'>,
  qualityIssues: ContractIssue[],
): ContractIssue[] {
  const issues: ContractIssue[] = [...qualityIssues]

  if (statusGroup === 'pending_signature') {
    pushIssue(issues, 'Awaiting final signature', 'high')
  }

  if (!(contract.credit_rating ?? '').trim()) {
    pushIssue(issues, 'Counterparty credit quality not captured', 'medium')
  } else if (getCreditTone(contract.credit_rating) === 'weak') {
    pushIssue(issues, `Counterparty credit below investment grade (${contract.credit_rating})`, 'high')
  }

  if (!(contract.pricing_basis ?? '').trim()) {
    pushIssue(issues, 'Pricing basis missing', 'medium')
  }

  if ((contract.tenor_years ?? 0) > 0 && (contract.tenor_years ?? 0) < 5) {
    pushIssue(issues, 'Short tenor for financing visibility', 'medium')
  }

  if (linkedProject) {
    if (
      contract.start_date &&
      linkedProject.completion_date &&
      contract.start_date < linkedProject.completion_date
    ) {
      pushIssue(issues, 'Start date precedes project completion date', 'high')
    }

    const volumeMtpd = contract.volume_mtpd ?? contract.volume ?? contract.volume_mt ?? 0
    if (linkedProject.capacity_mtpd > 0 && volumeMtpd > linkedProject.capacity_mtpd) {
      pushIssue(issues, 'Contracted volume exceeds registered project capacity', 'high')
    }

    for (const risk of linkedProject.bankability.risk_alerts.slice(0, 2)) {
      pushIssue(issues, risk, 'medium')
    }

    const offtakeGate = linkedProject.bankability.gates.find(
      gate => gate.id === 'G4_OFFTAKE_BANKABLE' && !gate.is_complete,
    )
    if (offtakeGate?.blocking_items.length) {
      pushIssue(issues, `${offtakeGate.name}: ${humanize(offtakeGate.blocking_items[0])}`, 'medium')
    }
  } else {
    pushIssue(issues, 'Project link missing in canonical registry', 'low')
  }

  return issues.sort((left, right) => ISSUE_RANK[left.level] - ISSUE_RANK[right.level])
}

function highestIssue(issues: ContractIssue[]): IssueLevel | null {
  return issues[0]?.level ?? null
}

function formatDate(value: string): string {
  if (!value || value === '—') return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date)
}

function formatVolume(value: number): string {
  return `${value.toLocaleString(undefined, {
    minimumFractionDigits: value % 1 === 0 ? 0 : 1,
    maximumFractionDigits: 1,
  })} MTPD`
}

function formatPrice(value: number | null): string {
  if (value === null) return '—'
  return `EUR ${value.toFixed(2)}/kg`
}

function describeInference(source: AgreementInference['source']): string {
  switch (source) {
    case 'owner-linked':
      return 'owned project'
    case 'associated-linked':
      return 'shared project'
    case 'counterparty-linked':
      return 'counterparty linked'
    default:
      return 'role inferred'
  }
}

function getPerspectiveCopy(role: UserRole): string {
  switch (role.business_function) {
    case 'COMMERCIAL':
      return 'Negotiation maturity, pricing and counterparty readiness remain visible until signature.'
    case 'FINANCE_TREASURY':
      return 'Tenor, credit quality and unresolved blockers stay in view for financing decisions.'
    case 'COMPLIANCE_LEGAL':
      return 'Signature status, origin traceability and open legal blockers remain visible.'
    default:
      return 'Pending and signed agreements bridge commercial execution into finance and settlement.'
  }
}

export function ContractsPage() {
  const { role } = useUserRole()
  const { projects: visibleProjects } = useVisibleProjects()
  const [searchParams] = useSearchParams()
  const initialSearch = [searchParams.get('project'), searchParams.get('counterparty')]
    .filter((value): value is string => Boolean(value))
    .join(' ')

  const [contracts, setContracts] = useState<RawContract[]>([])
  const [loading, setLoading] = useState(true)
  const [filterStatus, setFilterStatus] = useState<StatusFilter>('all')
  const [filterType, setFilterType] = useState<AgreementFilter>('all')
  const [filterMolecule, setFilterMolecule] = useState(searchParams.get('molecule') ?? 'all')
  const [searchTerm, setSearchTerm] = useState(initialSearch)
  const [issuesOnly, setIssuesOnly] = useState(false)

  useEffect(() => {
    void loadContracts()
  }, [])

  const visibleProjectIds = useMemo(
    () => new Set(visibleProjects.map(project => project.id)),
    [visibleProjects],
  )

  async function loadContracts() {
    setLoading(true)
    try {
      const response = await contractsAPI.list()
      setContracts(extractContracts(response))
    } catch (error) {
      console.error('Failed to load contracts:', error)
      setContracts([])
    } finally {
      setLoading(false)
    }
  }

  const normalizedContracts = useMemo<ContractView[]>(() => {
    return contracts
      .map(contract => {
        const statusGroup = toStatusGroup(contract.status)
        if (statusGroup === 'archived') return null
        const activeStatusGroup: Exclude<StatusGroup, 'archived'> = statusGroup

        const linkedProject = linkProject(contract)
        const agreement = deriveAgreementType(contract, linkedProject, role)
        const { summary: qualitySummary, issues: qualityIssues } = deriveQuality(contract, linkedProject)
        const issues = deriveIssues(contract, linkedProject, activeStatusGroup, qualityIssues)
        const volumeMtpd = contract.volume_mtpd ?? contract.volume ?? contract.volume_mt ?? 0
        const priceEurKg = contract.price_eur_kg ?? contract.price ?? null

        return {
          id: contract.id,
          externalId: contract.contract_id_external ?? contract.id,
          projectName: linkedProject?.name ?? contract.project_name ?? contract.project ?? 'Project not linked',
          counterparty: contract.counterparty ?? contract.buyer ?? contract.seller ?? 'Counterparty not captured',
          molecule: contract.molecule ?? contract.product ?? 'Unknown',
          volumeMtpd,
          priceEurKg,
          pricingBasis: contract.pricing_basis ?? 'Pricing basis not captured',
          startDate: contract.start_date ?? '—',
          endDate: contract.end_date ?? '—',
          tenorYears: contract.tenor_years ?? null,
          creditRating: contract.credit_rating ?? '',
          status: contract.status ?? '',
          statusGroup: activeStatusGroup,
          agreementType: agreement.type,
          inferenceSource: agreement.source,
          qualitySummary,
          originPrimary: linkedProject?.location ?? 'Origin not mapped',
          originSecondary: linkedProject?.owner_company ?? contract.project_name ?? contract.project_id ?? 'Project registry link missing',
          scopeLabel: getScopeLabel(linkedProject, visibleProjectIds, role),
          linkedProject,
          issues,
          highestIssue: highestIssue(issues),
        }
      })
      .filter((contract): contract is ContractView => contract !== null)
  }, [contracts, role, visibleProjectIds])

  const molecules = useMemo(
    () => Array.from(new Set(normalizedContracts.map(contract => contract.molecule))).sort(),
    [normalizedContracts],
  )

  const filteredContracts = useMemo(() => {
    const search = searchTerm.trim().toLowerCase()

    return normalizedContracts.filter(contract => {
      if (filterStatus !== 'all' && contract.statusGroup !== filterStatus) return false
      if (filterType !== 'all' && contract.agreementType !== filterType) return false
      if (filterMolecule !== 'all' && contract.molecule !== filterMolecule) return false
      if (issuesOnly && contract.issues.length === 0) return false

      if (!search) return true

      const searchable = [
        contract.externalId,
        contract.projectName,
        contract.counterparty,
        contract.molecule,
        contract.originPrimary,
        contract.agreementType,
        contract.status,
      ]
        .join(' ')
        .toLowerCase()

      return searchable.includes(search)
    })
  }, [filterMolecule, filterStatus, filterType, issuesOnly, normalizedContracts, searchTerm])

  const portfolio = useMemo(() => {
    const totalVolume = filteredContracts.reduce((sum, contract) => sum + contract.volumeMtpd, 0)
    const weightedPriceValue = filteredContracts.reduce((sum, contract) => {
      if (contract.priceEurKg === null) return sum
      return sum + contract.priceEurKg * contract.volumeMtpd
    }, 0)
    const tenorSum = filteredContracts.reduce((sum, contract) => sum + (contract.tenorYears ?? 0), 0)
    const tenorCount = filteredContracts.filter(contract => contract.tenorYears !== null).length

    return {
      agreements: filteredContracts.length,
      pending: filteredContracts.filter(contract => contract.statusGroup === 'pending_signature').length,
      signed: filteredContracts.filter(contract => contract.statusGroup === 'signed').length,
      purchaseVolume: filteredContracts
        .filter(contract => contract.agreementType === 'Purchase')
        .reduce((sum, contract) => sum + contract.volumeMtpd, 0),
      salesVolume: filteredContracts
        .filter(contract => contract.agreementType === 'Sale')
        .reduce((sum, contract) => sum + contract.volumeMtpd, 0),
      flagged: filteredContracts.filter(contract => contract.issues.length > 0).length,
      weightedPrice: totalVolume > 0 ? weightedPriceValue / totalVolume : null,
      avgTenor: tenorCount > 0 ? tenorSum / tenorCount : null,
    }
  }, [filteredContracts])

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Contracts</h1>
          <p className="mt-1 text-sm text-gray-600">
            Pending signature and signed purchase / sales agreements across commercial and finance.
          </p>
        </div>
        <button
          onClick={() => void loadContracts()}
          disabled={loading}
          className="rounded-lg p-2 hover:bg-gray-100"
          title="Refresh contracts"
        >
          <RefreshCw className={`h-5 w-5 text-gray-600 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-xs font-bold uppercase tracking-wide text-gray-500">
              Commercial → Finance Bridge
            </div>
            <p className="mt-1 text-sm text-gray-700">
              Perspective: <span className="font-semibold text-gray-900">{role.company_name}</span>{' '}
              · {humanize(role.company_type)} · {humanize(role.business_function)}. {getPerspectiveCopy(role)}
            </p>
            <p className="mt-2 text-xs text-gray-500">
              Agreement side resolves from owned projects first, then shared projects, then active trade role.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm text-gray-600 sm:grid-cols-4">
            <div>
              <div className="text-xs font-bold uppercase text-gray-500">Visible projects</div>
              <div className="mt-1 text-lg font-black text-gray-900">{visibleProjects.length}</div>
            </div>
            <div>
              <div className="text-xs font-bold uppercase text-gray-500">Weighted price</div>
              <div className="mt-1 text-lg font-black text-gray-900">
                {portfolio.weightedPrice === null ? '—' : `EUR ${portfolio.weightedPrice.toFixed(2)}`}
              </div>
            </div>
            <div>
              <div className="text-xs font-bold uppercase text-gray-500">Avg tenor</div>
              <div className="mt-1 text-lg font-black text-gray-900">
                {portfolio.avgTenor === null ? '—' : `${portfolio.avgTenor.toFixed(1)}y`}
              </div>
            </div>
            <div>
              <div className="text-xs font-bold uppercase text-gray-500">Registry linked</div>
              <div className="mt-1 text-lg font-black text-gray-900">
                {filteredContracts.filter(contract => contract.linkedProject).length}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-6">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-slate-500" />
            <div className="text-xs font-bold uppercase text-gray-500">Agreements</div>
          </div>
          <div className="mt-3 text-3xl font-black text-gray-900">{portfolio.agreements}</div>
        </div>

        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-600" />
            <div className="text-xs font-bold uppercase text-amber-700">Pending</div>
          </div>
          <div className="mt-3 text-3xl font-black text-amber-900">{portfolio.pending}</div>
        </div>

        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            <div className="text-xs font-bold uppercase text-emerald-700">Signed</div>
          </div>
          <div className="mt-3 text-3xl font-black text-emerald-900">{portfolio.signed}</div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs font-bold uppercase text-gray-500">Purchase position</div>
          <div className="mt-3 text-3xl font-black text-gray-900">{portfolio.purchaseVolume.toFixed(1)}</div>
          <div className="mt-1 text-xs text-gray-500">MTPD</div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs font-bold uppercase text-gray-500">Sales position</div>
          <div className="mt-3 text-3xl font-black text-gray-900">{portfolio.salesVolume.toFixed(1)}</div>
          <div className="mt-1 text-xs text-gray-500">MTPD</div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs font-bold uppercase text-gray-500">Flagged</div>
          <div className="mt-3 text-3xl font-black text-gray-900">{portfolio.flagged}</div>
          <div className="mt-1 text-xs text-gray-500">agreements with issues</div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white p-4">
        <Filter className="h-4 w-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search contract, project, counterparty..."
          value={searchTerm}
          onChange={event => setSearchTerm(event.target.value)}
          className="w-64 rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
        />
        <select
          value={filterType}
          onChange={event => setFilterType(event.target.value as AgreementFilter)}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="all">All agreement types</option>
          <option value="Purchase">Purchase</option>
          <option value="Sale">Sale</option>
        </select>
        <select
          value={filterStatus}
          onChange={event => setFilterStatus(event.target.value as StatusFilter)}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="all">All lifecycle states</option>
          <option value="pending_signature">Pending signature</option>
          <option value="signed">Signed</option>
        </select>
        <select
          value={filterMolecule}
          onChange={event => setFilterMolecule(event.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="all">All molecules</option>
          {molecules.map(molecule => (
            <option key={molecule} value={molecule}>
              {molecule}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={issuesOnly}
            onChange={event => setIssuesOnly(event.target.checked)}
            className="h-4 w-4 rounded border-gray-300"
          />
          Issues only
        </label>
        <span className="ml-auto text-xs text-gray-500">
          {filteredContracts.length} result{filteredContracts.length === 1 ? '' : 's'}
        </span>
      </div>

      {loading && (
        <div className="py-12 text-center text-gray-500">
          <RefreshCw className="mx-auto mb-3 h-8 w-8 animate-spin text-blue-500" />
        </div>
      )}

      {!loading && filteredContracts.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-12 text-center">
          <FileText className="mx-auto mb-3 h-12 w-12 text-gray-300" />
          <h3 className="mb-2 text-lg font-bold text-gray-900">
            {normalizedContracts.length === 0 ? 'No Contracts Yet' : 'No Matching Agreements'}
          </h3>
          <p className="text-gray-600">
            {normalizedContracts.length === 0
              ? 'Pending signature and signed agreements will appear here once trades reach contract stage.'
              : 'Adjust the filters to bring the portfolio view back into scope.'}
          </p>
        </div>
      )}

      {!loading && filteredContracts.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Agreement
                </th>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Counterparty
                </th>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Start
                </th>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Tenor
                </th>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Volume
                </th>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Price
                </th>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Quality
                </th>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Origin
                </th>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Credit
                </th>
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-gray-500">
                  Potential issues
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredContracts.map(contract => {
                const creditTone = getCreditTone(contract.creditRating)

                return (
                  <tr
                    key={contract.id}
                    className={`align-top hover:bg-gray-50 ${
                      contract.highestIssue === 'high' ? 'bg-red-50/30' : ''
                    }`}
                  >
                    <td className="px-4 py-4">
                      <div className="min-w-[220px]">
                        <div className="font-bold text-gray-900">{contract.externalId}</div>
                        <div className="mt-1 text-sm text-gray-600">{contract.projectName}</div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <span
                            className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
                              STATUS_TONE[contract.statusGroup]
                            }`}
                          >
                            {contract.statusGroup === 'signed' ? 'Signed' : 'Pending signature'}
                          </span>
                          <span className="text-[11px] text-gray-500">{prettyStatus(contract.status)}</span>
                        </div>
                        <div className="mt-2 text-[11px] text-gray-400">{contract.scopeLabel}</div>
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="min-w-[120px]">
                        <span
                          className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${
                            TYPE_TONE[contract.agreementType]
                          }`}
                        >
                          {contract.agreementType}
                        </span>
                        <div className="mt-2 text-xs text-gray-500">
                          {describeInference(contract.inferenceSource)}
                        </div>
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="min-w-[180px]">
                        <div className="font-semibold text-gray-900">{contract.counterparty}</div>
                        <div className="mt-1 text-xs text-gray-500">{contract.molecule}</div>
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="min-w-[130px]">
                        <div className="font-semibold text-gray-900">{formatDate(contract.startDate)}</div>
                        <div className="mt-1 text-xs text-gray-500">to {formatDate(contract.endDate)}</div>
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="min-w-[90px] font-semibold text-gray-900">
                        {contract.tenorYears === null ? '—' : `${contract.tenorYears}y`}
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="min-w-[110px] font-semibold text-gray-900">
                        {formatVolume(contract.volumeMtpd)}
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="min-w-[170px]">
                        <div className="font-semibold text-gray-900">{formatPrice(contract.priceEurKg)}</div>
                        <div className="mt-1 text-xs text-gray-500">{contract.pricingBasis}</div>
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="min-w-[180px]">
                        <div className="font-semibold text-gray-900">{contract.qualitySummary}</div>
                        <div className="mt-1 text-xs text-gray-500">{contract.molecule}</div>
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="min-w-[180px]">
                        <div className="font-semibold text-gray-900">{contract.originPrimary}</div>
                        <div className="mt-1 text-xs text-gray-500">{contract.originSecondary}</div>
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="min-w-[120px]">
                        <span
                          className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${getCreditClasses(
                            creditTone,
                          )}`}
                        >
                          {contract.creditRating || 'NR'}
                        </span>
                        <div className="mt-2 text-xs text-gray-500">{getCreditDescriptor(creditTone)}</div>
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="min-w-[260px]">
                        <div className="flex flex-wrap gap-1.5">
                          {contract.issues.slice(0, 3).map(issue => (
                            <span
                              key={issue.label}
                              className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                                ISSUE_TONE[issue.level]
                              }`}
                            >
                              {issue.label}
                            </span>
                          ))}
                          {contract.issues.length > 3 && (
                            <span className="inline-flex rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                              +{contract.issues.length - 3} more
                            </span>
                          )}
                          {contract.issues.length === 0 && (
                            <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                              No material issue flagged
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
