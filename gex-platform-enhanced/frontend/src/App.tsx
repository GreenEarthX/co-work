// Screen: All screens (root router)
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ProjectProvider } from '@/contexts/ProjectContext'
import { RequireAuth } from '@/components/RequireAuth'
import { Layout } from '@/components/Layout'
import { LoginPage } from '@/features/auth/LoginPage'
import { GuestLandingPage } from '@/features/auth/GuestLandingPage'
import { AccountPage } from '@/features/auth/AccountPage'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { FinanceDashboardPage } from '@/features/finance/FinanceDashboardPage'
import { StageGatesPage } from '@/features/finance/StageGatesPage'
import { RevenueOfftakePage } from '@/features/finance/RevenueOfftakePage'
import { CovenantsPage } from '@/features/finance/CovenantsPage'
import { InsurancePage } from '@/features/finance/InsurancePage'
import { CapacityPage } from '@/features/capacity/CapacityPage'
import { ProjectsPage } from '@/features/projects/ProjectsPage'
import { ProjectProfilePage } from '@/features/projects/ProjectProfilePage'
import EconomicsSnapshotPage from '@/features/economics/EconomicsSnapshotPage'
import { NewProjectPage } from '@/features/projects/NewProjectPage'
import { ProductionPage } from '@/features/production/ProductionPage'
import { TokenisationPage } from '@/features/tokenisation/TokenisationPage'
import { MarketplacePage } from '@/features/marketplace/MarketplacePage'
import { MatchingPage } from '@/features/matching/MatchingPage'
import { ContractsPage } from '@/features/contracts/ContractsPage'
import { SettlementPage } from '@/features/settlement/SettlementPage'
import { ReportsPage } from '@/features/reports/ReportsPage'
import { RegulatorDashboardPage } from '@/features/regulator/RegulatorDashboardPage'
import { ExecutiveBankabilityDashboard } from '@/features/executive/ExecutiveBankabilityDashboard'
import { ProducerBankabilityView } from '@/features/producer/ProducerBankabilityView'
import { FinanceBankabilityView } from '@/features/finance/FinanceBankabilityView'
import OnboardingWizard from '@/features/onboarding/OnboardingWizard'
// R6/R8/R9: Architectural Reform v6.0 imports
import EvidenceHierarchy from '@/features/finance/EvidenceHierarchy'
import { OfftakerSupplyTable } from '@/features/trader/OfftakerSupplyTable'
import { CISODashboardPage } from '@/features/ciso/CISODashboardPage'
import { SecurityMonitoringPage } from '@/features/ciso/SecurityMonitoringPage'
import { ABACManagementPage } from '@/features/ciso/ABACManagementPage'
import { ComplianceReportingPage } from '@/features/ciso/ComplianceReportingPage'
import { CommunicationPage } from '@/features/ciso/CommunicationPage'
import { BarrierManagement } from '@/features/ciso/BarrierManagement'
import { ResidencyPolicies } from '@/features/ciso/ResidencyPolicies'
import { GatewayStatus } from '@/features/ciso/GatewayStatus'
import { ClientCISODashboard } from '@/features/ciso/ClientCISODashboard'
import { ApprovalQueuePage } from '@/features/finance/ApprovalQueuePage'
import { CommitmentSigning } from '@/features/finance/CommitmentSigning'
import { CommitmentVerifier } from '@/features/finance/CommitmentVerifier'
import { PlantDataDashboard } from '@/features/producer/PlantDataDashboard'
import BankabilityScorePage from '@/features/finance/BankabilityScorePage'
import { BankersSnapshot } from '@/features/finance/BankersSnapshot'
import { DSCRHeatmap } from '@/features/finance/DSCRHeatmap'
import { FinanceRouteGuard } from '@/components/FinanceRouteGuard'
import { OfftakeQuality } from '@/features/finance/OfftakeQuality'
import { CertReadiness } from '@/features/finance/CertReadiness'
import { ProjectTimeline } from '@/features/finance/ProjectTimeline'
import { ICPackBuilder } from '@/features/finance/ICPackBuilder'
import { CFOReport } from '@/features/executive/CFOReport'
import { CapitalStack } from '@/features/finance/CapitalStack'
import { DataRoom } from '@/features/finance/DataRoom'
import { TermSheetTracker } from '@/features/finance/TermSheetTracker'
import { TransferReadiness } from '@/features/finance/TransferReadiness'
import { InsuranceSchedule } from '@/features/finance/InsuranceSchedule'
import { TraderDashboardPage } from '@/features/trader/TraderDashboardPage'
import { MarketDiscoveryPage } from '@/features/trader/MarketDiscoveryPage'
import RFQManagementPage from '@/features/trader/RFQManagementPage'
import { CounterpartiesPage } from '@/features/trader/CounterpartiesPage'
import { GanttVisibilityConfig } from '@/features/ciso/GanttVisibilityConfig'
import { ScreenAccessPage } from '@/features/ciso/ScreenAccessPage'
import { GapAnalysis } from '@/features/finance/GapAnalysis'
import { GabillonAdminPage } from '@/features/pricing/GabillonAdminPage'
import { MoleculePriceCurve } from '@/features/pricing/MoleculePriceCurve'
import MoleculeLineage from '@/features/pricing/MoleculeLineage'
import { InstrumentCatalog } from '@/features/finance/InstrumentCatalog'
import { InstrumentCompatibility } from '@/features/finance/InstrumentCompatibility'
import { PackageRegister } from '@/features/finance/PackageRegister'
import { RiskAllocationMatrix } from '@/features/finance/RiskAllocationMatrix'
import { StructuringTimeline } from '@/features/finance/StructuringTimeline'
import { DemandPipeline } from '@/features/finance/DemandPipeline'
import { PlantBuilder } from '@/features/finance/PlantBuilder'
import { AdversarialReviewPage } from '@/features/reviews/AdversarialReviewPage'
import { SpendWaveView } from '@/features/finance/SpendWaveView'
import { DebtCashflowWaterfall } from '@/features/finance/DebtCashflowWaterfall'
import { DrawdownTimeline } from '@/features/finance/DrawdownTimeline'
import { DFIDashboard } from '@/features/finance/DFIDashboard'
import { LineagePanel } from '@/features/finance/LineagePanel'
import { InsuranceCoverageBuilder } from '@/features/insurance/InsuranceCoverageBuilder'
import { InsuranceAssetRegister } from '@/features/insurance/InsuranceAssetRegister'
import { GatedRoute } from '@/components/GatedRoute'
import { ProcurementSimulatorPage } from '@/features/procurement/ProcurementSimulatorPage'
import { KycVerification } from '@/features/kyc/KycVerificationPage'
import { KybVerification } from '@/features/kyc/KybVerificationPage'
import PlantCanvas from '@/features/canvas/PlantCanvas'
import CanvasPlantBuilder from '@/features/canvas/PlantBuilder'
import SiteInfrastructure from '@/features/canvas/SiteInfrastructure'

