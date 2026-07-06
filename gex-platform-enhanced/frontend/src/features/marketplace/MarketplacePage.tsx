// Screen: Marketplace screen (/marketplace)
/**
 * Commercial Overview — Project-contextual, role-aware commercial dashboard
 *
 * Two-tab architecture (project finance rationale):
 *
 *   Tab 1 — PROJECT ECONOMICS
 *     Production Inputs + Sales & Offtake on one screen per project.
 *     These are two sides of the same operating cash flow waterfall:
 *       • Input costs → OPEX (variable) → drives break-even
 *       • Offtake contracts → Revenue line → drives DSCR
 *       • The margin between them = CFADS = bankability foundation
 *     A lender reads top-to-bottom: revenue, costs, margin, coverage.
 *
 *   Tab 2 — TRADING & PORTFOLIO
 *     Corporate/portfolio activity — molecules bought for resale, hedging,
 *     or portfolio management. Different legal entity (parent, not SPV),
 *     different financing (revolver, not project debt), different risk
 *     profile (mark-to-market, not contracted). Must NOT be commingled
 *     with project economics — it would distort DSCR and mislead lenders.
 *
 * Design rules:
 *   - ETFuels buying biogenic CO₂ → Production Input (it enters the reactor)
 *   - ETFuels buying e-methanol from a third party → Trading (not feedstock)
 *   - Behind-the-meter electricity → Production Input with evidence status
 *   - Purchased e-methanol for resale → Trading / Portfolio
 */

import { useState, useMemo, type ReactNode } from 'react'
import {
  Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Line, ComposedChart, ReferenceLine,
} from 'recharts'
import { Package, DollarSign, AlertTriangle } from 'lucide-react'
import { type CustomerProject } from '@/data/customerProjects'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'

// ── Types ────────────────────────────────────────────────────────────────────

type Granularity = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly'
type TableView = 'project_economics' | 'trading'
type ChartView = 'sales' | 'purchases' | 'combined'

type ItemPurpose = 'PRODUCTION_INPUT' | 'TRADING_PROCUREMENT' | 'OFFTAKE_SALE' | 'CERTIFICATION_EVIDENCE'
type VerificationState = 'UNVERIFIED' | 'SUBMITTED' | 'CONFIRMED' | 'AUDITED'
type ContractStatus = 'CONTRACTED' | 'TERM_SHEET' | 'PLANNED' | 'SPOT' | 'INDICATIVE'
type CertRelevance = 'RFNBO' | '45V' | 'FUELEU' | 'CORSIA' | 'RED_III' | 'NONE'
type CapitalRelevance = 'BANKABILITY_CRITICAL' | 'COST_DRIVER' | 'EVIDENCE_ITEM' | 'COMMERCIAL_ONLY'

interface SalesDetail {
  region: string
  eSource: string
  greenEnergyPct: number
  certifier: string
  bePrice: number
  available: { start: string; end: string; volume_mtpd: number; basePrice: number; pct: number; status: string }
  tokenised: { start: string; end: string; volume_mtpd: number; price: number; pct: number; status: string }
  inMarket: { start: string; end: string; volume_mtpd: number; targetPrice: number; pct: number; status: 'open' | 'pending' | 'sold'; counterparty: string | null }[]
}

/** Production input line — physical or contractual input to a production process */
interface FeedstockLine {
  projectId: string
  project: string
  outputMolecule: string
  feedstock: string
  supplier: string
  ratio: number
  ratioUnit: 'MT/MT' | 'MWh/MT' | 'kL/MT'
  annualVolume_mt: number
  unitPrice: number
  priceUnit: 'EUR/MWh' | 'EUR/MT' | 'EUR/kL'
  /** LCOE × ratio (or unitPrice × ratio for non-electricity) */
  costPerMtOutput: number
  /** For electricity: LCOE/CF + firming. For others: same as unitPrice. */
  effectiveCostPerMtOutput: number
  /** Capacity factor (electricity only) — 0 means N/A */
  capacityFactor: number
  status: 'contracted' | 'planned' | 'spot'
  isUtility: boolean
}

export interface ProjectFeedstockSummary {
  projectId: string
  project: string
  molecule: string
  location: string
  capacity_mtpd: number
  annualOutput_mt: number
  outputPrice: number
  /** Variable cost sum — LCOE-based */
  totalFeedstockCostPerMt: number
  /** Variable cost sum — effective (CF-adjusted + firming) */
  totalEffectiveCostPerMt: number
  /** outputPrice − totalEffectiveCostPerMt */
  grossMarginPerMt: number
  lines: FeedstockLine[]
  status: string
}

interface EnhancedChartPoint {
  period: string
  maxPotential: number
  sold: number
  pending: number
  open: number
  tokenised: number
  forwardCurve: number
  purchases: number
}

// ── Molecule pricing ─────────────────────────────────────────────────────────

const MOLECULE_SPOT: Record<string, { spot: number; unit: string }> = {
  H2:           { spot: 5500, unit: 'EUR/t' },
  NH3:          { spot: 700,  unit: 'EUR/t' },
  'e-Methanol': { spot: 1200, unit: 'EUR/t' },
  SAF:          { spot: 1500, unit: 'EUR/t' },
  'e-NG':       { spot: 120,  unit: 'EUR/MWh' },
}

// ── Per-project sales enrichment ─────────────────────────────────────────────

