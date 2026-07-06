/**
 * useCanvasData — Cloud-only plant data hook (v2).
 * Always fetches from / saves to the Supabase Storage bucket.
 * No static JSON fallbacks — the bucket is the single source of truth.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { isBackendConfigured } from "@/lib/envGuard";
import type { Node, Edge } from "@xyflow/react";
import { computeNodeIdMap } from "@/components/canvas/nodeIdSystem";
import { migrateLegacyHandle } from "@/components/canvas/portSystem";

const BUCKET = "plant-data";
const VERSIONS_PREFIX = "versions";
const SNAPSHOT_MIN_INTERVAL_MS = 60_000; // throttle: at most one snapshot per minute
const MAX_VERSIONS_KEPT = 30;

/** Lazy-import the runtime-safe backend client */
async function getSupabase() {
  if (!isBackendConfigured()) return null;
  const { supabase } = await import("@/lib/backendClient");
  return supabase;
}

export interface PlantSettings {
  hoursYear: number;
  plantAvailability: number;
  criticalPathNodeIds: string[];
  boundaryPadding?: { left: number; right: number; top: number; bottom: number };
}

const DEFAULT_PLANT_SETTINGS: PlantSettings = {
  hoursYear: 8760,
  plantAvailability: 91.3,
  criticalPathNodeIds: [],
  boundaryPadding: { left: 0, right: 0, top: 0, bottom: 0 },
};

export interface CanvasData {
  nodes: Node[];
  edges: Edge[];
  plantSettings?: PlantSettings;
  /**
   * Display IDs (e.g. "E2", "C5", "G3") that were once assigned but the
   * underlying node has since been deleted. Kept around so future nodes
   * never reuse the same number — preserves full traceability across
   * add/delete cycles.
   */
  retiredDisplayIds?: string[];
}

export interface VersionEntry {
  /** Storage object path (e.g. "versions/biogas-plant/2026-05-03T10-15-30-000Z.json") */
  path: string;
  /** Filename component, ISO-like timestamp */
  name: string;
  /** Parsed Date when the snapshot was taken */
  createdAt: Date;
  /** Size in bytes if known */
  size?: number;
}

function normalizeCanvasData(
  nodes: Node[],
  edges: Edge[],
  plantSettings?: PlantSettings,
  previousRetired: readonly string[] = [],
  previousAllDisplayIds: readonly string[] = [],
): CanvasData {
  const clonedNodes = JSON.parse(JSON.stringify(nodes)) as Node[];
  const clonedEdges = JSON.parse(JSON.stringify(edges)) as Edge[];
  const hasInnerNode = clonedNodes.some((node) => node.type === "equipment" || node.type === "carrier");
  const trimmedNodes = hasInnerNode ? clonedNodes : clonedNodes.filter((node) => node.type !== "boundary");

  // Pin a deterministic displayId (E1/C1/G1…) onto each node so reloads keep
  // the same identifier even if labels arrive later or new nodes get smaller
  // internal ids. Existing pinned displayIds are preserved by computeNodeIdMap.
  // Retired IDs (from previously-deleted nodes) are reserved so we never reuse
  // a number — preserving full traceability after add/delete cycles.
  const idMap = computeNodeIdMap(trimmedNodes, {}, previousRetired);
  const normalizedNodes = trimmedNodes.map((node) => {
    const info = idMap.get(node.id);
    if (!info) return node;
    const existing = (node.data as { displayId?: unknown })?.displayId;
    if (existing === info.displayId) return node;
    return { ...node, data: { ...(node.data ?? {}), displayId: info.displayId } };
  });

  // Compute the new retired set: union of (previous retired) + (previously
  // seen displayIds that are no longer present on any current node).
  const currentDisplayIds = new Set<string>();
  for (const n of normalizedNodes) {
    const did = (n.data as { displayId?: unknown })?.displayId;
    if (typeof did === "string") currentDisplayIds.add(did);
  }
  const retiredSet = new Set<string>(previousRetired);
  for (const prev of previousAllDisplayIds) {
    if (!currentDisplayIds.has(prev)) retiredSet.add(prev);
  }
  // Safety: never list a currently-active id as retired.
  for (const cur of currentDisplayIds) retiredSet.delete(cur);

  return {
    nodes: normalizedNodes,
    edges: clonedEdges,
    plantSettings: plantSettings ? JSON.parse(JSON.stringify(plantSettings)) : DEFAULT_PLANT_SETTINGS,
    retiredDisplayIds: [...retiredSet].sort(),
  };
}

