// Screen: Bankability scores screen (/bankability-scores, /finance/bankability-scores)
/**
 * BankabilityScorePage — CEO / CFO decision-first overview
 *
 * Hidalgo principle: information density → understanding
 * Sung principle: active recall, interleaving, progressive depth
 *
 * Layout (top-to-bottom, drillable):
 *   1. Project Quality Rating (GEX internal) — peer comparison chart
 *   2. Rating Trajectory — 6-month sparkline showing score trend
 *   3. Score Impact Simulator — "fix X → +Y pts → new rating" (top 3 levers)
 *   4. Bank Assessment panel — bank(s) provide own rating, gap + narrative
 *   5. Deal-killers ranked by score impact (not just severity)
 *   6. Committee Readiness binary (READY / NOT READY / CONDITIONAL)
 *   7. Attention items (verification gaps)
 *   8. Next action
 *   9. [Collapsible] Raw and effective gate scores
 */

import { useState, useMemo } from 'react'
import {
  ChevronDown, ChevronUp,
  ArrowRight, BarChart2, RefreshCw, Building2, Pencil, Save,
  TrendingUp, Zap, ArrowUpRight, ArrowDownRight, Minus, FileText,
} from 'lucide-react'
import { useActiveKillers } from '@/components/DealKillerBanner'
import type { ActiveKiller } from '@/components/DealKillerBanner'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { useNavigate } from 'react-router-dom'
import { MoleculeGatingAlert } from '@/components/finance/MoleculeGatingAlert'
import GexProjectRatingCard from '@/components/ratings/GexProjectRatingCard'
import type { ProjectRatingResponse, RatingLetter, RatingOutlook } from '@/types/projectRating'
import type { CustomerProject } from '@/data/customerProjects'
import {
  DecomposedCertaintyStack, axesFromBankability,
  AdjacencyCard, neighboursFromProjects,
} from '@/components/primitives'

// ─── Types ────────────────────────────────────────────────────────────────────

interface GateEffectiveScore {
  gate_id:          string
  raw_score:        number
  effective_score:  number
  AUDITED:          number
  CONFIRMED:        number
  SUBMITTED:        number
  UNVERIFIED:       number
}

interface AttentionItem {
  gate:    string
  issue:   string
  action:  string
  page:    string
}

interface BankRating {
  bank_name: string
  rating: RatingLetter
  outlook: RatingOutlook
  notes: string
  updated_at: string
}

/** Score Impact Simulator — what-if lever */
interface ScoreImpactLever {
  id: string
  label: string
  description: string
  pointsGain: number
  newScore: number
  newRating: RatingLetter
  effort: 'low' | 'medium' | 'high'
  page: string
}

/** Rating Trajectory — monthly snapshot */
interface TrajectoryPoint {
  month: string
  score: number
  rating: RatingLetter
  event?: string
}

// ─── Rating helpers ──────────────────────────────────────────────────────────