const PROJECT_SALES_DETAIL: Record<string, SalesDetail> = {
  proj_bremen_h2: {
    region: 'N. Europe', eSource: 'Offshore Wind', greenEnergyPct: 99, certifier: 'TÜV SÜD', bePrice: 4200,
    available: { start: '10/2026', end: '09/2031', volume_mtpd: 78, basePrice: 5800, pct: 92, status: 'Deposited' },
    tokenised: { start: '10/2026', end: '09/2031', volume_mtpd: 70, price: 5600, pct: 90, status: 'Deposited' },
    inMarket: [
      { start: '10/2026', end: '09/2031', volume_mtpd: 12, targetPrice: 5500, pct: 14, status: 'sold', counterparty: 'ThyssenKrupp' },
      { start: '10/2026', end: '09/2031', volume_mtpd: 50, targetPrice: 5650, pct: 59, status: 'pending', counterparty: 'Linde' },
      { start: '10/2026', end: '09/2031', volume_mtpd: 16, targetPrice: 5750, pct: 19, status: 'open', counterparty: null },
    ],
  },
  proj_rotterdam_nh3: {
    region: 'W. Europe', eSource: 'Grid PPA', greenEnergyPct: 95, certifier: "Lloyd's Register", bePrice: 480,
    available: { start: '07/2028', end: '06/2033', volume_mtpd: 140, basePrice: 750, pct: 88, status: 'Partially Deposited' },
    tokenised: { start: '07/2028', end: '06/2033', volume_mtpd: 110, price: 720, pct: 79, status: 'Deposited' },
    inMarket: [
      { start: '07/2028', end: '06/2033', volume_mtpd: 80, targetPrice: 780, pct: 50, status: 'pending', counterparty: 'Yara International' },
      { start: '07/2028', end: '06/2033', volume_mtpd: 30, targetPrice: 810, pct: 19, status: 'open', counterparty: null },
    ],
  },
  proj_sansebastian_emethanol: {
    region: 'S. Europe', eSource: 'Solar PPA', greenEnergyPct: 97, certifier: 'Bureau Veritas', bePrice: 850,
    available: { start: '01/2028', end: '12/2032', volume_mtpd: 37, basePrice: 1100, pct: 88, status: 'Partially Deposited' },
    tokenised: { start: '01/2028', end: '12/2032', volume_mtpd: 30, price: 1050, pct: 81, status: 'Deposited' },
    inMarket: [
      { start: '01/2028', end: '12/2032', volume_mtpd: 20, targetPrice: 1150, pct: 48, status: 'pending', counterparty: 'Maersk' },
      { start: '01/2028', end: '12/2032', volume_mtpd: 10, targetPrice: 1200, pct: 24, status: 'open', counterparty: null },
    ],
  },
  proj_wales_saf: {
    region: 'W. Europe', eSource: 'Wind PPA', greenEnergyPct: 96, certifier: 'DNV', bePrice: 1100,
    available: { start: '06/2028', end: '05/2033', volume_mtpd: 48, basePrice: 1600, pct: 87, status: 'Partially Deposited' },
    tokenised: { start: '06/2028', end: '05/2033', volume_mtpd: 40, price: 1550, pct: 83, status: 'Deposited' },
    inMarket: [
      { start: '06/2028', end: '05/2033', volume_mtpd: 28, targetPrice: 1650, pct: 51, status: 'pending', counterparty: 'Lufthansa Group' },
      { start: '06/2028', end: '05/2033', volume_mtpd: 12, targetPrice: 1700, pct: 22, status: 'open', counterparty: null },
    ],
  },
  proj_lehavre_eng: {
    region: 'W. Europe', eSource: 'Offshore Wind', greenEnergyPct: 98, certifier: 'Bureau Veritas', bePrice: 85,
    available: { start: '01/2025', end: '12/2029', volume_mtpd: 37, basePrice: 135, pct: 93, status: 'Deposited' },
    tokenised: { start: '01/2025', end: '12/2029', volume_mtpd: 35, price: 130, pct: 95, status: 'Deposited' },
    inMarket: [
      { start: '01/2025', end: '12/2029', volume_mtpd: 25, targetPrice: 128, pct: 63, status: 'sold', counterparty: 'Engie' },
      { start: '01/2025', end: '12/2029', volume_mtpd: 8, targetPrice: 140, pct: 20, status: 'pending', counterparty: 'TotalEnergies' },
      { start: '01/2025', end: '12/2029', volume_mtpd: 4, targetPrice: 145, pct: 10, status: 'open', counterparty: null },
    ],
  },
  proj_hamburgone_emethanol: {
    region: 'N. Europe', eSource: 'Solar + Wind', greenEnergyPct: 97, certifier: 'DNV', bePrice: 600,
    available: { start: '06/2027', end: '06/2032', volume_mtpd: 26, basePrice: 850, pct: 85, status: 'Partially Deposited' },
    tokenised: { start: '06/2027', end: '06/2032', volume_mtpd: 23, price: 820, pct: 75, status: 'Deposited' },
    inMarket: [
      { start: '06/2027', end: '06/2032', volume_mtpd: 18, targetPrice: 960, pct: 60, status: 'pending', counterparty: 'Vitol' },
      { start: '06/2027', end: '06/2032', volume_mtpd: 5, targetPrice: 975, pct: 15, status: 'open', counterparty: null },
    ],
  },
  proj_madrid2_sansebastian: {
    region: 'S. Europe', eSource: 'Offshore Wind', greenEnergyPct: 94, certifier: 'Bureau Veritas', bePrice: 750,
    available: { start: '07/2029', end: '06/2034', volume_mtpd: 36, basePrice: 1000, pct: 86, status: 'Pending Deposit' },
    tokenised: { start: '07/2029', end: '06/2034', volume_mtpd: 24, price: 950, pct: 67, status: 'Pending' },
    inMarket: [
      { start: '07/2029', end: '06/2034', volume_mtpd: 15, targetPrice: 1050, pct: 36, status: 'pending', counterparty: 'RotterdamOfftake4' },
      { start: '07/2029', end: '06/2034', volume_mtpd: 9, targetPrice: 1100, pct: 21, status: 'open', counterparty: null },
    ],
  },
  // ETFuels Pecos I / Rattlesnake Gap
  proj_etf_pecos1: {
    region: 'N. America', eSource: 'Behind-the-meter Wind', greenEnergyPct: 100, certifier: 'DNV', bePrice: 620,
    available: { start: '01/2030', end: '12/2039', volume_mtpd: 280, basePrice: 800, pct: 85, status: 'Pending Deposit' },
    tokenised: { start: '01/2030', end: '12/2039', volume_mtpd: 0, price: 0, pct: 0, status: 'Pre-production' },
    inMarket: [
      { start: '01/2030', end: '12/2039', volume_mtpd: 200, targetPrice: 800, pct: 61, status: 'sold', counterparty: 'RFOcean' },
      { start: '01/2030', end: '12/2039', volume_mtpd: 80, targetPrice: 850, pct: 24, status: 'open', counterparty: null },
    ],
  },
}

// ── Per-project production input specs ──────────────────────────────────────
// Renamed from PROJECT_FEEDSTOCK — these are production inputs, not "purchases"

interface FeedstockSpec {
  feedstock: string
  supplier: string
  ratio: number
  ratioUnit: 'MT/MT' | 'MWh/MT' | 'kL/MT'
  unitPrice: number           // LCOE or contract price (EUR/MWh or EUR/MT)
  priceUnit: 'EUR/MWh' | 'EUR/MT' | 'EUR/kL'
  status: 'contracted' | 'planned' | 'spot'
  isUtility: boolean
  /** For electricity: capacity factor (0–1). effectiveCost = unitPrice / CF + firmingCost */
  capacityFactor?: number
  /** Firming/storage adder (EUR/MWh) — battery, curtailment, backup */
  firmingCost?: number
}

/**
 * PROJECT_FEEDSTOCK — unbundled production inputs.
 *
 * Design rules:
 *   1. On-site H₂ is an INTERMEDIATE, not a purchased input.
 *      Show the actual inputs: electricity + water → electrolyser (CAPEX).
 *      Do NOT list "Green Hydrogen at €5,xxx/t" AND electricity — that double-counts.
 *   2. Ratios are PRACTICAL (85–95% conversion), not theoretical stoichiometric minimums.
 *   3. Electricity shows LCOE + capacity factor + firming cost → effective cost.
 *   4. Electrolyser is CAPEX — not in this table.
 *   5. If H₂ is purchased from a THIRD PARTY (not on-site), it IS a production input.
 */
