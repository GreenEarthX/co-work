/**
 * Procurement Simulator — shared types.
 *
 * The simulator turns user-declared constraints + the live plant equipment
 * list into a ranked set of plant-wide procurement configurations.
 */
import type { CatalogEntry } from "@/lib/equipmentCatalog";

export type RegionKey =
  | "Europe"
  | "North America"
  | "Asia Pacific"
  | "MENA"
  | "LATAM"
  | "Oceania"
  | "Other";

export type GeoMode = "include" | "exclude" | "prefer";

export interface GlobalPreferences {
  /** Minimum acceptable Technology Readiness Level. */
  trlMin: number;
  /** Selected regions. */
  regions: RegionKey[];
  /** Specific countries (chips). */
  countries: string[];
  /** How geographic selections behave. */
  geoMode: GeoMode;
  /** Manufacturers the user prefers (soft score boost). */
  preferredManufacturers: string[];
  /** Manufacturers the user excludes (hard filter). */
  excludedManufacturers: string[];
  /** Hard total CAPEX cap in EUR (optional). */
  totalCapexCapEur?: number;
  /** Max acceptable lead time in months (optional). */
  maxLeadTimeMonths?: number;
}

export interface CapacityRange {
  min?: number;
  nominal?: number;
  max?: number;
  unit: string;
}

export interface EquipmentConstraints {
  nodeId: string;
  label: string;
  /** Selected technology family keys (PEM, Alkaline, …). Empty = all. */
  technologies: string[];
  capacity: CapacityRange;
  /** Per-unit cost cap, EUR. Optional. */
  costCapEur?: number;
  /** Optional overrides — fall back to global when undefined. */
  override?: Partial<Pick<GlobalPreferences, "trlMin" | "regions" | "countries" | "geoMode" | "preferredManufacturers" | "excludedManufacturers">>;
}

export interface SimulatorInput {
  globals: GlobalPreferences;
  equipment: EquipmentConstraints[];
}

export interface ScoreBreakdown {
  cost: number;
  efficiency: number;
  leadTime: number;
  trl: number;
  preferredBonus: number;
  warningsPenalty: number;
  /** Final score 0–100. */
  total: number;
}

export interface ConfigurationSlot {
  nodeId: string;
  label: string;
  /** Chosen supplier; null when no candidate matched. */
  pick: CatalogEntry | null;
  /** All candidates considered for this slot, sorted by per-slot score. */
  candidates: CatalogEntry[];
}

export interface CompatibilityWarning {
  nodeId: string;
  message: string;
}

export interface Configuration {
  id: string;
  /** Display rank label (Config #1 …). */
  rank: number;
  slots: ConfigurationSlot[];
  totals: {
    capexEur: number;
    avgEfficiencyScore: number;
    maxLeadTimeMonths: number;
    minTrl: number;
    countryMix: Record<string, number>;
  };
  warnings: CompatibilityWarning[];
  score: ScoreBreakdown;
}

export interface SimulatorResult {
  configurations: Configuration[];
  /** Per-equipment count of candidates that passed all filters. */
  perSlotMatchCount: Record<string, number>;
  /** Total supplier count across the catalog used. */
  totalCatalogCount: number;
  /** Suppliers matching just the global filters. */
  globallyMatchingCount: number;
}

export const DEFAULT_GLOBALS: GlobalPreferences = {
  trlMin: 8,
  regions: [],
  countries: [],
  geoMode: "include",
  preferredManufacturers: [],
  excludedManufacturers: [],
};

export const REGION_OPTIONS: RegionKey[] = [
  "Europe",
  "North America",
  "Asia Pacific",
  "MENA",
  "LATAM",
  "Oceania",
];

export const COUNTRY_TO_REGION: Record<string, RegionKey> = {
  Germany: "Europe", France: "Europe", Norway: "Europe", Sweden: "Europe",
  Switzerland: "Europe", Denmark: "Europe", Netherlands: "Europe", Belgium: "Europe",
  Finland: "Europe", UK: "Europe", Spain: "Europe", Italy: "Europe", Austria: "Europe",
  Ireland: "Europe", Poland: "Europe", Portugal: "Europe", Czechia: "Europe",
  USA: "North America", Canada: "North America", Mexico: "North America",
  China: "Asia Pacific", Japan: "Asia Pacific", India: "Asia Pacific",
  "South Korea": "Asia Pacific", Singapore: "Asia Pacific", Taiwan: "Asia Pacific",
  Australia: "Oceania", "New Zealand": "Oceania",
  Israel: "MENA", UAE: "MENA", "Saudi Arabia": "MENA", Egypt: "MENA",
  Brazil: "LATAM", Chile: "LATAM", Argentina: "LATAM",
};

export function regionForCountry(country: string): RegionKey {
  return COUNTRY_TO_REGION[country] ?? "Other";
}