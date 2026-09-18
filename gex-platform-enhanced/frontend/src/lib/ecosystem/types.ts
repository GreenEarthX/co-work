/**
 * Ecosystem data types — canonical data shapes.
 * This is the API contract for all project data ingestion.
 */

/**
 * Lifecycle is two independent fields (Data Structure v4.2).
 *
 * One list cannot hold both. "concept, planned, construction, operational,
 * cancelled" mixed them, so a cancelled project had no recordable phase and a
 * planned one had no recordable status — and imported statuses (Global Energy
 * Monitor, IEA) had nowhere to land without being flattened.
 *
 * `ProjectPhase` says where a project is in its life. `ProjectStatus` says
 * whether it is going ahead. A project is Cancelled *at* a phase.
 */
export type ProjectPhase =
  | "concept" | "pre_feasibility" | "feed" | "financing"
  | "construction" | "commissioning" | "operation" | "unknown";

export type ProjectStatus =
  | "active" | "on_hold" | "cancelled" | "mothballed" | "decommissioned" | "superseded";

/**
 * Values written before the split. Still present in published rows and in any
 * source that copied this contract, so every read normalises through
 * `normaliseLifecycle`.
 */
export type LegacyProjectStatus =
  | "concept" | "planned" | "construction" | "operational" | "cancelled";

export interface ProjectLifecycle {
  phase: ProjectPhase;
  status: ProjectStatus;
}

export const PROJECT_PHASE_LABELS: Record<ProjectPhase, string> = {
  concept: "Concept (FEL 1)",
  pre_feasibility: "Pre-feasibility (FEL 2)",
  feed: "FEED (FEL 3)",
  financing: "Financing",
  construction: "Construction",
  commissioning: "Commissioning",
  operation: "Operation",
  unknown: "Unknown",
};

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  active: "Active",
  on_hold: "On hold",
  cancelled: "Cancelled",
  mothballed: "Mothballed",
  decommissioned: "Decommissioned",
  superseded: "Superseded",
};

/** Phases before a project is being built. Replaces filtering on "planned". */
export const PRE_CONSTRUCTION_PHASES: readonly ProjectPhase[] = [
  "concept", "pre_feasibility", "feed", "financing",
];

const PHASES = Object.keys(PROJECT_PHASE_LABELS) as ProjectPhase[];
const STATUSES = Object.keys(PROJECT_STATUS_LABELS) as ProjectStatus[];

export const isProjectPhase = (v: unknown): v is ProjectPhase =>
  typeof v === "string" && (PHASES as string[]).includes(v);

export const isProjectStatus = (v: unknown): v is ProjectStatus =>
  typeof v === "string" && (STATUSES as string[]).includes(v);

/**
 * Old value → new pair. Two of these deliberately land on `unknown`:
 * "planned" said only that building had not started, and "cancelled" never
 * recorded how far the project had got. Guessing a phase here would invent
 * evidence, which is the habit this split exists to stop.
 */
const LEGACY_LIFECYCLE: Record<LegacyProjectStatus, ProjectLifecycle> = {
  concept: { phase: "concept", status: "active" },
  planned: { phase: "unknown", status: "active" },
  construction: { phase: "construction", status: "active" },
  operational: { phase: "operation", status: "active" },
  cancelled: { phase: "unknown", status: "cancelled" },
};

/**
 * Read a lifecycle from a record that may be in either vocabulary. A recorded
 * phase wins; a legacy status supplies whatever is missing; anything
 * unrecognised reads as Unknown and Active rather than throwing, because this
 * runs over third-party rows.
 *
 * "unknown" is NOT a recorded phase — it is the absence of one, and it is what
 * the server writes into rows that pre-date the split. So a stored "unknown"
 * must not shadow the legacy status that carries the real meaning.
 */
export function normaliseLifecycle(
  input: { phase?: string | null; status?: string | null } | null | undefined,
): ProjectLifecycle {
  const phase = input?.phase;
  const status = input?.status;
  const legacy = typeof status === "string" && status in LEGACY_LIFECYCLE
    ? LEGACY_LIFECYCLE[status as LegacyProjectStatus]
    : undefined;

  if (isProjectPhase(phase) && phase !== "unknown") {
    if (isProjectStatus(status)) return { phase, status };
    return { phase, status: legacy ? legacy.status : "active" };
  }
  if (isProjectStatus(status)) return { phase: "unknown", status };
  if (legacy) return { ...legacy };
  return { phase: "unknown", status: "active" };
}

/** Molecule types produced at production facilities */
export type MoleculeType =
  | "hydrogen" | "methanol" | "methane" | "ammonia" | "diesel"
  | "gasoline" | "propane" | "butane" | "lpg" | "kerosene"
  | "naphtha" | "ethanol";

/** Production technology pathway */
export type ProductionPathway =
  | "Synthetic Pathway" | "Biogenic Pathway" | "Thermochemical Pathway"
  | "Hybrid Pathway" | "Physical Recovery Pathway";

/** Infrastructure asset types */
export type InfraType = "port" | "ccus" | "pipeline" | "hub" | "electricity" | "storage";

/** Top-level layer categories (determines marker shape) */
export type LayerCategory = "production" | "infrastructure" | "offtakers";

/**
 * Core project record — this is the **API contract**.
 * When ingesting real data, map your source fields to this interface.
 */
/** Data provenance tier */
export type DataSource = "verified" | "observatory" | "generated";

export interface EcoProject {
  id: string;
  name: string;
  lat: number;
  lng: number;
  /** Where it is in its life. See `ProjectPhase`. */
  phase: ProjectPhase;
  /** Whether it is going ahead. Independent of `phase`. */
  status: ProjectStatus;
  layer: LayerCategory;
  moleculeType?: MoleculeType;
  productionPathway?: ProductionPathway;
  infraType?: InfraType;
  capacity?: string;
  owner?: string;
  owned?: boolean;
  country?: string;
  offtakerSector?: string;
  offtakerSubSector?: string;
  offtakerApplication?: string;
  /** Data provenance — verified (IEA/HE), observatory (EU Hydrogen Observatory), or generated (mocked) */
  dataSource?: DataSource;
}

/** Transport corridor (shipping, aviation, or CO₂ pipeline) */
export interface TransportRoute {
  id: string;
  name: string;
  points: [number, number][];
  fuelType: string;
  mode: "shipping" | "aviation" | "co2_pipeline";
}

/** Industrial cluster overlay */
export interface EcoCluster {
  id: string;
  name: string;
  lat: number;
  lng: number;
  radius: number;
  projectCount: number;
  production: number;
  infrastructure: number;
  offtakers: number;
  country: string;
  keyMolecules: string[];
}
