/**
 * Publication persists to the BACKEND, not to browser storage.
 *
 * The module used to write `gex_ecosystem_user_projects` and
 * `gex_ecosystem_enrichments` to localStorage, so a project "published to the
 * map for everyone" reached exactly one browser. These tests pin that the
 * network is now the store, and that localStorage stays untouched.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { EcoProject } from "../types";

vi.mock("../mockData", () => ({ projects: [] as EcoProject[] }));
vi.mock("../observatoryData", () => ({ observatoryProjects: [] as EcoProject[] }));

const api = {
  fetchEcosystem: vi.fn(),
  publishProject: vi.fn(),
  attachEnrichment: vi.fn(),
  withdrawProject: vi.fn(),
  withdrawEnrichment: vi.fn(),
};
vi.mock("../ecosystemApi", () => api);

const {
  publishPlantToEcosystem, unpublishPlantFromEcosystem,
  refreshEcosystem, getPublishedEcosystemProjects,
  getEnrichmentsByProject,
} = await import("../userProjects");

const MAASVLAKTE: EcoProject = {
  id: "pub_1", name: "Maasvlakte Hydrogen Hub", lat: 51.95, lng: 4.05,
  phase: "unknown", status: "active", layer: "production", moleculeType: "hydrogen",
  owner: "Shell Nederland", country: "Netherlands",
};

const PLANT = {
  slug: "mv2", name: "Delfzijl Electrolyser", lat: 53.33, lng: 6.92,
  country: "Netherlands", fuelType: "Hydrogen", owner: "Nobian",
  capacity: "20 kt/yr", visibleFields: ["website"],
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  api.fetchEcosystem.mockResolvedValue({ projects: [], enrichments: [], count: 0 });
  api.publishProject.mockResolvedValue({ kind: "added", project: { id: "pub_new" } });
  api.attachEnrichment.mockResolvedValue({ kind: "enriched", enrichment_id: "enr_1" });
  api.withdrawProject.mockResolvedValue({ withdrawn: true });
  api.withdrawEnrichment.mockResolvedValue({ withdrawn: true });
});

describe("publication goes to the server", () => {
  it("posts a new marker and writes nothing to localStorage", async () => {
    const res = await publishPlantToEcosystem(PLANT);
    expect(api.publishProject).toHaveBeenCalledTimes(1);
    expect(res.kind).toBe("added");
    expect(localStorage.length).toBe(0);
  });

  it("carries the publisher's visibleFields to the server", async () => {
    await publishPlantToEcosystem(PLANT);
    expect(api.publishProject.mock.calls[0][0].visibleFields).toEqual(["website"]);
  });

  it("attaches to an existing project instead of creating a duplicate", async () => {
    api.fetchEcosystem.mockResolvedValue({
      projects: [MAASVLAKTE], enrichments: [], count: 1,
    });
    await refreshEcosystem();
    const res = await publishPlantToEcosystem({
      ...PLANT, slug: "mv-shell", name: "Maasvlakte Green H2 Plant",
      lat: 51.9505, lng: 4.0505, owner: "Shell Nederland",
    });
    expect(res.kind).toBe("enriched");
    expect(api.attachEnrichment).toHaveBeenCalledTimes(1);
    expect(api.publishProject).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
  });

  it("withdrawing calls the server and leaves browser storage alone", async () => {
    await unpublishPlantFromEcosystem(PLANT);
    expect(api.withdrawProject).toHaveBeenCalledWith("mv2");
    expect(localStorage.length).toBe(0);
  });

  it("refuses to place a marker without coordinates", async () => {
    const res = await publishPlantToEcosystem({
      slug: "nowhere", name: "Nowhere", fuelType: "Hydrogen",
    });
    expect(res.kind).toBe("skipped");
    expect(api.publishProject).not.toHaveBeenCalled();
  });
});

describe("the feed is other tenants' data, not just this browser's", () => {
  it("exposes projects published by someone else", async () => {
    api.fetchEcosystem.mockResolvedValue({
      projects: [{ ...MAASVLAKTE, owned: false }], enrichments: [], count: 1,
    });
    await refreshEcosystem();
    expect(getPublishedEcosystemProjects().map((p) => p.id)).toEqual(["pub_1"]);
  });

  it("keeps every tenant's reading of one project, not just the last", async () => {
    // Attach-not-overwrite is the whole design: two readings of one project
    // must both survive so the disagreement stays visible.
    api.fetchEcosystem.mockResolvedValue({
      projects: [MAASVLAKTE],
      enrichments: [
        { enrichment_id: "e1", target_eco_id: "pub_1", tenant_id: "t_beta",
          payload: { capacity: "20 kt/yr" }, visible_fields: [],
          match_rule: null, match_reason: null, updated_at: "2026-09-01" },
        { enrichment_id: "e2", target_eco_id: "pub_1", tenant_id: "t_gamma",
          payload: { capacity: "60 kt/yr" }, visible_fields: [],
          match_rule: null, match_reason: null, updated_at: "2026-09-02" },
      ],
      count: 1,
    });
    await refreshEcosystem();
    const byProject = getEnrichmentsByProject();
    expect(byProject["pub_1"]).toHaveLength(2);
    expect(byProject["pub_1"].map((e) => e.payload.capacity))
      .toEqual(expect.arrayContaining(["20 kt/yr", "60 kt/yr"]));
  });

  it("an empty cache means not-loaded, not nothing-published", async () => {
    // `_loaded` is module state, so a sibling test in this file has already
    // set it. Import a fresh copy of the module to see its initial value.
    vi.resetModules();
    const fresh = await import("../userProjects");
    expect(fresh.ecosystemLoaded()).toBe(false);
    expect(fresh.getPublishedEcosystemProjects()).toEqual([]);
    await fresh.refreshEcosystem();
    expect(fresh.ecosystemLoaded()).toBe(true);
  });
});