const PROJECT_FEEDSTOCK: Record<string, FeedstockSpec[]> = {
  // ── ETFuels Rattlesnake Gap (Pecos I) ──
  // Behind-the-meter wind → PEM electrolysis → methanol synthesis. All unbundled.
  proj_etf_pecos1: [
    { feedstock: 'Renewable Electricity (BtM)', supplier: 'Behind-the-meter 340 MW Wind Farm', ratio: 11.5, ratioUnit: 'MWh/MT', unitPrice: 28, priceUnit: 'EUR/MWh', status: 'planned', isUtility: false, capacityFactor: 0.42, firmingCost: 8 },
    { feedstock: 'Biogenic CO₂',                supplier: 'West Texas Ethanol Co-op',           ratio: 1.46, ratioUnit: 'MT/MT',  unitPrice: 45, priceUnit: 'EUR/MT',  status: 'contracted', isUtility: false },
    { feedstock: 'Demin Water',                  supplier: 'Pecos County Water District',        ratio: 9.5,  ratioUnit: 'kL/MT',  unitPrice: 1.2, priceUnit: 'EUR/kL', status: 'contracted', isUtility: true },
  ],
  // ── ETFuels Rattlesnake Gap (public-source record) ──
  etfuels_us_tx_rattlesnake_gap: [
    { feedstock: 'Renewable Electricity (BtM)', supplier: 'Behind-the-meter 500 MW Wind+Solar', ratio: 11.5, ratioUnit: 'MWh/MT', unitPrice: 30, priceUnit: 'EUR/MWh', status: 'planned', isUtility: false, capacityFactor: 0.40, firmingCost: 10 },
    { feedstock: 'Biogenic CO₂',                supplier: 'Source TBC (West Texas industrial)', ratio: 1.46, ratioUnit: 'MT/MT',  unitPrice: 50, priceUnit: 'EUR/MT',  status: 'planned', isUtility: false },
    { feedstock: 'Demin Water',                  supplier: 'Local water utility',                ratio: 9.5,  ratioUnit: 'kL/MT',  unitPrice: 1.5, priceUnit: 'EUR/kL', status: 'planned', isUtility: true },
  ],
  // ── ETFuels Näätäaapa, Finland ──
  etfuels_fi_ranua_naataaapa: [
    { feedstock: 'Renewable Electricity',        supplier: '300 MW Wind PPA (Lapland)',           ratio: 11.5, ratioUnit: 'MWh/MT', unitPrice: 35, priceUnit: 'EUR/MWh', status: 'planned', isUtility: false, capacityFactor: 0.38, firmingCost: 12 },
    { feedstock: 'Biogenic CO₂',                supplier: 'Finnish forestry/industrial chain',   ratio: 1.46, ratioUnit: 'MT/MT',  unitPrice: 65, priceUnit: 'EUR/MT',  status: 'spot', isUtility: false },
    { feedstock: 'Demin Water',                  supplier: 'Ranua municipal water',               ratio: 9.5,  ratioUnit: 'kL/MT',  unitPrice: 1.8, priceUnit: 'EUR/kL', status: 'planned', isUtility: true },
  ],
  // ── ETFuels SkyFuel Teesside ──
  // SAF via Methanol-to-Jet. e-Methanol IS the feedstock (from ETFuels pipeline).
  // H₂ from Protium is a THIRD-PARTY purchase — correctly listed as input.
  etfuels_uk_skyfuel_teesside: [
    { feedstock: 'Green H₂ (3rd party)',  supplier: 'Protium Green H₂ Partnership',    ratio: 0.21, ratioUnit: 'MT/MT',  unitPrice: 5200, priceUnit: 'EUR/MT',  status: 'planned', isUtility: false },
    { feedstock: 'Biogenic CO₂',          supplier: 'Teesside industrial capture',      ratio: 1.46, ratioUnit: 'MT/MT',  unitPrice: 85,   priceUnit: 'EUR/MT',  status: 'planned', isUtility: false },
    { feedstock: 'e-Methanol (feed)',      supplier: 'ETFuels pipeline (TX/FI)',         ratio: 1.0,  ratioUnit: 'MT/MT',  unitPrice: 800,  priceUnit: 'EUR/MT',  status: 'planned', isUtility: false },
    { feedstock: 'Renewable Electricity',  supplier: 'UK Grid PPA (REGO-backed)',        ratio: 14,   ratioUnit: 'MWh/MT', unitPrice: 72,   priceUnit: 'EUR/MWh', status: 'planned', isUtility: true, capacityFactor: 0.95, firmingCost: 0 },
  ],
  // ── Bremen H₂ ──
  // Pure electrolysis plant. Inputs: electricity + water. H₂ is the OUTPUT, not input.
  proj_bremen_h2: [
    { feedstock: 'Green Electricity',  supplier: 'North Sea Offshore Wind PPA',   ratio: 55,  ratioUnit: 'MWh/MT', unitPrice: 62,  priceUnit: 'EUR/MWh', status: 'contracted', isUtility: false, capacityFactor: 0.45, firmingCost: 5 },
    { feedstock: 'Demin Water',        supplier: 'Weserstrom Utilities GmbH',     ratio: 9,   ratioUnit: 'kL/MT',  unitPrice: 1.8, priceUnit: 'EUR/kL',  status: 'contracted', isUtility: true },
  ],
  // ── Rotterdam NH3 ──
  // Haber-Bosch: N₂ + H₂ → NH₃. H₂ from on-site PEM → unbundled to electricity + water.
  proj_rotterdam_nh3: [
    { feedstock: 'Renewable Electricity', supplier: 'Maasvlakte Grid PPA',        ratio: 12,   ratioUnit: 'MWh/MT', unitPrice: 68,   priceUnit: 'EUR/MWh', status: 'planned', isUtility: false, capacityFactor: 0.92, firmingCost: 3 },
    { feedstock: 'Nitrogen (N₂)',         supplier: 'Air Liquide Rozenburg (ASU)', ratio: 0.82, ratioUnit: 'MT/MT',  unitPrice: 180,  priceUnit: 'EUR/MT',  status: 'contracted', isUtility: false },
    { feedstock: 'Process Water',         supplier: 'Evides Waterbedrijf',         ratio: 2.5,  ratioUnit: 'kL/MT',  unitPrice: 2.1,  priceUnit: 'EUR/kL',  status: 'contracted', isUtility: true },
  ],
  // ── San Sebastián e-Methanol ──
  // On-site PEM → unbundled. Inputs: electricity + CO₂ + water.
  proj_sansebastian_emethanol: [
    { feedstock: 'Green Electricity',  supplier: 'Iberdrola Solar PPA',              ratio: 11.5, ratioUnit: 'MWh/MT', unitPrice: 58,  priceUnit: 'EUR/MWh', status: 'contracted', isUtility: false, capacityFactor: 0.25, firmingCost: 15 },
    { feedstock: 'Biogenic CO₂',      supplier: 'Papelera Guipuzcoana (pulp mill)', ratio: 1.46, ratioUnit: 'MT/MT',  unitPrice: 95,  priceUnit: 'EUR/MT',  status: 'planned', isUtility: false },
    { feedstock: 'Demin Water',        supplier: 'CAF Water Services',               ratio: 9.5,  ratioUnit: 'kL/MT',  unitPrice: 2.0, priceUnit: 'EUR/kL',  status: 'contracted', isUtility: true },
  ],
  // ── Wales SAF ──
  // Fischer-Tropsch: H₂ + CO₂ → syngas → SAF. On-site electrolysis → unbundled.
  proj_wales_saf: [
    { feedstock: 'Green Electricity',  supplier: 'National Grid Cymru PPA',    ratio: 14,   ratioUnit: 'MWh/MT', unitPrice: 72,  priceUnit: 'EUR/MWh', status: 'planned', isUtility: false, capacityFactor: 0.35, firmingCost: 10 },
    { feedstock: 'Biogenic CO₂',      supplier: 'Tata Steel Port Talbot DAC', ratio: 3.40, ratioUnit: 'MT/MT',  unitPrice: 110, priceUnit: 'EUR/MT',  status: 'planned', isUtility: false },
    { feedstock: 'Process Water',      supplier: 'Welsh Water / Dŵr Cymru',   ratio: 12,   ratioUnit: 'kL/MT',  unitPrice: 1.9, priceUnit: 'EUR/kL',  status: 'planned', isUtility: true },
  ],
  // ── Le Havre e-NG ──
  // Sabatier methanation: CO₂ + 4H₂ → CH₄ + 2H₂O. On-site PEM → unbundled.
  proj_lehavre_eng: [
    { feedstock: 'Green Electricity',  supplier: 'Normandie Offshore Wind PPA',  ratio: 13,   ratioUnit: 'MWh/MT', unitPrice: 55,  priceUnit: 'EUR/MWh', status: 'contracted', isUtility: false, capacityFactor: 0.48, firmingCost: 4 },
    { feedstock: 'Biogenic CO₂',      supplier: 'Carbon Capture Normandie SA',  ratio: 2.90, ratioUnit: 'MT/MT',  unitPrice: 88,  priceUnit: 'EUR/MT',  status: 'contracted', isUtility: false },
    { feedstock: 'Demin Water',        supplier: 'Veolia Le Havre',              ratio: 10,   ratioUnit: 'kL/MT',  unitPrice: 1.7, priceUnit: 'EUR/kL',  status: 'contracted', isUtility: true },
  ],
  // ── HamburgOne e-Methanol ──
  // On-site PEM → unbundled. Inputs: electricity + CO₂ + water.
  proj_hamburgone_emethanol: [
    { feedstock: 'Green Electricity',  supplier: 'Vattenfall Elbe Wind PPA',      ratio: 11.5, ratioUnit: 'MWh/MT', unitPrice: 62,  priceUnit: 'EUR/MWh', status: 'planned', isUtility: false, capacityFactor: 0.40, firmingCost: 8 },
    { feedstock: 'Biogenic CO₂',      supplier: 'Hamburg Waste-to-Energy Plant', ratio: 1.46, ratioUnit: 'MT/MT',  unitPrice: 105, priceUnit: 'EUR/MT',  status: 'planned', isUtility: false },
    { feedstock: 'Demin Water',        supplier: 'Hamburg Wasser',                ratio: 9.5,  ratioUnit: 'kL/MT',  unitPrice: 2.2, priceUnit: 'EUR/kL',  status: 'planned', isUtility: true },
  ],
  // ── Madrid2 San-Sebastián e-Methanol ──
  // On-site PEM → unbundled. Inputs: electricity + CO₂ + water.
  proj_madrid2_sansebastian: [
    { feedstock: 'Green Electricity',  supplier: 'Iberdrola Off-grid PPA',           ratio: 11.5, ratioUnit: 'MWh/MT', unitPrice: 55,  priceUnit: 'EUR/MWh', status: 'planned', isUtility: false, capacityFactor: 0.30, firmingCost: 12 },
    { feedstock: 'Biogenic CO₂',      supplier: 'ArcelorMittal Gijón (Green Carbon)', ratio: 1.46, ratioUnit: 'MT/MT',  unitPrice: 92,  priceUnit: 'EUR/MT',  status: 'planned', isUtility: false },
    { feedstock: 'Process Water',      supplier: 'Aguas del Añarbe',                  ratio: 9.5,  ratioUnit: 'kL/MT',  unitPrice: 1.9, priceUnit: 'EUR/kL',  status: 'planned', isUtility: true },
  ],
}

