/**
 * customLibrary — User-scoped custom equipment, carriers, and gates that
 * persist across all of a user's plants. Stored as one JSON document per user
 * behind /api/v1/plant-canvas/library, so any plant the user opens sees the
 * same custom palette items.
 *
 * Was the `plant-data` Supabase bucket, reached under the anon key with the
 * owner named by the browser. Falls back to localStorage when the backend is
 * unreachable, and pushes legacy localStorage data up on first load.
 */
import type { EquipmentDef, CarrierDef, GateDef } from "@/components/canvas/componentDatabase";

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

/**
 * Load the user's custom library. Backend first, falling back to
 * localStorage. If the backend has none but local does, push local up once so
 * future devices see it.
 *
 * `userId` is gone: the server derives the owner from the session token. It
 * used to compose `users/{userId}/custom-library.json` in the browser, so
 * naming another id read their library.
 */
export async function loadCustomLibrary(): Promise<CustomLibrary> {
  const local = readLocal();
  try {
    const { loadCustomLibrary: fetchLibrary } = await import("@/lib/canvasApi");
    const parsed = await fetchLibrary<Partial<CustomLibrary>>();
    if (parsed) {
      const merged: CustomLibrary = {
        equipment: parsed.equipment ?? [],
        carriers:  parsed.carriers  ?? [],
        gates:     parsed.gates     ?? [],
        updatedAt: parsed.updatedAt,
      };
      writeLocal(merged);
      return merged;
    }
  } catch { /* fall through to local */ }
  // Nothing stored — push local up so future devices see it.
  if (local.equipment.length || local.carriers.length || local.gates.length) {
    await saveCustomLibrary(local);
  }
  return local;
}

export async function saveCustomLibrary(lib: CustomLibrary): Promise<void> {
  writeLocal(lib);
  const payload: CustomLibrary = { ...lib, updatedAt: new Date().toISOString() };
  try {
    const { saveCustomLibrary: pushLibrary } = await import("@/lib/canvasApi");
    await pushLibrary(payload);
  } catch (err) {
    console.error("[customLibrary] cloud save failed:", err);
  }
}
