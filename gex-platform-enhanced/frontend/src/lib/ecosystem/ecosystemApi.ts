// Screen: Ecosystem Navigator (API client)
/**
 * Server-side Ecosystem Map publication.
 *
 * Replaces the `localStorage` store this module used to keep. Publishing wrote
 * to `gex_ecosystem_user_projects` in the publishing browser, so "published to
 * the map for everyone" reached exactly one device. These calls put the record
 * where other users can see it.
 */
import { getAuthToken } from "@/lib/authToken";
import { normaliseLifecycle } from "./types";
import type { EcoProject } from "./types";

const API_PREFIX = "/api/v1/ecosystem";

async function call<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  const res = await fetch(`${API_PREFIX}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/** One tenant's reading of a map project. Several may exist for one project. */
export interface ServerEnrichment {
  enrichment_id: string;
  target_eco_id: string;
  tenant_id: string;
  payload: Record<string, unknown>;
  visible_fields: string[];
  match_rule: string | null;
  match_reason: string | null;
  updated_at: string;
}

export interface EcosystemFeed {
  projects: (EcoProject & { owned?: boolean })[];
  enrichments: ServerEnrichment[];
  count: number;
}

export async function fetchEcosystem(): Promise<EcosystemFeed> {
  const feed = await call<EcosystemFeed>("/projects");
  // Rows published before the phase/status split carry a single legacy status
  // ("planned", "operational" …). Normalise here, at the boundary, so nothing
  // downstream has to know that two vocabularies ever existed.
  return {
    ...feed,
    projects: (feed.projects ?? []).map((p) => ({ ...p, ...normaliseLifecycle(p) })),
  };
}

export interface PublishBody {
  slug: string; name: string; lat: number; lng: number;
  phase?: string; status?: string; country?: string; moleculeType?: string;
  productionPathway?: string; owner?: string;
  capacity?: string; capacityValue?: string; capacityUnit?: string;
  extras?: Record<string, unknown>;
  visibleFields?: string[];
}

export function publishProject(body: PublishBody) {
  return call<{ kind: "added"; project: EcoProject }>("/publish", {
    method: "POST", body: JSON.stringify(body),
  });
}

export function attachEnrichment(body: {
  targetEcoId: string;
  payload: Record<string, unknown>;
  visibleFields?: string[];
  matchRule?: string | null;
  matchReason?: string | null;
}) {
  return call<{ kind: "enriched"; enrichment_id: string }>("/enrich", {
    method: "POST", body: JSON.stringify(body),
  });
}

export function withdrawProject(slug: string) {
  return call<{ withdrawn: boolean }>(`/publish/${encodeURIComponent(slug)}`,
    { method: "DELETE" });
}

export function withdrawEnrichment(targetEcoId: string) {
  return call<{ withdrawn: boolean }>(
    `/enrich/${encodeURIComponent(targetEcoId)}`, { method: "DELETE" });
}
