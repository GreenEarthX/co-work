/**
 * siteInfrastructure — Non-process equipment, construction and site cost
 * data for a plant. Stored as a separate JSON object in the same Supabase
 * Storage bucket as the canvas data, so it loads/saves independently from
 * the React Flow graph and never appears on the process canvas.
 */
import { isBackendConfigured } from "@/lib/envGuard";
import type { NodeProcurement } from "@/lib/procurementSync";

const BUCKET = "plant-data";

/** Items flagged `site_infrastructure=Yes` in equipment_list_2.csv */
export interface InfraEquipmentSpec {
  equipmentId: string;
  label: string;
  section: string;
}

export const INFRASTRUCTURE_EQUIPMENT: readonly InfraEquipmentSpec[] = [
  /* Power & Electrical */
  { equipmentId: "E4",    label: "Electrical Switchgear",         section: "Power & Electrical" },
  { equipmentId: "E5",    label: "Motor Control Center",          section: "Power & Electrical" },
  { equipmentId: "E6",    label: "Uninterruptible Power Supply",  section: "Power & Electrical" },
  { equipmentId: "EI-01", label: "Emergency Diesel Generator",    section: "Power & Electrical" },
  { equipmentId: "EI-02", label: "Plant Lighting & Lightning Protection", section: "Power & Electrical" },
  /* Fire & Gas Safety */
  { equipmentId: "E128",  label: "Flare System",                  section: "Fire & Gas Safety" },
  { equipmentId: "E129",  label: "Vent Stack",                    section: "Fire & Gas Safety" },
  { equipmentId: "E131",  label: "Blowdown System",               section: "Fire & Gas Safety" },
  { equipmentId: "E132",  label: "Inerting System",               section: "Fire & Gas Safety" },
  { equipmentId: "E133",  label: "Nitrogen Blanketing System",    section: "Fire & Gas Safety" },
  { equipmentId: "E134",  label: "Gas Detection System",          section: "Fire & Gas Safety" },
  { equipmentId: "E135",  label: "Fire Suppression System",       section: "Fire & Gas Safety" },
  { equipmentId: "E159",  label: "Firewater Pump Unit",           section: "Fire & Gas Safety" },
  /* Utilities & Auxiliaries */
  { equipmentId: "EI-10", label: "Cooling Tower or Chiller Package", section: "Utilities & Auxiliaries" },
  { equipmentId: "EI-11", label: "Instrument Air Compressor",     section: "Utilities & Auxiliaries" },
  { equipmentId: "EI-12", label: "Plant Air Compressor",          section: "Utilities & Auxiliaries" },
  { equipmentId: "EI-13", label: "Demineralised Water Package",   section: "Utilities & Auxiliaries" },
  { equipmentId: "EI-14", label: "Effluent Treatment Package",    section: "Utilities & Auxiliaries" },
  /* Storage & Handling */
  { equipmentId: "EI-20", label: "Weighbridge",                   section: "Storage & Handling" },
  { equipmentId: "EI-21", label: "Telecoms and Information Technology Backbone", section: "Storage & Handling" },
  { equipmentId: "EI-22", label: "Perimeter Security and Closed Circuit Television", section: "Storage & Handling" },
] as const;

/** Quick lookup set used by the canvas palette to hide these items. */
export const INFRASTRUCTURE_LABELS: ReadonlySet<string> = new Set(
  INFRASTRUCTURE_EQUIPMENT.map((e) => e.label),
);

/**
 * Broader hide-list used by the canvas Component Library palette to suppress
 * any equipment that belongs in the Site Infrastructure workspace, including
 * `componentDatabase.ts` aliases that don't exactly match the canonical
 * infrastructure labels (e.g. "Cooling Tower" vs "Cooling Tower or Chiller
 * Package", the whole "Safety & Emissions" group, etc.).
 */