// This fixes the QueryClient error
const queryClient = new QueryClient()

// Unbuilt screens are not routed (JML, 2026-10-23): no page shows a placeholder.

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ProjectProvider>
        <BrowserRouter>
          <Routes>
            {/* ── Public routes (no auth required) ── */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<GuestLandingPage />} />
            <Route path="/onboarding" element={<OnboardingWizard />} />
            <Route path="/get-started" element={<OnboardingWizard />} />

            {/* ── KYC/KYB — full-page flows with own header, outside Layout ── */}
            <Route path="/kyc" element={<RequireAuth><KycVerification /></RequireAuth>} />
            <Route path="/kyc/:projectId" element={<RequireAuth><KycVerification /></RequireAuth>} />
            <Route path="/kyb" element={<RequireAuth><KybVerification /></RequireAuth>} />

            {/* ── Protected routes — pathless layout so existing paths (/dashboard, /finance/*) stay intact ── */}
            <Route element={<RequireAuth><Layout /></RequireAuth>}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/account" element={<AccountPage />} />
              <Route path="projects" element={<ProjectsPage />} />
              <Route path="projects/new" element={<NewProjectPage />} />
              <Route path="projects/:id/edit" element={<ProjectProfilePage />} />
              <Route path="economics/:projectId" element={<EconomicsSnapshotPage />} />
              <Route path="adversarial-review" element={<AdversarialReviewPage />} />
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
              <Route path="finance-gaps" element={<GatedRoute path="/finance-gaps"><GapAnalysis /></GatedRoute>} />
              <Route path="finance-instruments" element={<InstrumentCatalog />} />
              <Route path="instrument-compatibility" element={<InstrumentCompatibility />} />
              <Route path="finance-package" element={<PackageRegister />} />
              <Route path="finance-risk-matrix" element={<RiskAllocationMatrix />} />
              <Route path="finance-structuring-timeline" element={<StructuringTimeline />} />
              <Route path="finance-demand" element={<DemandPipeline />} />
              <Route path="finance-plant-builder" element={<PlantBuilder />} />
              <Route path="procurement-simulator" element={<ProcurementSimulatorPage />} />

              {/* ── Canvas / Plant Design ── */}
              <Route path="canvas/:plantId" element={<PlantCanvas />} />
              <Route path="canvas/:plantId/infrastructure" element={<SiteInfrastructure />} />
              <Route path="plants" element={<CanvasPlantBuilder />} />

              {/* ── /finance/* — clean URLs used by deal-killer links & direct nav ── */}
              <Route path="finance">
                <Route index element={<FinanceDashboardPage />} />
                <Route path="dashboard"           element={<FinanceDashboardPage />} />
                <Route path="stage-gates"         element={<StageGatesPage />} />
                <Route path="revenue"             element={<RevenueOfftakePage />} />
                <Route path="covenants"           element={<CovenantsPage />} />
                <Route path="insurance"           element={<InsurancePage />} />
                <Route path="bankability"         element={<FinanceBankabilityView />} />
                <Route path="bankability-scores"  element={<BankabilityScorePage />} />
                <Route path="bankers-snapshot"    element={<BankersSnapshot />} />
                <Route path="dscr-sensitivity"    element={<FinanceRouteGuard routeLabel="DSCR Sensitivity Analysis"><DSCRHeatmap /></FinanceRouteGuard>} />
                <Route path="offtake-quality"     element={<GatedRoute path="/offtake-quality"><OfftakeQuality /></GatedRoute>} />
                <Route path="cert-readiness"      element={<CertReadiness />} />
                <Route path="timeline"            element={<ProjectTimeline />} />
                <Route path="ic-pack"             element={<GatedRoute path="/ic-pack"><ICPackBuilder /></GatedRoute>} />
                <Route path="capital-stack"       element={<GatedRoute path="/capital-stack"><CapitalStack /></GatedRoute>} />
                <Route path="data-room"           element={<GatedRoute path="/data-room"><DataRoom /></GatedRoute>} />
                <Route path="term-sheet"          element={<GatedRoute path="/term-sheet"><TermSheetTracker /></GatedRoute>} />
                <Route path="transfer-readiness"  element={<TransferReadiness />} />
                <Route path="insurance-schedule"  element={<GatedRoute path="/insurance-schedule"><InsuranceSchedule /></GatedRoute>} />
                <Route path="gaps"                element={<GatedRoute path="/finance-gaps"><GapAnalysis /></GatedRoute>} />
                <Route path="evidence-hierarchy"  element={<EvidenceHierarchy />} />
                <Route path="spend-wave"         element={<SpendWaveView />} />
                <Route path="debt-waterfall"     element={<DebtCashflowWaterfall />} />
                <Route path="drawdown-timeline"  element={<GatedRoute path="/finance/drawdown-timeline"><DrawdownTimeline /></GatedRoute>} />
                <Route path="dfi-dashboard"      element={<DFIDashboard />} />
                <Route path="lineage"            element={<LineagePanel />} />
                <Route path="approval-queue"      element={<GatedRoute path="/approval-queue"><ApprovalQueuePage /></GatedRoute>} />
                <Route path="commitment-signing"  element={<GatedRoute path="/commitment-signing"><CommitmentSigning /></GatedRoute>} />
                <Route path="commitment-verifier" element={<CommitmentVerifier />} />
              </Route>

              <Route path="trader-dashboard" element={<TraderDashboardPage />} />
              <Route path="market-discovery" element={<MarketDiscoveryPage />} />
              <Route path="rfqs" element={<RFQManagementPage />} />
              <Route path="counterparties" element={<CounterpartiesPage />} />

              <Route path="producer-bankability" element={<ProducerBankabilityView />} />
              <Route path="finance-bankability" element={<FinanceBankabilityView />} />

              <Route path="regulator-dashboard" element={<RegulatorDashboardPage />} />

              <Route path="executive-dashboard" element={<ExecutiveBankabilityDashboard />} />

              {/* ── WAE / Approval Queue (Finance + Executive) — gate-locked ── */}
              <Route path="approval-queue"      element={<GatedRoute path="/approval-queue"><ApprovalQueuePage /></GatedRoute>} />

              {/* ── CSS / Commitment Signing (Finance) — gate-locked ── */}
              <Route path="commitment-signing"  element={<GatedRoute path="/commitment-signing"><CommitmentSigning /></GatedRoute>} />
              <Route path="commitment-verifier" element={<CommitmentVerifier />} />

              {/* ── OT Plant Telemetry (Producer) ── */}
              <Route path="plant-data"          element={<PlantDataDashboard />} />

              {/* ── Bankability & Credibility Scores (Finance) ── */}
              <Route path="bankability-scores"  element={<BankabilityScorePage />} />
              {/* R9: Evidence Hierarchy — Credit Committee Chair view */}
              <Route path="evidence-hierarchy"  element={<EvidenceHierarchy />} />
              {/* R8: Offtaker 4-column supply table */}
              <Route path="offtaker-supply"     element={<OfftakerSupplyTable />} />

              {/* ── B1: Banker's Snapshot + DSCR Heatmap (Finance) — gate-locked ── */}
              <Route path="bankability-snapshot" element={<GatedRoute path="/bankability-snapshot"><BankersSnapshot /></GatedRoute>} />
              <Route path="dscr-sensitivity"     element={<FinanceRouteGuard routeLabel="DSCR Sensitivity Analysis"><DSCRHeatmap /></FinanceRouteGuard>} />

              {/* ── B2: Offtake Quality + Cert Readiness + Timeline (Finance) ── */}
              <Route path="offtake-quality"      element={<GatedRoute path="/offtake-quality"><OfftakeQuality /></GatedRoute>} />
              <Route path="cert-readiness"       element={<CertReadiness />} />
              <Route path="finance-timeline"     element={<ProjectTimeline />} />

              {/* ── B3: IC Pack Builder (Finance) — gate-locked ── */}
              <Route path="ic-pack"              element={<GatedRoute path="/ic-pack"><ICPackBuilder /></GatedRoute>} />

              {/* ── CEO Report (Operations / Executive) ── */}
              <Route path="cfo-report"           element={<CFOReport />} />

              {/* ── B3: Capital Stack + Data Room + Terms + Transfer (Finance) — gate-locked ── */}
              <Route path="capital-stack"        element={<GatedRoute path="/capital-stack"><CapitalStack /></GatedRoute>} />
              <Route path="data-room"            element={<GatedRoute path="/data-room"><DataRoom /></GatedRoute>} />
              <Route path="term-sheet"           element={<GatedRoute path="/term-sheet"><TermSheetTracker /></GatedRoute>} />
              <Route path="transfer-readiness"   element={<TransferReadiness />} />
              <Route path="insurance-schedule"   element={<GatedRoute path="/insurance-schedule"><InsuranceSchedule /></GatedRoute>} />

              {/* ── Gantt Visibility Config (CISO) ── */}
              <Route path="ciso-gantt-config"    element={<GanttVisibilityConfig />} />
              <Route path="ciso-screen-access"   element={<ScreenAccessPage />} />

              {/* ── Gabillon / Pricing (CISO Webmaster + project view) ── */}
              <Route path="ciso-pricing"         element={<GabillonAdminPage />} />
              <Route path="pricing-lineage"      element={<FinanceRouteGuard routeLabel="Price Decomposition (Gabillon)"><MoleculeLineage /></FinanceRouteGuard>} />
              <Route path="pricing-curves"       element={
                <div className="space-y-6">
                  <div>
                    <h1 className="font-display text-2xl font-bold text-[var(--text-primary)] mb-1">
                      Green Fuel Forward Curves
                    </h1>
                    <p className="text-sm text-[var(--text-secondary)]">
                      Gabillon two-factor model — published by GEX webmaster. Updated on calibration.
                    </p>
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    {['E_METHANE','E_METHANOL','E_NH3','HVO','SAF','E_GASOLINE','E_LG','E_NAPHTHA'].map(mol => (
                      <MoleculePriceCurve key={mol} molecule={mol} showTable />
                    ))}
                  </div>
                </div>
              } />

              {/* ── Insurance Workspace (Insurer + Producer Finance) ── */}
              <Route path="insurance-coverage" element={<GatedRoute path="/insurance-coverage"><InsuranceCoverageBuilder /></GatedRoute>} />
              <Route path="insurance-assets"   element={<InsuranceAssetRegister />} />

              {/* ── CISO Workspace ── */}
              <Route path="ciso/client/:companyId" element={<ClientCISODashboard />} />
              <Route path="ciso-dashboard"      element={<CISODashboardPage />} />
              <Route path="ciso-access-monitor" element={<SecurityMonitoringPage />} />
              <Route path="ciso-identity"       element={<ABACManagementPage />} />
              <Route path="ciso-compliance"     element={<ComplianceReportingPage />} />
              <Route path="ciso-policy"         element={<ComplianceReportingPage />} />
              <Route path="ciso-communications" element={<CommunicationPage />} />
              <Route path="ciso-barriers"       element={<BarrierManagement />} />
              <Route path="ciso-residency"      element={<ResidencyPolicies />} />
              <Route path="ciso-gateways"       element={<GatewayStatus />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ProjectProvider>
    </QueryClientProvider>
  )
}

export default App
