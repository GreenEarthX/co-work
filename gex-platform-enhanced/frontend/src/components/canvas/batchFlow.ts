/**
 * Batch flow stream model — types, defaults, and conversion helpers.
 *
 * A stream edge has a `flowMode`:
 *   - "continuous" (default): user enters a rate via `flowValue` + `flowUnit`.
 *   - "batch": user configures a `BatchFlowConfig` and we derive the equivalent
 *     continuous rate so the balance engine and equation engine keep working
 *     unchanged.
 */

export type BatchPeriod = "hour" | "day" | "week" | "month" | "year";
export type BatchFrequencyMode = "perPeriod" | "interval";
export type BatchIdleBehavior = "none" | "buffered" | "stop_downstream";
export type BatchArrivalPattern = "regular" | "scheduled" | "stochastic";
export type BatchTransportMode =
  | "truck"
  | "ship"
  | "rail"
  | "pipeline_intermittent"
  | "manual";

export interface BatchFlowConfig {
  batchSize: number;
  batchUnit: string;
  frequency: number;
  frequencyMode: BatchFrequencyMode;
  period: BatchPeriod;
  chargeDuration?: number; // minutes
  idleBehavior: BatchIdleBehavior;
  bufferCapacity?: number;
  bufferUnit?: string;
  arrivalPattern: BatchArrivalPattern;
  variability?: number; // ± %
  transportMode?: BatchTransportMode;
  notes?: string;
}

/** Hours in one period — used to normalize to per-hour rates. */
const PERIOD_HOURS: Record<BatchPeriod, number> = {
  hour: 1,
  day: 24,
  week: 24 * 7,
  month: 24 * 30,
  year: 24 * 365,
};

/** Mass conversion factors to kg (for unit normalization in derived rate). */
const MASS_TO_KG: Record<string, number> = {
  kg: 1,
  t: 1000,
  kt: 1_000_000,
  Nm3: 0.0899, // hydrogen approximation; users override flowUnit if needed
  "Nm³": 0.0899,
  MWh: 1, // not mass; keep dimensionless — flowUnit drives meaning
  GJ: 1,
  mol: 1,
  pieces: 1,
};

/** Default config seeded when switching from continuous → batch. */
export function defaultBatchConfig(
  currentFlowValue?: number,
  currentFlowUnit?: string,
): BatchFlowConfig {
  // If the user had a continuous kg/h rate, seed as that × 24 per day.
  const seedSize = currentFlowValue && currentFlowValue > 0 ? currentFlowValue * 24 : 1000;
  const seedUnit = currentFlowUnit ? guessBatchUnit(currentFlowUnit) : "kg";
  return {
    batchSize: Number(seedSize.toFixed(2)),
    batchUnit: seedUnit,
    frequency: 1,
    frequencyMode: "perPeriod",
    period: "day",
    idleBehavior: "buffered",
    arrivalPattern: "regular",
    transportMode: "truck",
  };
}

function guessBatchUnit(flowUnit: string): string {
  const lower = flowUnit.toLowerCase();
  if (lower.startsWith("kg")) return "kg";
  if (lower.startsWith("t/")) return "t";
  if (lower.startsWith("kt")) return "t";
  if (lower.includes("nm")) return "Nm³";
  if (lower.includes("mwh") || lower.includes("mw")) return "MWh";
  if (lower.includes("gj")) return "GJ";
  if (lower.includes("mol")) return "mol";
  return "kg";
}

/** Derive equivalent continuous rate from a batch config, in `targetUnit`.
 *  Best-effort: matches mass-family units; otherwise returns size×freq/periodHours. */
export function computeEquivalentRate(
  config: BatchFlowConfig,
  targetUnit: string,
): number {
  const batchesPerPeriod =
    config.frequencyMode === "perPeriod"
      ? config.frequency
      : config.frequency > 0
      ? 1 / config.frequency
      : 0;
  const totalPerPeriod = config.batchSize * batchesPerPeriod;
  const perHour = totalPerPeriod / PERIOD_HOURS[config.period];

  // Try mass-family conversion to align units (kg ↔ t).
  const srcKg = MASS_TO_KG[config.batchUnit];
  const dstFamily = targetUnit.split("/")[0];
  const dstKg = MASS_TO_KG[dstFamily];
  if (srcKg && dstKg) {
    return (perHour * srcKg) / dstKg;
  }
  return perHour;
}

/** Human-readable summary used on the edge chip and tooltips. */
export function describeBatch(config: BatchFlowConfig): { line1: string; line2: string } {
  const line1 = `${formatNum(config.batchSize)} ${config.batchUnit} / batch`;
  const periodLabel: Record<BatchPeriod, string> = {
    hour: "h",
    day: "day",
    week: "wk",
    month: "mo",
    year: "yr",
  };
  const line2 =
    config.frequencyMode === "perPeriod"
      ? `× ${formatNum(config.frequency)} / ${periodLabel[config.period]}`
      : `every ${formatNum(config.frequency)} ${periodLabel[config.period]}`;
  return { line1, line2 };
}

function formatNum(n: number): string {
  if (!isFinite(n)) return "—";
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (n % 1 === 0) return String(n);
  return n.toFixed(2);
}

export const BATCH_UNITS = ["kg", "t", "Nm³", "MWh", "GJ", "mol", "pieces"];
export const BATCH_PERIODS: BatchPeriod[] = ["hour", "day", "week", "month", "year"];
export const BATCH_TRANSPORT_MODES: BatchTransportMode[] = [
  "truck",
  "ship",
  "rail",
  "pipeline_intermittent",
  "manual",
];