export const INFRASTRUCTURE_HIDE_LABELS: ReadonlySet<string> = new Set<string>([
  ...INFRASTRUCTURE_EQUIPMENT.map((e) => e.label),
  // Power & Electrical aliases
  "Engine Generator Set",
  "Electric Generator",
  // Fire & Gas Safety — entire Safety & Emissions group
  "Thermal Oxidizer",
  "Catalytic Oxidizer",
  "Pressure Relief System",
  // Utilities & Auxiliaries aliases
  "Cooling Tower",
  "Chiller",
  "Air Compressor",
  "Demineralization Unit",
  "Effluent Neutralization Unit",
  "Wastewater Treatment Unit",
]);

export const INFRASTRUCTURE_SECTIONS = [
  "Power & Electrical",
  "Fire & Gas Safety",
  "Utilities & Auxiliaries",
  "Storage & Handling",
] as const;

/** Legacy section labels that may still appear in older saved JSON. */
const LEGACY_SECTION_MAP: Record<string, (typeof INFRASTRUCTURE_SECTIONS)[number]> = {
  "Electrical Systems": "Power & Electrical",
  "Safety & Disposal": "Fire & Gas Safety",
  "Storage & Logistics": "Storage & Handling",
  "Separation & Purification": "Fire & Gas Safety",
};

export interface InfraEquipmentItem {
  /** Stable per-row id (`${equipmentId}` is unique since each spec appears once) */
  id: string;
  equipmentId: string;
  label: string;
  section: string;
  claimed: boolean;
  quantity: number;
  unitCostEur: number;
  /** User explicitly marked this row as Not Applicable for this plant. */
  notApplicable?: boolean;
  notes?: string;
  procurement?: NodeProcurement;
}

export interface InfraConstruction {
  /* Direct: Civil & Structural */
  foundationsEur: number;
  structuralSteelEur: number;
  concreteMaterialsEur: number;
  buildingsEur: number;
  pavingRoadsEur: number;

  /* Direct: Mechanical (utility / off-site scope only) */
  utilityPipingEur: number;
  siteEquipmentInstallationEur: number;
  insulationPaintingEur: number;

  /* Direct: Electrical & Instrumentation */
  cablingTraysEur: number;
  substationEur: number;
  controlRoomDcsEur: number;
  instrumentationEur: number;

  /* Indirect / Services */
  feedEngineeringEur: number;
  detailedEngineeringEur: number;
  projectManagementEur: number;
  epcFeeEur: number;
  commissioningStartupEur: number;
  hsseSecurityEur: number;

  contingencyPct: number;
  notes?: string;

  /* Legacy — kept for backward-compat reads, no longer surfaced in UI */
  civilWorksEur?: number;
  epcEur?: number;
  pipingValvesEur?: number;
  equipmentInstallationEur?: number;
  tankageInternalsEur?: number;
}

export interface InfraSite {
  landAreaHa: number;
  landAcquisitionEur: number;
  permittingEur: number;
  sitePreparationEur: number;
  utilitiesConnectionEur: number;
  geotechSurveyEur: number;
  topoSurveyEur: number;
  eiaStudyEur: number;
  demolitionEur: number;
  ownersCostsEur: number;
  sparesInventoryEur: number;
  contingencyPct: number;
  notes?: string;
}

export interface InfrastructureData {
  items: InfraEquipmentItem[];
  construction: InfraConstruction;
  site: InfraSite;
  /** Project-wide contingency on equipment subtotal (percent). */
  equipmentContingencyPct?: number;
  /** Capital cost reference year (e.g. 2026). */
  referenceYear?: number;
  /** ISO currency code; only EUR rendered for now. */
  currency?: "EUR" | "USD" | "GBP";
  updatedAt?: string;
}

