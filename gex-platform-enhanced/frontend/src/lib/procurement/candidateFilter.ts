/**
 * Per-equipment candidate filtering. Applies global preferences + per-slot
 * overrides + technology lock-in + capacity tolerance + cost cap.
 */
import { getCatalogForLabel, getFullCatalog, type CatalogEntry } from "@/lib/equipmentCatalog";
import { technologyForEntry } from "./technologyMap";
import {
  regionForCountry,
  type EquipmentConstraints,
  type GlobalPreferences,
} from "./simulatorTypes";

function passesGeo(
  country: string,
  geo: Pick<GlobalPreferences, "regions" | "countries" | "geoMode">,
): { pass: boolean; preferred: boolean } {
  const region = regionForCountry(country);
  const hasGeoFilter = geo.regions.length > 0 || geo.countries.length > 0;
  if (!hasGeoFilter) return { pass: true, preferred: false };

  const matches =
    geo.countries.includes(country) || geo.regions.includes(region);

  if (geo.geoMode === "include") return { pass: matches, preferred: matches };
  if (geo.geoMode === "exclude") return { pass: !matches, preferred: false };
  // prefer: never filter out, just boost
  return { pass: true, preferred: matches };
}

/** A catalog entry annotated with metadata used during scoring. */
export interface AnnotatedCandidate extends CatalogEntry {
  technology: string;
  geoPreferred: boolean;
}

export function filterCandidatesForSlot(
  constraints: EquipmentConstraints,
  globals: GlobalPreferences,
): AnnotatedCandidate[] {
  const eff = {
    trlMin: constraints.override?.trlMin ?? globals.trlMin,
    regions: constraints.override?.regions ?? globals.regions,
    countries: constraints.override?.countries ?? globals.countries,
    geoMode: constraints.override?.geoMode ?? globals.geoMode,
    preferredManufacturers:
      constraints.override?.preferredManufacturers ?? globals.preferredManufacturers,
    excludedManufacturers:
      constraints.override?.excludedManufacturers ?? globals.excludedManufacturers,
  };

  const labelCatalog = getCatalogForLabel(constraints.label);
  // getCatalogForLabel falls back to the full catalog when nothing matches.
  // In that case (no label match at all), prefer to surface zero rather than
  // a 700-row list that confuses scoring. We detect "fallback" by checking
  // whether the label exists in any entry's keywords.
  const lower = constraints.label.toLowerCase().trim();
  const labelMatchesAnything = labelCatalog.some((e) =>
    e.keywords.some((kw) => lower.includes(kw.toLowerCase())),
  );
  const pool = labelMatchesAnything ? labelCatalog : [];

  const out: AnnotatedCandidate[] = [];
  for (const entry of pool) {
    // TRL
    if (entry.trl < eff.trlMin) continue;
    // Excluded manufacturer
    if (eff.excludedManufacturers.some((m) => sameVendor(m, entry.manufacturer))) continue;
    // Geo
    const geo = passesGeo(entry.country, eff);
    if (!geo.pass) continue;
    // Lead time
    if (globals.maxLeadTimeMonths !== undefined && entry.leadTimeMonths > globals.maxLeadTimeMonths) continue;
    // Cost cap
    if (constraints.costCapEur !== undefined && entry.priceEur > constraints.costCapEur) continue;
    // Technology lock-in
    const tech = technologyForEntry(entry);
    if (constraints.technologies.length > 0 && !constraints.technologies.includes(tech) && tech !== "Unknown") {
      continue;
    }
    out.push({ ...entry, technology: tech, geoPreferred: geo.preferred });
  }
  return out;
}

function sameVendor(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

/** Convenience — count of catalog entries matching just the global filters. */
export function countGloballyMatching(globals: GlobalPreferences): number {
  let n = 0;
  for (const entry of getFullCatalog()) {
    if (entry.trl < globals.trlMin) continue;
    if (globals.excludedManufacturers.some((m) => sameVendor(m, entry.manufacturer))) continue;
    const geo = passesGeo(entry.country, globals);
    if (!geo.pass) continue;
    if (globals.maxLeadTimeMonths !== undefined && entry.leadTimeMonths > globals.maxLeadTimeMonths) continue;
    n += 1;
  }
  return n;
}