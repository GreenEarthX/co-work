/**
 * iterations — shared helper to fork a plant into a new "iteration"
 * inside the same collection (projectGroupId). Used by both the
 * Plant Builder list and the in-canvas Iterations dropdown so the
 * behavior stays consistent.
 *
 * A new iteration:
 *   • shares projectGroupId with the source
 *   • gets a unique slug `${groupId}-iter-N`
 *   • copies the source canvas JSON to its own user-scoped storage path
 *     (so future edits are fully independent)
 *   • upserts a `plants` row scoped to the user
 *   • updates the localStorage cache and notifies listeners
 */
import type { Node, Edge } from "@xyflow/react";
import {
  type ProjectRecord,
  nextIterationNumber,
  stripIterationSuffix,
} from "./projectRegistry";
import { isBackendConfigured } from "./envGuard";
import { saveToStorage } from "@/hooks/useLocalPersistence";
import { notifyPlantsChanged, getCachedPlants } from "./plantStore";

async function getSupabase() {
  const { supabase } = await import("./backendClient");
  return supabase;
}

export interface IterationCanvasSnapshot {
  nodes: Node[];
  edges: Edge[];
  plantSettings?: unknown;
  retiredDisplayIds?: string[];
}

export interface CreateIterationOptions {
  /** Plant we are forking from */
  source: ProjectRecord;
  /** Authenticated user id (storage + cloud row are scoped to it) */
  userId?: string;
  /** Current plants list, used to pick a unique iteration number */
  plants: ProjectRecord[];
  /**
   * Optional live canvas snapshot. When provided, the helper uploads it
   * directly to the new iteration's storage path — guarantees the fork
   * captures the current editor state even if it hasn't been autosaved
   * to cloud yet. When omitted, falls back to copying the source's
   * existing storage object.
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
async function upsertPlantRow(userId: string, plant: ProjectRecord) {
  if (!isBackendConfigured() || !userId) return;
  try {
    const sb = await getSupabase();
    await sb.from("plants").upsert(
      { user_id: userId, slug: plant.id, data: JSON.parse(JSON.stringify(plant)) },
      { onConflict: "user_id,slug" },
    );
  } catch (err) {
    console.error("[iterations] upsert plant row failed:", err);
  }
}

function scopedCanvasPath(userId: string | undefined, slug: string): string {
  return userId ? `users/${userId}/${slug}.json` : `${slug}.json`;
}

/**
 * Create a new iteration and return its metadata. Throws on hard failures
 * (network, storage) so callers can surface toasts.
 */
export async function createIteration(
  opts: CreateIterationOptions,
): Promise<CreateIterationResult> {
  const { source, userId, plants, liveCanvas, customVariantLabel } = opts;
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

  // 1) Seed canvas storage for the new iteration.
  if (isBackendConfigured()) {
    try {
      const sb = await getSupabase();
      const destPath = scopedCanvasPath(userId, newId);

      if (liveCanvas) {
        const payload = {
          nodes: liveCanvas.nodes,
          edges: liveCanvas.edges,
          plantSettings: liveCanvas.plantSettings,
          retiredDisplayIds: liveCanvas.retiredDisplayIds ?? [],
        };
        const blob = new Blob([JSON.stringify(payload, null, 2)], {
          type: "application/json",
        });
        await sb.storage
          .from("plant-data")
          .upload(destPath, blob, { upsert: true, cacheControl: "0" });
      } else {
        // Fall back to copying the source plant's stored JSON.
        const candidates = [
          userId ? `users/${userId}/${source.id}.json` : null,
          `${source.id}.json`,
        ].filter(Boolean) as string[];
        let sourceJson: string | null = null;
        for (const path of candidates) {
          const { data: urlData } = sb.storage
            .from("plant-data")
            .getPublicUrl(path);
          try {
            const resp = await fetch(`${urlData.publicUrl}?t=${Date.now()}`, {
              cache: "no-store",
            });
            if (resp.ok) {
              sourceJson = await resp.text();
              break;
            }
          } catch {
            /* try next */
          }
        }
        if (sourceJson) {
          const blob = new Blob([sourceJson], { type: "application/json" });
          await sb.storage
            .from("plant-data")
            .upload(destPath, blob, { upsert: true, cacheControl: "0" });
        }
      }
    } catch (err) {
      console.error("[iterations] canvas seed failed:", err);
      throw err;
    }
  }

  // 2) Persist the plant row.
  if (userId) await upsertPlantRow(userId, newPlant);

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
  userId?: string;
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
  if (opts.userId) await upsertPlantRow(opts.userId, updated);
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
  userId?: string;
}): Promise<void> {
  const { plant, userId } = opts;
  if (isBackendConfigured()) {
    try {
      const sb = await getSupabase();
      if (userId) {
        await sb.from("plants").delete().eq("user_id", userId).eq("slug", plant.id);
      }
      const targets = [
        userId ? `users/${userId}/${plant.id}.json` : null,
        `${plant.id}.json`,
      ].filter(Boolean) as string[];
      await sb.storage.from("plant-data").remove(targets);
      const versionRoots = [
        userId ? `versions/users/${userId}/${plant.id}` : null,
        `versions/${plant.id}`,
      ].filter(Boolean) as string[];
      for (const root of versionRoots) {
        let pageOffset = 0;
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { data: files } = await sb.storage
            .from("plant-data")
            .list(root, { limit: 100, offset: pageOffset });
          if (!files || files.length === 0) break;
          await sb.storage
            .from("plant-data")
            .remove(files.map((f: { name: string }) => `${root}/${f.name}`));
          if (files.length < 100) break;
          pageOffset += 100;
        }
      }
    } catch (err) {
      console.error("[iterations] delete failed:", err);
      throw err;
    }
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
