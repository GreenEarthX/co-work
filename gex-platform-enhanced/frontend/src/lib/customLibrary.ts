/**
 * customLibrary — the user's own equipment, carriers and gates, kept server-side.
 *
 * The system of record is `/api/v1/plant-canvas/library`, which stores one
 * document per owner in `canvas_blobs` — PostgreSQL since migration 050, under
 * an owner-only RLS policy with no admin clause. The browser keeps a cache so
 * the palette still renders while a request is in flight or the backend is
 * briefly unreachable.
 *
 * THE CACHE IS NAMESPACED PER USER, AND THAT IS NOT A DETAIL
 * ----------------------------------------------------------
 * It used to live under the bare keys `customEquipment` / `customCarriers` /
 * `customGates`, with no owner anywhere in them. On a shared browser that was a
 * cross-account leak with an upload path attached:
 *
 *   1. A builds a custom library. It lands in those keys.
 *   2. A signs out. B signs in on the same browser.
 *   3. B's server library is empty, so `loadCustomLibrary` took "nothing
 *      stored" as its cue to push the local copy up — A's equipment, into B's
 *      account, over B's session token.
 *
 * Keying the cache by the signed-in user id makes that unsayable: this code
 * cannot see another account's cache, so it cannot upload one either. The
 * legacy keys are migrated into the current user's namespace once and then
 * deleted, because leaving them would leave the leak.
 */
import { getAuthUserId } from "@/lib/authToken";
import type { EquipmentDef, CarrierDef, GateDef } from "@/components/canvas/componentDatabase";

/** Pre-2026-09-23 keys: no owner, shared by every account on the browser. */
const LEGACY_KEYS = {
  equipment: "customEquipment",
  carriers: "customCarriers",
  gates: "customGates",
} as const;

const CACHE_PREFIX = "gex:customLibrary:";

export interface CustomLibrary {
  equipment: EquipmentDef[];
  carriers: CarrierDef[];
  gates: GateDef[];
  updatedAt?: string;
}

/** Raised when the server rejected a save, so a caller can say so. */
export class LibrarySaveFailed extends Error {}

export function emptyLibrary(): CustomLibrary {
  return { equipment: [], carriers: [], gates: [] };
}

function cacheKey(): string | null {
  const userId = getAuthUserId();
  return userId ? `${CACHE_PREFIX}${userId}` : null;
}

function readCache(): CustomLibrary {
  const key = cacheKey();
  if (!key) return emptyLibrary();      // signed out: this browser owns nothing
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return emptyLibrary();
    const parsed = JSON.parse(raw) as Partial<CustomLibrary>;
    return {
      equipment: parsed.equipment ?? [],
      carriers: parsed.carriers ?? [],
      gates: parsed.gates ?? [],
      updatedAt: parsed.updatedAt,
    };
  } catch {
    return emptyLibrary();
  }
}

function writeCache(lib: CustomLibrary): void {
  const key = cacheKey();
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify(lib));
  } catch { /* quota or disabled storage — the server still has it */ }
}

/**
 * Move the un-owned legacy keys into this user's namespace, once.
 *
 * Claimed by whoever is signed in when it first runs, which is the best any
 * code can do: the old keys genuinely do not record who made them. It happens
 * at most once because the legacy keys are removed immediately, and it only
 * ever writes the CACHE — nothing is uploaded here.
 */
function adoptLegacyCache(): CustomLibrary | null {
  const key = cacheKey();
  if (!key) return null;
  try {
    const legacy = {
      equipment: JSON.parse(localStorage.getItem(LEGACY_KEYS.equipment) || "[]") as EquipmentDef[],
      carriers: JSON.parse(localStorage.getItem(LEGACY_KEYS.carriers) || "[]") as CarrierDef[],
      gates: JSON.parse(localStorage.getItem(LEGACY_KEYS.gates) || "[]") as GateDef[],
    };
    const hasAny = legacy.equipment.length || legacy.carriers.length || legacy.gates.length;
    for (const k of Object.values(LEGACY_KEYS)) localStorage.removeItem(k);
    if (!hasAny) return null;
    writeCache(legacy);
    return legacy;
  } catch {
    return null;
  }
}

/**
 * Load the user's custom library: server first, cache only as a stand-in.
 *
 * `userId` is not a parameter and must not become one — the server derives the
 * owner from the session token. It used to compose
 * `users/{userId}/custom-library.json` in the browser, so naming another id
 * read their library.
 */
export async function loadCustomLibrary(): Promise<CustomLibrary> {
  const adopted = adoptLegacyCache();
  const cached = adopted ?? readCache();

  try {
    const { loadCustomLibrary: fetchLibrary } = await import("@/lib/canvasApi");
    const parsed = await fetchLibrary<Partial<CustomLibrary>>();
    if (parsed) {
      const merged: CustomLibrary = {
        equipment: parsed.equipment ?? [],
        carriers: parsed.carriers ?? [],
        gates: parsed.gates ?? [],
        updatedAt: parsed.updatedAt,
      };
      writeCache(merged);
      return merged;
    }
    // The server answered and has nothing for this owner. Only now is it safe
    // to push the cache up — it is this user's own cache, by construction.
    if (cached.equipment.length || cached.carriers.length || cached.gates.length) {
      await saveCustomLibrary(cached);
    }
    return cached;
  } catch {
    // Unreachable backend, or no session yet. Show this user their own cached
    // palette and upload NOTHING: an upload here is how another account's work
    // used to travel.
    return cached;
  }
}

/**
 * Persist the library. The server is the record; the cache follows it.
 *
 * Throws `LibrarySaveFailed` when the server refuses, instead of logging to a
 * console nobody is reading. The cache is still written first so the work
 * survives a reload, but a caller that swallows this is telling the user their
 * library is saved when only their browser has it.
 */
export async function saveCustomLibrary(lib: CustomLibrary): Promise<void> {
  const payload: CustomLibrary = { ...lib, updatedAt: new Date().toISOString() };
  writeCache(payload);
  try {
    const { saveCustomLibrary: pushLibrary } = await import("@/lib/canvasApi");
    await pushLibrary(payload);
  } catch (err) {
    throw new LibrarySaveFailed(
      `Custom library not saved to your account: ${(err as Error)?.message ?? "request failed"}. ` +
      "It is still in this browser and will retry on the next change.",
    );
  }
}
