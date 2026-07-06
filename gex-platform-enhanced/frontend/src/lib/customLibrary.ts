/**
 * customLibrary — User-scoped custom equipment, carriers, and gates that
 * persist across all of a user's plants. Stored as one JSON object per user
 * in the `plant-data` Supabase storage bucket so that any plant the user
 * opens sees the same custom palette items.
 *
 * Falls back to localStorage when the backend is not configured or the user
 * is anonymous, and migrates legacy localStorage data into the cloud on
 * first load.
 */
import { isBackendConfigured } from "@/lib/envGuard";
import type { EquipmentDef, CarrierDef, GateDef } from "@/components/canvas/componentDatabase";

const BUCKET = "plant-data";
const LS_KEYS = {
  equipment: "customEquipment",
  carriers: "customCarriers",
  gates: "customGates",
} as const;

export interface CustomLibrary {
  equipment: EquipmentDef[];
  carriers: CarrierDef[];
  gates: GateDef[];
  updatedAt?: string;
}

export function emptyLibrary(): CustomLibrary {
  return { equipment: [], carriers: [], gates: [] };
}

function readLocal(): CustomLibrary {
  const safe = <T>(k: string): T[] => {
    try { return JSON.parse(localStorage.getItem(k) || "[]") as T[]; } catch { return []; }
  };
  return {
    equipment: safe<EquipmentDef>(LS_KEYS.equipment),
    carriers:  safe<CarrierDef>(LS_KEYS.carriers),
    gates:     safe<GateDef>(LS_KEYS.gates),
  };
}

function writeLocal(lib: CustomLibrary): void {
  try {
    localStorage.setItem(LS_KEYS.equipment, JSON.stringify(lib.equipment));
    localStorage.setItem(LS_KEYS.carriers,  JSON.stringify(lib.carriers));
    localStorage.setItem(LS_KEYS.gates,     JSON.stringify(lib.gates));
  } catch { /* quota or disabled storage — ignore */ }
}

async function getSupabase() {
  if (!isBackendConfigured()) return null;
  const { supabase } = await import("@/lib/backendClient");
  return supabase;
}

function path(userId: string): string {
  return `users/${userId}/custom-library.json`;
}

/**
 * Load the user's custom library. Tries cloud first, falls back to
 * localStorage. If cloud is empty but local has data, uploads local data
 * (one-time migration) and returns it.
 */
export async function loadCustomLibrary(userId?: string): Promise<CustomLibrary> {
  const local = readLocal();
  const sb = await getSupabase();
  if (!sb || !userId) return local;
  const { data: urlData } = sb.storage.from(BUCKET).getPublicUrl(path(userId));
  try {
    const resp = await fetch(`${urlData.publicUrl}?t=${Date.now()}`, { cache: "no-store" });
    if (resp.ok) {
      const parsed = JSON.parse(await resp.text()) as Partial<CustomLibrary>;
      const merged: CustomLibrary = {
        equipment: parsed.equipment ?? [],
        carriers:  parsed.carriers  ?? [],
        gates:     parsed.gates     ?? [],
        updatedAt: parsed.updatedAt,
      };
      writeLocal(merged);
      return merged;
    }
  } catch { /* fall through */ }
  // Cloud empty — push local up so future devices see it
  if (local.equipment.length || local.carriers.length || local.gates.length) {
    await saveCustomLibrary(local, userId);
  }
  return local;
}

export async function saveCustomLibrary(lib: CustomLibrary, userId?: string): Promise<void> {
  writeLocal(lib);
  const sb = await getSupabase();
  if (!sb || !userId) return;
  const payload: CustomLibrary = { ...lib, updatedAt: new Date().toISOString() };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  await sb.storage.from(BUCKET).upload(path(userId), blob, { upsert: true, cacheControl: "0" });
}