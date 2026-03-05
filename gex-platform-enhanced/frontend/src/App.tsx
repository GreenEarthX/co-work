import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { WorkspaceProvider } from '@/contexts/WorkspaceContext'
import { Layout } from '@/components/Layout'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { FinanceDashboardPage } from '@/features/finance/FinanceDashboardPage'
import { StageGatesPage } from '@/features/finance/StageGatesPage'
import { RevenueOfftakePage } from '@/features/finance/RevenueOfftakePage'
import { CovenantsPage } from '@/features/finance/CovenantsPage'
import { InsurancePage } from '@/features/finance/InsurancePage'
import { CapacityPage } from '@/features/capacity/CapacityPage'
import { ProjectsPage } from '@/features/projects/ProjectsPage'
import { ProductionPage } from '@/features/production/ProductionPage'
import { TokenisationPage } from '@/features/tokenisation/TokenisationPage'
import { MarketplacePage } from '@/features/marketplace/MarketplacePage'
import { MatchingPage } from '@/features/matching/MatchingPage'
import { ContractsPage } from '@/features/contracts/ContractsPage'
import { SettlementPage } from '@/features/settlement/SettlementPage'
import { ReportsPage } from '@/features/reports/ReportsPage'
import { RegulatorDashboardPage } from '@/features/regulator/RegulatorDashboardPage'
import OnboardingWizard from '@/features/onboarding/OnboardingWizard'

// This fixes the QueryClient error
const queryClient = new QueryClient()

const PlaceholderPage = ({ title, workspace }: { title: string; workspace?: string }) => (
  <div className="max-w-4xl mx-auto">
    <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">{title}</h2>
      {workspace && <p className="text-sm text-gray-500 mb-4">{workspace} Workspace</p>}
      <p className="text-gray-600">This section is under development.</p>
    </div>
  </div>
)

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <WorkspaceProvider defaultWorkspace="producer">
        <BrowserRouter>
          <Routes>
            <Route path="/onboarding" element={<OnboardingWizard />} />
            <Route path="/get-started" element={<OnboardingWizard />} />
            <Route path="/" element={<Layout />}>
              <Route index element={<Navigate to="/dashboard" replace />} />
              
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="projects" element={<ProjectsPage />} />
              <Route path="production" element={<ProductionPage />} />
              <Route path="capacity" element={<CapacityPage />} />
              <Route path="tokenisation" element={<TokenisationPage />} />
              <Route path="marketplace" element={<MarketplacePage />} />
              <Route path="matching" element={<MatchingPage />} />
              <Route path="contracts" element={<ContractsPage />} />
              <Route path="settlement" element={<SettlementPage />} />
              <Route path="reports" element={<ReportsPage />} />

              <Route path="finance-dashboard" element={<FinanceDashboardPage />} />
              <Route path="stage-gates" element={<StageGatesPage />} />
              <Route path="revenue" element={<RevenueOfftakePage />} />
              <Route path="covenants" element={<CovenantsPage />} />
              <Route path="insurance" element={<InsurancePage />} />
              <Route path="finance-reports" element={<PlaceholderPage title="Reports & Audit" workspace="Finance" />} />

              <Route path="trader-dashboard" element={<PlaceholderPage title="Trader Dashboard" workspace="Trader" />} />
              <Route path="market-discovery" element={<PlaceholderPage title="Market Discovery" workspace="Trader" />} />
              <Route path="rfqs" element={<PlaceholderPage title="RFQs & Negotiation" workspace="Trader" />} />
              <Route path="counterparties" element={<PlaceholderPage title="Counterparties" workspace="Trader" />} />
              <Route path="trader-analytics" element={<PlaceholderPage title="Analytics" workspace="Trader" />} />

              <Route path="regulator-dashboard" element={<RegulatorDashboardPage />} />
              <Route path="project-registry" element={<PlaceholderPage title="Project Registry" workspace="Regulator" />} />
              <Route path="compliance" element={<PlaceholderPage title="Compliance Verification" workspace="Regulator" />} />
              <Route path="documentation" element={<PlaceholderPage title="Documentation Review" workspace="Regulator" />} />
              <Route path="inspections" element={<PlaceholderPage title="Inspections & Audits" workspace="Regulator" />} />
              <Route path="market-oversight" element={<PlaceholderPage title="Market Oversight" workspace="Regulator" />} />
              <Route path="regulator-reports" element={<PlaceholderPage title="Reports" workspace="Regulator" />} />

              <Route path="executive-dashboard" element={<PlaceholderPage title="Executive Dashboard" workspace="Executive" />} />
              <Route path="strategic" element={<PlaceholderPage title="Strategic Overview" workspace="Executive" />} />
              <Route path="financial" element={<PlaceholderPage title="Financial Performance" workspace="Executive" />} />
              <Route path="operations" element={<PlaceholderPage title="Operations & Production" workspace="Executive" />} />
              <Route path="commercial" element={<PlaceholderPage title="Market & Commercial" workspace="Executive" />} />
              <Route path="risk" element={<PlaceholderPage title="Risk & Compliance" workspace="Executive" />} />
              <Route path="stakeholders" element={<PlaceholderPage title="Stakeholder View" workspace="Executive" />} />
              <Route path="executive-analytics" element={<PlaceholderPage title="Advanced Analytics" workspace="Executive" />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </WorkspaceProvider>
    </QueryClientProvider>
  )
}

export default App