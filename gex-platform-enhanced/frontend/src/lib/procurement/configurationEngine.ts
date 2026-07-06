/**
 * Configuration engine — assembles plant-wide procurement configurations
 * from per-slot candidate shortlists using a greedy + diversification pass.
 */
import { getFullCatalog } from "@/lib/equipmentCatalog";
import {
  filterCandidatesForSlot,
  countGloballyMatching,
  type AnnotatedCandidate,
} from "./candidateFilter";
import { evaluateCompatibility } from "./compatibilityRules";
// regionForCountry available if needed for geo-diversity scoring
import type {
  Configuration,
  ConfigurationSlot,
  ScoreBreakdown,
  SimulatorInput,
  SimulatorResult,
} from "./simulatorTypes";

/** Fixed institutional scoring weights — not user-tunable. */
const W = { cost: 45, efficiency: 30, leadTime: 15, trl: 10 } as const;
const W_SUM = W.cost + W.efficiency + W.leadTime + W.trl;
/** Fixed number of configurations the engine produces. */
const NUM_CONFIGURATIONS = 6;

/* ── normalisation helpers ── */

function normaliseInverse(value: number, min: number, max: number): number {
  if (max === min) return 50;
  return 100 - ((value - min) / (max - min)) * 100;
}

function normaliseDirect(value: number, min: number, max: number): number {
  if (max === min) return 50;
  return ((value - min) / (max - min)) * 100;
}

/**
 * Per-slot score used to rank shortlist candidates BEFORE configuration
 * assembly. Uses normalisation across the slot's own candidate pool.
 */
function scoreCandidate(
  c: AnnotatedCandidate,
  pool: AnnotatedCandidate[],
  preferredManufacturers: string[],
): { score: number; breakdown: ScoreBreakdown } {
  const prices = pool.map((p) => p.priceEur);
  const leads = pool.map((p) => p.leadTimeMonths);
  const trls = pool.map((p) => p.trl);
  // Efficiency: we don't have a numeric efficiency in the catalog, so we
  // approximate using TRL + a parsed leading number from the efficiency
  // string when available. This is a demo heuristic.
  const effScore = parseEfficiency(c.efficiency);
  const effPool = pool.map((p) => parseEfficiency(p.efficiency));

  const minP = Math.min(...prices), maxP = Math.max(...prices);
  const minL = Math.min(...leads), maxL = Math.max(...leads);
  const minT = Math.min(...trls), maxT = Math.max(...trls);
  const minE = Math.min(...effPool), maxE = Math.max(...effPool);

  const cost = normaliseInverse(c.priceEur, minP, maxP);
  const leadTime = normaliseInverse(c.leadTimeMonths, minL, maxL);
  const trl = normaliseDirect(c.trl, minT, maxT);
  const efficiency = normaliseDirect(effScore, minE, maxE);

  const preferredBonus = preferredManufacturers.some(
    (m) => m.trim().toLowerCase() === c.manufacturer.trim().toLowerCase(),
  )
    ? 12
    : 0;
  const geoBonus = c.geoPreferred ? 6 : 0;

  const weighted =
    (cost * W.cost + efficiency * W.efficiency + leadTime * W.leadTime + trl * W.trl) /
    W_SUM;

  const total = Math.min(100, Math.max(0, weighted + preferredBonus + geoBonus));

  return {
    score: total,
    breakdown: {
      cost,
      efficiency,
      leadTime,
      trl,
      preferredBonus: preferredBonus + geoBonus,
      warningsPenalty: 0,
      total,
    },
  };
}

function parseEfficiency(eff: string): number {
  // Try to pull the first percentage; fall back to neutral 50.
  const pct = /(\d+(?:\.\d+)?)\s*%/.exec(eff);
  if (pct) return Number.parseFloat(pct[1]);
  return 50;
}

/* ── public API ── */