// ── Trading / Portfolio Procurement demo data ───────────────────────────────
// These are molecules bought for resale — NOT production inputs

interface TradingProcurement {
  id: string
  projectId: string | null
  project: string
  purpose: 'TRADING_PROCUREMENT'
  molecule: string
  counterparty: string
  annualVolume_mt: number
  unitPrice: number
  contractStatus: ContractStatus
  verification: VerificationState
  notes: string
}

const TRADING_PROCUREMENT: TradingProcurement[] = [
  {
    id: 'TP_01',
    projectId: null,
    project: 'Portfolio — no project link',
    purpose: 'TRADING_PROCUREMENT',
    molecule: 'e-Methanol',
    counterparty: 'OCI Global NV',
    annualVolume_mt: 15000,
    unitPrice: 920,
    contractStatus: 'INDICATIVE',
    verification: 'UNVERIFIED',
    notes: 'Spot bridge — covers Q1 2030 delivery gap before Rattlesnake Gap COD',
  },
  {
    id: 'TP_02',
    projectId: null,
    project: 'Portfolio — no project link',
    purpose: 'TRADING_PROCUREMENT',
    molecule: 'SAF',
    counterparty: 'Neste Oyj',
    annualVolume_mt: 8000,
    unitPrice: 1450,
    contractStatus: 'TERM_SHEET',
    verification: 'SUBMITTED',
    notes: 'HVO-based SAF for Lufthansa pool obligation — not ETFuels production',
  },
  {
    id: 'TP_03',
    projectId: null,
    project: 'Portfolio — no project link',
    purpose: 'TRADING_PROCUREMENT',
    molecule: 'NH3',
    counterparty: 'ACME Green Ammonia Ltd',
    annualVolume_mt: 5000,
    unitPrice: 680,
    contractStatus: 'SPOT',
    verification: 'UNVERIFIED',
    notes: 'Hedge position — ammonia market exposure balancing',
  },
]

// ── Production Input enrichment ─────────────────────────────────────────────
// Maps feedstock names to certification & capital relevance

interface InputEnrichment {
  certRelevance: CertRelevance[]
  capitalRelevance: CapitalRelevance
  itemType: string
}

const INPUT_ENRICHMENT: Record<string, InputEnrichment> = {
  'Renewable Electricity (BtM)': { certRelevance: ['45V', 'RFNBO'], capitalRelevance: 'BANKABILITY_CRITICAL', itemType: 'Energy / BtM' },
  'Renewable Electricity':       { certRelevance: ['45V', 'RFNBO'], capitalRelevance: 'BANKABILITY_CRITICAL', itemType: 'Energy / PPA' },
  'Green Electricity':           { certRelevance: ['45V', 'RFNBO'], capitalRelevance: 'BANKABILITY_CRITICAL', itemType: 'Energy / PPA' },
  'Biogenic CO₂':               { certRelevance: ['RFNBO', '45V'], capitalRelevance: 'BANKABILITY_CRITICAL', itemType: 'Carbon source' },
  'Biogenic CO2':                { certRelevance: ['RFNBO', '45V'], capitalRelevance: 'BANKABILITY_CRITICAL', itemType: 'Carbon source' },
  'Nitrogen (N₂)':              { certRelevance: ['NONE'],         capitalRelevance: 'COST_DRIVER',          itemType: 'Chemical input' },
  'Demin Water':                 { certRelevance: ['NONE'],         capitalRelevance: 'COST_DRIVER',          itemType: 'Utility' },
  'Process Water':               { certRelevance: ['NONE'],         capitalRelevance: 'COST_DRIVER',          itemType: 'Utility' },
  'Green H₂ (3rd party)':       { certRelevance: ['RFNBO', '45V'], capitalRelevance: 'BANKABILITY_CRITICAL', itemType: '3rd-party H₂' },
  'e-Methanol (feed)':           { certRelevance: ['FUELEU'],       capitalRelevance: 'COST_DRIVER',          itemType: 'Intermediate' },
}

function getEnrichment(feedstock: string): InputEnrichment {
  return INPUT_ENRICHMENT[feedstock] ?? { certRelevance: ['NONE'], capitalRelevance: 'COMMERCIAL_ONLY', itemType: 'Other' }
}

// ── Data builders ────────────────────────────────────────────────────────────

export function buildFeedstockSummary(p: CustomerProject): ProjectFeedstockSummary {
  const specs = PROJECT_FEEDSTOCK[p.id] ?? []
  const annualOutput = Math.round(p.capacity_mtpd * 330)
  const outputPrice = MOLECULE_SPOT[p.molecule]?.spot ?? 1000

  const lines: FeedstockLine[] = specs.map(s => {
    const annualVol = Math.round(annualOutput * s.ratio)
    const lcoeBasedCost = Math.round(s.ratio * s.unitPrice * 100) / 100

    // Effective cost: for electricity with CF data, adjust for capacity factor + firming
    let effectiveCost = lcoeBasedCost
    if (s.capacityFactor && s.capacityFactor > 0 && s.capacityFactor < 1) {
      const effectiveUnitPrice = s.unitPrice / s.capacityFactor + (s.firmingCost ?? 0)
      effectiveCost = Math.round(s.ratio * effectiveUnitPrice * 100) / 100
    }

    return {
      projectId: p.id,
      project: p.name,
      outputMolecule: p.molecule,
      feedstock: s.feedstock,
      supplier: s.supplier,
      ratio: s.ratio,
      ratioUnit: s.ratioUnit,
      annualVolume_mt: annualVol,
      unitPrice: s.unitPrice,
      priceUnit: s.priceUnit,
      costPerMtOutput: lcoeBasedCost,
      effectiveCostPerMtOutput: effectiveCost,
      capacityFactor: s.capacityFactor ?? 0,
      status: s.status,
      isUtility: s.isUtility,
    }
  })

  const totalFeedstockCostPerMt = lines.reduce((sum, l) => sum + l.costPerMtOutput, 0)
  const totalEffectiveCostPerMt = lines.reduce((sum, l) => sum + l.effectiveCostPerMtOutput, 0)

  return {
    projectId: p.id,
    project: p.name,
    molecule: p.molecule,
    location: p.location,
    capacity_mtpd: p.capacity_mtpd,
    annualOutput_mt: annualOutput,
    outputPrice,
    totalFeedstockCostPerMt: Math.round(totalFeedstockCostPerMt),
    totalEffectiveCostPerMt: Math.round(totalEffectiveCostPerMt),
    grossMarginPerMt: Math.round(outputPrice - totalEffectiveCostPerMt),
    lines,
    status: p.status,
  }
}

