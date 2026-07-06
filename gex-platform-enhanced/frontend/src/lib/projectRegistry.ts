/**
 * projectRegistry — Single source of truth for all project/plant metadata.
 *
 * Every feature (Map, Plant Builder, Canvas, Viability Dashboard) reads
 * from this registry so project identity stays unified across the app.
 */

export type PlantStatus = "concept" | "design" | "feasibility" | "construction" | "operational";

export interface ProjectRecord {
  /** URL-safe slug, used as route param */
  id: string;
  /** Groups plant variants under one project umbrella */
  projectGroupId: string;
  /**
   * Optional display name for the collection (group of iterations). When set,
   * this overrides the auto-derived base name shown in the collection header.
   * Stored on every member; the first non-empty value wins at render time.
   */
  collectionName?: string;
  /** Human label for this variant (e.g. "PEM Configuration") */
  variantLabel: string;
  /** Full display name */
  name: string;
  /** Short subtitle for canvas/compact views */
  subtitle: string;
  /** City, Country */
  location: string;
  /** ISO-style country key */
  country: string;
  /** Current project stage */
  status: PlantStatus;
  /** e.g. "Green Hydrogen", "e-Methanol" */
  fuelType: string;
  /** Human-readable capacity */
  capacity: string;
  /** Electrolyzer / plant size in MW */
  capacityMW: number;
  /** Commercial Operation Date year */
  codYear: number;
  /** Legacy static "X ago" label; superseded by `updatedAt`. Optional. */
  lastEdited?: string;
  /** Whether the current demo user owns this project */
  owned: boolean;
  /** Latitude for map placement */
  lat: number;
  /** Longitude for map placement */
  lng: number;
  /** Distinct brand color (HSL) for visual coherence across screens */
  brandHsl: string;
  /** Whether the plant has been archived */
  archived?: boolean;
  /** ISO timestamp of the last cloud update (set when hydrated from Supabase) */
  updatedAt?: string;
}

/**
 * Master project list — the ONLY place project metadata is defined.
 * Add new demo projects here and they propagate everywhere.
 */
export const projectRegistry: ProjectRecord[] = [
  {
    id: "rotterdam-rfnbo",
    projectGroupId: "rotterdam",
    variantLabel: "PEM Configuration",
    name: "Rotterdam RFNBO Hydrogen Plant",
    subtitle: "e-H₂ PEM",
    location: "Rotterdam, Netherlands",
    country: "netherlands",
    status: "feasibility",
    fuelType: "Green Hydrogen",
    capacity: "20 kt H₂/year",
    capacityMW: 100,
    codYear: 2028,
    lastEdited: "2 hours ago",
    owned: true,
    lat: 51.9225,
    lng: 4.47917,
    brandHsl: "174 60% 40%",
  },
  {
    id: "hamburg-h2",
    projectGroupId: "hamburg",
    variantLabel: "PEM Configuration",
    name: "Hamburg Green Hydrogen Plant",
    subtitle: "e-H₂ PEM",
    location: "Hamburg, Germany",
    country: "germany",
    status: "concept",
    fuelType: "Green Hydrogen",
    capacity: "10 kt H₂/year",
    capacityMW: 50,
    codYear: 2030,
    lastEdited: "3 days ago",
    owned: true,
    lat: 53.5511,
    lng: 9.9937,
    brandHsl: "220 55% 50%",
  },
  {
    id: "marseille-efuel",
    projectGroupId: "marseille",
    variantLabel: "Base Configuration",
    name: "Marseille eFuel Pilot",
    subtitle: "e-Methanol",
    location: "Fos-sur-Mer, France",
    country: "france",
    status: "design",
    fuelType: "e-Methanol",
    capacity: "5 kt eMeOH/year",
    capacityMW: 25,
    codYear: 2029,
    lastEdited: "1 week ago",
    owned: true,
    lat: 43.4279,
    lng: 4.9441,
    brandHsl: "32 70% 50%",
  },
  {
    id: "northsea-hydrogen",
    projectGroupId: "northsea",
    variantLabel: "Hybrid Configuration",
    name: "North Sea Hydrogen 10MW",
    subtitle: "e-H₂ + e-MeOH",
    location: "North Sea, Germany",
    country: "germany",
    status: "design",
    fuelType: "Green Hydrogen + e-Methanol",
    capacity: "10 MW",
    capacityMW: 10,
    codYear: 2029,
    lastEdited: "Just now",
    owned: true,
    lat: 54.5,
    lng: 7.5,
    brandHsl: "262 45% 55%",
  },
  {
    id: "antwerp-methanol",
    projectGroupId: "antwerp",
    variantLabel: "Base Configuration",
    name: "Antwerp Green Methanol",
    subtitle: "e-Methanol",
    location: "Antwerp, Belgium",
    country: "belgium",
    status: "concept",
    fuelType: "e-Methanol",
    capacity: "15 kt eMeOH/year",
    capacityMW: 75,
    codYear: 2031,
    lastEdited: "2 weeks ago",
    owned: true,
    lat: 51.2194,
    lng: 4.4025,
    brandHsl: "350 55% 50%",
  },
];

/** Look up a single project by ID — checks localStorage overrides first */
export function getProject(id: string): ProjectRecord | undefined {
  try {
    const raw = localStorage.getItem("ptool_plant_list");
    if (raw) {
      const saved = JSON.parse(raw) as ProjectRecord[];
      const found = saved.find((p) => p.id === id);
      if (found) return found;
    }
  } catch { /* ignore */ }
  return projectRegistry.find((p) => p.id === id);
}

/**
 * Get project by id, or fall back to the user's first real plant from the
 * plant builder cache. Only falls back to the registry seed if nothing
 * is cached yet (first-run, before the user creates anything).
 */
