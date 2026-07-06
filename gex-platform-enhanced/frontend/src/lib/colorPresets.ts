/**
 * colorPresets — user-configurable list of quick-pick brand colors,
 * shown inside the Legend Recolor popover.
 *
 * Persisted in localStorage; subscribers re-render on change.
 */

const STORAGE_KEY = "canvas.colorPresets.v1";

const DEFAULT_PRESETS: string[] = [
  "#10B981", // hydrogen green
  "#0EA5E9", // sky / oxygen
  "#3B82F6", // water blue
  "#8B5CF6", // methanol purple
  "#F59E0B", // amber
  "#EF4444", // red
  "#14B8A6", // teal
  "#6B7280", // neutral gray
  "#1F2937", // near-black
  "#FFFFFF", // white
];

let cache: string[] | null = null;
const listeners = new Set<() => void>();

function read(): string[] {
  if (cache) return cache;
  if (typeof window === "undefined") return (cache = [...DEFAULT_PRESETS]);
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    cache = raw ? (JSON.parse(raw) as string[]) : [...DEFAULT_PRESETS];
  } catch {
    cache = [...DEFAULT_PRESETS];
  }
  return cache!;
}

function write(next: string[]) {
  cache = [...next];
  if (typeof window !== "undefined") {
    try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(cache)); } catch { /* ignore */ }
  }
  listeners.forEach((l) => l());
}

export function getColorPresets(): string[] {
  // Must return a referentially stable snapshot for useSyncExternalStore.
  // `write()` swaps `cache` to a fresh array whenever the data changes,
  // so sharing the cached reference here is safe and avoids React error
  // #185 (infinite re-render) when subscribers mount.
  return read();
}

export function setColorPresets(next: string[]) {
  write(next.slice(0, 24));
}

export function addColorPreset(color: string) {
  const curr = read();
  if (curr.includes(color)) return;
  write([...curr, color].slice(0, 24));
}

export function removeColorPreset(idx: number) {
  const curr = read();
  if (idx < 0 || idx >= curr.length) return;
  write(curr.filter((_, i) => i !== idx));
}

export function resetColorPresets() {
  write([...DEFAULT_PRESETS]);
}

export function subscribeColorPresets(fn: () => void): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}
