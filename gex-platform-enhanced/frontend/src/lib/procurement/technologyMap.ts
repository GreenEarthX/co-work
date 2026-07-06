/**
 * Maps equipment label + supplier model strings to a coarse technology family,
 * and exposes the available families per equipment type so the user can
 * lock the simulator to a subset.
 */
import type { CatalogEntry } from "@/lib/equipmentCatalog";

/** Ordered list of families per equipment keyword. First match wins. */
export const TECHNOLOGY_FAMILIES: Record<string, string[]> = {
  electrolyzer: ["PEM", "Alkaline", "AEM", "SOEC"],
  compressor: ["Reciprocating", "Centrifugal", "Diaphragm", "Ionic"],
  "water treatment": ["RO", "EDI", "Ultrafiltration", "Mixed-Bed"],
  purif: ["PSA", "TSA", "Membrane"],
  "heat exchanger": ["Plate", "Shell & Tube", "Welded Plate", "Air-Cooled"],
  pump: ["Centrifugal", "Diaphragm", "Sealless", "Positive Displacement"],
  reformer: ["SMR", "ATR", "Partial Oxidation"],
  reactor: ["Fixed-Bed", "Slurry", "Tubular", "Fluidized-Bed"],
  tank: ["Atmospheric", "Cryogenic", "High-Pressure"],
  turbine: ["Steam", "Gas", "Wind", "Hydraulic"],
  "fuel cell": ["PEMFC", "SOFC", "MCFC"],
  desalination: ["SWRO", "MED", "MSF"],
  dac: ["Solid Sorbent", "Liquid Solvent"],
  digester: ["CSTR", "Plug Flow", "UASB"],
  "biogas upgrading": ["Water Scrubbing", "PSA", "Membrane", "Amine"],
  transformer: ["Oil-Filled", "Dry-Type"],
  separator: ["Cyclonic", "Gravity", "Coalescing"],
  distillation: ["Tray", "Packed"],
};

const MODEL_KEYWORD_RULES: Array<{ family: string; patterns: RegExp[] }> = [
  { family: "PEM", patterns: [/\bPEM\b/i, /proton exchange/i] },
  { family: "Alkaline", patterns: [/\bALK\b/i, /alkaline/i, /KOH/i] },
  { family: "AEM", patterns: [/\bAEM\b/i, /anion exchange/i] },
  { family: "SOEC", patterns: [/\bSOEC\b/i, /solid oxide/i] },
  { family: "SOFC", patterns: [/\bSOFC\b/i, /solid oxide fuel/i] },
  { family: "PEMFC", patterns: [/\bPEMFC\b/i] },
  { family: "MCFC", patterns: [/\bMCFC\b/i, /molten carbonate/i] },
  { family: "Diaphragm", patterns: [/diaphragm/i] },
  { family: "Reciprocating", patterns: [/reciprocating/i] },
  { family: "Centrifugal", patterns: [/centrifugal/i] },
  { family: "Ionic", patterns: [/\bionic\b/i] },
  { family: "Sealless", patterns: [/sealless/i, /\bmag\b/i] },
  { family: "Plate", patterns: [/plate heat/i, /plate exchanger/i, /\bplate\b/i] },
  { family: "Shell & Tube", patterns: [/shell ?& ?tube/i, /shell ?and ?tube/i] },
  { family: "Welded Plate", patterns: [/welded plate/i] },
  { family: "Air-Cooled", patterns: [/air[- ]cooled/i] },
  { family: "RO", patterns: [/\bRO\b/i, /reverse osmosis/i] },
  { family: "EDI", patterns: [/\bEDI\b/i, /electrodeionization/i, /CDI/i] },
  { family: "Ultrafiltration", patterns: [/ultrafiltrat/i, /\bUF\b/i] },
  { family: "Mixed-Bed", patterns: [/mixed[- ]bed/i] },
  { family: "PSA", patterns: [/\bPSA\b/i, /pressure swing/i] },
  { family: "TSA", patterns: [/\bTSA\b/i, /temperature swing/i] },
  { family: "Membrane", patterns: [/membrane/i] },
  { family: "Amine", patterns: [/amine/i, /MEA\b/i] },
  { family: "Water Scrubbing", patterns: [/water scrub/i] },
  { family: "SMR", patterns: [/\bSMR\b/i, /steam methane/i] },
  { family: "ATR", patterns: [/\bATR\b/i, /autothermal/i] },
  { family: "Partial Oxidation", patterns: [/partial oxidation/i, /\bPOX\b/i] },
  { family: "Cryogenic", patterns: [/cryogenic/i, /\bLH2\b/i, /\bLNG\b/i] },
  { family: "High-Pressure", patterns: [/high.?pressure/i, /\b350 ?bar\b/i, /\b700 ?bar\b/i, /\b900 ?bar\b/i] },
  { family: "SWRO", patterns: [/\bSWRO\b/i, /seawater/i] },
  { family: "MED", patterns: [/\bMED\b/i, /multi.?effect/i] },
  { family: "MSF", patterns: [/\bMSF\b/i, /multi.?stage flash/i] },
  { family: "Solid Sorbent", patterns: [/solid sorbent/i] },
  { family: "Liquid Solvent", patterns: [/liquid solvent/i, /\bKOH\b.*DAC/i] },
  { family: "CSTR", patterns: [/\bCSTR\b/i, /stirred tank/i] },
  { family: "Plug Flow", patterns: [/plug ?flow/i] },
  { family: "UASB", patterns: [/\bUASB\b/i] },
  { family: "Oil-Filled", patterns: [/oil[- ]filled/i] },
  { family: "Dry-Type", patterns: [/dry[- ]type/i] },
  { family: "Fixed-Bed", patterns: [/fixed[- ]bed/i] },
  { family: "Slurry", patterns: [/slurry/i] },
  { family: "Tubular", patterns: [/tubular/i, /multi.?tube/i] },
  { family: "Fluidized-Bed", patterns: [/fluidized/i] },
  { family: "Steam", patterns: [/steam turbine/i] },
  { family: "Gas", patterns: [/gas turbine/i] },
];

/** Identify the technology family of an individual catalog entry. */
export function technologyForEntry(entry: CatalogEntry): string {
  const text = `${entry.model} ${entry.manufacturer}`;
  for (const { family, patterns } of MODEL_KEYWORD_RULES) {
    if (patterns.some((p) => p.test(text))) return family;
  }
  return "Unknown";
}

/** Get the family options shown to the user for a given equipment label. */
export function familiesForLabel(label: string): string[] {
  const lower = label.toLowerCase();
  for (const [keyword, families] of Object.entries(TECHNOLOGY_FAMILIES)) {
    if (lower.includes(keyword)) return families;
  }
  return [];
}