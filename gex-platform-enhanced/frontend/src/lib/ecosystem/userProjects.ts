/**
 * userProjects — bridge between Plant Builder and the Ecosystem Map.
 *
 * When a user creates a new plant we publish a NON-SENSITIVE EcoProject
 * record so the project shows up on the map for everyone. If a matching
 * project already exists we ATTACH the user's reading to it instead of
 * duplicating the marker — and never overwrite what was already there.
 *
 * PERSISTENCE MOVED TO THE BACKEND (2026-09-17). This module used to write
 * `localStorage` under `gex_ecosystem_user_projects` and
 * `gex_ecosystem_enrichments`. The comment above said "for everyone", but
 * browser storage is per-device, so a published project reached no other user,
 * no other device and never the backend. Publication now goes through
 * `ecosystemApi`, and this module keeps only an in-memory cache of the server
 * feed so the matcher has a pool to work against synchronously.
 *
 * Keep this layer free of sensitive data (no company internals, no costs, no
 * emails). What a publisher chooses to expose beyond the core marker fields is
 * carried in `visibleFields` and enforced server-side.
 */
import type {
  EcoProject, MoleculeType, ProductionPathway, ProjectPhase, ProjectStatus,
} from "./types";
import { projects as verifiedProjects } from "./mockData";
import { observatoryProjects } from "./observatoryData";
import {
  attachEnrichment, fetchEcosystem, publishProject,
  withdrawEnrichment, withdrawProject,
  type ServerEnrichment,
} from "./ecosystemApi";

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
  /** Where the project is in its life. */
  phase?: ProjectPhase;
  /** Whether it is going ahead. Independent of `phase`. */
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

/* ── server feed cache ───────────────────────────────────────────────────
 * The matcher runs synchronously against a candidate pool, and the callers of
 * getPlantPublication/applyEnrichments are synchronous too. So the feed is
 * fetched asynchronously and cached here. Nothing is persisted in the browser:
 * an empty cache means "not loaded yet", never "nothing published".
 */
let _publishedCache: EcoProject[] = [];
let _enrichmentCache: ServerEnrichment[] = [];
let _loaded = false;

/** Refresh the cached server feed. Call on map mount and after publishing. */
export async function refreshEcosystem(): Promise<void> {
  const feed = await fetchEcosystem();
  _publishedCache = feed.projects;
  _enrichmentCache = feed.enrichments;
  _loaded = true;
}

/** False until the first successful refresh — callers can distinguish
 *  "nothing published" from "not loaded yet". */
export function ecosystemLoaded(): boolean { return _loaded; }

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

/**
 * Plant-builder maturity stage → Declared Phase (Data Structure v4.2, L2).
 *
 * The plant builder's own list is the 11-value one (Concept … Operating), so
 * this maps that ladder, not the FEL-numbered variant. A stage this does not
 * recognise reads as "unknown" rather than being rounded to a neighbour:
 * inventing a phase is what the split exists to prevent.
 */
