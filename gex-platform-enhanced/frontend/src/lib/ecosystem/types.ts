/**
 * Ecosystem data types — canonical data shapes.
 * This is the API contract for all project data ingestion.
 */

/** Project lifecycle status */
export type ProjectStatus = "operational" | "construction" | "planned" | "concept" | "cancelled";

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
