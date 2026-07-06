/**
 * plantStore — Single source of truth for the user's plants list across pages.
 *
 * Reads/writes the `ptool_plant_list` localStorage cache and additionally
 * hydrates from the cloud `plants` table (scoped by user_id) on mount so a
 * user signing in on a new device immediately sees their real portfolio
 * — not the hard-coded `projectRegistry` defaults.
 *
 * PlantBuilder remains the writer to the cloud; this hook just makes sure
 * any consumer (Portfolio, Orchestrator, …) reflects cloud state too.
 */
import { useEffect, useState } from "react";
import type { ProjectRecord } from "./projectRegistry";
import { projectRegistry } from "./projectRegistry";
import { isBackendConfigured } from "./envGuard";

const STORAGE_KEY = "ptool_plant_list";
const EVENT_NAME = "gex:plants-updated";
const TOUCH_EVENT = "gex:plant-touched";

export function getCachedPlants(): ProjectRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const list = JSON.parse(raw) as ProjectRecord[];
      // Discard the legacy static `lastEdited: "Just now"` so the card
      // never freezes on a stale label; the live `updatedAt` drives it.
      return list.map((p) => {
        if ((p?.lastEdited || "").trim().toLowerCase() === "just now") {
          const { lastEdited: _drop, ...rest } = p as ProjectRecord & { lastEdited?: string };
          return rest as ProjectRecord;
        }
        return p;
      });
    }
  } catch { /* ignore */ }
  return [...projectRegistry];
}

function writeCache(plants: ProjectRecord[]) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(plants)); } catch { /* ignore */ }
}

/** Call after any local mutation so other pages re-render in this tab. */
export function notifyPlantsChanged() {
  try { window.dispatchEvent(new CustomEvent(EVENT_NAME)); } catch { /* ignore */ }
}

async function loadFromCloud(userId: string): Promise<ProjectRecord[] | null> {
  if (!isBackendConfigured() || !userId) return null;
  try {
    const { supabase } = await import("@/lib/backendClient");
    const { data, error } = await supabase
      .from("plants")
      .select("data, updated_at")
      .eq("user_id", userId);
    if (error) return null;
    if (!data || data.length === 0) return [];
    return data
      .map((r: any) => ({ ...(r.data as ProjectRecord), updatedAt: r.updated_at as string }))
      .filter((p: Record<string, unknown> | null) => p && p.id);
  } catch {
    return null;
  }
}

/**
 * Subscribe to plant-list changes. On mount, the hook also fetches the
 * cloud-stored plants for the supplied user and refreshes the cache so
 * cross-device portfolios stay consistent.
 */
export function useSyncedPlants(userId?: string): ProjectRecord[] {
  const [plants, setPlants] = useState<ProjectRecord[]>(() => getCachedPlants());

  useEffect(() => {
    const refresh = () => setPlants(getCachedPlants());
    window.addEventListener(EVENT_NAME, refresh);
    const onStorage = (e: StorageEvent) => { if (e.key === STORAGE_KEY) refresh(); };
    window.addEventListener("storage", onStorage);
    const onTouched = (ev: Event) => {
      const detail = (ev as CustomEvent<{ plantId?: string; updatedAt?: string }>).detail;
      if (!detail?.plantId || !detail?.updatedAt) return;
      setPlants((prev) => {
        let changed = false;
        const next = prev.map((p) => {
          if (p.id === detail.plantId) {
            changed = true;
            const { lastEdited: _drop, ...rest } = p as ProjectRecord & { lastEdited?: string };
            return { ...rest, updatedAt: detail.updatedAt } as ProjectRecord;
          }
          return p;
        });
        if (changed) writeCache(next);
        return changed ? next : prev;
      });
    };
    window.addEventListener(TOUCH_EVENT, onTouched as EventListener);
    return () => {
      window.removeEventListener(EVENT_NAME, refresh);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(TOUCH_EVENT, onTouched as EventListener);
    };
  }, []);

  // Hydrate from cloud whenever the userId becomes known/changes.
  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    (async () => {
      const cloud = await loadFromCloud(userId);
      if (cancelled || cloud === null) return;
      if (cloud.length === 0) return; // first-device user: PlantBuilder will seed
      setPlants(cloud);
      writeCache(cloud);
      notifyPlantsChanged();
    })();
    return () => { cancelled = true; };
  }, [userId]);

  return plants;
}