export function getProjectOrDefault(id?: string): ProjectRecord {
  if (id) {
    const found = getProject(id);
    if (found) return found;
  }
  try {
    const raw = localStorage.getItem("ptool_plant_list");
    if (raw) {
      const saved = JSON.parse(raw) as ProjectRecord[];
      if (Array.isArray(saved) && saved.length > 0) {
        const owned = saved.find((p) => p.owned && !p.archived) ?? saved[0];
        if (owned) return owned;
      }
    }
  } catch { /* ignore */ }
  return projectRegistry[0];
}

export const statusStyles: Record<PlantStatus, { bg: string; text: string; label: string }> = {
  concept: { bg: "bg-muted", text: "text-muted-foreground", label: "Concept" },
  design: { bg: "bg-warning-soft", text: "text-warning-soft-foreground", label: "Design" },
  feasibility: { bg: "bg-success-soft", text: "text-success-soft-foreground", label: "Feasibility" },
  construction: { bg: "bg-primary/10", text: "text-primary", label: "Construction" },
  operational: { bg: "bg-success", text: "text-success-foreground", label: "Operational" },
};

/** All plants that belong to a given collection (projectGroupId). */
export function getCollectionPlants(groupId: string, plants: ProjectRecord[]): ProjectRecord[] {
  return plants.filter((p) => p.projectGroupId === groupId);
}

/**
 * Next iteration number for a collection. Counts existing members + 1, but
 * also avoids colliding with a previous iteration that was deleted by
 * scanning current `variantLabel`s and ids for the highest "Iteration N".
 */
export function nextIterationNumber(groupId: string, plants: ProjectRecord[]): number {
  const members = getCollectionPlants(groupId, plants);
  let max = 0;
  for (const m of members) {
    const fromLabel = /iteration\s+(\d+)/i.exec(m.variantLabel ?? "");
    if (fromLabel) max = Math.max(max, parseInt(fromLabel[1], 10));
    const fromVariation = /variation\s*#?\s*(\d+)/i.exec(m.variantLabel ?? "");
    if (fromVariation) max = Math.max(max, parseInt(fromVariation[1], 10));
    const fromId = /-iter-(\d+)$/.exec(m.id);
    if (fromId) max = Math.max(max, parseInt(fromId[1], 10));
  }
  return Math.max(members.length, max) + 1;
}

/** Default label "Plant variation #N" used by the duplicate / new-iteration flow. */
export function nextIterationLabel(groupId: string, plants: ProjectRecord[]): string {
  return `Plant variation #${nextIterationNumber(groupId, plants)}`;
}

/** Strip a trailing " — Iteration N" or " — Plant variation #N" suffix from a plant name. */
export function stripIterationSuffix(name: string): string {
  return (name || "")
    .replace(/\s*[—-]\s*Iteration\s+\d+\s*$/i, "")
    .replace(/\s*[—-]\s*Plant\s+variation\s*#?\s*\d+\s*$/i, "")
    .trim();
}

/**
 * Strip ANY trailing " — <anything>" suffix from a plant name.
 * Used to migrate legacy rows whose `name` was stored as
 * `${baseName} — ${variantLabel}` even when the variant label is custom.
 */
export function stripAnyEmDashSuffix(name: string): string {
  return (name || "").replace(/\s*—\s*[^—]+\s*$/u, "").trim();
}

/** Display name including the variation, joined with a middle dot. */
export function formatPlantFullName(p: Pick<ProjectRecord, "name" | "variantLabel">): string {
  const base = stripAnyEmDashSuffix(p.name);
  return p.variantLabel ? `${base} · ${p.variantLabel}` : base;
}

/**
 * Display name for a collection. Prefers any member's explicit
 * `collectionName`; otherwise derives it from the first member's plant name.
 */
export function getCollectionDisplayName(members: ProjectRecord[]): string {
  const explicit = members.find((m) => (m.collectionName || "").trim())?.collectionName;
  if (explicit && explicit.trim()) return explicit.trim();
  if (members.length === 0) return "Collection";
  return stripAnyEmDashSuffix(members[0].name) || members[0].name;
}

/**
 * Format a plant's "last edited" timestamp into a relative label.
 * Prefers the ISO `updatedAt` so each card ages independently; falls back
 * to the legacy `lastEdited` static string when no timestamp is available.
 */
export function formatPlantUpdated(plant: Pick<ProjectRecord, "updatedAt" | "lastEdited">): string {
  const iso = plant.updatedAt;
  if (iso) {
    const t = Date.parse(iso);
    if (Number.isFinite(t)) {
      const diff = Date.now() - t;
      if (diff < 0) return "Just now";
      const sec = Math.round(diff / 1000);
      if (sec < 45) return "Just now";
      const min = Math.round(sec / 60);
      if (min < 60) return `${min} minute${min === 1 ? "" : "s"} ago`;
      const hr = Math.round(min / 60);
      if (hr < 24) return `${hr} hour${hr === 1 ? "" : "s"} ago`;
      const day = Math.round(hr / 24);
      if (day < 7) return `${day} day${day === 1 ? "" : "s"} ago`;
      const wk = Math.round(day / 7);
      if (wk < 5) return `${wk} week${wk === 1 ? "" : "s"} ago`;
      const mo = Math.round(day / 30);
      if (mo < 12) return `${mo} month${mo === 1 ? "" : "s"} ago`;
      const yr = Math.round(day / 365);
      return `${yr} year${yr === 1 ? "" : "s"} ago`;
    }
  }
  // Ignore the legacy static "Just now" fallback — without a real timestamp
  // it would freeze every card on that label forever.
  const legacy = (plant.lastEdited || "").trim();
  if (legacy && legacy.toLowerCase() !== "just now") return legacy;
  return "—";
}