export const DEFAULT_CONSTRUCTION: InfraConstruction = {
  foundationsEur: 0,
  structuralSteelEur: 0,
  concreteMaterialsEur: 0,
  buildingsEur: 0,
  pavingRoadsEur: 0,
  utilityPipingEur: 0,
  siteEquipmentInstallationEur: 0,
  insulationPaintingEur: 0,
  cablingTraysEur: 0,
  substationEur: 0,
  controlRoomDcsEur: 0,
  instrumentationEur: 0,
  feedEngineeringEur: 0,
  detailedEngineeringEur: 0,
  projectManagementEur: 0,
  epcFeeEur: 0,
  commissioningStartupEur: 0,
  hsseSecurityEur: 0,
  contingencyPct: 0,
};

/** Numeric construction line items (excludes contingencyPct, notes, legacy). */
export const CONSTRUCTION_LINE_KEYS: (keyof InfraConstruction)[] = [
  "foundationsEur", "structuralSteelEur", "concreteMaterialsEur", "buildingsEur", "pavingRoadsEur",
  "utilityPipingEur", "siteEquipmentInstallationEur", "insulationPaintingEur",
  "cablingTraysEur", "substationEur", "controlRoomDcsEur", "instrumentationEur",
  "feedEngineeringEur", "detailedEngineeringEur", "projectManagementEur",
  "epcFeeEur", "commissioningStartupEur", "hsseSecurityEur",
];

export const DEFAULT_SITE: InfraSite = {
  landAreaHa: 0,
  landAcquisitionEur: 0,
  permittingEur: 0,
  sitePreparationEur: 0,
  utilitiesConnectionEur: 0,
  geotechSurveyEur: 0,
  topoSurveyEur: 0,
  eiaStudyEur: 0,
  demolitionEur: 0,
  ownersCostsEur: 0,
  sparesInventoryEur: 0,
  contingencyPct: 0,
};

/** Site numeric line items (excludes landAreaHa, contingencyPct, notes). */
export const SITE_LINE_KEYS: (keyof InfraSite)[] = [
  "landAcquisitionEur", "geotechSurveyEur", "topoSurveyEur", "eiaStudyEur",
  "permittingEur", "demolitionEur", "sitePreparationEur",
  "utilitiesConnectionEur", "ownersCostsEur", "sparesInventoryEur",
];

export function defaultInfrastructure(): InfrastructureData {
  return {
    items: INFRASTRUCTURE_EQUIPMENT.map((e) => ({
      id: e.equipmentId,
      equipmentId: e.equipmentId,
      label: e.label,
      section: e.section,
      claimed: false,
      quantity: 1,
      unitCostEur: 0,
    })),
    construction: { ...DEFAULT_CONSTRUCTION },
    site: { ...DEFAULT_SITE },
    equipmentContingencyPct: 0,
    referenceYear: new Date().getFullYear(),
    currency: "EUR",
  };
}

/** Backfill: ensure every spec row exists even if the saved blob is older. */
export function reconcileInfrastructure(raw: Partial<InfrastructureData> | null | undefined): InfrastructureData {
  const base = defaultInfrastructure();
  if (!raw) return base;
  const items = base.items.map((row) => {
    const existing = raw.items?.find((i) => i.equipmentId === row.equipmentId);
    if (!existing) return row;
    // Re-map any legacy section the user might have on disk.
    const mappedSection = LEGACY_SECTION_MAP[existing.section] ?? row.section;
    return { ...row, ...existing, section: mappedSection };
  });
  // Migrate legacy construction field names into the new direct keys (only
  // when the new key is empty — never overwrite explicit user input).
  const rawC = (raw.construction ?? {}) as Partial<InfraConstruction>;
  const migratedConstruction: InfraConstruction = {
    ...base.construction,
    ...rawC,
    utilityPipingEur: rawC.utilityPipingEur ?? rawC.pipingValvesEur ?? 0,
    siteEquipmentInstallationEur: rawC.siteEquipmentInstallationEur ?? rawC.equipmentInstallationEur ?? 0,
  };
  return {
    items,
    construction: migratedConstruction,
    site: { ...base.site, ...(raw.site ?? {}) },
    equipmentContingencyPct: raw.equipmentContingencyPct ?? 0,
    referenceYear: raw.referenceYear ?? new Date().getFullYear(),
    currency: raw.currency ?? "EUR",
    updatedAt: raw.updatedAt,
  };
}