function generateEnhancedChartData(
  gran: Granularity,
  project: CustomerProject,
  detail: SalesDetail | undefined,
): EnhancedChartPoint[] {
  const pts: EnhancedChartPoint[] = []
  const base = new Date(2026, 3, 1)
  const counts: Record<Granularity, number> = { daily: 90, weekly: 52, monthly: 12, quarterly: 8, yearly: 5 }
  const n = counts[gran]
  const spot = MOLECULE_SPOT[project.molecule]?.spot ?? 1000
  const opFactor = project.status === 'operating' ? 0.92 : project.status === 'construction' ? 0.65 : 0.30

  const avail = detail?.available.volume_mtpd ?? project.capacity_mtpd * 0.85
  const soldMtpd = detail?.inMarket.filter(r => r.status === 'sold').reduce((s, r) => s + r.volume_mtpd, 0) ?? 0
  const pendingMtpd = detail?.inMarket.filter(r => r.status === 'pending').reduce((s, r) => s + r.volume_mtpd, 0) ?? 0
  const openMtpd = Math.max(0, avail - soldMtpd - pendingMtpd)
  const total = soldMtpd + pendingMtpd + openMtpd
  const soldShare = total > 0 ? soldMtpd / total : 0
  const pendingShare = total > 0 ? pendingMtpd / total : 0
  const openShare = total > 0 ? openMtpd / total : 1
  const tokenisedShare = detail ? detail.tokenised.volume_mtpd / (detail.available.volume_mtpd || 1) : 0.7

  for (let i = 0; i < n; i++) {
    const d = new Date(base)
    let label = '', tau = 0, days = 1
    switch (gran) {
      case 'daily':    d.setDate(d.getDate() + i); label = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }); tau = i / 365; days = 1; break
      case 'weekly':   d.setDate(d.getDate() + i * 7); label = `W${i + 1}`; tau = (i * 7) / 365; days = 7; break
      case 'monthly':  d.setMonth(d.getMonth() + i); label = d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }); tau = i / 12; days = 30; break
      case 'quarterly':d.setMonth(d.getMonth() + i * 3); label = `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`; tau = (i * 3) / 12; days = 90; break
      case 'yearly':   d.setFullYear(d.getFullYear() + i); label = String(d.getFullYear()); tau = i; days = 330; break
    }
    const seasonal = 0.09 * Math.sin(2 * Math.PI * (d.getMonth() / 12))
    const fwd = Math.round(spot * Math.exp((0.04 - 0.05) * tau + seasonal * Math.exp(-0.12 * tau)))
    const ramp = project.status === 'operating' ? opFactor : Math.min(opFactor, 0.1 + (opFactor - 0.1) * (1 - Math.exp(-2 * tau)))

    const maxPotential = Math.round(project.capacity_mtpd * days)
    const nominal = Math.round(project.capacity_mtpd * days * ramp * (1 + 0.04 * Math.sin(i * 1.7)))

    pts.push({
      period: label,
      maxPotential,
      sold: Math.round(nominal * soldShare),
      pending: Math.round(nominal * pendingShare),
      open: Math.round(nominal * openShare),
      tokenised: Math.round(nominal * tokenisedShare),
      forwardCurve: fwd,
      purchases: -Math.round(project.capacity_mtpd * days * ramp * 0.82 * (1 + 0.03 * Math.sin(i * 2.1))),
    })
  }
  return pts
}

// ── Badge components ────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  return (
    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border bg-gray-100 text-gray-600 border-gray-200">
      {status}
    </span>
  )
}

function MarketStatusBadge({ status }: { status: 'open' | 'pending' | 'sold' }) {
  const styles = {
    sold:    'bg-emerald-50 text-emerald-700 border-emerald-200',
    pending: 'bg-amber-50 text-amber-700 border-amber-200',
    open:    'bg-gray-100 text-gray-600 border-gray-200',
  }
  return (
    <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${styles[status]}`}>
      {status}
    </span>
  )
}

function VerifBadge({ state }: { state: VerificationState }) {
  const styles: Record<VerificationState, string> = {
    UNVERIFIED: 'bg-gray-100 text-gray-500 border-gray-300',
    SUBMITTED:  'bg-amber-50 text-amber-600 border-amber-300',
    CONFIRMED:  'bg-teal-50 text-teal-700 border-teal-300',
    AUDITED:    'bg-emerald-50 text-emerald-700 border-emerald-300',
  }
  return (
    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${styles[state]}`}>
      {state}
    </span>
  )
}

