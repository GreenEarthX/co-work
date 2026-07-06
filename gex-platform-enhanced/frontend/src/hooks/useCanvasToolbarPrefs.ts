/**
 * useCanvasToolbarPrefs — single source of truth for the user's canvas
 * toolbar preferences. Persisted in localStorage under one key so the state
 * survives page reloads, project switches, and tab changes (cross-tab sync
 * via the `storage` event).
 *
 * Stored keys are intentionally GLOBAL (not per-projectId) so when the user
 * jumps between plants, the toolbar UI feels stable.
 */
import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "canvas.toolbarPrefs.v1";

export interface CanvasToolbarPrefs {
  /** Show E1/C1/G1 identifier badges on nodes. */
  showNodeIds: boolean;
  /** Show the duplicate-counter QA debug overlay on nodes. */
  debugNodeIds: boolean;
  /** Show the bottom-right canvas legend panel. */
  showLegend: boolean;
  /** Collapsed state of the left-side Component Library. */
  componentLibraryCollapsed: boolean;
  /** Auto-layout orientation last selected by the user. */
  layoutOrientation: "horizontal" | "vertical";
  /** Whether the ID-legend pill tooltip is pinned open (persists across sessions). */
  idLegendTooltipPinned: boolean;
  /** Compact equipment node mode — reduces paddings while keeping NAME and ID readable. */
  compactNodes: boolean;
  /** Render edges as single straight segments instead of orthogonal smooth-step paths. */
  straightEdges: boolean;
}

const DEFAULTS: CanvasToolbarPrefs = {
  showNodeIds: true,
  debugNodeIds: false,
  showLegend: false,
  componentLibraryCollapsed: false,
  layoutOrientation: "horizontal",
  idLegendTooltipPinned: false,
  compactNodes: false,
  straightEdges: false,
};

function read(): CanvasToolbarPrefs {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<CanvasToolbarPrefs>;
    return { ...DEFAULTS, ...parsed };
  } catch {
    return DEFAULTS;
  }
}

function write(prefs: CanvasToolbarPrefs) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* quota / private mode — ignore */
  }
}

export function useCanvasToolbarPrefs() {
  const [prefs, setPrefs] = useState<CanvasToolbarPrefs>(() => read());

  // Persist on every change.
  useEffect(() => {
    write(prefs);
  }, [prefs]);

  // Cross-tab sync: when another tab updates the same key, mirror it here.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY || !e.newValue) return;
      try {
        const next = JSON.parse(e.newValue) as Partial<CanvasToolbarPrefs>;
        setPrefs((curr) => ({ ...curr, ...next }));
      } catch {
        /* ignore malformed payloads */
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const update = useCallback(<K extends keyof CanvasToolbarPrefs>(key: K, value: CanvasToolbarPrefs[K]) => {
    setPrefs((curr) => (curr[key] === value ? curr : { ...curr, [key]: value }));
  }, []);

  return { prefs, update, setPrefs };
}