/**
 * useLabelNormalizationPrefs — persistent prefs for the canvas label
 * normalization rules used by computeNodeIdMap. Stored in localStorage so
 * the user's preferred duplicate-detection rules survive reloads, project
 * switches, and other tabs.
 */
import { useCallback, useEffect, useState } from "react";
import type { LabelNormalizationOptions } from "@/components/canvas/nodeIdSystem";

const STORAGE_KEY = "canvas.labelNormalization.v1";

export const DEFAULT_PLACEHOLDERS = [
  "untitled", "new", "n/a", "na", "tbd", "todo", "?",
];

export type LabelNormalizationPrefs = Required<LabelNormalizationOptions>;

const DEFAULTS: LabelNormalizationPrefs = {
  trim: true,
  caseFold: true,
  stripDiacritics: true,
  stripNumericSuffix: true,
  placeholders: DEFAULT_PLACEHOLDERS,
};

function read(): LabelNormalizationPrefs {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<LabelNormalizationPrefs>;
    return {
      ...DEFAULTS,
      ...parsed,
      placeholders: Array.isArray(parsed.placeholders)
        ? parsed.placeholders.filter((p) => typeof p === "string")
        : DEFAULTS.placeholders,
    };
  } catch {
    return DEFAULTS;
  }
}

function write(prefs: LabelNormalizationPrefs) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* quota / private mode — ignore */
  }
}

export function useLabelNormalizationPrefs() {
  const [prefs, setPrefs] = useState<LabelNormalizationPrefs>(() => read());

  useEffect(() => { write(prefs); }, [prefs]);

  // Cross-tab sync
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY || !e.newValue) return;
      try {
        const next = JSON.parse(e.newValue) as Partial<LabelNormalizationPrefs>;
        setPrefs((curr) => ({ ...curr, ...next }));
      } catch { /* ignore */ }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const update = useCallback(<K extends keyof LabelNormalizationPrefs>(
    key: K, value: LabelNormalizationPrefs[K],
  ) => {
    setPrefs((curr) => ({ ...curr, [key]: value }));
  }, []);

  const reset = useCallback(() => setPrefs(DEFAULTS), []);

  return { prefs, update, setPrefs, reset, defaults: DEFAULTS };
}