const RATING_ORDER: RatingLetter[] = ['AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'CCC', 'CC', 'C', 'D']

function scoreToRating(score: number): RatingLetter {
  if (score >= 92) return 'AAA'
  if (score >= 84) return 'AA'
  if (score >= 76) return 'A'
  if (score >= 68) return 'BBB'
  if (score >= 60) return 'BB'
  if (score >= 52) return 'B'
  if (score >= 44) return 'CCC'
  if (score >= 36) return 'CC'
  if (score >= 20) return 'C'
  return 'D'
}

function ratingGap(gex: RatingLetter, bank: RatingLetter): number {
  return RATING_ORDER.indexOf(bank) - RATING_ORDER.indexOf(gex)
}

function ratingToApproxScore(r: RatingLetter): number {
  const MAP: Record<RatingLetter, number> = {
    AAA: 96, AA: 88, A: 80, BBB: 72, BB: 64, B: 56, CCC: 48, CC: 36, C: 15, D: 0,
  }
  return MAP[r]
}

/** Build a fallback ProjectRatingResponse from project data (no backend needed). */
function buildFallbackRating(project: CustomerProject): ProjectRatingResponse {
  const c = project.bankability.overall_completion
  const statusBonus = project.status === 'operating' ? 12 : project.status === 'construction' ? 5 : 0

  // Base score: sqrt curve so mid-range completion maps to investable ratings
  const baseScore = Math.round((Math.sqrt(c) * 8.5 + statusBonus) * 10) / 10

  // Modifiers from quality indicators
  let modifiers = 0
  const gates = project.bankability.gates
  const avgGate = gates.length > 0 ? gates.reduce((s, g) => s + g.completion_pct, 0) / gates.length : 0
  if (avgGate > 70) modifiers += 4
  else if (avgGate > 50) modifiers += 2

  const committedCapital = project.bankability.capital_status.filter(ci =>
    ['TERM_SHEET', 'CREDIT_APPROVED', 'LEGAL_COMPLETE', 'DRAWN'].includes(ci.commitment_status),
  )
  if (committedCapital.length > 0) modifiers += 4

  modifiers -= Math.min(3, project.bankability.risk_alerts.length * 0.7)
  modifiers = Math.round(modifiers * 10) / 10

  const preliminary = Math.round((baseScore + modifiers) * 10) / 10
  const finalScore = Math.min(98, Math.max(5, preliminary))
  const rating = scoreToRating(finalScore)
  const outlook: RatingOutlook = c > 65 ? 'Positive' : c > 40 ? 'Stable' : 'Negative'

  // Peer portfolio (simulated anonymous scores)
  const peers = [91, 84, 78, 73, 69, 64, 58, 52, 46, 40, 33]
  const allScores = [...peers, finalScore].sort((a, b) => b - a)
  const rank = allScores.indexOf(finalScore) + 1

  // Derive strengths & constraints from project data
  const strengths: string[] = []
  const constraints: string[] = []

  gates.filter(g => g.is_complete).forEach(g => strengths.push(`${g.name} — complete`))
  gates.filter(g => !g.is_complete && g.completion_pct >= 70).forEach(g =>
    strengths.push(`${g.name} (${g.completion_pct}% complete)`),
  )
  if (committedCapital.length > 0) strengths.push('Capital commitment at term-sheet stage or beyond')
  if (project.status === 'operating') strengths.push('Plant is operational — revenue generating')
  if (project.status === 'construction') strengths.push('Construction phase — physical progress underway')

  project.bankability.risk_alerts.forEach(r => constraints.push(r))
  gates
    .filter(g => g.blocking_items.length > 0 && g.completion_pct < 50)
    .forEach(g => constraints.push(`${g.name}: ${g.blocking_items[0].replace(/_/g, ' ')}`))

  return {
    project_name: project.name,
    phase: project.phase,
    base_score: baseScore,
    modifier_points: modifiers,
    preliminary_score: preliminary,
    final_score: finalScore,
    rating,
    outlook,
    cap_reason: 'No cap applied',
    displayed_scale: ['AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'CCC', 'CC', 'C', 'D'],
    current_rank: rank,
    peer_count: allScores.length,
    anonymous_peer_scores: allScores,
    quantitative_inputs: {
      downside_min_dscr: 1.15 + c * 0.005,
      base_case_dscr: 1.35 + c * 0.004,
      contracted_revenue_pct: Math.min(95, c * 1.1),
    },
    pillar_scores: {
      business_market: Math.min(5, 2 + c * 0.03),
      construction_technology: Math.min(5, 2.5 + c * 0.025),
      legal_structural: Math.min(5, 2 + c * 0.028),
      sustainability: Math.min(5, 3 + c * 0.02),
    },
    gate_status: {
      land_and_permits_ok: gates.some(g => g.id.includes('G0') && g.is_complete),
      technology_wrap_ok: gates.some(g => g.id.includes('G3') && g.completion_pct >= 70),
      regulatory_path_ok: gates.some(g => g.id.includes('G2') && g.completion_pct >= 60),
      funding_path_ok: committedCapital.length > 0,
      revenue_path_ok: gates.some(g => g.id.includes('G4') && g.completion_pct >= 50),
      traceability_ok: c > 40,
    },
    key_strengths: strengths.slice(0, 4),
    key_constraints: constraints.slice(0, 4),
    methodology_label: 'GEX Quality Rating \u00b7 v2.1',
    methodology_name: 'GEX_PQR',
    methodology_version: '2.1',
    reviewer_type: 'internal',
    review_state: 'draft_screening',
  }
}

// ─── Score Impact Simulator logic ────────────────────────────────────────────

function buildImpactLevers(project: CustomerProject, currentScore: number): ScoreImpactLever[] {
  const levers: ScoreImpactLever[] = []
  const gates = project.bankability.gates

  // Lever 1: Complete lowest-completion gate with blocking items
  const worstBlockedGate = [...gates]
    .filter(g => !g.is_complete && g.blocking_items.length > 0)
    .sort((a, b) => a.completion_pct - b.completion_pct)[0]
  if (worstBlockedGate) {
    const gain = Math.round((100 - worstBlockedGate.completion_pct) * 0.08 * 10) / 10
    const ns = Math.min(98, currentScore + gain)
    levers.push({
      id: `gate-${worstBlockedGate.id}`,
      label: `Complete ${worstBlockedGate.name}`,
      description: `${worstBlockedGate.id} at ${worstBlockedGate.completion_pct}% — ${worstBlockedGate.blocking_items.length} blocker${worstBlockedGate.blocking_items.length > 1 ? 's' : ''}`,
      pointsGain: gain,
      newScore: ns,
      newRating: scoreToRating(ns),
      effort: worstBlockedGate.completion_pct > 50 ? 'medium' : 'high',
      page: '/finance/stage-gates',
    })
  }

  // Lever 2: Resolve risk alerts
  if (project.bankability.risk_alerts.length > 0) {
    const penalty = Math.min(3, project.bankability.risk_alerts.length * 0.7)
    const gain = Math.round(penalty * 10) / 10
    const ns = Math.min(98, currentScore + gain)
    levers.push({
      id: 'risk-alerts',
      label: 'Resolve all risk alerts',
      description: `${project.bankability.risk_alerts.length} active alert${project.bankability.risk_alerts.length > 1 ? 's' : ''} penalising score by ${gain} pts`,
      pointsGain: gain,
      newScore: ns,
      newRating: scoreToRating(ns),
      effort: 'medium',
      page: '/finance/stage-gates',
    })
  }

  // Lever 3: Advance verification (UNVERIFIED → CONFIRMED on weakest gates)
  const unverifiedGates = gates.filter(g => !g.is_complete && g.total_evidence > g.verified_count)
  if (unverifiedGates.length > 0) {
    const totalUnverified = unverifiedGates.reduce((s, g) => s + (g.total_evidence - g.verified_count), 0)
    const gain = Math.round(Math.min(5, totalUnverified * 0.4) * 10) / 10
    const ns = Math.min(98, currentScore + gain)
    levers.push({
      id: 'verification',
      label: 'Submit unverified evidence',
      description: `${totalUnverified} items awaiting verification across ${unverifiedGates.length} gates`,
      pointsGain: gain,
      newScore: ns,
      newRating: scoreToRating(ns),
      effort: 'low',
      page: '/finance/stage-gates',
    })
  }

  // Lever 4: Secure capital commitment (if not already committed)
  const committedCapital = project.bankability.capital_status.filter(ci =>
    ['TERM_SHEET', 'CREDIT_APPROVED', 'LEGAL_COMPLETE', 'DRAWN'].includes(ci.commitment_status),
  )
  if (committedCapital.length === 0) {
    const gain = 4
    const ns = Math.min(98, currentScore + gain)
    levers.push({
      id: 'capital',
      label: 'Secure capital term sheet',
      description: 'No committed capital — term sheet adds +4 modifier',
      pointsGain: gain,
      newScore: ns,
      newRating: scoreToRating(ns),
      effort: 'high',
      page: '/finance/capital-stack',
    })
  }

  // Lever 5: Advance to next project phase
  if (project.status === 'development') {
    const gain = 5
    const ns = Math.min(98, currentScore + gain)
    levers.push({
      id: 'phase',
      label: 'Advance to construction phase',
      description: 'Construction status adds +5 base score bonus',
      pointsGain: gain,
      newScore: ns,
      newRating: scoreToRating(ns),
      effort: 'high',
      page: '/finance/stage-gates',
    })
  }

  // Sort by points gain descending, take top 4
  return levers.sort((a, b) => b.pointsGain - a.pointsGain).slice(0, 4)
}

// ─── Rating Trajectory logic ────────────────────────────────────────────────

function buildTrajectory(project: CustomerProject, currentScore: number): TrajectoryPoint[] {
  const c = project.bankability.overall_completion
  const months = ['Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr']
  // Simulate backwards from current score — realistic growth curve
  const trajectory: TrajectoryPoint[] = []

  // Work backwards: each prior month had ~3-8% less completion
  for (let i = 0; i < months.length; i++) {
    const monthsBack = months.length - 1 - i
    const priorCompletion = Math.max(5, c - monthsBack * (3 + Math.random() * 5))
    const statusBonus = project.status === 'operating' ? 12
      : project.status === 'construction' ? (monthsBack > 3 ? 0 : 5) : 0
    const base = Math.sqrt(priorCompletion) * 8.5 + statusBonus
    // Simplified modifier estimate
    const avgGate = project.bankability.gates.length > 0
      ? project.bankability.gates.reduce((s, g) => s + Math.max(0, g.completion_pct - monthsBack * 5), 0) / project.bankability.gates.length
      : 0
    let mod = avgGate > 70 ? 4 : avgGate > 50 ? 2 : 0
    mod -= Math.min(3, project.bankability.risk_alerts.length * 0.7)
    const score = Math.min(98, Math.max(5, Math.round((base + mod) * 10) / 10))
    const point: TrajectoryPoint = { month: months[i], score, rating: scoreToRating(score) }

    // Add milestone events
    if (i === 2 && project.bankability.gates.some(g => g.id.includes('G0') && g.is_complete)) {
      point.event = 'G0 complete'
    }
    if (i === 4 && project.bankability.capital_status.some(ci => ci.commitment_status === 'TERM_SHEET')) {
      point.event = 'Term sheet signed'
    }

    trajectory.push(point)
  }

  // Override last point with actual current score
  trajectory[trajectory.length - 1] = {
    month: months[months.length - 1],
    score: currentScore,
    rating: scoreToRating(currentScore),
  }

  return trajectory
}

// ─── Deal-killer score impact estimation ────────────────────────────────────

interface RankedKiller extends ActiveKiller {
  estimatedImpact: number
  impactLabel: string
}

function rankKillersByImpact(killers: ActiveKiller[], project: CustomerProject): RankedKiller[] {
  return killers.map(k => {
    // Estimate score impact based on gate and severity
    const gate = project.bankability.gates.find(g => g.id === k.gate || k.gate.includes(g.id))
    let impact = k.severity === 'FATAL' ? 6 : 3
    if (gate) {
      // Lower completion = higher potential uplift when fixed
      impact += Math.round((100 - (gate.completion_pct ?? 50)) * 0.04)
    }
    impact = Math.min(12, impact)

    return {
      ...k,
      estimatedImpact: impact,
      impactLabel: `+${impact} pts if resolved`,
    }
  }).sort((a, b) => b.estimatedImpact - a.estimatedImpact)
}

// ─── Bank gap narrative ──────────────────────────────────────────────────────

function buildGapNarrative(
  gexRating: RatingLetter,
  bankRating: RatingLetter,
  project: CustomerProject,
): string {
  const gap = ratingGap(gexRating, bankRating)
  if (gap === 0) return 'Bank and GEX assessments are aligned. No material disagreement on credit quality.'

  const gates = project.bankability.gates
  const uncommitted = project.bankability.capital_status.filter(ci =>
    ['NONE', 'INDICATIVE'].includes(ci.commitment_status),
  )
  const lowGates = gates.filter(g => g.completion_pct < 40)
  const risks = project.bankability.risk_alerts

  if (gap > 0) {
    // Bank rates lower than GEX
    const reasons: string[] = []
    if (uncommitted.length > 0) reasons.push('uncommitted capital tranches')
    if (lowGates.length > 0) reasons.push(`${lowGates.length} gate${lowGates.length > 1 ? 's' : ''} below 40%`)
    if (risks.length > 0) reasons.push(`${risks.length} unresolved risk alert${risks.length > 1 ? 's' : ''}`)
    if (project.status === 'development') reasons.push('pre-construction stage')

    const reasonText = reasons.length > 0
      ? `likely due to ${reasons.join(', ')}`
      : 'likely reflecting more conservative credit methodology'
    return `Bank rates ${gap} notch${gap > 1 ? 'es' : ''} below GEX ${reasonText}. Closing the gap requires addressing the bank's specific concerns, which typically align with the lowest-scoring gates.`
  }

  // Bank rates higher than GEX
  return `Bank rates ${Math.abs(gap)} notch${Math.abs(gap) > 1 ? 'es' : ''} above GEX. This may reflect the bank's view on sponsor quality or market factors not yet captured in GEX gate completion. Consider whether GEX gates are lagging actual project progress.`
}

// ─── Constraint → route mapping ────────────────────────────────────────────

function constraintRoute(text: string): string {
  const t = text.toLowerCase()
  if (t.includes('insurance') || t.includes('g7')) return '/finance/insurance'
  if (t.includes('capital') || t.includes('funding') || t.includes('term sheet')) return '/finance/capital-stack'
  if (t.includes('offtake') || t.includes('g4') || t.includes('revenue')) return '/finance/stage-gates'
  if (t.includes('certification') || t.includes('45v') || t.includes('rfnbo')) return '/sustainability/cert-readiness'
  if (t.includes('epc') || t.includes('g5') || t.includes('technology') || t.includes('g3')) return '/finance/stage-gates'
  return '/finance/stage-gates'
}

function enrichConstraints(constraints: string[]): Array<{ text: string; route: string }> {
  return constraints.map(text => ({ text, route: constraintRoute(text) }))
}

// ─── Report generation ─────────────────────────────────────────────────────

function generateReport(
  project: CustomerProject,
  ratingData: ProjectRatingResponse,
  readiness: string,
  rankedKillers: RankedKiller[],
  attentionItems: AttentionItem[],
): string {
  const lines: string[] = []
  const hr = '─'.repeat(50)

  lines.push('BANKABILITY STATUS REPORT')
  lines.push(hr)
  lines.push(`Project:     ${project.name}`)
  lines.push(`Date:        ${new Date().toISOString().slice(0, 10)}`)
  lines.push(`Rating:      ${ratingData.rating} (${ratingData.final_score.toFixed(1)}) · ${ratingData.outlook}`)
  lines.push(`Phase:       ${project.phase}`)
  lines.push(`Methodology: ${ratingData.methodology_label}`)
  lines.push('')
  lines.push(`COMMITTEE READINESS: ${readiness.replace('_', ' ')}`)
  lines.push(hr)

  if (ratingData.key_strengths.length > 0) {
    lines.push('')
    lines.push('STRENGTHS')
    ratingData.key_strengths.forEach(s => lines.push(`  · ${s}`))
  }

  if (ratingData.key_constraints.length > 0) {
    lines.push('')
    lines.push('CONSTRAINTS')
    ratingData.key_constraints.forEach(c => lines.push(`  · ${c}`))
  }

  if (rankedKillers.length > 0 || attentionItems.length > 0) {
    lines.push('')
    lines.push('ACTION ITEMS (Priority Order)')
    lines.push(hr)
    let n = 0
    rankedKillers.forEach(k => {
      n++
      lines.push(`  ${n}. [${k.severity}] ${k.plain_language}`)
      lines.push(`     Impact: ${k.impactLabel}`)
    })
    attentionItems.forEach(a => {
      n++
      lines.push(`  ${n}. [ATTENTION] ${a.gate}: ${a.issue}`)
      lines.push(`     Action: ${a.action}`)
    })
  }

  lines.push('')
  lines.push('RATING MECHANICS')
  lines.push(`  Base: ${ratingData.base_score.toFixed(1)}`)
  lines.push(`  Modifiers: ${ratingData.modifier_points >= 0 ? '+' : ''}${ratingData.modifier_points.toFixed(1)}`)
  lines.push(`  Final: ${ratingData.final_score.toFixed(1)}`)

  lines.push('')
  lines.push(hr)
  lines.push(`Generated by GEX Platform · ${new Date().toISOString().slice(0, 10)}`)

  return lines.join('\n')
}

// ─── Demo data ───────────────────────────────────────────────────────────────

const DEMO_GATE_SCORES: GateEffectiveScore[] = [
  { gate_id: 'G0', raw_score: 100, effective_score: 90, AUDITED: 1, CONFIRMED: 3, SUBMITTED: 0, UNVERIFIED: 0 },
  { gate_id: 'G1', raw_score: 95, effective_score: 76, AUDITED: 1, CONFIRMED: 2, SUBMITTED: 1, UNVERIFIED: 0 },
  { gate_id: 'G2', raw_score: 90, effective_score: 85, AUDITED: 2, CONFIRMED: 2, SUBMITTED: 0, UNVERIFIED: 0 },
  { gate_id: 'G3', raw_score: 80, effective_score: 44, AUDITED: 0, CONFIRMED: 1, SUBMITTED: 2, UNVERIFIED: 1 },
  { gate_id: 'G4', raw_score: 78, effective_score: 39, AUDITED: 0, CONFIRMED: 3, SUBMITTED: 2, UNVERIFIED: 1 },
  { gate_id: 'G5', raw_score: 45, effective_score: 11, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 1, UNVERIFIED: 4 },
  { gate_id: 'G6', raw_score: 40, effective_score: 10, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 1, UNVERIFIED: 2 },
  { gate_id: 'G7', raw_score: 30, effective_score: 8, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 0, UNVERIFIED: 3 },
  { gate_id: 'G8', raw_score: 68, effective_score: 65, AUDITED: 1, CONFIRMED: 5, SUBMITTED: 0, UNVERIFIED: 0 },
  { gate_id: 'G9', raw_score: 20, effective_score: 9, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 2, UNVERIFIED: 2 },
  { gate_id: 'G10', raw_score: 10, effective_score: 3, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 0, UNVERIFIED: 4 },
  { gate_id: 'G11', raw_score: 5, effective_score: 1, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 0, UNVERIFIED: 2 },
]

const DEMO_ATTENTION: AttentionItem[] = [
  {
    gate: 'G5', issue: '4 evidence items are UNVERIFIED — EPC risk gate cannot advance.',
    action: 'Submit EPC contract and performance guarantee for third-party confirmation.',
    page: '/finance/stage-gates',
  },
  {
    gate: 'G6', issue: 'No independent engineer appointed. Gate cannot progress.',
    action: 'Appoint named IE firm and confirm scope.',
    page: '/finance/stage-gates',
  },
  {
    gate: 'G7', issue: 'Insurance programme not placed. All items UNVERIFIED.',
    action: 'Bind CAR/EAR and DSU insurance lines.',
    page: '/finance/insurance',
  },
]

// ─── Main component ──────────────────────────────────────────────────────────

export default function BankabilityScorePage() {
  const navigate = useNavigate()
  const { selectedProjectId } = useSelectedProject()
  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId) ?? visibleProjects[0]
  const { killers } = useActiveKillers(project.id)

  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showImpactSim, setShowImpactSim] = useState(true)
  const [reportCopied, setReportCopied] = useState(false)

  const fatalKillers = killers.filter(k => k.severity === 'FATAL')
  const readiness =
    fatalKillers.length > 0 ? 'NOT_READY' :
      killers.length > 0 ? 'CONDITIONAL' :
        'READY'

  // Rating — derived from project data (works without backend)
  const ratingData = useMemo(() => buildFallbackRating(project), [project])

  // NEW: Score Impact Simulator levers
  const impactLevers = useMemo(
    () => buildImpactLevers(project, ratingData.final_score),
    [project, ratingData.final_score],
  )

  // NEW: Rating Trajectory (6-month history)
  const trajectory = useMemo(
    () => buildTrajectory(project, ratingData.final_score),
    [project, ratingData.final_score],
  )

  // NEW: Deal-killers ranked by estimated score impact
  const rankedKillers = useMemo(
    () => rankKillersByImpact(killers, project),
    [killers, project],
  )

  // Trajectory delta
  const trajectoryDelta = trajectory.length >= 2
    ? Math.round((trajectory[trajectory.length - 1].score - trajectory[0].score) * 10) / 10
    : 0

  // Enriched constraints with routes for rating card
  const constraintActions = useMemo(
    () => enrichConstraints(ratingData.key_constraints),
    [ratingData.key_constraints],
  )

  // Report export
  const handleExportReport = async () => {
    const report = generateReport(project, ratingData, readiness, rankedKillers, DEMO_ATTENTION)
    try {
      await navigator.clipboard.writeText(report)
    } catch {
      // Fallback: open report in a new window for copy/paste
      const w = window.open('', '_blank', 'width=700,height=600')
      if (w) {
        w.document.write(`<pre style="font-family:monospace;white-space:pre-wrap;padding:24px">${report}</pre>`)
        w.document.title = 'GEX Bankability Report'
      }
    }
    setReportCopied(true)
    setTimeout(() => setReportCopied(false), 2000)
  }

  return (
    <div className="space-y-5 max-w-5xl mx-auto">
      {/* ── Page header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">Bankability Status<span className="ml-3">{project.name}</span></h1>
          <p className="text-xs text-gray-500 mt-0.5">{project.name} &middot; {project.phase}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExportReport}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-xs font-medium text-gray-600 hover:bg-gray-50"
          >
            <FileText className="w-3.5 h-3.5" />
            {reportCopied ? 'Copied!' : 'Export Report'}
          </button>
          <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-xs font-medium text-gray-600 hover:bg-gray-50">
            <RefreshCw className="w-3.5 h-3.5" />
            Re-evaluate
          </button>
        </div>
      </div>

      {/* ── 1. Project Quality Rating (GEX internal + peer comparison) ── */}
      <GexProjectRatingCard data={ratingData} constraintActions={constraintActions} onNavigate={r => navigate(r)} />

      {/* ── 2. Rating Trajectory — 6-month sparkline ── */}
      <RatingTrajectory trajectory={trajectory} delta={trajectoryDelta} />

      {/* ── E.3 Decomposed Certainty Stack + E.4 Adjacency Card ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3">
          <div className="flex items-center gap-2 mb-2">
            <BarChart2 className="w-3.5 h-3.5 text-gray-400" />
            <h3 className="text-xs font-bold text-gray-600">Certainty Decomposition</h3>
            <InfoTooltip text="Weighted certainty per axis: COST · REVENUE · CERTIFICATION · EXECUTION · COUNTERPARTY. Fill = raw_score × verification_weight. Red ≥0.50 amber, green ≥0.75. Lock = blocking gate." />
          </div>
          <DecomposedCertaintyStack
            axes={axesFromBankability({
              score: project.bankability.overall_completion,
              sub_scores: undefined,
            })}
            effective_score={project.bankability.overall_completion / 100}
            threshold={0.70}
          />
        </div>
        <AdjacencyCard
          focal_project_id={project.id}
          focal_project_name={project.name}
          neighbours={neighboursFromProjects(project, visibleProjects)}
          platform_density={Math.min(1, visibleProjects.length / 20)}
          max_shown={3}
        />
      </div>

      {/* ── 3. Score Impact Simulator ── */}
      {impactLevers.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <button
            onClick={() => setShowImpactSim(v => !v)}
            className="w-full flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" />
              <h3 className="text-sm font-bold text-gray-700">Score Impact Simulator</h3>
              <span className="text-[10px] text-gray-400 font-medium">Fix X &rarr; +Y pts &rarr; new rating</span>
            </div>
            {showImpactSim
              ? <ChevronUp className="w-4 h-4 text-gray-400" />
              : <ChevronDown className="w-4 h-4 text-gray-400" />}
          </button>
          {showImpactSim && (
            <div className="px-5 pb-4 space-y-2">
              {impactLevers.map(lever => {
                const ratingChanged = lever.newRating !== ratingData.rating
                return (
                  <div
                    key={lever.id}
                    className="flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-4 py-2.5 hover:border-gray-200 transition-colors"
                  >
                    {/* Gain badge */}
                    <div className="flex-shrink-0 w-16 text-center">
                      <span className="text-sm font-black text-emerald-600">+{lever.pointsGain}</span>
                      <span className="text-[10px] text-gray-400 block">pts</span>
                    </div>

                    {/* Description */}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-gray-800">{lever.label}</p>
                      <p className="text-[11px] text-gray-500 mt-0.5">{lever.description}</p>
                    </div>

                    {/* Result */}
                    <div className="flex-shrink-0 text-right">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-gray-400 font-mono">{ratingData.rating}</span>
                        <ArrowRight className="w-3 h-3 text-gray-300" />
                        <span className={`text-sm font-black ${ratingChanged ? 'text-emerald-600' : 'text-gray-700'}`}>
                          {lever.newRating}
                        </span>
                      </div>
                      <span className="text-[10px] text-gray-400 font-mono">{lever.newScore.toFixed(1)}</span>
                    </div>

                    {/* Effort + action */}
                    <div className="flex-shrink-0 flex items-center gap-2">
                      <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                        lever.effort === 'low' ? 'bg-green-100 text-green-700' :
                        lever.effort === 'medium' ? 'bg-amber-100 text-amber-700' :
                        'bg-red-100 text-red-700'
                      }`}>
                        {lever.effort}
                      </span>
                      <button
                        onClick={() => navigate(lever.page)}
                        className="text-xs font-semibold text-teal-600 hover:text-teal-800 flex items-center gap-0.5"
                      >
                        Go <ArrowRight className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                )
              })}
              <p className="text-[10px] text-gray-400 pt-1">
                Estimates are additive approximations. Actual score depends on gate interdependencies and verification state.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── 4. Bank Rating Comparison ── */}
      <BankRatingPanel
        projectId={project.id}
        gexRating={ratingData.rating}
        gexScore={ratingData.final_score}
        project={project}
      />

      {/* ── 5. Molecule-specific hazmat gating (NH3 / SAF only) ── */}
      <MoleculeGatingAlert project={project} />

      {/* ── 6. Unified Action Plan (deal-killers + attention + readiness + next step) ── */}
      <ActionPlan
        readiness={readiness}
        rankedKillers={rankedKillers}
        attentionItems={DEMO_ATTENTION}
        navigate={navigate}
      />

      {/* ── 10. Advanced: gate scores (collapsible) ── */}
      <div className="rounded-lg border border-gray-200 overflow-hidden">
        <button
          onClick={() => setShowAdvanced(v => !v)}
          className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-sm font-semibold text-gray-600"
        >
          <div className="flex items-center gap-2">
            <BarChart2 className="w-4 h-4 text-gray-400" />
            Advanced: Gate scores
            <InfoTooltip text={`Raw scores reflect evidence completion. Effective scores are weighted by verification state (UNVERIFIED\u00d70.25 \u2192 AUDITED\u00d71.00). State machine uses effective scores.`} />
          </div>
          {showAdvanced
            ? <ChevronUp className="w-4 h-4 text-gray-400" />
            : <ChevronDown className="w-4 h-4 text-gray-400" />
          }
        </button>

        {showAdvanced && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="text-left px-4 py-2 font-semibold text-gray-500">Gate</th>
                  <th className="text-right px-3 py-2 font-semibold text-gray-500">Raw</th>
                  <th className="text-right px-3 py-2 font-semibold text-gray-700">Effective</th>
                  <th className="text-right px-3 py-2 font-semibold text-green-600">Aud</th>
                  <th className="text-right px-3 py-2 font-semibold text-blue-600">Conf</th>
                  <th className="text-right px-3 py-2 font-semibold text-amber-600">Sub</th>
                  <th className="text-right px-3 py-2 font-semibold text-gray-400">Unver</th>
                </tr>
              </thead>
              <tbody>
                {DEMO_GATE_SCORES.map(g => (
                  <tr key={g.gate_id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2 font-semibold text-gray-700">{g.gate_id}</td>
                    <td className="px-3 py-2 text-right text-gray-400 tabular-nums">{g.raw_score}</td>
                    <td className="px-3 py-2 text-right font-semibold text-gray-800 tabular-nums">
                      {g.effective_score}
                      <span className="ml-1 text-gray-400 font-normal">
                        ({Math.round((g.effective_score / Math.max(g.raw_score, 1)) * 100)}%)
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-green-700 tabular-nums">{g.AUDITED}</td>
                    <td className="px-3 py-2 text-right text-blue-700 tabular-nums">{g.CONFIRMED}</td>
                    <td className="px-3 py-2 text-right text-amber-600 tabular-nums">{g.SUBMITTED}</td>
                    <td className="px-3 py-2 text-right text-gray-400 tabular-nums">{g.UNVERIFIED}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-4 py-2 bg-gray-50 border-t border-gray-200">
              <p className="text-[10px] text-gray-400">
                Effective = Raw &times; mean(verification weights). State machine transitions use effective scores.
                Raw scores are retained for reference only.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Rating Trajectory (sparkline + milestone markers) ──────────────────────

function RatingTrajectory({ trajectory, delta }: { trajectory: TrajectoryPoint[]; delta: number }) {
  if (trajectory.length < 2) return null

  const scores = trajectory.map(t => t.score)
  const minScore = Math.min(...scores) - 5
  const maxScore = Math.max(...scores) + 5
  const range = maxScore - minScore || 1

  // SVG sparkline dimensions
  const W = 400
  const H = 60
  const PAD_X = 8
  const PAD_Y = 6

  const points = trajectory.map((t, i) => {
    const x = PAD_X + (i / (trajectory.length - 1)) * (W - PAD_X * 2)
    const y = PAD_Y + (1 - (t.score - minScore) / range) * (H - PAD_Y * 2)
    return { x, y, ...t }
  })

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')

  // Gradient area
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${H - PAD_Y} L ${points[0].x} ${H - PAD_Y} Z`

  const current = trajectory[trajectory.length - 1]
  const DeltaIcon = delta > 0 ? ArrowUpRight : delta < 0 ? ArrowDownRight : Minus
  const deltaColor = delta > 0 ? 'text-emerald-600' : delta < 0 ? 'text-red-600' : 'text-gray-500'

  return (
    <div className="rounded-xl border border-gray-200 bg-white px-5 py-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-bold text-gray-700">Rating Trajectory</h3>
          <span className="text-[10px] text-gray-400">6-month trend</span>
        </div>
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-1 ${deltaColor}`}>
            <DeltaIcon className="w-3.5 h-3.5" />
            <span className="text-sm font-bold">{delta > 0 ? '+' : ''}{delta}</span>
            <span className="text-[10px] text-gray-400">pts</span>
          </div>
          <div className="text-right">
            <span className="text-xs text-gray-400">Current </span>
            <span className="text-sm font-black text-gray-900">{current.rating}</span>
            <span className="text-xs text-gray-400 font-mono ml-1">{current.score.toFixed(1)}</span>
          </div>
        </div>
      </div>

      {/* Sparkline */}
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-16" preserveAspectRatio="none">
          {/* Gradient fill */}
          <defs>
            <linearGradient id="trajGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0ea5a0" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#0ea5a0" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={areaPath} fill="url(#trajGrad)" />
          <path d={linePath} fill="none" stroke="#0ea5a0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />

          {/* Data points */}
          {points.map((p, i) => (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={i === points.length - 1 ? 4 : 2.5}
              fill={i === points.length - 1 ? '#0ea5a0' : 'white'}
              stroke="#0ea5a0"
              strokeWidth={i === points.length - 1 ? 2 : 1.5}
            />
          ))}

          {/* Milestone markers */}
          {points.filter(p => p.event).map((p, i) => (
            <g key={`ev-${i}`}>
              <line x1={p.x} y1={p.y + 6} x2={p.x} y2={H - PAD_Y} stroke="#0ea5a0" strokeWidth="0.5" strokeDasharray="2 2" />
            </g>
          ))}
        </svg>

        {/* Month labels + events below chart */}
        <div className="flex justify-between mt-1 px-2">
          {trajectory.map((t, i) => (
            <div key={i} className="text-center" style={{ width: `${100 / trajectory.length}%` }}>
              <span className={`text-[10px] font-medium ${i === trajectory.length - 1 ? 'text-gray-800 font-bold' : 'text-gray-400'}`}>
                {t.month}
              </span>
              {t.event && (
                <p className="text-[9px] text-teal-600 font-medium mt-0.5 leading-tight">{t.event}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Rating band boundaries */}
      <div className="flex items-center gap-1 mt-2">
        {(['A', 'BBB', 'BB', 'B', 'CCC'] as const).map(r => (
          <div
            key={r}
            className={`flex-1 text-center text-[9px] py-0.5 rounded ${
              r === current.rating
                ? 'bg-teal-100 text-teal-700 font-bold'
                : 'bg-gray-50 text-gray-400'
            }`}
          >
            {r}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Bank Rating Panel ───────────────────────────────────────────────────────

function BankRatingPanel({
  projectId, gexRating, gexScore, project,
}: { projectId: string; gexRating: RatingLetter; gexScore: number; project: CustomerProject }) {
  const storageKey = `gex_bank_rating_${projectId}`

  const [bankRating, setBankRating] = useState<BankRating | null>(() => {
    try {
      const stored = localStorage.getItem(storageKey)
      return stored ? JSON.parse(stored) : null
    } catch { return null }
  })
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    bank_name: bankRating?.bank_name ?? '',
    rating: bankRating?.rating ?? 'BBB' as RatingLetter,
    outlook: bankRating?.outlook ?? 'Stable' as RatingOutlook,
    notes: bankRating?.notes ?? '',
  })

  const save = () => {
    const saved: BankRating = { ...form, updated_at: new Date().toISOString() }
    localStorage.setItem(storageKey, JSON.stringify(saved))
    setBankRating(saved)
    setEditing(false)
  }

  const gap = bankRating ? ratingGap(gexRating, bankRating.rating) : null
  const gapLabel = gap === null ? null
    : gap === 0 ? 'Aligned'
      : gap > 0 ? `Bank ${gap} notch${gap > 1 ? 'es' : ''} below GEX`
        : `Bank ${Math.abs(gap)} notch${Math.abs(gap) > 1 ? 'es' : ''} above GEX`
  const gapColor = gap === null ? '' : gap === 0 ? 'text-emerald-600' : gap > 0 ? 'text-amber-600' : 'text-blue-600'

  // NEW: Gap narrative
  const gapNarrative = bankRating
    ? buildGapNarrative(gexRating, bankRating.rating, project)
    : null

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Building2 className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-bold text-gray-700">Bank Assessment</h3>
          <InfoTooltip text="Authorised banks can submit their own credit assessment for this project. This enables side-by-side comparison with the GEX internal rating." />
        </div>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium text-gray-500 hover:bg-gray-100 transition-colors"
          >
            <Pencil className="w-3 h-3" /> {bankRating ? 'Edit' : 'Add Bank Rating'}
          </button>
        )}
      </div>

      {editing ? (
        <div className="px-5 py-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Bank Name</label>
              <input
                type="text"
                value={form.bank_name}
                onChange={e => setForm(f => ({ ...f, bank_name: e.target.value }))}
                placeholder="e.g. NordLB"
                className="mt-1 w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm bg-white"
              />
            </div>
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Credit Rating</label>
              <select
                value={form.rating}
                onChange={e => setForm(f => ({ ...f, rating: e.target.value as RatingLetter }))}
                className="mt-1 w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm bg-white"
              >
                {RATING_ORDER.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Outlook</label>
              <select
                value={form.outlook}
                onChange={e => setForm(f => ({ ...f, outlook: e.target.value as RatingOutlook }))}
                className="mt-1 w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm bg-white"
              >
                <option value="Positive">Positive</option>
                <option value="Stable">Stable</option>
                <option value="Negative">Negative</option>
              </select>
            </div>
            <div className="flex items-end gap-2">
              <button onClick={save} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-gray-900 text-white text-xs font-semibold hover:bg-gray-800 transition-colors">
                <Save className="w-3 h-3" /> Save
              </button>
              <button onClick={() => setEditing(false)} className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 hover:bg-gray-100 transition-colors">
                Cancel
              </button>
            </div>
          </div>
          <div>
            <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Notes (optional)</label>
            <textarea
              value={form.notes}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              rows={2}
              placeholder="Assessment rationale, conditions, reservations..."
              className="mt-1 w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm bg-white resize-none"
            />
          </div>
        </div>
      ) : bankRating ? (
        <div className="px-5 py-4">
          {/* Comparison strip */}
          <div className="flex items-center gap-4 flex-wrap">
            {/* GEX rating */}
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">GEX Internal</span>
              <span className="text-xl font-black text-gray-900">{gexRating}</span>
              <span className="text-xs text-gray-500 font-mono">{gexScore.toFixed(1)}</span>
            </div>

            {/* Gap indicator */}
            <div className="flex items-center gap-1.5">
              <div className="w-8 h-px bg-gray-300" />
              <span className={`text-xs font-bold ${gapColor}`}>{gapLabel}</span>
              <div className="w-8 h-px bg-gray-300" />
            </div>

            {/* Bank rating */}
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{bankRating.bank_name || 'Bank'}</span>
              <span className="text-xl font-black text-gray-900">{bankRating.rating}</span>
              <span className="text-xs text-gray-500">{bankRating.outlook}</span>
            </div>
          </div>

          {/* Visual bars */}
          <div className="mt-3 space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="w-20 text-[10px] text-gray-400 text-right">GEX</span>
              <div className="flex-1 bg-gray-100 rounded-full h-2">
                <div className="h-full rounded-full bg-teal-500" style={{ width: `${Math.min(100, gexScore)}%` }} />
              </div>
              <span className="w-8 text-[10px] font-mono text-gray-500 text-right">{gexScore.toFixed(0)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-20 text-[10px] text-gray-400 text-right">{bankRating.bank_name || 'Bank'}</span>
              <div className="flex-1 bg-gray-100 rounded-full h-2">
                <div
                  className={`h-full rounded-full ${gap !== null && gap > 0 ? 'bg-amber-400' : 'bg-blue-500'}`}
                  style={{ width: `${Math.min(100, ratingToApproxScore(bankRating.rating))}%` }}
                />
              </div>
              <span className="w-8 text-[10px] font-mono text-gray-500 text-right">
                {ratingToApproxScore(bankRating.rating)}
              </span>
            </div>
          </div>

          {/* NEW: Gap narrative */}
          {gapNarrative && (
            <div className={`mt-3 rounded-lg px-3 py-2 text-xs leading-relaxed ${
              gap === 0 ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
              (gap ?? 0) > 0 ? 'bg-amber-50 text-amber-700 border border-amber-200' :
              'bg-blue-50 text-blue-700 border border-blue-200'
            }`}>
              {gapNarrative}
            </div>
          )}

          {bankRating.notes && (
            <p className="mt-3 text-xs text-gray-500 italic border-l-2 border-gray-200 pl-3">{bankRating.notes}</p>
          )}
          <p className="mt-2 text-[10px] text-gray-400">
            Last updated: {new Date(bankRating.updated_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
          </p>
        </div>
      ) : (
        <div className="px-5 py-4 text-xs text-gray-400">
          No bank assessment submitted yet. Click &ldquo;Add Bank Rating&rdquo; to enter a credit assessment from an authorised lender.
        </div>
      )}
    </div>
  )
}

// ─── Unified Action Plan ────────────────────────────────────────────────────

function ActionPlan({
  readiness, rankedKillers, attentionItems, navigate,
}: {
  readiness: string
  rankedKillers: RankedKiller[]
  attentionItems: AttentionItem[]
  navigate: (path: string) => void
}) {
  const fatal = rankedKillers.filter(k => k.severity === 'FATAL')
  const critical = rankedKillers.filter(k => k.severity === 'CRITICAL')

  const statusLabel = readiness === 'READY' ? 'READY' : readiness === 'CONDITIONAL' ? 'CONDITIONAL' : 'BLOCKED'
  const statusBadge = readiness === 'READY'
    ? 'bg-emerald-100 text-emerald-700'
    : readiness === 'CONDITIONAL'
      ? 'bg-amber-100 text-amber-700'
      : 'bg-red-100 text-red-700'
  const statusSummary = readiness === 'READY'
    ? 'All clear — no blocking items'
    : readiness === 'CONDITIONAL'
      ? `${critical.length} critical · ${attentionItems.length} verification gap${attentionItems.length !== 1 ? 's' : ''}`
      : `${fatal.length} fatal · ${critical.length} critical · ${attentionItems.length} gap${attentionItems.length !== 1 ? 's' : ''}`

  const nextRoute = readiness === 'READY' ? '/finance/ic-pack' : '/finance/stage-gates'
  const nextLabel = readiness === 'READY'
    ? 'Generate IC Pack'
    : readiness === 'CONDITIONAL'
      ? 'Resolve critical items or obtain waivers'
      : 'Resolve FATAL deal-killers'
  const nextButton = readiness === 'READY' ? 'IC Pack Builder' : readiness === 'CONDITIONAL' ? 'View Gates' : 'View Blockers'

  // Pre-compute numbering offsets (no mutable state during render)
  const fatalStart = 1
  const criticalStart = fatalStart + fatal.length
  const attentionStart = criticalStart + critical.length

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      {/* Status header */}
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-gray-800">Action Plan</h3>
          <p className="text-xs text-gray-500 mt-0.5">{statusSummary}</p>
        </div>
        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded ${statusBadge}`}>
          {statusLabel}
        </span>
      </div>

      {fatal.length === 0 && critical.length === 0 && attentionItems.length === 0 ? (
        <div className="px-5 py-4 text-xs text-gray-500">
          No action items. Project may proceed to committee.
        </div>
      ) : (
        <div className="divide-y divide-gray-100">
          {/* FATAL blockers */}
          {fatal.length > 0 && (
            <div className="px-5 py-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-red-600 mb-2">
                Blockers — resolve first
              </div>
              <div className="space-y-1">
                {fatal.map((k, i) => (
                  <div key={k.id} className="flex items-center gap-3 py-1 text-xs">
                    <span className="w-5 text-right font-mono font-bold text-gray-400">{fatalStart + i}.</span>
                    <span className="shrink-0 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-red-100 text-red-700">fatal</span>
                    <span className="flex-1 text-gray-700 truncate">{k.plain_language}</span>
                    <span className="shrink-0 font-mono text-[11px] text-gray-400">{k.impactLabel}</span>
                    <button onClick={() => navigate(k.page)} className="shrink-0 text-xs font-semibold text-teal-600 hover:text-teal-800">Fix &rarr;</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* CRITICAL items */}
          {critical.length > 0 && (
            <div className="px-5 py-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-amber-600 mb-2">
                Critical — waiver or resolution required
              </div>
              <div className="space-y-1">
                {critical.map((k, i) => (
                  <div key={k.id} className="flex items-center gap-3 py-1 text-xs">
                    <span className="w-5 text-right font-mono font-bold text-gray-400">{criticalStart + i}.</span>
                    <span className="shrink-0 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">critical</span>
                    <span className="flex-1 text-gray-700 truncate">{k.plain_language}</span>
                    <span className="shrink-0 font-mono text-[11px] text-gray-400">{k.impactLabel}</span>
                    <button onClick={() => navigate(k.page)} className="shrink-0 text-xs font-semibold text-teal-600 hover:text-teal-800">Fix &rarr;</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Verification gaps */}
          {attentionItems.length > 0 && (
            <div className="px-5 py-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-2">
                Verification gaps
              </div>
              <div className="space-y-1">
                {attentionItems.map((item, i) => (
                  <div key={item.gate} className="flex items-center gap-3 py-1 text-xs">
                    <span className="w-5 text-right font-mono font-bold text-gray-400">{attentionStart + i}.</span>
                    <span className="shrink-0 text-[10px] font-bold text-gray-500 w-6">{item.gate}</span>
                    <span className="flex-1 text-gray-600">{item.issue}</span>
                    <button onClick={() => navigate(item.page)} className="shrink-0 text-xs font-semibold text-teal-600 hover:text-teal-800">
                      {item.page.includes('insurance') ? 'Insurance' : 'Gates'} &rarr;
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Next step footer */}
      <div className="px-5 py-3 bg-gray-50 border-t border-gray-200 flex items-center justify-between">
        <span className="text-xs font-medium text-gray-600">Next: {nextLabel}</span>
        <button
          onClick={() => navigate(nextRoute)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-900 text-white text-xs font-semibold hover:bg-gray-800 transition-colors"
        >
          {nextButton} <ArrowRight className="w-3 h-3" />
        </button>
      </div>
    </div>
  )
}
