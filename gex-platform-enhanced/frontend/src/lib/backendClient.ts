import { createClient } from "@supabase/supabase-js";

const FALLBACK_BACKEND_URL = "https://fcgjgtqqcuafbmhwmzfq.supabase.co";
const FALLBACK_PUBLISHABLE_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZjZ2pndHFxY3VhZmJtaHdtemZxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MDU0NTQsImV4cCI6MjA5MDA4MTQ1NH0.Of5KPFJwNeVC7FlhE-eVl3b8gkoINHQAbrZjthzhSNE";

/** Loose sanity check — must be an http(s) URL we can hand to fetch(). */
function isUsableUrl(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0) return false;
  try {
    const u = new URL(value);
    return u.protocol === "https:" || u.protocol === "http:";
  } catch {
    return false;
  }
}

/** A publishable/anon JWT is opaque, but we can at least reject empty strings. */
function isUsableKey(value: unknown): value is string {
  return typeof value === "string" && value.length > 20;
}

interface BackendConfig {
  url: string;
  key: string;
  /** True when env vars were missing/invalid and we fell back to baked-in defaults. */
  usingFallback: boolean;
  /** True when neither env vars nor fallbacks were usable. */
  unavailable: boolean;
}

let warned = false;

export function getBackendConfig(): BackendConfig {
  const envUrl = import.meta.env.VITE_SUPABASE_URL;
  const envKey =
    import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ||
    import.meta.env.VITE_SUPABASE_ANON_KEY;

  const envOk = isUsableUrl(envUrl) && isUsableKey(envKey);
  const url = envOk ? (envUrl as string) : FALLBACK_BACKEND_URL;
  const key = envOk ? (envKey as string) : FALLBACK_PUBLISHABLE_KEY;

  const usable = isUsableUrl(url) && isUsableKey(key);

  if (!envOk && !warned && typeof console !== "undefined") {
    warned = true;
    console.warn(
      "[backendClient] VITE_SUPABASE_URL or VITE_SUPABASE_PUBLISHABLE_KEY missing/invalid, falling back to baked-in publishable defaults. Backend writes still work; re-publish to refresh env.",
    );
  }

  return { url, key, usingFallback: !envOk, unavailable: !usable };
}

export function isBackendConfigured(): boolean {
  return !getBackendConfig().unavailable;
}

/**
 * Build a real Supabase client, or — if even the fallbacks are unusable — a
 * stub that resolves every call to a clear error instead of throwing at import
 * time. This guarantees `import { supabase } from "@/lib/backendClient"` never
 * crashes a page on module load.
 */
function buildClient() {
  const cfg = getBackendConfig();
  if (cfg.unavailable) {
    if (typeof console !== "undefined") {
      console.error(
        "[backendClient] No usable backend configuration. All Supabase calls will return an error result.",
      );
    }
    const err = {
      message: "Backend not configured",
      details: "VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY are missing.",
      hint: "Re-publish the app to restore environment variables.",
      code: "BACKEND_UNAVAILABLE",
    };
    const reject = async () => ({ data: null, error: err });
    // Minimal shape covering the call sites used in this app.
    const stub: any = {
      from: () => ({
        select: reject, insert: reject, update: reject, upsert: reject,
        delete: reject, eq: () => stub.from(), order: () => stub.from(),
        limit: () => stub.from(), maybeSingle: reject, single: reject,
      }),
      auth: {
        getSession: async () => ({ data: { session: null }, error: err }),
        getUser: async () => ({ data: { user: null }, error: err }),
        signInWithPassword: reject,
        signInWithOAuth: reject,
        signOut: async () => ({ error: null }),
        onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      },
      storage: {
        from: () => ({
          list: reject, upload: reject, download: reject, remove: reject,
          getPublicUrl: () => ({ data: { publicUrl: "" } }),
        }),
      },
      functions: { invoke: reject },
      channel: () => ({ on: () => ({ subscribe: () => ({ unsubscribe: () => {} }) }) }),
      removeChannel: () => {},
    };
    return stub;
  }

  const storage = typeof window !== "undefined" ? window.localStorage : undefined;
  return createClient(cfg.url, cfg.key, {
    auth: { storage, persistSession: true, autoRefreshToken: true },
  });
}

let currentClient: any = buildClient();
const rebuildListeners = new Set<() => void>();

/**
 * Re-detect env/config and rebuild the underlying Supabase client. Returns the
 * fresh config so callers (e.g. retry buttons) can decide what to show next.
 */
export function rebuildBackendClient(): BackendConfig {
  warned = false; // allow the warning to fire again on the new attempt
  currentClient = buildClient();
  for (const fn of rebuildListeners) {
    try { fn(); } catch { /* swallow */ }
  }
  return getBackendConfig();
}

/** Subscribe to client rebuilds (e.g. to force a React re-render). */
export function onBackendClientRebuild(fn: () => void): () => void {
  rebuildListeners.add(fn);
  return () => { rebuildListeners.delete(fn); };
}

/**
 * Stable proxy so existing `import { supabase }` references always hit the
 * latest underlying client after a rebuild — no refactor needed at call sites.
 */
export const supabase: any = new Proxy(
  {},
  {
    get(_t, prop) {
      const value = (currentClient as any)[prop];
      return typeof value === "function" ? value.bind(currentClient) : value;
    },
  },
);
