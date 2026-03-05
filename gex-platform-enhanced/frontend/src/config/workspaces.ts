import { 
  Activity, Layers, Box, CheckCircle2, ShoppingCart, Zap, 
  Users, Shield, FileCheck, BarChart3, Settings, 
  DollarSign, TrendingUp, FileText, AlertTriangle,
  Search, Package, Truck, Building
} from 'lucide-react'

export type WorkspaceId = 'producer' | 'finance' | 'trader' | 'regulator' | 'executive'

export interface NavItem {
  name: string
  path: string
  icon: any
  description: string
  badge?: number
}

export interface Workspace {
  id: WorkspaceId
  name: string
  description: string
  color: string // Tailwind color
  navigation: NavItem[]
  defaultRoute: string
}

// ═══════════════════════════════════════════════════════════════
// PRODUCER WORKSPACE
// ═══════════════════════════════════════════════════════════════)
export const producerWorkspace: Workspace = {
  id: 'producer',
  name: 'Producer',
  description: 'Production management & market access',
  color: 'emerald',
  defaultRoute: '/dashboard',
  navigation: [
    {
      name: 'Dashboard',
      path: '/dashboard',
      icon: Activity,
      description: 'Production flow & metrics',
    },
    {
      name: 'Projects & Assets',
      path: '/projects',
      icon: Layers,
      description: 'Sites, permits, milestones',
    },
    {
      name: 'Production',
      path: '/capacity',
      icon: Box,
      description: 'Capacity & batches',
    },
    {
      name: 'Tokenisation',
      path: '/tokenisation',
      icon: CheckCircle2,
      description: 'Mint & allocate',
    },
    {
      name: 'Market',
      path: '/marketplace',
      icon: ShoppingCart,
      description: 'Create offers',
    },
    {
      name: 'Matching',
      path: '/matching',
      icon: Zap,
      description: 'Find buyers',
    },
    {
      name: 'Contracts',
      path: '/contracts',
      icon: FileText,
      description: 'Commitments & terms',
    },
    {
      name: 'Delivery & Settlement',
      path: '/settlement',
      icon: Truck,
      description: 'Proofs & invoices',
    },
    {
      name: 'Reports',
      path: '/reports',
      icon: BarChart3,
      description: 'Analytics & exports',
    },
  ],
}

// ═══════════════════════════════════════════════════════════════
// FINANCE WORKSPACE
// ═══════════════════════════════════════════════════════════════
export const financeWorkspace: Workspace = {
  id: 'finance',
  name: 'Finance',
  description: 'Risk, covenants & banking metrics',
  color: 'blue',
  defaultRoute: '/finance-dashboard',
  navigation: [
    {
      name: 'Dashboard',
      path: '/finance-dashboard',
      icon: Activity,
      description: 'Risk signals & alerts',
    },
    {
      name: 'Stage Gates & Risk',
      path: '/stage-gates',
      icon: TrendingUp,
      description: 'FEL → FEED → FID → FC → COD',
    },
    {
      name: 'Revenue & Offtake',
      path: '/revenue',
      icon: DollarSign,
      description: 'Contract coverage',
    },
    {
      name: 'Covenants & Compliance',
      path: '/covenants',
      icon: Shield,
      description: 'DSCR, LLCR, reserves',
    },
    {
      name: 'Projects & Assets',
      path: '/projects',
      icon: Layers,
      description: 'Capex, construction',
    },
    {
      name: 'Insurance & Guarantees',
      path: '/insurance',
      icon: AlertTriangle,
      description: 'Coverage & expiries',
    },
    {
      name: 'Reports & Audit',
      path: '/finance-reports',
      icon: BarChart3,
      description: 'Lender reports',
    },
  ],
}
// ═══════════════════════════════════════════════════════════════
// TRADER WORKSPACE
// ═══════════════════════════════════════════════════════════════
export const traderWorkspace: Workspace = {
  id: 'trader',
  name: 'Trader',
  description: 'Market discovery & book management',
  color: 'purple',
  defaultRoute: '/trader-dashboard',
  navigation: [
    {
      name: 'Dashboard',
      path: '/trader-dashboard',
      icon: Activity,
      description: 'Market pulse & opportunities',
    },
    {
      name: 'Market Discovery',
      path: '/market-discovery',
      icon: Search,
      description: 'Browse offers',
    },
    {
      name: 'Matching Engine',
      path: '/matching',
      icon: Zap,
      description: 'Find suppliers',
    },
    {
      name: 'RFQs & Negotiation',
      path: '/rfqs',
      icon: FileText,
      description: 'Request quotes',
    },
    {
      name: 'Contracts & Book',
      path: '/contracts',
      icon: Package,
      description: 'Active positions',
    },
    {
      name: 'Counterparties',
      path: '/counterparties',
      icon: Users,
      description: 'Due diligence',
    },
    {
      name: 'Delivery & Settlement',
      path: '/settlement',
      icon: Truck,
      description: 'Nominations & proofs',
    },
    {
      name: 'Analytics',
      path: '/trader-analytics',
      icon: BarChart3,
      description: 'Portfolio metrics',
    },
  ],
}