interface UseCanvasDataResult {
  data: CanvasData | null;
  loadedPlantId: string | null;
  loading: boolean;
  error: string | null;
  source: "cloud" | null;
  saveCanvasData: (nodes: Node[], edges: Edge[], plantSettings?: PlantSettings) => Promise<void>;
  saving: boolean;
  listVersions: () => Promise<VersionEntry[]>;
  loadVersion: (path: string) => Promise<CanvasData | null>;
  restoreVersion: (path: string) => Promise<CanvasData | null>;
}

export function useCanvasData(plantId: string | undefined, userId?: string): UseCanvasDataResult {
  const [data, setData] = useState<CanvasData | null>(null);
  const [loadedPlantId, setLoadedPlantId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [source, setSource] = useState<"cloud" | null>(null);
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());
  const lastSnapshotAtRef = useRef<number>(0);
  // Hash of the last payload we either loaded from cloud or successfully
  // uploaded. Used to short-circuit no-op saves so opening/switching/viewing
  // a plant never bumps `plants.updated_at`.
  const lastSavedHashRef = useRef<string | null>(null);
  // Track the union of every displayId we've ever observed for this plant
  // (current + retired). Used to detect deletions and grow the retired set.
  const seenDisplayIdsRef = useRef<Set<string>>(new Set());
  const retiredDisplayIdsRef = useRef<Set<string>>(new Set());

  /** Cheap, dependency-free djb2 string hash. */
  function hashString(s: string): string {
    let h = 5381;
    for (let i = 0; i < s.length; i++) {
      h = ((h << 5) + h + s.charCodeAt(i)) | 0;
    }
    return h.toString(36);
  }

  // Per-user storage prefix so each demo account has its own canvas for a
  // given slug. Anonymous visitors fall back to the legacy global path so
  // existing public seeds still work as a default.
  const scopedPath = useCallback(
    (slug: string) => (userId ? `users/${userId}/${slug}.json` : `${slug}.json`),
    [userId],
  );
  const versionsDir = useCallback(
    (slug: string) => (userId ? `${VERSIONS_PREFIX}/users/${userId}/${slug}` : `${VERSIONS_PREFIX}/${slug}`),
    [userId],
  );

  const ingestSeenIds = useCallback((d: CanvasData | null) => {
    if (!d) return;
    for (const n of d.nodes) {
      const did = (n.data as { displayId?: unknown })?.displayId;
      if (typeof did === "string") seenDisplayIdsRef.current.add(did);
    }
    for (const r of d.retiredDisplayIds ?? []) {
      seenDisplayIdsRef.current.add(r);
      retiredDisplayIdsRef.current.add(r);
    }
  }, []);

  useEffect(() => {
    if (!plantId) {
      setData({ nodes: [], edges: [], plantSettings: DEFAULT_PLANT_SETTINGS });
      setLoadedPlantId(null);
      setLoading(false);
      setSource(null);
      return;
    }
    // Reset per-plant tracking when switching plants so retired IDs from
    // one plant never leak into another.
    seenDisplayIdsRef.current = new Set();
    retiredDisplayIdsRef.current = new Set();
    lastSavedHashRef.current = null;
    // Clear stale data so the canvas hydration effect doesn't briefly see
    // the previous plant's nodes/edges while the new plant is loading.
    setData(null);
    setLoadedPlantId(null);

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      setSource(null);

      try {
        const sb = await getSupabase();
        if (!sb) {
          if (!cancelled) {
            setError("Backend not configured, cannot load plant data");
            setData({ nodes: [], edges: [], plantSettings: DEFAULT_PLANT_SETTINGS });
            setLoadedPlantId(plantId ?? null);
            setLoading(false);
          }
          return;
        }

        // Try the user-scoped path first, then fall back to the legacy
        // unscoped seed so first-time visits hydrate from the public default.
        const candidates: string[] = [];
        if (userId) candidates.push(scopedPath(plantId ?? ""));
        candidates.push(`${plantId ?? ""}.json`);

        for (const path of candidates) {
          const { data: urlData } = sb.storage.from(BUCKET).getPublicUrl(path);
          const resp = await fetch(`${urlData.publicUrl}?t=${Date.now()}`, { cache: "no-store" });
          if (!resp.ok) continue;
          let parsed: CanvasData;
          try {
            parsed = JSON.parse(await resp.text()) as CanvasData;
          } catch { continue; }
          if (!parsed || !Array.isArray(parsed.nodes)) continue;
          if (!cancelled) {
            const loaded: CanvasData = {
              ...parsed,
              plantSettings: parsed.plantSettings ?? DEFAULT_PLANT_SETTINGS,
              edges: (() => {
                const migrated = (parsed.edges ?? []).map((e) => {
                  const src = migrateLegacyHandle(e.sourceHandle, "source");
                  const tgt = migrateLegacyHandle(e.targetHandle, "target");
                  if (src === e.sourceHandle && tgt === e.targetHandle) return e;
                  return { ...e, sourceHandle: src ?? e.sourceHandle, targetHandle: tgt ?? e.targetHandle };
                });
                // Deduplicate edges that share the same source/target/handles
                // tuple — React Flow uses that as its internal key and will
                // crash with duplicate-key warnings (and sometimes render
                // failures) if more than one edge collides. Keep the first.
                const seen = new Set<string>();
                const deduped: typeof migrated = [];
                for (const e of migrated) {
                  const key = `${e.source}|${e.sourceHandle ?? ""}|${e.target}|${e.targetHandle ?? ""}`;
                  if (seen.has(key)) {
                    console.warn(`[useCanvasData] Dropping duplicate edge ${e.id} (${key})`);
                    continue;
                  }
                  seen.add(key);
                  deduped.push(e);
                }
                return deduped;
              })(),
            };
            ingestSeenIds(loaded);
            setData(loaded);
            setLoadedPlantId(plantId ?? null);
            setSource("cloud");
            setLoading(false);
            // Seed the hash with the same normalized+serialized form that
            // saveCanvasData will produce, so a defensive save of the
            // unchanged payload is recognized as a no-op (and "Last edited"
            // doesn't bump on plant open/switch).
            try {
              const normalized = normalizeCanvasData(
                loaded.nodes,
                loaded.edges,
                loaded.plantSettings,
                [...(loaded.retiredDisplayIds ?? [])],
                (loaded.nodes
                  .map((n) => (n.data as { displayId?: unknown })?.displayId)
                  .filter((v): v is string => typeof v === "string"))
                  .concat(loaded.retiredDisplayIds ?? []),
              );
              lastSavedHashRef.current = hashString(JSON.stringify(normalized, null, 2));
            } catch { lastSavedHashRef.current = null; }
            console.log(`[useCanvasData] Loaded ${plantId} from ${path}`);
          }
          return;
        }

        // No cloud data — empty canvas (new plant)
        if (!cancelled) {
          console.warn(`[useCanvasData] No cloud data for ${plantId}, starting empty`);
          setData({ nodes: [], edges: [], plantSettings: DEFAULT_PLANT_SETTINGS });
          setLoadedPlantId(plantId ?? null);
          setSource(null);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("[useCanvasData] Load error:", err);
          setError(err instanceof Error ? err.message : "Failed to load canvas data");
          setData({ nodes: [], edges: [], plantSettings: DEFAULT_PLANT_SETTINGS });
          setLoadedPlantId(plantId ?? null);
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [plantId, userId, scopedPath, ingestSeenIds]);

  const saveCanvasData = useCallback(
    (nodes: Node[], edges: Edge[], plantSettings?: PlantSettings) => {
      if (!plantId) return Promise.resolve();

      const payload = normalizeCanvasData(
        nodes,
        edges,
        plantSettings,
        [...retiredDisplayIdsRef.current],
        [...seenDisplayIdsRef.current],
      );
      // Update refs from the freshly normalized payload so subsequent saves
      // keep tracking deletions correctly.
      ingestSeenIds(payload);

      const runSave = saveChainRef.current.catch(() => undefined).then(async () => {
        setSaving(true);
        try {
          const serialized = JSON.stringify(payload, null, 2);
          const payloadHash = hashString(serialized);
          // No-op guard: if the serialized canvas hasn't changed since the
          // last load/save, skip the upload, plants touch, snapshot, and
          // touched event. This ensures opening/switching/viewing a plant
          // never bumps "Last edited".
          if (lastSavedHashRef.current && lastSavedHashRef.current === payloadHash) {
            return;
          }
          const blob = new Blob([serialized], { type: "application/json" });

          const sb = await getSupabase();
          if (!sb) {
            console.warn("[useCanvasData] Backend not configured, skipping cloud save");
            return;
          }
          const { error: uploadError } = await sb.storage
            .from(BUCKET)
            .upload(scopedPath(plantId), blob, { upsert: true, cacheControl: "0" });

          if (uploadError) {
            console.error("[useCanvasData] Save failed:", uploadError.message);
          } else {
            console.log(`[useCanvasData] Saved ${plantId} to cloud storage`);
            setSource("cloud");
            lastSavedHashRef.current = payloadHash;
            // Touch the plants metadata row so the portfolio card's
            // "Last edited" label stays in sync with real canvas saves.
            // Fire-and-forget — never block the canvas on this.
            if (userId) {
              const touchTs = new Date().toISOString();
              sb.from("plants")
                .update({ updated_at: touchTs })
                .eq("user_id", userId)
                .eq("slug", plantId)
                .then(() => {
                  try {
                    window.dispatchEvent(
                      new CustomEvent("gex:plant-touched", {
                        detail: { plantId, updatedAt: touchTs },
                      }),
                    );
                  } catch { /* ignore */ }
                }, () => { /* ignore touch errors */ });
            }
            // NOTE: Do NOT call setData(payload) here. The PlantCanvas
            // component holds the authoritative live nodes/edges; echoing
            // the saved payload back into `data` retriggers the hydration
            // effect and causes ReactFlow to re-mount, wiping selection
            // and producing visible flashing during edits.
            // Create a throttled timestamped snapshot for version history
            const now = Date.now();
            if (now - lastSnapshotAtRef.current >= SNAPSHOT_MIN_INTERVAL_MS) {
              lastSnapshotAtRef.current = now;
              const stamp = new Date(now).toISOString().replace(/[:.]/g, "-");
              const versionPath = `${versionsDir(plantId)}/${stamp}.json`;
              try {
                await sb.storage
                  .from(BUCKET)
                  .upload(versionPath, blob, { upsert: false, cacheControl: "0" });
                // Prune old versions to MAX_VERSIONS_KEPT
                const { data: versionFiles } = await sb.storage
                  .from(BUCKET)
                  .list(versionsDir(plantId), { limit: 100, sortBy: { column: "name", order: "desc" } });
                if (versionFiles && versionFiles.length > MAX_VERSIONS_KEPT) {
                  const toDelete = versionFiles
                    .slice(MAX_VERSIONS_KEPT)
                    .map((f: { name: string }) => `${versionsDir(plantId)}/${f.name}`);
                  if (toDelete.length > 0) {
                    await sb.storage.from(BUCKET).remove(toDelete);
                  }
                }
              } catch (snapErr) {
                console.warn("[useCanvasData] Snapshot failed:", snapErr);
              }
            }
          }
        } catch (err) {
          console.error("[useCanvasData] Save error:", err);
        } finally {
          setSaving(false);
        }
      });

      saveChainRef.current = runSave;
      return runSave;
    },
    [plantId, userId, scopedPath, versionsDir]
  );

  const listVersions = useCallback(async (): Promise<VersionEntry[]> => {
    if (!plantId) return [];
    const sb = await getSupabase();
    if (!sb) return [];
    const { data: files, error: listErr } = await sb.storage
      .from(BUCKET)
      .list(versionsDir(plantId), { limit: 100, sortBy: { column: "name", order: "desc" } });
    if (listErr || !files) return [];
    return files
      .filter((f: { name: string; created_at?: string; metadata?: { size?: number } }) => f.name.endsWith(".json"))
      .map((f: { name: string; created_at?: string; metadata?: { size?: number } }) => {
        // Reverse the replace done at write time: turn "2026-05-03T10-15-30-000Z" back to ISO
        const base = f.name.replace(/\.json$/, "");
        // Format: YYYY-MM-DDTHH-mm-ss-SSSZ
        const isoLike = base.replace(
          /^(\d{4}-\d{2}-\d{2}T\d{2})-(\d{2})-(\d{2})-(\d{3})Z$/,
          "$1:$2:$3.$4Z"
        );
        const createdAt = new Date(isoLike);
        return {
          path: `${versionsDir(plantId)}/${f.name}`,
          name: f.name,
          createdAt: isNaN(createdAt.getTime()) ? new Date(f.created_at ?? Date.now()) : createdAt,
          size: f.metadata?.size,
        };
      });
  }, [plantId, versionsDir]);

  const loadVersion = useCallback(async (path: string): Promise<CanvasData | null> => {
    const sb = await getSupabase();
    if (!sb) return null;
    const { data: urlData } = sb.storage.from(BUCKET).getPublicUrl(path);
    const resp = await fetch(`${urlData.publicUrl}?t=${Date.now()}`, { cache: "no-store" });
    if (!resp.ok) return null;
    const parsed = JSON.parse(await resp.text()) as CanvasData;
    return { ...parsed, plantSettings: parsed.plantSettings ?? DEFAULT_PLANT_SETTINGS };
  }, []);

  const restoreVersion = useCallback(async (path: string): Promise<CanvasData | null> => {
    if (!plantId) return null;
    const restored = await loadVersion(path);
    if (!restored) return null;
    // Persist restored snapshot as the current canvas (skip new snapshot via cooldown reset)
    lastSnapshotAtRef.current = Date.now(); // prevent immediate re-snapshot
    ingestSeenIds(restored);
    await saveCanvasData(restored.nodes, restored.edges, restored.plantSettings);
    setData(restored);
    return restored;
  }, [plantId, loadVersion, saveCanvasData, ingestSeenIds]);

  return { data, loadedPlantId, loading, error, source, saveCanvasData, saving, listVersions, loadVersion, restoreVersion };
}
