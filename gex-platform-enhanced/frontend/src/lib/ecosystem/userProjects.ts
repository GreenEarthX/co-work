/**
 * userProjects — bridge between Plant Builder and the Ecosystem Map.
 *
 * When a user creates a new plant we publish a NON-SENSITIVE EcoProject
 * record so the project shows up on the map for everyone. If a matching
 * verified project already exists (same lower-cased name and within ~5 km)
 * we ATTACH user-supplied enrichments instead of duplicating the marker.
 *
 * Persisted to localStorage so it survives reloads. Keep this layer free
 * of any sensitive data (no company internals, no costs, no emails).
 */
import type { EcoProject, MoleculeType, ProductionPathway, ProjectStatus } from "./types";
import { projects as verifiedProjects } from "./mockData";
import { observatoryProjects } from "./observatoryData";

const LS_USER_PROJECTS = "gex_ecosystem_user_projects";
const LS_ENRICHMENTS = "gex_ecosystem_enrichments";

export interface ProjectEnrichment {
  /** Free-text production pathway (mapped to ProductionPathway when possible). */
  productionPathway?: ProductionPathway;
  /** Capacity label (e.g. "20 kt H₂/year"). */
  capacity?: string;
  /** Capacity unit (e.g. "kt H₂/year", "MW"). Stored alongside capacity for round-tripping. */
  capacityUnit?: string;
  /** Numeric capacity value (raw, without unit). */
  capacityValue?: string;
  /** Updated owner / developer name. */
  owner?: string;
  /** Lifecycle status. */
  status?: ProjectStatus;
  /** Country (display). */
  country?: string;
  /** Optional extras (only displayed when their key is in `visibleFields`). */
  commissioningYear?: string;
  website?: string;
  offtakers?: string;
  certifications?: string;
  technology?: string;
  /** Fields the user opted to expose on the public Ecosystem Map detail panel. */
  visibleFields?: string[];
  /** When this enrichment was applied. */
  updatedAt: number;
}

function safeRead<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch { return null; }
}
function safeWrite(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* quota */ }
}

/* ── molecule mapping ────────────────────────────────────────────────── */
const MOLECULE_LOOKUP: Record<string, MoleculeType> = {
  hydrogen: "hydrogen", h2: "hydrogen", "green hydrogen": "hydrogen",
  methanol: "methanol", emethanol: "methanol", "e-methanol": "methanol",
  methane: "methane", ammonia: "ammonia", diesel: "diesel",
  gasoline: "gasoline", propane: "propane", butane: "butane", lpg: "lpg",
  kerosene: "kerosene", naphtha: "naphtha", ethanol: "ethanol",
};
function detectMolecule(fuel: string): MoleculeType | undefined {
  const k = fuel.trim().toLowerCase();
  return MOLECULE_LOOKUP[k] ?? Object.entries(MOLECULE_LOOKUP)
    .find(([alias]) => k.includes(alias))?.[1];
}

const PATHWAY_LOOKUP: Record<string, ProductionPathway> = {
  "synthetic pathway": "Synthetic Pathway",
  "biogenic pathway": "Biogenic Pathway",
  "thermochemical pathway": "Thermochemical Pathway",
  "hybrid pathway": "Hybrid Pathway",
  "physical recovery pathway": "Physical Recovery Pathway",
};
function detectPathway(p?: string): ProductionPathway | undefined {
  if (!p) return undefined;
  return PATHWAY_LOOKUP[p.trim().toLowerCase()];
}

function mapMaturityToEcoStatus(stage?: string): ProjectStatus {
  const s = (stage ?? "").toLowerCase();
  if (s.includes("operating") || s.includes("commission")) return "operational";
  if (s.includes("construction")) return "construction";
  if (s.includes("concept")) return "concept";
  return "planned";
}

/* ── public API ──────────────────────────────────────────────────────── */

export interface PlantPublishInput {
  /** Stable id (use the plant slug). */
  slug: string;
  name: string;
  lat?: number;
  lng?: number;
  country?: string;
  fuelType: string;        // e.g. "Hydrogen + Methanol"
  capacity?: string;
  capacityUnit?: string;
  capacityValue?: string;
  owner?: string;          // company name
  pathway?: string;        // free-text from form
  maturityStage?: string;
  /** Optional extras */
  commissioningYear?: string;
  website?: string;
  offtakers?: string;
  certifications?: string;
  technology?: string;
  visibleFields?: string[];
}

/** Haversine distance in km. */
function distanceKm(a: [number, number], b: [number, number]) {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const R = 6371;
  const dLat = toRad(b[0] - a[0]); const dLng = toRad(b[1] - a[1]);
  const s = Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(s)));
}