// ═══════════════════════════════════════════════════════════════
// REGULATOR WORKSPACE
// ═══════════════════════════════════════════════════════════════
export const regulatorWorkspace: Workspace = {
  id: 'regulator',
  name: 'Regulator',
  description: 'Compliance verification & audit',
  color: 'red',
  defaultRoute: '/regulator-dashboard',
  navigation: [
    {
      name: 'Dashboard',
      path: '/regulator-dashboard',
      icon: Activity,
      description: 'Compliance alerts',
    },
    {
      name: 'Project Registry',
      path: '/project-registry',
      icon: Layers,
      description: 'All facilities',
    },
    {
      name: 'Compliance Verification',
      path: '/compliance',
      icon: Shield,
      description: 'RFNBO / 45V / RED',
    },
    {
      name: 'Documentation Review',
      path: '/documentation',
      icon: FileCheck,
      description: 'Permits & certs',
    },
    {
      name: 'Inspections & Audits',
      path: '/inspections',
      icon: AlertTriangle,
      description: 'Site visits',
    },
    {
      name: 'Market Oversight',
      path: '/market-oversight',
      icon: BarChart3,
      description: 'Transaction monitor',
    },
    {
      name: 'Reports',
      path: '/regulator-reports',
      icon: FileText,
      description: 'Statistics & trends',
    },
  ],
}

// ═══════════════════════════════════════════════════════════════
// EXECUTIVE WORKSPACE
// ═══════════════════════════════════════════════════════════════
export const executiveWorkspace: Workspace = {
  id: 'executive',
  name: 'Executive',
  description: 'Portfolio overview & strategic KPIs',
  color: 'gray',
  defaultRoute: '/executive-dashboard',
  navigation: [
    {
      name: 'Dashboard',
      path: '/executive-dashboard',
      icon: Activity,
      description: 'Portfolio KPIs',
    },
    {
      name: 'Strategic Overview',
      path: '/strategic',
      icon: TrendingUp,
      description: 'Goals & milestones',
    },
    {
      name: 'Financial Performance',
      path: '/financial',
      icon: DollarSign,
      description: 'P&L, cash flow',
    },
    {
      name: 'Operations & Production',
      path: '/operations',
      icon: Box,
      description: 'Utilization & trends',
    },
    {
      name: 'Market & Commercial',
      path: '/commercial',
      icon: ShoppingCart,
      description: 'Offtake & pricing',
    },
    {
      name: 'Risk & Compliance',
      path: '/risk',
      icon: Shield,
      description: 'Heat map & ESG',
    },
    {
      name: 'Stakeholder View',
      path: '/stakeholders',
      icon: Users,
      description: 'IR & board materials',
    },
    {
      name: 'Advanced Analytics',
      path: '/executive-analytics',
      icon: BarChart3,
      description: 'Scenarios & forecasts',
    },
  ],
}

// All workspaces registry
export const workspaces: Record<WorkspaceId, Workspace> = {
  producer: producerWorkspace,
  finance: financeWorkspace,
  trader: traderWorkspace,
  regulator: regulatorWorkspace,
  executive: executiveWorkspace,
}

// Get workspace by ID
export const getWorkspace = (id: WorkspaceId): Workspace => {
  return workspaces[id]
}

// Get all workspace IDs
export const getWorkspaceIds = (): WorkspaceId[] => {
  return Object.keys(workspaces) as WorkspaceId[]
}