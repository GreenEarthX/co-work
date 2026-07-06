/**
 * Equipment Catalog — single source of truth for the supplier list.
 *
 * Both the Supplier Database page and the Browse Suppliers dialog (Project
 * Procurement) MUST consume this module so counts and entries are identical.
 * Adding new equipment in `procurementDatabase.ts` or new alternatives in
 * `procurementAlternatives.ts` automatically appears in both views.
 */
import {
  procurementDatabase,
  type EquipmentProcurement,
} from "@/components/canvas/procurementDatabase";
import { procurementAlternatives } from "@/components/canvas/procurementAlternatives";

export interface CatalogEntry {
  manufacturer: string;
  model: string;
  country: string;
  priceEur: number;
  priceDisplay: string;
  efficiency: string;
  leadTimeMonths: number;
  trl: number;
  scaleThreshold?: string;
  /** "Best Price" | "Best Efficiency" | "Scale Optimised" | … */
  strategyOrigin: string;
  /** Internal strategy key kept for consumers that need it */
  strategyKey: "bestPrice" | "bestEfficiency" | "economiesOfScale";
  /** Capitalised equipment-type label derived from the entry's first keyword */
  equipmentType: string;
  /** Friendly category label used by the Supplier Database filter chips */
  categoryLabel: string;
  pricingUnit: string;
  /** All keywords from the source entry — used for label-based matching */
  keywords: string[];
}

const STRATEGY_LABELS: Record<CatalogEntry["strategyKey"], string> = {
  bestPrice: "Best Price",
  bestEfficiency: "Best Efficiency",
  economiesOfScale: "Scale Optimised",
};

const CATEGORY_MAP: Record<string, string> = {
  electrolyzer: "Electrolyzers",
  compressor: "Compressors",
  "water treatment": "Water Treatment",
  purif: "Purification (PSA)",
  "heat exchanger": "Heat Exchangers",
  pump: "Pumps",
  reformer: "Reforming Reactors",
  reactor: "Synthesis Reactors",
  tank: "Storage Tanks",
  boiler: "Boilers / HRSG",
  turbine: "Turbines",
  separator: "Separators",
  distillation: "Distillation Columns",
  valve: "Valves",
  transformer: "Transformers",
  "fuel cell": "Fuel Cells",
  desalination: "Desalination",
  dac: "Direct Air Capture",
  "co2 capture": "CO₂ Capture",
  mixer: "Mixers",
  dryer: "Dryers",
  deoxo: "Deoxidation Units",
  instrument: "Instrumentation & Controls",
  piping: "Piping & Fittings",
  cooling: "Cooling Systems",
  "anaerobic digester": "Anaerobic Digesters",
  digester: "Anaerobic Digesters",
  "biogas upgrading": "Biogas Upgrading",
};

function categoryFor(keywords: string[]): string {
  const first = (keywords[0] ?? "Equipment").toLowerCase();
  for (const [key, label] of Object.entries(CATEGORY_MAP)) {
    if (first.includes(key)) return label;
  }
  return first.charAt(0).toUpperCase() + first.slice(1);
}

function equipmentTypeFor(keywords: string[]): string {
  const kw = keywords[0] ?? "Equipment";
  return kw.charAt(0).toUpperCase() + kw.slice(1);
}

function flattenEntry(ep: EquipmentProcurement): CatalogEntry[] {
  const equipmentType = equipmentTypeFor(ep.keywords);
  const categoryLabel = categoryFor(ep.keywords);
  const out: CatalogEntry[] = [];

  // 1. Three base strategy options
  (["bestPrice", "bestEfficiency", "economiesOfScale"] as const).forEach((k) => {
    const o = ep[k];
    out.push({
      manufacturer: o.manufacturer,
      model: o.model,
      country: o.country,
      priceEur: o.priceEur,
      priceDisplay: o.priceDisplay,
      efficiency: o.efficiency,
      leadTimeMonths: o.leadTimeMonths,
      trl: o.trl,
      scaleThreshold: o.scaleThreshold,
      strategyOrigin: STRATEGY_LABELS[k],
      strategyKey: k,
      equipmentType,
      categoryLabel,
      pricingUnit: ep.pricingUnit,
      keywords: ep.keywords,
    });
  });

  // 2. Alternatives (matched by the entry's first keyword)
  const alts = procurementAlternatives[ep.keywords[0]];
  if (alts) {
    for (const a of alts) {
      out.push({
        manufacturer: a.manufacturer,
        model: a.model,
        country: a.country,
        priceEur: a.priceEur,
        priceDisplay: a.priceDisplay,
        efficiency: a.efficiency,
        leadTimeMonths: a.leadTimeMonths,
        trl: a.trl,
        scaleThreshold: a.scaleThreshold,
        strategyOrigin: STRATEGY_LABELS[a.strategyTag],
        strategyKey: a.strategyTag,
        equipmentType,
        categoryLabel,
        pricingUnit: ep.pricingUnit,
        keywords: ep.keywords,
      });
    }
  }

  return out;
}

let _cache: CatalogEntry[] | null = null;

/** Full flat catalog — base DB + alternatives, identical for every consumer. */
export function getFullCatalog(): CatalogEntry[] {
  if (!_cache) {
    _cache = procurementDatabase.flatMap(flattenEntry);
  }
  return _cache;
}

/**
 * Catalog filtered to entries matching the equipment label (substring match
 * on any of the source keywords). Falls back to the full catalog when the
 * label matches nothing — same behaviour as the original picker dialog.
 */
export function getCatalogForLabel(label: string): CatalogEntry[] {
  const all = getFullCatalog();
  const lower = (label ?? "").toLowerCase().trim();
  if (!lower) return all;
  const matches = all.filter((e) =>
    e.keywords.some((kw) => lower.includes(kw.toLowerCase())),
  );
  return matches.length > 0 ? matches : all;
}

/** Diagnostic helper — count of suppliers per category. */
export function countByCategory(): Record<string, number> {
  const out: Record<string, number> = {};
  for (const e of getFullCatalog()) {
    out[e.categoryLabel] = (out[e.categoryLabel] ?? 0) + 1;
  }
  return out;
}

/** Sorted unique list of every country represented in the catalog. */
export function listCatalogCountries(): string[] {
  return Array.from(new Set(getFullCatalog().map((e) => e.country))).sort();
}