export function mapMaturityToPhase(stage?: string): ProjectPhase {
  const s = (stage ?? "").toLowerCase();
  if (!s.trim()) return "unknown";
  if (s.includes("operating") || s.includes("operation")) return "operation";
  if (s.includes("commission")) return "commissioning";
  if (s.includes("construction")) return "construction";
  // "Pre FID", "FID" and "Permitting" all sit in the financing window; permits
  // are a workstream, not a phase, so they do not move the phase on their own.
  if (s.includes("fid") || s.includes("permitting")) return "financing";
  if (s.includes("pre feed") || s.includes("pre-feed")) return "pre_feasibility";
  if (s.includes("feed")) return "feed";
  if (s.includes("feasibility")) return "pre_feasibility";
  if (s.includes("concept")) return "concept";
  return "unknown";
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
  /** Declared phase, when the caller knows it. Otherwise derived from `maturityStage`. */
  phase?: ProjectPhase;
  /** Whether the project is going ahead. Defaults to active. */
  status?: ProjectStatus;
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
 *   1. name-exact              — identical names AND location does not conflict
 *   2. name+molecule           — normalized names match AND molecules align
 *   3. name+proximity          — normalized names match AND ≤ 25 km apart
 *   4. molecule+proximity+owner — same molecule AND ≤ 5 km AND same owner
 * Lower-confidence rules are only used when the higher ones don't fire.
 *
 * A false MERGE (two real projects collapsed into one) is far more costly than
 * a false SPLIT (one project shown as two markers): a split is visible and is
 * fixed by merging, a merge silently corrupts both records. Every rule here is
 * therefore biased towards NOT matching when the evidence is thin.
 *
 * Two rules were tightened on 2026-09-16:
 *   - Rule 1 had no location test, so two projects sharing a generic name on
 *     different continents merged. Names like "Green Hydrogen Project" are the
 *     norm in this sector. It now requires location agreement.
 *   - Rule 4 had no name and no owner test, so ANY two same-molecule projects
 *     within 5 km merged — which describes every industrial cluster in Europe
 *     (Rotterdam, Antwerp, Duisburg, Humber). It now requires the same owner.
 * Both were latent only because the candidate pool ships empty; they would have
 * fired on the first real import.
 */
export type MatchRule =
  | "name-exact"
  | "name+molecule"
  | "name+proximity"
  | "molecule+proximity+owner";

export interface MatchResult {
  project: EcoProject;
  rule: MatchRule;
  /** Human-readable explanation suitable for tooltips/toasts. */
  reason: string;
  /** Distance in km when proximity contributed (else undefined). */
  distanceKm?: number;
}

/**
 * Letters that NFD does NOT decompose — they are distinct letters, not a base
 * plus a combining mark, so the accent strip below misses them entirely and
 * "Ørsted" would normalize to "rsted". Nordic names are common in this sector.
 */
const TRANSLITERATE: Record<string, string> = {
  "ø": "o", "æ": "ae", "å": "a", "ß": "ss", "ð": "d", "þ": "th",
  "ł": "l", "đ": "d", "ı": "i", "œ": "oe", "ǅ": "dz",
};

/** Lower-case, strip accents/punctuation, collapse whitespace. */
function normalizeName(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[øæåßðþłđıœǅ]/g, (c) => TRANSLITERATE[c] ?? c)
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function hasCoords(input: PlantPublishInput): boolean {
  return typeof input.lat === "number" && typeof input.lng === "number" &&
    Number.isFinite(input.lat) && Number.isFinite(input.lng) &&
    (input.lat !== 0 || input.lng !== 0);
}

/** True when a pool entry carries usable coordinates (0,0 is a placeholder). */
function ecoHasCoords(p: EcoProject): boolean {
  return Number.isFinite(p.lat) && Number.isFinite(p.lng) &&
    (p.lat !== 0 || p.lng !== 0);
}

/**
 * Normalize an organisation name for comparison: strip accents, punctuation and
 * the common legal-form suffixes, so "Ørsted A/S" and "Orsted AS" agree.
 * Deliberately NOT a substring test — that is how unrelated companies match.
 */
const ORG_SUFFIXES = new Set([
  "as", "a s", "asa", "ab", "ag", "bv", "nv", "gmbh", "sa", "sas", "sarl",
  "srl", "spa", "plc", "ltd", "limited", "llc", "lp", "inc", "incorporated",
  "corp", "corporation", "co", "company", "oy", "oyj", "aps", "kft", "sp z oo",
  "pte", "pty", "holding", "holdings", "group",
]);
function normalizeOrg(s: string | undefined | null): string {
  if (!s) return "";
  // Punctuated legal forms ("A/S", "S.A.", "B.V.") survive normalizeName as runs
  // of single letters; rejoin them so they can be recognised as suffixes.
  const collapsed = normalizeName(s)
    .replace(/\b(?:[a-z] )+[a-z]\b/g, (m) => m.replace(/ /g, ""));
  const words = collapsed.split(" ").filter(Boolean);
  while (words.length > 1 && ORG_SUFFIXES.has(words[words.length - 1])) {
    words.pop();
  }
  return words.join(" ");
}

/** Does the country string agree, once normalized? Empty on either side = unknown. */
function countriesAgree(a: string | undefined, b: string | undefined): boolean | null {
  const x = normalizeName(a ?? ""); const y = normalizeName(b ?? "");
  if (!x || !y) return null;
  return x === y;
}

/**
 * Tokens that appear in a large share of project names in this sector and carry
 * no identifying information. A name made only of these has no identity, and
 * two names sharing only these have nothing in common.
 *
 * Molecule words are here deliberately: Rule 2 compares molecule separately, so
 * counting "hydrogen" as a name match would double-count the same evidence.
 */
const GENERIC_NAME_TOKENS = new Set([
  "project", "projects", "plant", "plants", "facility", "facilities", "site",
  "sites", "unit", "units", "complex", "hub", "park", "terminal", "station",
  "works", "refinery", "factory", "production", "plan", "development",
  "green", "blue", "grey", "clean", "renewable", "sustainable", "low", "carbon",
  "energy", "energies", "power", "fuel", "fuels", "efuel", "efuels", "gas",
  "hydrogen", "h2", "ammonia", "nh3", "methanol", "meoh", "methane", "ch4",
  "diesel", "kerosene", "gasoline", "ethanol", "naphtha", "propane", "butane",
  "lpg", "saf", "hvo", "ptx", "powertox", "power2x",
  "phase", "stage", "step", "expansion", "extension", "the", "of", "and", "at",
  "new", "international", "global", "group", "company", "limited", "ltd",
  // connectors, and the X of "Power-to-X" / "PtX", which is a category not a name
  "to", "for", "in", "on", "by", "with", "x",
]);

/**
 * Standalone roman numerals we trust as ordinals. "i" and "v" are ambiguous
 * (initials, roman one and five). "x" is excluded too — "Power-to-X" and "PtX"
 * are ubiquitous in this sector, and reading that X as ten would make every
 * Power-to-X project look like a different phase from every numbered one.
 */
const ROMAN: Record<string, number> = {
  ii: 2, iii: 3, iv: 4, vi: 6, vii: 7, viii: 8, ix: 9,
};

interface NameParts {
  distinctive: Set<string>;
  ordinals: Set<number>;
}

/**
 * Split a normalized name into the tokens that actually identify it, plus any
 * ordinals. Single characters are dropped — they are initials and punctuation
 * fragments, not identity.
 */
function nameParts(normalized: string): NameParts {
  const distinctive = new Set<string>();
  const ordinals = new Set<number>();
  for (const tok of normalized.split(" ").filter(Boolean)) {
    if (/^\d+$/.test(tok)) { ordinals.add(Number(tok)); continue; }
    if (tok in ROMAN) { ordinals.add(ROMAN[tok]); continue; }
    if (tok.length < 2) continue;
    if (GENERIC_NAME_TOKENS.has(tok)) continue;
    distinctive.add(tok);
  }
  return { distinctive, ordinals };
}

const NAME_OVERLAP_MIN = 0.5;
const NAME_PROXIMITY_MAX_KM = 10;

/**
 * Do two project names overlap enough to be the same project?
 *
 * Replaces a two-way substring test that matched far too much: any pool name
 * that normalized to a short string was a substring of almost every input, so
 * a project literally named "H2" captured every name containing "h2", and
 * "hydro" matched "hydrogen". Substring also has no notion of which words
 * carry identity — "Green Hydrogen Project" overlapped every other project
 * with those words, which in this sector is most of them.
 *
 * The test is now: the DISTINCTIVE tokens must intersect, and the intersection
 * must cover at least half of the shorter name's distinctive tokens. A name
 * with no distinctive tokens at all matches nothing, which is correct — it
 * identifies nothing.
 *
 * `score` is that coverage ratio, returned so candidates can be RANKED rather
 * than taken in whatever order the pool happens to be in.
 */
function namesOverlap(
  a: string, b: string,
): { ok: boolean; score: number; why: string } {
  const A = nameParts(a); const B = nameParts(b);

  if (A.distinctive.size === 0 || B.distinctive.size === 0) {
    return { ok: false, score: 0, why: "no distinctive words in the name" };
  }
  const shared = [...A.distinctive].filter((w) => B.distinctive.has(w));
  if (shared.length === 0) {
    return { ok: false, score: 0, why: "no shared distinctive words" };
  }

  const ratio = shared.length / Math.min(A.distinctive.size, B.distinctive.size);
  return ratio >= NAME_OVERLAP_MIN
    ? { ok: true, score: ratio, why: `shared name words: ${shared.join(", ")}` }
    : { ok: false, score: ratio, why: "name overlap too thin" };
}

/**
 * "Phase 1" and "Phase 2" are different projects however well the rest of the
 * record agrees — same owner, same molecule, a few hundred metres apart is the
 * NORMAL shape of two phases of one development, so proximity and ownership
 * argue for merging exactly when they should not.
 *
 * This sits with the location guard rather than inside namesOverlap because
 * Rule 4 never looks at names at all, and would otherwise merge the phases that
 * Rules 2 and 3 had just declined.
 *
 * Only a contradiction when BOTH sides state an ordinal. One side being silent
 * says nothing: "NEOM Helios" may well be "NEOM Helios Phase 1".
 */
function ordinalsConflict(a: string, b: string): boolean {
  const A = nameParts(a).ordinals; const B = nameParts(b).ordinals;
  if (A.size === 0 || B.size === 0) return false;
  return ![...A].some((n) => B.has(n));
}

/**
 * Rule 1's guard. An identical name is strong evidence, but not on its own:
 * it must not be CONTRADICTED by location. Returns false when we have no
 * location evidence at all — failing to match costs a duplicate marker, which
 * is the cheap error.
 */
const NAME_EXACT_MAX_KM = 50;

/**
 * POSITIVE evidence that two records are in different places. "Unknown" is not
 * a conflict — we only exclude a candidate we can actually rule out.
 *
 * This is applied to the whole cascade, not just Rule 1. Rule 2 matches on name
 * substring with no distance test, and an exact name is also a substring, so a
 * candidate rejected by Rule 1 on location would otherwise fall straight through
 * to Rule 2 and merge anyway.
 */
function locationConflicts(
  here: [number, number] | null, p: EcoProject,
  inputCountry: string | undefined, d: number,
): boolean {
  if (here && ecoHasCoords(p)) return d > NAME_EXACT_MAX_KM;
  return countriesAgree(inputCountry, p.country) === false;
}

function locationSupportsMatch(
  here: [number, number] | null, p: EcoProject,
  inputCountry: string | undefined, d: number,
): { ok: boolean; why: string } {
  if (here && ecoHasCoords(p)) {
    return d <= NAME_EXACT_MAX_KM
      ? { ok: true, why: `${d.toFixed(1)} km apart` }
      : { ok: false, why: `${d.toFixed(0)} km apart` };
  }
  const sameCountry = countriesAgree(inputCountry, p.country);
  if (sameCountry === true) return { ok: true, why: `both in ${p.country}` };
  if (sameCountry === false) return { ok: false, why: "different countries" };
  return { ok: false, why: "no location evidence on either side" };
}

/** Find a verified ecosystem project that this plant should attach to. */
export function findExistingEcosystemMatchDetailed(
  input: PlantPublishInput,
): MatchResult | null {
  // The pool now includes what OTHER tenants have published, which is the
  // point of moving publication server-side: a user's plant can attach to a
  // project somebody else put on the map.
  const pool: EcoProject[] = [
    ...verifiedProjects, ...observatoryProjects, ..._publishedCache,
  ].filter((p) => p.layer === "production");
  const nameKey = normalizeName(input.name);
  const moleculeKey = detectMolecule(input.fuelType);
  const here: [number, number] | null = hasCoords(input)
    ? [input.lat as number, input.lng as number] : null;

  const ownerKey = normalizeOrg(input.owner);

  // Pre-compute distance once per pool entry (when BOTH sides have real coords).
  const enriched = pool.map((p) => ({
    p,
    nName: normalizeName(p.name),
    nOwner: normalizeOrg(p.owner),
    d: here && ecoHasCoords(p) ? distanceKm(here, [p.lat, p.lng]) : Infinity,
  }));

  // Drop candidates we can positively rule out, before any rule runs — either
  // because we can place them somewhere else, or because the two names state
  // different phase numbers. Every rule inherits both guards; applied inside a
  // single rule they would be cosmetic, since a later rule would re-merge what
  // an earlier one declined.
  const candidates = enriched.filter(
    (x) => !locationConflicts(here, x.p, input.country, x.d) &&
           !ordinalsConflict(nameKey, x.nName));

  // Rule 1 — exact normalized name, AND location must positively support it.
  // Without the location test, two projects sharing a generic name on
  // different continents merge. Generic names are the norm in this sector.
  for (const x of candidates.filter((e) => e.nName === nameKey)) {
    const loc = locationSupportsMatch(here, x.p, input.country, x.d);
    if (!loc.ok) continue;
    return {
      project: x.p, rule: "name-exact",
      reason: `Exact name match: "${x.p.name}" (${loc.why}).`,
      distanceKm: Number.isFinite(x.d) ? x.d : undefined,
    };
  }

  // Names that share enough DISTINCTIVE words to plausibly be the same project.
  // Was a two-way substring test, which matched on generic sector vocabulary
  // and on any short pool name. See namesOverlap.
  const nameLike = candidates
    .map((x) => ({ x, ov: namesOverlap(nameKey, x.nName) }))
    .filter((e) => e.ov.ok);

  // Rule 2 — distinctive name overlap AND same molecule.
  // Ranked by name-overlap strength: taking the first hit made the result
  // depend on the order the pool arrays happen to be concatenated in.
  if (moleculeKey) {
    const m = nameLike
      .filter((e) => e.x.p.moleculeType === moleculeKey)
      .sort((a, b) => b.ov.score - a.ov.score || a.x.d - b.x.d)[0];
    if (m) return {
      project: m.x.p, rule: "name+molecule",
      reason: `Name overlap with "${m.x.p.name}" (${m.ov.why}) ` +
              `and same molecule (${moleculeKey}).`,
      distanceKm: here && Number.isFinite(m.x.d) ? m.x.d : undefined,
    };
  }

  // Rule 3 — distinctive name overlap AND proximity, when the molecule is
  // simply UNKNOWN rather than different.
  //
  // Rule 3 only ever runs when Rule 2 did not fire, and Rule 2 fires whenever
  // the molecules agree. So Rule 3's live cases are exactly two: the molecule
  // is unknown on one side, or the molecules are known and CONTRADICT. It used
  // to merge both. Merging on a contradiction is wrong — a methanol plant and
  // an ammonia plant sharing a site and a site name are two projects, and this
  // is the normal shape of a developer's cluster. Requiring the molecule to be
  // unknown leaves Rule 3 doing only its defensible job.
  //
  // A rule-local guard is enough here, unlike the location and ordinal cases:
  // the only later rule is Rule 4, which requires the molecules to be EQUAL, so
  // nothing downstream can re-merge what this declines. A test pins that.
  //
  // The radius drops from 25 km to 10 km. 25 km spans a whole port complex and
  // several unrelated developments; this rule has no molecule agreement and no
  // owner agreement behind it, so it should be the tightest of the proximity
  // rules, not the loosest.
  if (here) {
    const moleculeKnownBothSides = (pm?: MoleculeType) =>
      moleculeKey !== undefined && pm !== undefined;
    const n = nameLike
      .filter((e) => e.x.d <= NAME_PROXIMITY_MAX_KM &&
                     !moleculeKnownBothSides(e.x.p.moleculeType))
      .sort((a, b) => b.ov.score - a.ov.score || a.x.d - b.x.d)[0];
    if (n) return {
      project: n.x.p, rule: "name+proximity",
      reason: `Name overlap with "${n.x.p.name}" (${n.ov.why}) ` +
              `within ${n.x.d.toFixed(1)} km, molecule not stated on both sides.`,
      distanceKm: n.x.d,
    };
  }

  // Rule 4 — same molecule AND ≤ 5 km AND the SAME OWNER.
  // The owner test is what makes this rule safe. Without it the rule matched
  // any two same-molecule projects within 5 km, which is the definition of an
  // industrial cluster — it would have attached a user's plant to a stranger's
  // project in Rotterdam, Antwerp or the Humber. With it, the rule still does
  // its real job: catching the same project filed under a different name.
  if (here && moleculeKey && ownerKey) {
    const n = candidates
      .filter((x) => x.p.moleculeType === moleculeKey && x.d <= 5 &&
                     x.nOwner !== "" && x.nOwner === ownerKey)
      .sort((a, b) => a.d - b.d)[0];
    if (n) return {
      project: n.p, rule: "molecule+proximity+owner",
      reason: `Same owner (${n.p.owner}) and molecule (${moleculeKey}) ` +
              `within ${n.d.toFixed(1)} km of "${n.p.name}".`,
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
export async function publishPlantToEcosystem(input: PlantPublishInput): Promise<{
  kind: "enriched" | "added" | "skipped";
  ecoProjectId: string | null;
  rule?: MatchRule;
  reason?: string;
}> {
  const coords = hasCoords(input);

  const enrichment: ProjectEnrichment = {
    productionPathway: detectPathway(input.pathway),
    capacity: input.capacity || undefined,
    capacityUnit: input.capacityUnit || undefined,
    capacityValue: input.capacityValue || undefined,
    owner: input.owner || undefined,
    phase: input.phase ?? mapMaturityToPhase(input.maturityStage),
    status: input.status ?? "active",
    country: input.country || undefined,
    commissioningYear: input.commissioningYear || undefined,
    website: input.website || undefined,
    offtakers: input.offtakers || undefined,
    certifications: input.certifications || undefined,
    technology: input.technology || undefined,
    visibleFields: input.visibleFields,
    updatedAt: Date.now(),
  };

  // ATTACH, NEVER OVERWRITE. The server keys an enrichment by (target, tenant),
  // so this adds THIS tenant's reading beside any other tenant's. Nothing that
  // is already on the map is destroyed by publishing.
  const match = findExistingEcosystemMatchDetailed(input);
  if (match) {
    await attachEnrichment({
      targetEcoId: match.project.id,
      payload: enrichment as unknown as Record<string, unknown>,
      visibleFields: input.visibleFields ?? [],
      matchRule: match.rule,
      matchReason: match.reason,
    });
    await refreshEcosystem();
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

  const res = await publishProject({
    slug: input.slug,
    name: input.name,
    lat: input.lat as number,
    lng: input.lng as number,
    phase: enrichment.phase ?? "unknown",
    status: enrichment.status ?? "active",
    country: input.country,
    moleculeType: detectMolecule(input.fuelType),
    productionPathway: enrichment.productionPathway,
    owner: enrichment.owner,
    capacity: enrichment.capacity,
    capacityValue: enrichment.capacityValue,
    capacityUnit: enrichment.capacityUnit,
    extras: {
      commissioningYear: enrichment.commissioningYear,
      website: enrichment.website,
      offtakers: enrichment.offtakers,
      certifications: enrichment.certifications,
      technology: enrichment.technology,
    },
    visibleFields: input.visibleFields ?? [],
  });
  await refreshEcosystem();
  return {
    kind: "added", ecoProjectId: res.project?.id ?? null,
    reason: "No existing ecosystem project matched, added a new marker.",
  };
}

/** Projects this viewer published, from the cached server feed. */
export function getUserPublishedProjects(): EcoProject[] {
  return _publishedCache.filter((p) => (p as { owned?: boolean }).owned);
}

/** Every published project in the cached server feed, whoever published it. */
export function getPublishedEcosystemProjects(): EcoProject[] {
  return _publishedCache;
}

/**
 * Enrichments keyed by target project id.
 *
 * NOTE: a project may carry MORE THAN ONE enrichment, from different tenants.
 * This accessor keeps only the most recent per project, which is what the
 * existing single-value map UI expects. Use `getEnrichmentsByProject` when the
 * disagreement matters — collapsing two readings into one is exactly what the
 * review document warns against, and this accessor is a display convenience,
 * not the source of truth.
 */
export function getEcosystemEnrichments(): Record<string, ProjectEnrichment> {
  const out: Record<string, ProjectEnrichment> = {};
  for (const e of [..._enrichmentCache].sort(
    (a, b) => a.updated_at.localeCompare(b.updated_at))) {
    out[e.target_eco_id] = e.payload as unknown as ProjectEnrichment;
  }
  return out;
}

/** All readings of each project, so a caller can show the disagreement. */
export function getEnrichmentsByProject(): Record<string, ServerEnrichment[]> {
  const out: Record<string, ServerEnrichment[]> = {};
  for (const e of _enrichmentCache) {
    (out[e.target_eco_id] ||= []).push(e);
  }
  return out;
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
      phase: e.phase ?? p.phase,
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
  const added = getUserPublishedProjects().find(
    (p) => p.id && _slugOf(p) === input.slug);
  if (added) return {
    kind: "added", ecoProjectId: added.id,
    added, reason: "Published as a standalone marker.",
  };
  const match = findExistingEcosystemMatchDetailed(input);
  if (match) {
    const mine = _enrichmentCache.find((e) => e.target_eco_id === match.project.id);
    if (mine) {
      return {
        kind: "enriched", ecoProjectId: match.project.id,
        enrichment: mine.payload as unknown as ProjectEnrichment,
        rule: match.rule, reason: match.reason,
      };
    }
  }
  return {
    kind: "none", ecoProjectId: null,
    reason: hasCoords(input)
      ? (ecosystemLoaded() ? "Not published yet." : "Ecosystem feed not loaded yet.")
      : "Missing coordinates, add latitude/longitude to enable matching.",
  };
}

/** The publishing slug a server record came from. */
function _slugOf(p: EcoProject): string | undefined {
  return (p as { slug?: string }).slug;
}

/**
 * Remove this plant from the Ecosystem Map.
 *
 * Withdrawal is a SOFT delete server-side: the row is retained and stops being
 * served. Nothing another tenant published or enriched is touched.
 */
export async function unpublishPlantFromEcosystem(
  input: PlantPublishInput,
): Promise<void> {
  await withdrawProject(input.slug).catch(() => undefined);
  const match = findExistingEcosystemMatchDetailed(input);
  if (match) await withdrawEnrichment(match.project.id).catch(() => undefined);
  await refreshEcosystem().catch(() => undefined);
}
