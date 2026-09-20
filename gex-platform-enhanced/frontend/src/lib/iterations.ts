/**
 * iterations — shared helper to fork a plant into a new "iteration"
 * inside the same collection (projectGroupId). Used by both the
 * Plant Builder list and the in-canvas Iterations dropdown so the
 * behavior stays consistent.
 *
 * A new iteration:
 *   • shares projectGroupId with the source
 *   • gets a unique slug `${groupId}-iter-N`
 *   • copies the source canvas to its own document (so future edits are
 *     fully independent)
 *   • upserts the plant row
 *   • updates the localStorage cache and notifies listeners
 */
import type { Node, Edge } from "@xyflow/react";
import {
  type ProjectRecord,
  nextIterationNumber,
  stripIterationSuffix,
} from "./projectRegistry";
import { saveToStorage } from "@/hooks/useLocalPersistence";
import { notifyPlantsChanged, getCachedPlants } from "./plantStore";

export interface IterationCanvasSnapshot {
  nodes: Node[];
  edges: Edge[];
  plantSettings?: unknown;
  retiredDisplayIds?: string[];
}

export interface CreateIterationOptions {
  /** Plant we are forking from */
  source: ProjectRecord;
  /** Current plants list, used to pick a unique iteration number */
  plants: ProjectRecord[];
  /**
   * Optional live canvas snapshot. When provided, the helper uploads it
   * directly as the new iteration's canvas — guarantees the fork captures
   * the current editor state even if it has not been autosaved yet. When
   * omitted, the source's stored canvas is copied instead.
   */
  liveCanvas?: IterationCanvasSnapshot | null;
  /**
   * Optional user-supplied variation label (e.g. "PEM + offshore wind").
   * When omitted, defaults to `Plant variation #N`.
   */
  customVariantLabel?: string;
}

export interface CreateIterationResult {
  plant: ProjectRecord;
  variantLabel: string;
}

/**
 * Persist a single plant row (per-user, per-slug) without touching siblings.
 * Kept local to this module so callers don't need to know about Supabase.
 */
async function upsertPlantRow(plant: ProjectRecord) {
  try {
    const { upsertPlant } = await import("@/lib/plantsApi");
    await upsertPlant(plant.id, JSON.parse(JSON.stringify(plant)));
  } catch (err) {
    console.error("[iterations] upsert plant row failed:", err);
  }
}

/**
 * Create a new iteration and return its metadata. Throws on hard failures
 * (network, storage) so callers can surface toasts.
 */
export async function createIteration(
  opts: CreateIterationOptions,
): Promise<CreateIterationResult> {
  const { source, plants, liveCanvas, customVariantLabel } = opts;
  const groupId = source.projectGroupId || source.id;

  // Pick a unique slug — bump past any collisions.
  let n = nextIterationNumber(groupId, plants);
  let newId = `${groupId}-iter-${n}`;
  while (plants.some((p) => p.id === newId)) {
    n += 1;
    newId = `${groupId}-iter-${n}`;
  }
  const variantLabel = (customVariantLabel || "").trim() || `Plant variation #${n}`;
  const baseName = stripIterationSuffix(source.name);

  const newPlant: ProjectRecord = {
    ...source,
    id: newId,
    projectGroupId: groupId,
    variantLabel,
    // Keep `name` = collection base name. The variation is a first-class
    // field (`variantLabel`), so we never need the em-dashed combo string.
    name: baseName,
    updatedAt: new Date().toISOString(),
  };

  // 1) Seed the new iteration's canvas.
  //
  // The fork used to copy the source object inside the bucket by composing
  // both paths in the browser, reading the source through getPublicUrl (which
  // never worked — the bucket is not public) and re-uploading. Now both ends
  // are addressed by slug and the owner comes from the token.
  try {
    const { loadCanvas, saveCanvas } = await import("@/lib/canvasApi");
    const payload = liveCanvas
      ? {
          nodes: liveCanvas.nodes,
          edges: liveCanvas.edges,
          plantSettings: liveCanvas.plantSettings,
          retiredDisplayIds: liveCanvas.retiredDisplayIds ?? [],
        }
      : await loadCanvas<unknown>(source.id);
    if (payload) await saveCanvas(newId, payload);
  } catch (err) {
    console.error("[iterations] canvas seed failed:", err);
    throw err;
  }

  // 2) Persist the plant row.
  await upsertPlantRow(newPlant);

  // 3) Update local cache + notify listeners.
  try {
    const cached = getCachedPlants();
    const without = cached.filter((p) => p.id !== newPlant.id);
    const next = [...without, newPlant];
    saveToStorage("plant_list", next);
    notifyPlantsChanged();
  } catch (err) {
    console.warn("[iterations] cache update failed:", err);
  }

  return { plant: newPlant, variantLabel };
}

/**
 * Rename an iteration / plant (its `variantLabel` and the display
 * `name`). Updates the per-user `plants` row and the local cache.
 */
export async function renamePlantVariation(opts: {
  plant: ProjectRecord;
  variantLabel: string;
}): Promise<ProjectRecord> {
  const label = opts.variantLabel.trim() || opts.plant.variantLabel;
  const baseName = stripIterationSuffix(opts.plant.name);
  const updated: ProjectRecord = {
    ...opts.plant,
    variantLabel: label,
    name: baseName,
    updatedAt: new Date().toISOString(),
  };
  await upsertPlantRow(updated);
  try {
    const cached = getCachedPlants();
    const next = cached.map((p) => (p.id === updated.id ? updated : p));
    saveToStorage("plant_list", next);
    notifyPlantsChanged();
  } catch (err) {
    console.warn("[iterations] rename cache update failed:", err);
  }
  return updated;
}

/**
 * Permanently delete an iteration: removes its per-user `plants` row, its
 * user-scoped canvas JSON, and every version snapshot.
 */
export async function deletePlantVariation(opts: {
  plant: ProjectRecord;
}): Promise<void> {
  const { plant } = opts;

  // Both halves go through the backend now.
  try {
    const { deletePlant } = await import("@/lib/plantsApi");
    await deletePlant(plant.id);
  } catch (err) {
    console.error("[iterations] plant row delete failed:", err);
  }

  // The canvas and every snapshot of it go in one call — the browser used to
  // remove the object, then page through `versions/` deleting each one.
  try {
    const { deleteCanvas } = await import("@/lib/canvasApi");
    await deleteCanvas(plant.id);
  } catch (err) {
    console.error("[iterations] canvas delete failed:", err);
  }

  try {
    const cached = getCachedPlants();
    const next = cached.filter((p) => p.id !== plant.id);
    saveToStorage("plant_list", next);
    notifyPlantsChanged();
  } catch (err) {
    console.warn("[iterations] delete cache update failed:", err);
  }
}
