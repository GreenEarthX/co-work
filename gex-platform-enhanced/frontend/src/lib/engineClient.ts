/**
 * engineClient.ts — typed HTTPS client for gex_pf_engine.
 *
 * Sits next to backendClient.ts. Where backendClient.ts talks to Supabase
 * (app data + auth + realtime), this module talks to the Python compute
 * service. The same Supabase user-JWT is forwarded as a Bearer token; the
 * engine verifies it with the same keys Supabase uses.
 *
 * Usage:
 *   import { engineClient, EngineUnavailable } from "@/lib/engineClient";
 *
 *   try {
 *     const result = await engineClient.computeDeal(dealId, { scenario: "base" });
 *     // result.summary.min_dscr, etc.
 *   } catch (e) {
 *     if (e instanceof EngineUnavailable) { /* show banner *\/ }
 *     else throw e;
 *   }
 *
 * Env vars (Vite — must be prefixed VITE_):
 *   VITE_GEX_ENGINE_URL    e.g. https://gex-pf-engine-xxxxxx.run.app
 *
 * If the env var is missing, every method throws EngineUnavailable rather
 * than silently failing. That mirrors how backendClient handles missing
 * Supabase config.
 */
import { supabase } from "@/integrations/supabase/client";

// ---------------------------------------------------------------------------
// Types — mirror the Pydantic models in gex_pf_engine/main.py exactly.
// ---------------------------------------------------------------------------

export type Scenario = "worst" | "base" | "best";

export interface WhoamiResponse {
  user_id: string;
  email: string | null;
  role: string;
  engine_version: string;
}

export interface YearRow {
  year: number;
  revenue_eur: number;
  opex_eur: number;
  ebitda_eur: number;
  debt_service_eur: number;
  dscr: number | null;
  fcf_eur: number;
}

export interface ComputeSummary {
  project_irr: number | null;
  equity_irr: number | null;
  npv_eur: number | null;
  min_dscr: number | null;
  avg_dscr: number | null;
  llcr: number | null;
  rating_band: string | null;
  binding_covenant: string | null;
}

export interface ComputeResponse {
  deal_structure_id: string;
  inputs_hash: string;
  engine_version: string;
  cashflow_schedule: YearRow[];
  summary: ComputeSummary;
}

export interface ComputeRequest {
  scenario?: Scenario;
  use_latest_plant_version?: boolean;
}

// ---------------------------------------------------------------------------
// Error classes — call sites can branch cleanly.
// ---------------------------------------------------------------------------

/** Engine URL not configured at build time. */
export class EngineUnavailable extends Error {
  constructor(message = "GEX engine URL not configured") {
    super(message);
    this.name = "EngineUnavailable";
  }
}

/** No Supabase session — user must sign in before calling the engine. */
export class EngineUnauthenticated extends Error {
  constructor(message = "No active session") {
    super(message);
    this.name = "EngineUnauthenticated";
  }
}

/** Engine returned a non-2xx response. */
export class EngineHttpError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `Engine HTTP ${status}`);
    this.name = "EngineHttpError";
    this.status = status;
    this.body = body;
  }
}

// ---------------------------------------------------------------------------
// Configuration + low-level request
// ---------------------------------------------------------------------------

const ENGINE_URL: string | undefined = (
  import.meta.env.VITE_GEX_ENGINE_URL as string | undefined
)?.replace(/\/+$/, "");

let warned = false;

export function isEngineConfigured(): boolean {
  return typeof ENGINE_URL === "string" && ENGINE_URL.length > 0;
}

async function authHeader(): Promise<Record<string, string>> {
  const { data, error } = await supabase.auth.getSession();
  if (error) {
    throw new EngineUnauthenticated(`session error: ${error.message}`);
  }
  const token = data.session?.access_token;
  if (!token) {
    throw new EngineUnauthenticated();
  }
  return { Authorization: `Bearer ${token}` };
}

interface RequestOpts<TBody> {
  method?: "GET" | "POST";
  path: string;
  body?: TBody;
  /** Pass through to fetch — useful for AbortController. */
  signal?: AbortSignal;
}

async function request<TResponse, TBody = unknown>(
  opts: RequestOpts<TBody>,
): Promise<TResponse> {
  if (!isEngineConfigured()) {
    if (!warned && typeof console !== "undefined") {
      warned = true;
      console.warn(
        "[engineClient] VITE_GEX_ENGINE_URL is not set. Engine calls disabled.",
      );
    }
    throw new EngineUnavailable();
  }

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(await authHeader()),
  };
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const url = `${ENGINE_URL}${opts.path}`;
  const resp = await fetch(url, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    signal: opts.signal,
    credentials: "omit",
  });

  let parsed: unknown = null;
  const text = await resp.text();
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!resp.ok) {
    throw new EngineHttpError(
      resp.status,
      parsed,
      typeof parsed === "object" && parsed !== null && "detail" in parsed
        ? String((parsed as { detail: unknown }).detail)
        : `Engine HTTP ${resp.status}`,
    );
  }
  return parsed as TResponse;
}

export function engineFetch<TResponse, TBody = unknown>(
  opts: RequestOpts<TBody>,
): Promise<TResponse> {
  return request<TResponse, TBody>(opts);
}

// ---------------------------------------------------------------------------
// Public API — typed methods for each engine endpoint.
// ---------------------------------------------------------------------------

export const engineClient = {
  /** Liveness probe. No auth required. */
  async healthz(): Promise<{ ok: boolean; version: string }> {
    if (!isEngineConfigured()) throw new EngineUnavailable();
    const resp = await fetch(`${ENGINE_URL}/healthz`, { credentials: "omit" });
    if (!resp.ok) throw new EngineHttpError(resp.status, await resp.text());
    return (await resp.json()) as { ok: boolean; version: string };
  },

  /** Verifies the auth bridge end-to-end. Returns the user the engine saw. */
  whoami(signal?: AbortSignal): Promise<WhoamiResponse> {
    return request<WhoamiResponse>({ path: "/whoami", signal });
  },

  /** Run the financial model for a deal structure. Sprint 1 = stub. */
  computeDeal(
    dealStructureId: string,
    req: ComputeRequest = {},
    signal?: AbortSignal,
  ): Promise<ComputeResponse> {
    return request<ComputeResponse, ComputeRequest>({
      method: "POST",
      path: `/deals/${encodeURIComponent(dealStructureId)}/compute`,
      body: {
        scenario: req.scenario ?? "base",
        use_latest_plant_version: req.use_latest_plant_version ?? true,
      },
      signal,
    });
  },
};

// ---------------------------------------------------------------------------
// React Query helpers — drop-in for the existing useProjectFinance pattern.
// ---------------------------------------------------------------------------

/**
 * Optional helper: build a stable React Query key for a compute call. Use:
 *
 *   const { data } = useQuery({
 *     queryKey: engineQueryKeys.computeDeal(dealId, { scenario }),
 *     queryFn: ({ signal }) => engineClient.computeDeal(dealId, { scenario }, signal),
 *     staleTime: 60_000,
 *   });
 */
export const engineQueryKeys = {
  whoami: () => ["engine", "whoami"] as const,
  computeDeal: (dealStructureId: string, req: ComputeRequest = {}) =>
    [
      "engine",
      "computeDeal",
      dealStructureId,
      req.scenario ?? "base",
      req.use_latest_plant_version ?? true,
    ] as const,
};