/* ── Matching engine ───────────────────────────────────────────────────
 * Tiered rules (highest confidence first):
 *   1. name-exact            — normalized names are identical
 *   2. name+molecule         — normalized names match AND molecules align
 *   3. name+proximity        — normalized names match AND ≤ 25 km apart
 *   4. molecule+proximity    — same molecule AND ≤ 5 km apart
 * Lower-confidence rules are only used when the higher ones don't fire.
 */
export type MatchRule =
  | "name-exact"
  | "name+molecule"
  | "name+proximity"
  | "molecule+proximity";

export interface MatchResult {
  project: EcoProject;
  rule: MatchRule;
  /** Human-readable explanation suitable for tooltips/toasts. */
  reason: string;
  /** Distance in km when proximity contributed (else undefined). */
  distanceKm?: number;
}

/** Lower-case, strip accents/punctuation, collapse whitespace. */
function normalizeName(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function hasCoords(input: PlantPublishInput): boolean {
  return typeof input.lat === "number" && typeof input.lng === "number" &&
    Number.isFinite(input.lat) && Number.isFinite(input.lng) &&
    (input.lat !== 0 || input.lng !== 0);
}

/** Find a verified ecosystem project that this plant should attach to. */
export function findExistingEcosystemMatchDetailed(
  input: PlantPublishInput,
): MatchResult | null {
  const pool: EcoProject[] = [...verifiedProjects, ...observatoryProjects]
    .filter((p) => p.layer === "production");
  const nameKey = normalizeName(input.name);
  const moleculeKey = detectMolecule(input.fuelType);
  const here: [number, number] | null = hasCoords(input)
    ? [input.lat as number, input.lng as number] : null;

  // Pre-compute distance once per pool entry (when we have coords).
  const enriched = pool.map((p) => ({
    p,
    nName: normalizeName(p.name),
    d: here ? distanceKm(here, [p.lat, p.lng]) : Infinity,
  }));

  // Rule 1 — exact normalized name
  const exact = enriched.find((x) => x.nName === nameKey);
  if (exact) return {
    project: exact.p, rule: "name-exact",
    reason: `Exact name match: "${exact.p.name}".`,
    distanceKm: here ? exact.d : undefined,
  };

  // Rule 2 — normalized name (substring either way) AND same molecule
  const nameLike = enriched.filter((x) =>
    x.nName.includes(nameKey) || nameKey.includes(x.nName));
  if (moleculeKey) {
    const m = nameLike.find((x) => x.p.moleculeType === moleculeKey);
    if (m) return {
      project: m.p, rule: "name+molecule",
      reason: `Name overlap with "${m.p.name}" and same molecule (${moleculeKey}).`,
      distanceKm: here ? m.d : undefined,
    };
  }

  // Rule 3 — name overlap AND ≤ 25 km
  if (here) {
    const n = nameLike
      .filter((x) => x.d <= 25)
      .sort((a, b) => a.d - b.d)[0];
    if (n) return {
      project: n.p, rule: "name+proximity",
      reason: `Name overlap with "${n.p.name}" within ${n.d.toFixed(1)} km.`,
      distanceKm: n.d,
    };
  }

  // Rule 4 — same molecule AND ≤ 5 km
  if (here && moleculeKey) {
    const n = enriched
      .filter((x) => x.p.moleculeType === moleculeKey && x.d <= 5)
      .sort((a, b) => a.d - b.d)[0];
    if (n) return {
      project: n.p, rule: "molecule+proximity",
      reason: `Same molecule (${moleculeKey}) within ${n.d.toFixed(1)} km of "${n.p.name}".`,
      distanceKm: n.d,
    };
  }

  return null;
}

/** Backwards-compatible wrapper returning only the matched project. */
export function findExistingEcosystemMatch(input: PlantPublishInput): EcoProject | null {
  return findExistingEcosystemMatchDetailed(input)?.project ?? null;
}

/**
 * Publish a plant to the Ecosystem Map.
 * - If a matching verified project exists → write an Enrichment patch.
 * - Otherwise → create a new user-owned EcoProject record.
 * Returns `{ kind, ecoProjectId }`.
 */
export function publishPlantToEcosystem(input: PlantPublishInput): {
  kind: "enriched" | "added" | "skipped";
  ecoProjectId: string | null;
  rule?: MatchRule;
  reason?: string;
} {
  const coords = hasCoords(input);

  const enrichment: ProjectEnrichment = {
    productionPathway: detectPathway(input.pathway),
    capacity: input.capacity || undefined,
    capacityUnit: input.capacityUnit || undefined,
    capacityValue: input.capacityValue || undefined,
    owner: input.owner || undefined,
    status: mapMaturityToEcoStatus(input.maturityStage),
    country: input.country || undefined,
    commissioningYear: input.commissioningYear || undefined,
    website: input.website || undefined,
    offtakers: input.offtakers || undefined,
    certifications: input.certifications || undefined,
    technology: input.technology || undefined,
    visibleFields: input.visibleFields,
    updatedAt: Date.now(),
  };

  const match = findExistingEcosystemMatchDetailed(input);
  if (match) {
    const all = safeRead<Record<string, ProjectEnrichment>>(LS_ENRICHMENTS) ?? {};
    all[match.project.id] = enrichment;
    safeWrite(LS_ENRICHMENTS, all);
    return {
      kind: "enriched", ecoProjectId: match.project.id,
      rule: match.rule, reason: match.reason,
    };
  }

  if (!coords) {
    return {
      kind: "skipped", ecoProjectId: null,
      reason: "Missing coordinates, cannot place a marker on the map.",
    };
  }

  const molecule = detectMolecule(input.fuelType);
  const eco: EcoProject = {
    id: `user-${input.slug}`,
    name: input.name,
    lat: input.lat as number,
    lng: input.lng as number,
    status: enrichment.status ?? "planned",
    layer: "production",
    moleculeType: molecule,
    productionPathway: enrichment.productionPathway,
    capacity: enrichment.capacity,
    owner: enrichment.owner,
    country: input.country,
    dataSource: "generated",
    owned: true,
  };

  const list = safeRead<EcoProject[]>(LS_USER_PROJECTS) ?? [];
  const next = list.filter((p) => p.id !== eco.id).concat(eco);
  safeWrite(LS_USER_PROJECTS, next);
  return {
    kind: "added", ecoProjectId: eco.id,
    reason: "No existing ecosystem project matched, added a new marker.",
  };
}

/** Read all locally-published user projects. */
export function getUserPublishedProjects(): EcoProject[] {
  return safeRead<EcoProject[]>(LS_USER_PROJECTS) ?? [];
}

/** Read enrichments keyed by the ecosystem project id. */
export function getEcosystemEnrichments(): Record<string, ProjectEnrichment> {
  return safeRead<Record<string, ProjectEnrichment>>(LS_ENRICHMENTS) ?? {};
}

/** Apply enrichment patches to a list of EcoProjects (returns a new array). */
export function applyEnrichments(list: EcoProject[]): EcoProject[] {
  const enr = getEcosystemEnrichments();
  if (Object.keys(enr).length === 0) return list;
  return list.map((p) => {
    const e = enr[p.id];
    if (!e) return p;
    return {
      ...p,
      productionPathway: e.productionPathway ?? p.productionPathway,
      capacity: e.capacity ?? p.capacity,
      owner: e.owner ?? p.owner,
      status: e.status ?? p.status,
      country: e.country ?? p.country,
    };
  });
}

/** Look up the current publication state for a plant slug. */
export function getPlantPublication(input: PlantPublishInput): {
  kind: "added" | "enriched" | "none";
  ecoProjectId: string | null;
  enrichment?: ProjectEnrichment;
  added?: EcoProject;
  rule?: MatchRule;
  reason?: string;
} {
  const userId = `user-${input.slug}`;
  const userList = safeRead<EcoProject[]>(LS_USER_PROJECTS) ?? [];
  const added = userList.find((p) => p.id === userId);
  if (added) return {
    kind: "added", ecoProjectId: userId, added,
    reason: "Published as a standalone marker.",
  };
  const match = findExistingEcosystemMatchDetailed(input);
  if (match) {
    const enr = safeRead<Record<string, ProjectEnrichment>>(LS_ENRICHMENTS) ?? {};
    if (enr[match.project.id]) {
      return {
        kind: "enriched", ecoProjectId: match.project.id,
        enrichment: enr[match.project.id],
        rule: match.rule, reason: match.reason,
      };
    }
  }
  return {
    kind: "none", ecoProjectId: null,
    reason: hasCoords(input)
      ? "Not published yet."
      : "Missing coordinates, add latitude/longitude to enable matching.",
  };
}

/** Remove this plant from the Ecosystem Map (drops added marker and any enrichment). */
export function unpublishPlantFromEcosystem(input: PlantPublishInput): void {
  const userId = `user-${input.slug}`;
  const userList = safeRead<EcoProject[]>(LS_USER_PROJECTS) ?? [];
  const nextList = userList.filter((p) => p.id !== userId);
  if (nextList.length !== userList.length) safeWrite(LS_USER_PROJECTS, nextList);
  const match = findExistingEcosystemMatch(input);
  if (match) {
    const enr = safeRead<Record<string, ProjectEnrichment>>(LS_ENRICHMENTS) ?? {};
    if (enr[match.id]) {
      delete enr[match.id];
      safeWrite(LS_ENRICHMENTS, enr);
    }
  }
}