/* ── Totals ── */
export interface InfraTotals {
  equipmentBaseEur: number;
  equipmentContingencyEur: number;
  equipmentEur: number;
  constructionBaseEur: number;
  constructionContingencyEur: number;
  constructionEur: number;
  siteBaseEur: number;
  siteContingencyEur: number;
  siteEur: number;
  grandTotalEur: number;
}

export function computeInfraTotals(d: InfrastructureData): InfraTotals {
  const equipmentBaseEur = d.items
    .filter((i) => i.claimed && !i.notApplicable)
    .reduce((sum, i) => sum + (i.quantity || 0) * (i.unitCostEur || 0), 0);
  const equipmentContingencyEur = equipmentBaseEur * ((d.equipmentContingencyPct || 0) / 100);
  const equipmentEur = equipmentBaseEur + equipmentContingencyEur;

  const direct = CONSTRUCTION_LINE_KEYS.reduce(
    (sum, k) => sum + (Number(d.construction[k]) || 0),
    0,
  );
  // Migrate legacy fields if user data still has them and new fields are zero
  const legacy = (d.construction.civilWorksEur || 0) + (d.construction.epcEur || 0);
  const constructionBaseEur = direct > 0 ? direct : legacy;
  const constructionContingencyEur = constructionBaseEur * ((d.construction.contingencyPct || 0) / 100);
  const constructionEur = constructionBaseEur + constructionContingencyEur;

  const siteBaseEur = SITE_LINE_KEYS.reduce(
    (sum, k) => sum + (Number(d.site[k]) || 0),
    0,
  );
  const siteContingencyEur = siteBaseEur * ((d.site.contingencyPct || 0) / 100);
  const siteEur = siteBaseEur + siteContingencyEur;

  return {
    equipmentBaseEur,
    equipmentContingencyEur,
    equipmentEur,
    constructionBaseEur,
    constructionContingencyEur,
    constructionEur,
    siteBaseEur,
    siteContingencyEur,
    siteEur,
    grandTotalEur: equipmentEur + constructionEur + siteEur,
  };
}

/* ── Storage I/O ── */
async function getSupabase() {
  if (!isBackendConfigured()) return null;
  const { supabase } = await import("@/lib/backendClient");
  return supabase;
}

function scopedPath(slug: string, userId?: string): string {
  return userId ? `users/${userId}/${slug}.infrastructure.json` : `${slug}.infrastructure.json`;
}

export async function loadInfrastructure(
  slug: string,
  userId?: string,
): Promise<InfrastructureData> {
  const sb = await getSupabase();
  if (!sb) return defaultInfrastructure();
  const candidates = userId
    ? [scopedPath(slug, userId), scopedPath(slug)]
    : [scopedPath(slug)];
  for (const path of candidates) {
    const { data: urlData } = sb.storage.from(BUCKET).getPublicUrl(path);
    try {
      const resp = await fetch(`${urlData.publicUrl}?t=${Date.now()}`, { cache: "no-store" });
      if (!resp.ok) continue;
      const parsed = JSON.parse(await resp.text()) as Partial<InfrastructureData>;
      return reconcileInfrastructure(parsed);
    } catch {
      continue;
    }
  }
  return defaultInfrastructure();
}

export async function saveInfrastructure(
  slug: string,
  data: InfrastructureData,
  userId?: string,
): Promise<{ ok: boolean; error?: string }> {
  const sb = await getSupabase();
  if (!sb) return { ok: false, error: "Backend not configured" };
  const payload: InfrastructureData = { ...data, updatedAt: new Date().toISOString() };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const { error } = await sb.storage
    .from(BUCKET)
    .upload(scopedPath(slug, userId), blob, { upsert: true, cacheControl: "0" });
  if (error) return { ok: false, error: error.message };
  return { ok: true };
}

export function formatEur(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n || 0);
}
