/**
 * carrierColorOverrides — global, persistent per-carrier color overrides
 * editable from the Plant Settings dialog (Plant Display tab → Legend Recolor).
 *
 * Stored in localStorage under one key. Subscribers (canvas, edges, legend)
 * are notified via a tiny pub/sub so colors update live without reload.
 */

const STORAGE_KEY = "canvas.carrierColorOverrides.v1";

type Overrides = Record<string, string>; // label → CSS color (hex / rgb / hsl)

let cache: Overrides | null = null;
const listeners = new Set<() => void>();

function read(): Overrides {
  if (cache) return cache;
  if (typeof window === "undefined") return (cache = {});
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    cache = raw ? (JSON.parse(raw) as Overrides) : {};
  } catch {
    cache = {};
  }
  return cache!;
}

function write(next: Overrides) {
  cache = { ...next };
  if (typeof window !== "undefined") {
    try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(cache)); } catch { /* ignore */ }
  }
  listeners.forEach((l) => l());
}

export function getCarrierColorOverride(label: string): string | undefined {
  return read()[label];
}

export function setCarrierColorOverride(label: string, color: string | null) {
  const curr = { ...read() };
  if (color == null || color === "") {
    delete curr[label];
  } else {
    curr[label] = color;
  }
  write(curr);
}

export function getAllCarrierOverrides(): Overrides {
  return { ...read() };
}

export function resetCarrierOverrides() {
  write({});
}

export function subscribeCarrierOverrides(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Convert an "rgb(r,g,b)" or "#rrggbb" string to "#rrggbb". Returns input on failure. */
export function toHex(input: string): string {
  const m = /^rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/.exec(input);
  if (m) {
    const [, r, g, b] = m;
    const hex = (n: string) => Number(n).toString(16).padStart(2, "0");
    return `#${hex(r)}${hex(g)}${hex(b)}`;
  }
  return input;
}

/** Convert "#rrggbb" → { r, g, b }. */
export function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const v = parseInt(m[1], 16);
  return { r: (v >> 16) & 0xff, g: (v >> 8) & 0xff, b: v & 0xff };
}

/** HSL → { r, g, b } with channels in [0, 255]. h in [0,360], s,l in [0,100]. */
export function hslToRgb(h: number, s: number, l: number): { r: number; g: number; b: number } {
  const sn = s / 100, ln = l / 100;
  const c = (1 - Math.abs(2 * ln - 1)) * sn;
  const hp = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let r1 = 0, g1 = 0, b1 = 0;
  if (hp < 1)      [r1, g1, b1] = [c, x, 0];
  else if (hp < 2) [r1, g1, b1] = [x, c, 0];
  else if (hp < 3) [r1, g1, b1] = [0, c, x];
  else if (hp < 4) [r1, g1, b1] = [0, x, c];
  else if (hp < 5) [r1, g1, b1] = [x, 0, c];
  else             [r1, g1, b1] = [c, 0, x];
  const m = ln - c / 2;
  return {
    r: Math.round((r1 + m) * 255),
    g: Math.round((g1 + m) * 255),
    b: Math.round((b1 + m) * 255),
  };
}

/** Parse a hex / rgb() / "h s% l%" / hsl() color into { r, g, b }, or null. */
export function parseColor(input: string): { r: number; g: number; b: number } | null {
  if (!input) return null;
  const s = input.trim();
  const hex = hexToRgb(s);
  if (hex) return hex;
  const rgb = /^rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/i.exec(s);
  if (rgb) return { r: +rgb[1], g: +rgb[2], b: +rgb[3] };
  const hsl = /^hsl\s*\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)$/i.exec(s);
  if (hsl) return hslToRgb(+hsl[1], +hsl[2], +hsl[3]);
  // bare "h s% l%" tokens used in CSS variables
  const tokens = /^([\d.]+)\s+([\d.]+)%\s+([\d.]+)%$/i.exec(s);
  if (tokens) return hslToRgb(+tokens[1], +tokens[2], +tokens[3]);
  return null;
}

/** Read a CSS HSL custom property (e.g. --background) from :root and return rgb. */
export function readCssVarRgb(varName: string): { r: number; g: number; b: number } | null {
  if (typeof window === "undefined") return null;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  if (!raw) return null;
  return parseColor(raw) ?? parseColor(`hsl(${raw.replace(/%/g, "%").replace(/\s+/g, ", ")})`);
}

/** Relative luminance per WCAG 2.1. */
export function relativeLuminance(rgb: { r: number; g: number; b: number }): number {
  const channel = (c: number) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b);
}

/** WCAG contrast ratio between two colors, range 1..21. */
export function contrastRatio(
  a: { r: number; g: number; b: number },
  b: { r: number; g: number; b: number },
): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}