function ContractBadge({ status }: { status: ContractStatus }) {
  const styles: Record<ContractStatus, string> = {
    CONTRACTED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    TERM_SHEET: 'bg-blue-50 text-blue-700 border-blue-200',
    PLANNED:    'bg-amber-50 text-amber-600 border-amber-200',
    SPOT:       'bg-gray-100 text-gray-600 border-gray-200',
    INDICATIVE: 'bg-gray-50 text-gray-500 border-gray-200',
  }
  return (
    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${styles[status]}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

function CertBadges({ certs }: { certs: CertRelevance[] }) {
  if (certs.length === 0 || (certs.length === 1 && certs[0] === 'NONE')) return <span className="text-[9px] text-gray-300">—</span>
  return (
    <div className="flex items-center gap-0.5 flex-wrap">
      {certs.filter(c => c !== 'NONE').map(c => (
        <span key={c} className="text-[8px] font-bold uppercase px-1 py-[1px] rounded bg-violet-50 text-violet-600 border border-violet-200">
          {c}
        </span>
      ))}
    </div>
  )
}

function CapitalBadge({ rel }: { rel: CapitalRelevance }) {
  const styles: Record<CapitalRelevance, string> = {
    BANKABILITY_CRITICAL: 'text-rose-600 bg-rose-50 border-rose-200',
    COST_DRIVER:          'text-amber-600 bg-amber-50 border-amber-200',
    EVIDENCE_ITEM:        'text-blue-600 bg-blue-50 border-blue-200',
    COMMERCIAL_ONLY:      'text-gray-500 bg-gray-50 border-gray-200',
  }
  const labels: Record<CapitalRelevance, string> = {
    BANKABILITY_CRITICAL: 'Bankability',
    COST_DRIVER:          'Cost driver',
    EVIDENCE_ITEM:        'Evidence',
    COMMERCIAL_ONLY:      'Commercial',
  }
  return (
    <span className={`text-[8px] font-bold uppercase px-1 py-[1px] rounded border ${styles[rel]}`}>
      {labels[rel]}
    </span>
  )
}

function PurposeBadge({ purpose }: { purpose: ItemPurpose }) {
  const styles: Record<ItemPurpose, string> = {
    PRODUCTION_INPUT:        'bg-teal-50 text-teal-700 border-teal-200',
    TRADING_PROCUREMENT:     'bg-orange-50 text-orange-700 border-orange-200',
    OFFTAKE_SALE:            'bg-blue-50 text-blue-700 border-blue-200',
    CERTIFICATION_EVIDENCE:  'bg-violet-50 text-violet-700 border-violet-200',
  }
  const labels: Record<ItemPurpose, string> = {
    PRODUCTION_INPUT:        'Production Input',
    TRADING_PROCUREMENT:     'Trading',
    OFFTAKE_SALE:            'Offtake',
    CERTIFICATION_EVIDENCE:  'Evidence',
  }
  return (
    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${styles[purpose]}`}>
      {labels[purpose]}
    </span>
  )
}

function Tip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs">
      <div className="font-bold text-gray-900 mb-1.5">{label}</div>
      {payload.map((e: any) => (
        <div key={e.dataKey} className="flex items-center gap-2 py-0.5">
          <span className="w-2 h-2 rounded-full" style={{ background: e.color }} />
          <span className="text-gray-600">{e.name}:</span>
          <span className="font-mono font-bold text-gray-900">
            {e.dataKey === 'forwardCurve' ? `${Math.abs(e.value).toLocaleString()} EUR/t` : `${Math.abs(e.value).toLocaleString()} MT`}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Offtake binding status badge ────────────────────────────────────────────

function BindingBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    BINDING:     'bg-emerald-50 text-emerald-700 border-emerald-200',
    TERM_SHEET:  'bg-blue-50 text-blue-700 border-blue-200',
    LOI:         'bg-amber-50 text-amber-600 border-amber-200',
    MOU:         'bg-amber-50 text-amber-600 border-amber-200',
    INDICATIVE:  'bg-gray-50 text-gray-500 border-gray-200',
  }
  return (
    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${styles[status] ?? styles.INDICATIVE}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

function RelatedPartyFlag({ isRelated }: { isRelated: boolean }) {
  if (!isRelated) return null
  return (
    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border bg-rose-50 text-rose-600 border-rose-200 flex items-center gap-0.5">
      <AlertTriangle className="w-2.5 h-2.5" /> Related
    </span>
  )
}

// ── Project Economics card — flat Bloomberg-density layout ──────────────────
// Revenue (offtake) + Variable costs (inputs) → Margin. All flat, no toggles.

function ProjectEconomicsCard({
  project,
  summary,
  detail,
}: {
  project: CustomerProject
  summary: ProjectFeedstockSummary
  detail: SalesDetail | undefined
}) {
  const allLines = summary.lines
  const offtakes = project.offtakes ?? []
  const annualOutput = summary.annualOutput_mt

  // Offtake coverage
  const bindingOfftakes = offtakes.filter(o => o.binding_status === 'BINDING')
  const thirdPartyBinding = bindingOfftakes.filter(o => !o.is_related_party)
  const hasBindingThirdParty = thirdPartyBinding.length > 0
  const bindingVol = bindingOfftakes.reduce((s, o) => s + (o.volume_tpy ?? 0), 0)
  const coveragePct = annualOutput > 0 && bindingVol > 0 ? Math.round((bindingVol / annualOutput) * 100) : 0

  // Offtake price
  const avgOfftakePrice = detail
    ? Math.round(detail.inMarket.reduce((s, r) => s + r.targetPrice * r.volume_mtpd, 0) / Math.max(1, detail.inMarket.reduce((s, r) => s + r.volume_mtpd, 0)))
    : summary.outputPrice
  const margin = avgOfftakePrice - summary.totalEffectiveCostPerMt

  return (
    <div className="border-b border-gray-200 last:border-0">
      {/* ── Project header: identity + economics on one line ── */}
      <div className="px-5 py-2 bg-gray-50/60 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-bold text-gray-900 whitespace-nowrap">{project.name}</span>
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-gray-200 text-gray-600">{project.molecule}</span>
          <span className="text-[10px] text-gray-500">{project.location}</span>
          <StatusBadge status={project.status} />
        </div>
        <div className="flex items-center gap-4 text-xs font-mono whitespace-nowrap">
          <span className="text-gray-400">{annualOutput.toLocaleString()} <span className="text-[9px]">MT/yr</span></span>
          <span className="text-gray-400">Offtake <span className="font-bold text-emerald-700">{avgOfftakePrice.toLocaleString()}</span></span>
          <span className="text-gray-400">Cost <span className="text-gray-700">{summary.totalEffectiveCostPerMt.toLocaleString()}</span></span>
          <span className={`font-bold ${margin > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
            Margin {margin > 0 ? '+' : ''}{margin.toLocaleString()}
          </span>
          <span className="text-gray-400">B/E <span className="text-gray-600">{summary.totalEffectiveCostPerMt.toLocaleString()}</span></span>
          {offtakes.length > 0 && (
            <span className={coveragePct >= 50 ? 'text-emerald-600' : coveragePct > 0 ? 'text-amber-600' : 'text-rose-500'}>
              Bdg {coveragePct}%
            </span>
          )}
          {!hasBindingThirdParty && offtakes.length > 0 && (
            <span className="text-rose-500 text-[9px] font-bold">NO 3RD-PTY</span>
          )}
        </div>
      </div>

      {/* ── Revenue: offtake contracts ── */}
      <div className="px-5 py-1 flex items-center text-[10px] font-bold text-gray-400 uppercase tracking-wider border-t border-gray-100">
        <div className="w-[20%] pl-2">Revenue — Counterparty</div>
        <div className="w-[11%]">Binding</div>
        <div className="w-[6%]">Rel.</div>
        <div className="w-[12%] text-right">Volume</div>
        <div className="w-[8%] text-right">Term</div>
        <div className="w-[10%] text-right">Price</div>
        <div className="w-[8%]">Delivery</div>
        <div className="w-[7%] text-center">Verif.</div>
        <div className="w-[18%] text-right">
          {detail && (
            <span className="normal-case tracking-normal font-mono text-gray-400">
              {detail.region} · {detail.eSource} · {detail.greenEnergyPct}% green
            </span>
          )}
        </div>
      </div>

      {offtakes.length === 0 ? (
        <div className="px-5 py-2 pl-7 text-xs text-rose-400 border-t border-gray-50">
          No offtake on file — DK_G4 ACTIVE
        </div>
      ) : (
        offtakes.map((o, i) => (
          <div key={i} className="px-5 py-1 flex items-center text-xs border-t border-gray-50">
            <div className="w-[20%] pl-2 text-gray-900 font-medium truncate">{o.party}</div>
            <div className="w-[11%]"><BindingBadge status={o.binding_status} /></div>
            <div className="w-[6%]">{o.is_related_party ? <RelatedPartyFlag isRelated /> : null}</div>
            <div className="w-[12%] text-right font-mono text-gray-700">
              {o.volume_tpy ? `${o.volume_tpy.toLocaleString()} t/yr` : <span className="text-gray-400">undisclosed</span>}
            </div>
            <div className="w-[8%] text-right font-mono text-gray-500">{o.term_years ? `${o.term_years}yr` : '—'}</div>
            <div className="w-[10%] text-right text-[10px] text-gray-500">{o.price_type ?? '—'}</div>
            <div className="w-[8%] font-mono text-[10px] text-gray-500">{o.delivery_start?.slice(0, 7) ?? '—'}</div>
            <div className="w-[7%] text-center"><VerifBadge state={o.verification as VerificationState} /></div>
            <div className="w-[18%]" />
          </div>
        ))
      )}

      {/* Market allocation inline (if detail exists) — one compact line */}
      {detail && (
        <div className="px-5 py-1 pl-7 flex items-center gap-4 text-[10px] text-gray-400 border-t border-gray-50">
          {detail.inMarket.map((row, i) => (
            <span key={i} className="flex items-center gap-1">
              <MarketStatusBadge status={row.status} />
              <span className="font-mono">{row.volume_mtpd}</span>
              <span>@ {row.targetPrice.toLocaleString()}</span>
              {row.counterparty && <span className="text-gray-500">→ {row.counterparty}</span>}
            </span>
          ))}
          <span className="ml-auto">Tok: {detail.tokenised.pct}%</span>
        </div>
      )}

      {/* ── Variable costs: production inputs — all flat, no toggle ── */}
      <div className="px-5 py-1 flex items-center text-[10px] font-bold text-gray-400 uppercase tracking-wider border-t border-gray-100">
        <div className="w-[7%] pl-2">Costs — Type</div>
        <div className="w-[14%]">Input</div>
        <div className="w-[16%]">Supplier</div>
        <div className="w-[9%] text-right">Ratio</div>
        <div className="w-[8%] text-right">Volume/yr</div>
        <div className="w-[8%] text-right">Unit &#8364;</div>
        <div className="w-[8%] text-right">Eff. &#8364;/MT</div>
        <div className="w-[4%] text-center">CF</div>
        <div className="w-[6%] text-center">Ctr.</div>
        <div className="w-[5%] text-center">Vrf.</div>
        <div className="w-[7%] text-center">Cert</div>
        <div className="w-[8%] text-center">Capital</div>
      </div>

      {allLines.map((line, i) => {
        const enrich = getEnrichment(line.feedstock)
        const contractStatus: ContractStatus = line.status === 'contracted' ? 'CONTRACTED' : line.status === 'spot' ? 'SPOT' : 'PLANNED'
        const verifState: VerificationState = line.status === 'contracted' ? 'CONFIRMED' : 'UNVERIFIED'
        return (
          <div key={i} className={`px-5 py-1 flex items-center text-xs border-t border-gray-50 ${line.isUtility ? 'text-gray-400' : ''}`}>
            <div className="w-[7%] pl-2 text-[10px] text-gray-500">{enrich.itemType}</div>
            <div className={`w-[14%] ${line.isUtility ? '' : 'text-gray-900 font-medium'}`}>{line.feedstock}</div>
            <div className="w-[16%] text-[11px] truncate">{line.supplier}</div>
            <div className="w-[9%] text-right font-mono">{line.ratio} <span className="text-[9px]">{line.ratioUnit}</span></div>
            <div className="w-[8%] text-right font-mono">{line.annualVolume_mt.toLocaleString()}</div>
            <div className="w-[8%] text-right font-mono">{line.unitPrice} <span className="text-[9px]">{line.priceUnit.replace('EUR/', '€/')}</span></div>
            <div className={`w-[8%] text-right font-mono ${line.isUtility ? '' : 'font-bold text-gray-700'}`}>{line.effectiveCostPerMtOutput.toLocaleString()}</div>
            <div className="w-[4%] text-center font-mono text-[10px]">{line.capacityFactor > 0 ? `${Math.round(line.capacityFactor * 100)}%` : ''}</div>
            <div className="w-[6%] text-center"><ContractBadge status={contractStatus} /></div>
            <div className="w-[5%] text-center"><VerifBadge state={verifState} /></div>
            <div className="w-[7%] text-center"><CertBadges certs={enrich.certRelevance} /></div>
            <div className="w-[8%] text-center"><CapitalBadge rel={enrich.capitalRelevance} /></div>
          </div>
        )
      })}
    </div>
  )
}

// ── Project Economics panel ─────────────────────────────────────────────────

function ProjectEconomicsPanel({
  projects,
  feedstockSummaries,
}: {
  projects: CustomerProject[]
  feedstockSummaries: ProjectFeedstockSummary[]
}) {
  const summaryMap = useMemo(() => {
    const m = new Map<string, ProjectFeedstockSummary>()
    feedstockSummaries.forEach(s => m.set(s.projectId, s))
    return m
  }, [feedstockSummaries])

  if (projects.length === 0) {
    return <div className="px-5 py-8 text-center text-sm text-gray-400">No projects match the current filter</div>
  }

  return (
    <div>
      {projects.map(p => {
        const summary = summaryMap.get(p.id)
        if (!summary) return null
        return (
          <ProjectEconomicsCard
            key={p.id}
            project={p}
            summary={summary}
            detail={PROJECT_SALES_DETAIL[p.id]}
          />
        )
      })}
    </div>
  )
}

// ── Legacy exports for backward compat (OfftakerSupplyTable) ───────────────

export function ProductionInputsPanel({
  feedstockSummaries,
  emptyMessage = 'No production inputs match the current filter',
}: {
  feedstockSummaries: ProjectFeedstockSummary[]
  emptyMessage?: string
  renderProjectAction?: (summary: ProjectFeedstockSummary) => ReactNode
}) {
  // Legacy: renders just the input lines without offtake context
  return (
    <div>
      {feedstockSummaries.length === 0 && (
        <div className="px-5 py-8 text-center text-sm text-gray-400">{emptyMessage}</div>
      )}
      {feedstockSummaries.map(summary => (
        <div key={summary.projectId} className="border-b border-gray-100 last:border-0 px-5 py-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-semibold text-gray-900">{summary.project}</span>
            <span className="text-xs font-bold px-2 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-200">{summary.molecule}</span>
            <span className="text-xs text-gray-500">{summary.location}</span>
            <span className="ml-auto text-xs font-mono text-gray-500">Eff. cost: {summary.totalEffectiveCostPerMt.toLocaleString()} EUR/MT</span>
          </div>
          {summary.lines.map((line, i) => (
            <div key={i} className="flex items-center gap-3 text-xs py-0.5">
              <span className="text-gray-900 w-40">{line.feedstock}</span>
              <span className="text-gray-500 w-48 truncate">{line.supplier}</span>
              <span className="font-mono text-gray-500 w-24 text-right">{line.ratio} {line.ratioUnit}</span>
              <span className="font-mono font-bold text-gray-700 w-20 text-right">{line.effectiveCostPerMtOutput.toLocaleString()} €/MT</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

export function FeedstockPurchasesPanel(props: {
  feedstockSummaries: ProjectFeedstockSummary[]
  emptyMessage?: string
  renderProjectAction?: (summary: ProjectFeedstockSummary) => ReactNode
}) {
  return <ProductionInputsPanel {...props} />
}

// ── Trading Procurement panel ───────────────────────────────────────────────

function TradingProcurementPanel() {
  if (TRADING_PROCUREMENT.length === 0) {
    return <div className="px-5 py-8 text-center text-sm text-gray-400">No trading procurement items</div>
  }

  return (
    <div>
      {/* Header */}
      <div className="px-5 py-2 flex items-center text-[10px] font-bold text-gray-400 uppercase tracking-wider bg-gray-50 border-b border-gray-100">
        <div className="w-[7%] pl-4">Purpose</div>
        <div className="w-[10%]">Molecule</div>
        <div className="w-[16%]">Counterparty</div>
        <div className="w-[10%] text-right">Volume/yr</div>
        <div className="w-[9%] text-right">Unit Price</div>
        <div className="w-[8%] text-center">Contract</div>
        <div className="w-[8%] text-center">Verif.</div>
        <div className="w-[12%]">Project Link</div>
        <div className="w-[20%]">Notes</div>
      </div>
      {TRADING_PROCUREMENT.map(item => (
        <div key={item.id} className="px-5 py-2 flex items-center text-xs border-t border-gray-50">
          <div className="w-[7%] pl-4"><PurposeBadge purpose="TRADING_PROCUREMENT" /></div>
          <div className="w-[10%]">
            <span className="font-bold px-2 py-0.5 rounded bg-orange-50 text-orange-700 border border-orange-200 text-[10px]">
              {item.molecule}
            </span>
          </div>
          <div className="w-[16%] text-gray-900 font-medium truncate">{item.counterparty}</div>
          <div className="w-[10%] text-right font-mono text-gray-900 font-bold">{item.annualVolume_mt.toLocaleString()} MT</div>
          <div className="w-[9%] text-right font-mono text-gray-700">{item.unitPrice.toLocaleString()} EUR/t</div>
          <div className="w-[8%] text-center"><ContractBadge status={item.contractStatus} /></div>
          <div className="w-[8%] text-center"><VerifBadge state={item.verification} /></div>
          <div className="w-[12%] text-[10px] text-gray-400 truncate">{item.project}</div>
          <div className="w-[20%] text-[10px] text-gray-500 truncate">{item.notes}</div>
        </div>
      ))}

      {/* Classification notice */}
      <div className="px-5 py-2 bg-orange-50/50 border-t border-orange-100">
        <div className="text-[10px] text-orange-600 font-mono">
          These molecules are bought for resale, hedging, or portfolio management — not production inputs.
          They do not enter any project reactor or production pathway.
        </div>
      </div>
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────────────────

export function MarketplacePage() {
  const [tableView, setTableView] = useState<TableView>('project_economics')
  const [chartView, setChartView] = useState<ChartView>('sales')
  const [gran, setGran] = useState<Granularity>('monthly')
  const [filterMol, setFilterMol] = useState('all')
  const [filterProj, setFilterProj] = useState('all')

  const { projects } = useVisibleProjects()
  const molecules = [...new Set(projects.map(p => p.molecule))]

  const filteredProjects = useMemo(() => {
    return projects.filter(p => {
      if (filterMol !== 'all' && p.molecule !== filterMol) return false
      if (filterProj !== 'all' && p.id !== filterProj) return false
      return true
    })
  }, [projects, filterMol, filterProj])

  const chartProject = useMemo(() => {
    if (filterProj !== 'all') return projects.find(p => p.id === filterProj) ?? projects[0]
    if (filterMol !== 'all') return projects.find(p => p.molecule === filterMol) ?? projects[0]
    return projects[0]
  }, [filterProj, filterMol, projects])

  const chartDetail = PROJECT_SALES_DETAIL[chartProject.id]

  const chartData = useMemo(
    () => generateEnhancedChartData(gran, chartProject, chartDetail),
    [gran, chartProject, chartDetail],
  )

  const feedstockSummaries = useMemo(() => {
    const subset = filterProj !== 'all' ? projects.filter(p => p.id === filterProj)
      : filterMol !== 'all' ? projects.filter(p => p.molecule === filterMol) : projects
    return subset.map(p => buildFeedstockSummary(p))
  }, [projects, filterProj, filterMol])

  // KPIs
  const totalSalesVol = filteredProjects.reduce((s, p) => s + Math.round(p.capacity_mtpd * 330), 0)
  const totalInputLines = feedstockSummaries.reduce((s, fs) => s + fs.lines.length, 0)
  const bankabilityCriticalCount = feedstockSummaries.reduce((s, fs) =>
    s + fs.lines.filter(l => {
      const e = getEnrichment(l.feedstock)
      return e.capitalRelevance === 'BANKABILITY_CRITICAL'
    }).length, 0)
  const avgGrossMargin = feedstockSummaries.length > 0
    ? Math.round(feedstockSummaries.reduce((s, fs) => s + fs.grossMarginPerMt, 0) / feedstockSummaries.length)
    : 0

  const grans: { v: Granularity; l: string }[] = [
    { v: 'daily', l: 'D' }, { v: 'weekly', l: 'W' }, { v: 'monthly', l: 'M' }, { v: 'quarterly', l: 'Q' }, { v: 'yearly', l: 'Y' },
  ]

  return (
    <div className="max-w-[1440px] mx-auto space-y-6">
      {/* Header + Filters */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-black text-gray-900">Commercial</h1>
        </div>
        <div className="flex items-center gap-2">
          <select value={filterMol} onChange={e => { setFilterMol(e.target.value); setFilterProj('all') }}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white">
            <option value="all">All Molecules</option>
            {molecules.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <select value={filterProj} onChange={e => setFilterProj(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white">
            <option value="all">All Projects</option>
            {(filterMol !== 'all' ? projects.filter(p => p.molecule === filterMol) : projects)
              .map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      </div>

      {/* KPI Strip — 3 bankability signals */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Output</span>
            <span className="text-[10px] text-gray-400">{filteredProjects.length} project{filteredProjects.length !== 1 ? 's' : ''}</span>
          </div>
          <span className="text-xl font-black text-gray-900 font-mono">{totalSalesVol.toLocaleString()}</span>
          <span className="text-[10px] text-gray-400 ml-1">MT/yr</span>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Avg Margin</span>
            <span className="text-[10px] text-gray-400">{totalInputLines} inputs · {bankabilityCriticalCount} critical</span>
          </div>
          <span className={`text-xl font-black font-mono ${avgGrossMargin >= 0 ? 'text-gray-900' : 'text-red-600'}`}>
            {avgGrossMargin >= 0 ? '+' : ''}{avgGrossMargin.toLocaleString()}
          </span>
          <span className="text-[10px] text-gray-400 ml-1">EUR/MT</span>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Offtake Coverage</span>
            <span className="text-[10px] text-gray-400">{feedstockSummaries.reduce((s, fs) => s + (projects.find(p => p.id === fs.projectId)?.offtakes?.length ?? 0), 0)} contracts</span>
          </div>
          <span className="text-xl font-black text-gray-900 font-mono">
            {feedstockSummaries.length > 0
              ? Math.round(feedstockSummaries.reduce((s, fs) => {
                  const p = projects.find(pp => pp.id === fs.projectId)
                  const binding = (p?.offtakes ?? []).filter(o => o.binding_status === 'BINDING')
                  const bv = binding.reduce((a, o) => a + (o.volume_tpy ?? 0), 0)
                  return s + (fs.annualOutput_mt > 0 && bv > 0 ? (bv / fs.annualOutput_mt) * 100 : 0)
                }, 0) / feedstockSummaries.length)
              : 0}%
          </span>
          <span className="text-[10px] text-gray-400 ml-1">binding avg</span>
        </div>
      </div>

      {/* ─── Table: 2 tabs — Project Economics vs Trading ─────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-4 py-2 border-b border-gray-100 flex items-center gap-1">
          <button onClick={() => setTableView('project_economics')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold transition-colors ${tableView === 'project_economics' ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100'}`}>
            <DollarSign className="w-3 h-3" /> Project Economics
          </button>
          <button onClick={() => setTableView('trading')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold transition-colors ${tableView === 'trading' ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100'}`}>
            <Package className="w-3 h-3" /> Trading & Portfolio
          </button>
        </div>

        {tableView === 'project_economics' && (
          <ProjectEconomicsPanel
            projects={filteredProjects}
            feedstockSummaries={feedstockSummaries}
          />
        )}

        {tableView === 'trading' && (
          <TradingProcurementPanel />
        )}
      </div>

      {/* ─── Charts ───────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-3.5 border-b border-gray-100 flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold text-gray-900 mr-2">{chartProject.name} — {chartProject.molecule}</h2>
            {(['sales', 'purchases', 'combined'] as ChartView[]).map(v => (
              <button key={v} onClick={() => setChartView(v)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${chartView === v ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}>
                {v === 'sales' ? 'Output' : v === 'purchases' ? 'Inputs' : 'Combined'}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            {grans.map(g => (
              <button key={g.v} onClick={() => setGran(g.v)}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${gran === g.v ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}>
                {g.l}
              </button>
            ))}
          </div>
        </div>

        {(chartView === 'sales' || chartView === 'combined') && (
          <div className="px-5 pt-5 pb-2">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Production Segments (MT) — Gabillon forward curve overlay</span>
            </div>
            <ResponsiveContainer width="100%" height={chartView === 'combined' ? 220 : 300}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="period" tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={{ stroke: '#e5e7eb' }} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} width={50} tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)} />
                <Tooltip content={<Tip />} />
                <Bar dataKey="sold" name="Sold" stackId="output" fill="#047857" radius={[0, 0, 0, 0]} maxBarSize={36} />
                <Bar dataKey="pending" name="Pending" stackId="output" fill="#10b981" radius={[0, 0, 0, 0]} maxBarSize={36} />
                <Bar dataKey="open" name="Open" stackId="output" fill="#6ee7b7" radius={[3, 3, 0, 0]} maxBarSize={36} />
                <Line dataKey="maxPotential" name="Max Potential" type="monotone" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="6 3" dot={false} />
                <Line dataKey="tokenised" name="Tokenised" type="monotone" stroke="#0ea5a0" strokeWidth={2} dot={{ r: 2.5, fill: '#0ea5a0' }} />
                <Line dataKey="forwardCurve" name="Gabillon Forward" type="monotone" stroke="#ef4444" strokeWidth={2} strokeDasharray="6 3" dot={{ r: 2, fill: '#ef4444' }} yAxisId={0} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        {chartView === 'combined' && <div className="mx-5 border-t border-gray-100" />}

        {(chartView === 'purchases' || chartView === 'combined') && (
          <div className="px-5 pt-4 pb-3">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-2 h-2 rounded-full bg-gray-400" />
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Production Input Consumption (MT) — no forward curve</span>
            </div>
            <ResponsiveContainer width="100%" height={chartView === 'combined' ? 180 : 260}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="period" tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={{ stroke: '#e5e7eb' }} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} width={50}
                  tickFormatter={v => { const a = Math.abs(v); return a >= 1000 ? `-${(a / 1000).toFixed(1)}k` : String(v) }} domain={['dataMin', 0]} />
                <ReferenceLine y={0} stroke="#e5e7eb" />
                <Tooltip content={<Tip />} />
                <Bar dataKey="purchases" name="Input Consumption" fill="#d1d5db" radius={[0, 0, 3, 3]} maxBarSize={36} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="px-5 pb-4 flex items-center gap-5 text-xs text-gray-500 flex-wrap">
          {(chartView === 'sales' || chartView === 'combined') && (
            <>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm" style={{ background: '#047857' }} /> Sold</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm" style={{ background: '#10b981' }} /> Pending</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm" style={{ background: '#6ee7b7' }} /> Open</span>
              <span className="flex items-center gap-1.5"><span className="w-6 h-0 border-t-[1.5px] border-dashed" style={{ borderColor: '#94a3b8' }} /> Max Potential</span>
              <span className="flex items-center gap-1.5"><span className="w-6 h-0 border-t-2" style={{ borderColor: '#0ea5a0' }} /> Tokenised</span>
              <span className="flex items-center gap-1.5"><span className="w-6 h-0 border-t-2 border-dashed border-red-500" /> Gabillon Forward</span>
            </>
          )}
          {(chartView === 'purchases' || chartView === 'combined') && (
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-gray-300" /> Input Consumption (negative)</span>
          )}
        </div>
      </div>
    </div>
  )
}