export function runSimulator(input: SimulatorInput): SimulatorResult {
  const { globals, equipment } = input;

  // 1. Per-slot candidate filtering + per-slot ranking.
  const slotShortlists: Array<{
    nodeId: string;
    label: string;
    ranked: Array<{ c: AnnotatedCandidate; score: number; breakdown: ScoreBreakdown }>;
  }> = equipment.map((eq) => {
    const candidates = filterCandidatesForSlot(eq, globals);
    if (candidates.length === 0) {
      return { nodeId: eq.nodeId, label: eq.label, ranked: [] };
    }
    const ranked = candidates
      .map((c) => ({ c, ...scoreCandidate(c, candidates, globals.preferredManufacturers) }))
      .sort((a, b) => b.score - a.score);
    return { nodeId: eq.nodeId, label: eq.label, ranked };
  });

  const perSlotMatchCount: Record<string, number> = {};
  for (const s of slotShortlists) perSlotMatchCount[s.nodeId] = s.ranked.length;

  // 2. Generate N configurations via diversified greedy.
  // For variation we rotate which rank we pick at each slot per config index,
  // weighted toward top picks (so config #1 = all top picks, later configs
  // swap in 2nd/3rd ranks at rotating slots).
  const N = NUM_CONFIGURATIONS;
  const configurations: Configuration[] = [];
  for (let i = 0; i < N; i += 1) {
    const slots: ConfigurationSlot[] = slotShortlists.map((s, idx) => {
      if (s.ranked.length === 0) {
        return { nodeId: s.nodeId, label: s.label, pick: null, candidates: [] };
      }
      // Diversification: slot `idx` in config `i` picks rank floor((i + idx) / slotCount mod ranked.length)
      // — but biased so config 0 always picks rank 0.
      let rank = 0;
      if (i > 0) {
        const offset = (i + idx) % Math.max(1, s.ranked.length);
        rank = offset;
      }
      const chosen = s.ranked[rank].c;
      return {
        nodeId: s.nodeId,
        label: s.label,
        pick: chosen,
        candidates: s.ranked.map((r) => r.c),
      };
    });

    const config = buildConfigurationMetadata(slots, i + 1, globals);
    configurations.push(config);
  }

  // 3. Deduplicate identical configurations (same picks across slots).
  const seen = new Set<string>();
  const unique = configurations.filter((c) => {
    const key = c.slots.map((s) => `${s.nodeId}:${s.pick?.manufacturer ?? "-"}:${s.pick?.model ?? "-"}`).join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  // 4. Sort by score and re-rank.
  unique.sort((a, b) => b.score.total - a.score.total);
  unique.forEach((c, i) => { c.rank = i + 1; });

  return {
    configurations: unique,
    perSlotMatchCount,
    totalCatalogCount: getFullCatalog().length,
    globallyMatchingCount: countGloballyMatching(globals),
  };
}

function buildConfigurationMetadata(
  slots: ConfigurationSlot[],
  rank: number,
  globals: SimulatorInput["globals"],
): Configuration {
  const picked = slots.filter((s) => s.pick);
  const capexEur = picked.reduce((sum, s) => sum + (s.pick?.priceEur ?? 0), 0);
  const leads = picked.map((s) => s.pick!.leadTimeMonths);
  const trls = picked.map((s) => s.pick!.trl);
  const effScores = picked.map((s) => parseEfficiency(s.pick!.efficiency));

  const countryMix: Record<string, number> = {};
  for (const s of picked) {
    if (!s.pick) continue;
    countryMix[s.pick.country] = (countryMix[s.pick.country] ?? 0) + 1;
  }

  const warnings = evaluateCompatibility(slots);

  // Recompute a config-level score using normalised values across the picks.
  const priceMin = Math.min(...picked.map((s) => s.pick!.priceEur), Number.POSITIVE_INFINITY);
  const priceMax = Math.max(...picked.map((s) => s.pick!.priceEur), 0);
  const cost = normaliseInverse(capexEur / Math.max(1, picked.length), priceMin, priceMax || 1);
  const efficiency = effScores.length ? effScores.reduce((a, b) => a + b, 0) / effScores.length : 0;
  const leadTime = leads.length ? 100 - Math.min(100, (Math.max(...leads) / 24) * 100) : 0;
  const trl = trls.length ? (trls.reduce((a, b) => a + b, 0) / trls.length) * (100 / 9) : 0;

  const weighted =
    (cost * W.cost + efficiency * W.efficiency + leadTime * W.leadTime + trl * W.trl) /
    W_SUM;

  const preferredBonus = picked.reduce((sum, s) => {
    if (!s.pick) return sum;
    const matched = globals.preferredManufacturers.some(
      (m) => m.trim().toLowerCase() === s.pick!.manufacturer.trim().toLowerCase(),
    );
    return sum + (matched ? 4 : 0);
  }, 0);
  const warningsPenalty = warnings.length * 5;

  // Hard cap penalty if CAPEX cap exceeded
  let capPenalty = 0;
  if (globals.totalCapexCapEur !== undefined && capexEur > globals.totalCapexCapEur) {
    capPenalty = 25;
  }

  const total = Math.min(100, Math.max(0, weighted + preferredBonus - warningsPenalty - capPenalty));

  return {
    id: `cfg-${rank}-${Math.random().toString(36).slice(2, 8)}`,
    rank,
    slots,
    totals: {
      capexEur,
      avgEfficiencyScore: efficiency,
      maxLeadTimeMonths: leads.length ? Math.max(...leads) : 0,
      minTrl: trls.length ? Math.min(...trls) : 0,
      countryMix,
    },
    warnings,
    score: {
      cost,
      efficiency,
      leadTime,
      trl,
      preferredBonus,
      warningsPenalty,
      total,
    },
  };
}