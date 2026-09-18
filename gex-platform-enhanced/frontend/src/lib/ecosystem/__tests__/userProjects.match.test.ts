/**
 * Ecosystem matcher — false-merge regression tests.
 *
 * A false MERGE collapses two real projects into one and silently corrupts both.
 * A false SPLIT shows one project as two markers and is fixed by merging. These
 * tests pin the asymmetry: when evidence is thin the matcher must decline.
 *
 * Rules 1 and 4 were tightened on 2026-09-16. The bugs were latent only because
 * the candidate pool ships empty, so they are unobservable in the running app
 * and would have appeared on the first real import. The pool is mocked here so
 * the rules can be exercised at all.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { EcoProject } from "../types";

/* The matcher's candidate pool. Both modules ship as empty arrays. */
const verified: EcoProject[] = [];
const observatory: EcoProject[] = [];
vi.mock("../mockData", () => ({ get projects() { return verified; } }));
vi.mock("../observatoryData", () => ({
  get observatoryProjects() { return observatory; },
}));

const { findExistingEcosystemMatchDetailed } = await import("../userProjects");

function eco(p: Partial<EcoProject> & { id: string; name: string }): EcoProject {
  return {
    lat: 0, lng: 0, phase: "unknown", status: "active", layer: "production",
    ...p,
  } as EcoProject;
}

/* Two real Rotterdam-area hydrogen projects, ~2 km apart, different owners. */
const ROTTERDAM_A = eco({
  id: "v1", name: "Maasvlakte Hydrogen Hub", lat: 51.9500, lng: 4.0500,
  moleculeType: "hydrogen", owner: "Shell Nederland", country: "Netherlands",
});
const ROTTERDAM_B = eco({
  id: "v2", name: "Europoort Green H2", lat: 51.9650, lng: 4.0600,
  moleculeType: "hydrogen", owner: "Air Liquide", country: "Netherlands",
});

beforeEach(() => { verified.length = 0; observatory.length = 0; });

describe("Rule 4 — molecule + proximity + owner", () => {
  it("does NOT merge two different companies' plants in the same cluster", () => {
    verified.push(ROTTERDAM_A);
    const match = findExistingEcosystemMatchDetailed({
      slug: "al-h2", name: "Air Liquide Rotterdam Electrolyser",
      lat: 51.9650, lng: 4.0600, country: "Netherlands",
      fuelType: "Hydrogen", owner: "Air Liquide",
    });
    // Same molecule, 2 km apart — the old rule matched on exactly this.
    expect(match).toBeNull();
  });

  it("still attaches the same owner's project filed under another name", () => {
    verified.push(ROTTERDAM_A);
    const match = findExistingEcosystemMatchDetailed({
      slug: "shell-mv", name: "Shell MV2 Electrolysis Plant",
      lat: 51.9510, lng: 4.0510, country: "Netherlands",
      fuelType: "Hydrogen", owner: "Shell Nederland",
    });
    expect(match?.rule).toBe("molecule+proximity+owner");
    expect(match?.project.id).toBe("v1");
  });

  it("treats legal-form variants of one owner as the same owner", () => {
    // Names deliberately share no distinctive word, so Rules 2 and 3 cannot
    // fire and the owner comparison is what is under test.
    verified.push(eco({
      id: "v3", name: "Esbjerg Power-to-X", lat: 55.4700, lng: 8.4500,
      moleculeType: "ammonia", owner: "Ørsted A/S", country: "Denmark",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "orsted-nh3", name: "Kassø Ammonia Plant",
      lat: 55.4720, lng: 8.4520, country: "Denmark",
      fuelType: "Ammonia", owner: "Orsted AS",
    });
    expect(match?.rule).toBe("molecule+proximity+owner");
  });

  it("declines when the publishing plant has no owner to compare", () => {
    verified.push(ROTTERDAM_A);
    const match = findExistingEcosystemMatchDetailed({
      slug: "anon", name: "Unnamed Electrolyser",
      lat: 51.9510, lng: 4.0510, country: "Netherlands",
      fuelType: "Hydrogen",
    });
    expect(match).toBeNull();
  });
});

describe("Rule 1 — exact name requires location agreement", () => {
  const CHILE = eco({
    id: "v9", name: "Green Hydrogen Project", lat: -53.1600, lng: -70.9100,
    moleculeType: "hydrogen", owner: "HIF Global", country: "Chile",
  });

  it("does NOT merge identically named projects on different continents", () => {
    verified.push(CHILE);
    const match = findExistingEcosystemMatchDetailed({
      slug: "de-ghp", name: "Green Hydrogen Project",
      lat: 53.5500, lng: 9.9900, country: "Germany",
      fuelType: "Hydrogen", owner: "Hamburger Energiewerke",
    });
    expect(match).toBeNull();
  });

  it("matches an identical name at the same site", () => {
    verified.push(CHILE);
    const match = findExistingEcosystemMatchDetailed({
      slug: "cl-ghp", name: "Green Hydrogen Project",
      lat: -53.1620, lng: -70.9130, country: "Chile",
      fuelType: "Hydrogen", owner: "HIF Global",
    });
    expect(match?.rule).toBe("name-exact");
  });

  it("falls back to country when coordinates are missing on one side", () => {
    verified.push(eco({
      id: "v10", name: "Coastal Ammonia One", lat: 0, lng: 0,
      moleculeType: "ammonia", owner: "Yara", country: "Norway",
    }));
    const same = findExistingEcosystemMatchDetailed({
      slug: "ca1", name: "Coastal Ammonia One", country: "Norway",
      fuelType: "Ammonia", owner: "Yara",
    });
    expect(same?.rule).toBe("name-exact");

    const elsewhere = findExistingEcosystemMatchDetailed({
      slug: "ca2", name: "Coastal Ammonia One", country: "Australia",
      fuelType: "Ammonia", owner: "Yara",
    });
    expect(elsewhere).toBeNull();
  });

  it("declines when there is no location evidence on either side", () => {
    // Different molecules, so Rule 2 (name + molecule) cannot fire and Rule 1
    // is tested in isolation. Note Rule 2 is deliberately left as it was: an
    // exact name AND an agreeing molecule is still a match without coordinates.
    verified.push(eco({
      id: "v11", name: "Pilot Methanol Plant", lat: 0, lng: 0,
      moleculeType: "methanol",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "pmp", name: "Pilot Methanol Plant", fuelType: "Ammonia",
    });
    expect(match).toBeNull();
  });
});

describe("Rule 2 — distinctive name overlap, not substring", () => {
  it("a short generic pool name no longer captures every input containing it", () => {
    // Was: "rotterdam h2 plant".includes("h2") === true, so this merged.
    verified.push(eco({
      id: "v20", name: "H2", lat: 51.9200, lng: 4.4800,
      moleculeType: "hydrogen", owner: "Nobody BV", country: "Netherlands",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "rh2", name: "Rotterdam H2 Plant",
      lat: 51.9210, lng: 4.4810, country: "Netherlands",
      fuelType: "Hydrogen", owner: "Uniper Benelux",
    });
    expect(match).toBeNull();
  });

  it("does not match on shared generic sector vocabulary alone", () => {
    // Both are "Green Hydrogen Project"-shaped. Nothing identifying is shared.
    verified.push(eco({
      id: "v21", name: "Green Hydrogen Production Facility", lat: 43.3000,
      lng: 5.3700, moleculeType: "hydrogen", owner: "Engie", country: "France",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "ghp2", name: "Clean Hydrogen Plant",
      lat: 43.3020, lng: 5.3720, country: "France",
      fuelType: "Hydrogen", owner: "TotalEnergies",
    });
    expect(match).toBeNull();
  });

  it("no longer treats one word being inside another as a match", () => {
    // "hydro" is a substring of "hydrogen"; a hydro scheme is not an H2 plant.
    verified.push(eco({
      id: "v22", name: "Hydro", lat: 60.3900, lng: 5.3200,
      moleculeType: "hydrogen", owner: "Statkraft", country: "Norway",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "hydrogen-no", name: "Hydrogen",
      lat: 60.3910, lng: 5.3210, country: "Norway",
      fuelType: "Hydrogen", owner: "Nel",
    });
    expect(match).toBeNull();
  });

  it("keeps matching a genuine alias of the same project", () => {
    verified.push(eco({
      id: "v23", name: "Maasvlakte Hydrogen Hub", lat: 51.9500, lng: 4.0500,
      moleculeType: "hydrogen", owner: "Shell Nederland", country: "Netherlands",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "mv-h2", name: "Maasvlakte Green H2 Plant",
      lat: 51.9505, lng: 4.0505, country: "Netherlands",
      fuelType: "Hydrogen", owner: "Shell Nederland",
    });
    expect(match?.rule).toBe("name+molecule");
    expect(match?.project.id).toBe("v23");
  });

  it("does not merge Phase 1 into Phase 2 of the same development", () => {
    verified.push(eco({
      id: "v24", name: "NEOM Helios Phase 1", lat: 28.0000, lng: 35.0000,
      moleculeType: "ammonia", owner: "NEOM Green Hydrogen Company",
      country: "Saudi Arabia",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "neom2", name: "NEOM Helios Phase 2",
      lat: 28.0010, lng: 35.0010, country: "Saudi Arabia",
      fuelType: "Ammonia", owner: "NEOM Green Hydrogen Company",
    });
    expect(match).toBeNull();
  });

  it("still matches when only one side states a phase number", () => {
    verified.push(eco({
      id: "v25", name: "NEOM Helios", lat: 28.0000, lng: 35.0000,
      moleculeType: "ammonia", owner: "NEOM Green Hydrogen Company",
      country: "Saudi Arabia",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "neom1", name: "NEOM Helios Phase 1",
      lat: 28.0010, lng: 35.0010, country: "Saudi Arabia",
      fuelType: "Ammonia", owner: "NEOM Green Hydrogen Company",
    });
    expect(match?.rule).toBe("name+molecule");
  });

  it("reads Power-to-X as a category, not as roman numeral ten", () => {
    verified.push(eco({
      id: "v26", name: "Kassø Power-to-X", lat: 55.0500, lng: 9.3500,
      moleculeType: "methanol", owner: "European Energy", country: "Denmark",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "kasso2", name: "Kassø PtX Phase 2",
      lat: 55.0510, lng: 9.3510, country: "Denmark",
      fuelType: "Methanol", owner: "European Energy",
    });
    // The X must not read as "10" and collide with the "2".
    expect(match?.rule).toBe("name+molecule");
  });
});

describe("Rule 3 — name overlap plus proximity, molecule not contradicted", () => {
  it("does not merge two molecules at one site under a shared site name", () => {
    // A developer's methanol plant and ammonia plant on the same site, sharing
    // the site name, is the normal shape of a cluster — not one project. Rule 2
    // cannot fire (molecules differ), so this used to fall to Rule 3 and merge.
    verified.push(eco({
      id: "v30", name: "Kassø Methanol", lat: 55.0500, lng: 9.3500,
      moleculeType: "methanol", owner: "European Energy", country: "Denmark",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "kasso-nh3", name: "Kassø Ammonia",
      lat: 55.0510, lng: 9.3510, country: "Denmark",
      fuelType: "Ammonia", owner: "European Energy",
    });
    expect(match).toBeNull();
  });

  it("still attaches when the pool entry has no molecule recorded", () => {
    verified.push(eco({
      id: "v31", name: "Lingen Electrolyser", lat: 52.5200, lng: 7.3200,
      owner: "RWE", country: "Germany",   // moleculeType deliberately absent
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "lingen", name: "Lingen Electrolyser Expansion",
      lat: 52.5210, lng: 7.3210, country: "Germany",
      fuelType: "Hydrogen", owner: "RWE",
    });
    expect(match?.rule).toBe("name+proximity");
    expect(match?.project.id).toBe("v31");
  });

  it("no longer reaches 25 km — the radius is 10 km", () => {
    verified.push(eco({
      id: "v32", name: "Teesside Electrolyser", lat: 54.5800, lng: -1.2000,
      owner: "BP", country: "United Kingdom",
    }));
    // ~18 km away: inside the old radius, outside the new one.
    const match = findExistingEcosystemMatchDetailed({
      slug: "tees", name: "Teesside Electrolyser Two",
      lat: 54.7400, lng: -1.2000, country: "United Kingdom",
      fuelType: "Hydrogen", owner: "BP",
    });
    expect(match).toBeNull();
  });

  it("Rule 4 cannot re-merge what Rule 3 declines on a molecule contradiction", () => {
    // Same owner, 100 m apart — Rule 4's other conditions are all met. It must
    // still decline, because it requires the molecules to be equal.
    verified.push(eco({
      id: "v33", name: "Esbjerg Methanol", lat: 55.4700, lng: 8.4500,
      moleculeType: "methanol", owner: "Ørsted A/S", country: "Denmark",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "esb-nh3", name: "Esbjerg Ammonia",
      lat: 55.4705, lng: 8.4505, country: "Denmark",
      fuelType: "Ammonia", owner: "Ørsted A/S",
    });
    expect(match).toBeNull();
  });
});

describe("candidate ranking does not depend on pool order", () => {
  it("picks the strongest name overlap, not the first entry in the pool", () => {
    // Input distinctive tokens: {wilhelmshaven, salzgitter}.
    // "weak"   shares 1 of 2 → 0.5, and is listed FIRST and is NEARER.
    // "strong" shares 2 of 2 → 1.0, and is listed second and further away.
    // Only ranking by overlap strength can pick "strong".
    verified.push(eco({
      id: "weak", name: "Wilhelmshaven Import Terminal",
      lat: 53.5101, lng: 8.1401, moleculeType: "ammonia",
      owner: "Uniper", country: "Germany",
    }));
    verified.push(eco({
      id: "strong", name: "Wilhelmshaven Salzgitter Facility",
      lat: 53.5130, lng: 8.1430, moleculeType: "ammonia",
      owner: "Uniper", country: "Germany",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "whv", name: "Wilhelmshaven Salzgitter",
      lat: 53.5100, lng: 8.1400, country: "Germany",
      fuelType: "Ammonia", owner: "Uniper",
    });
    expect(match?.rule).toBe("name+molecule");
    expect(match?.project.id).toBe("strong");
  });
});

describe("the location guard covers the whole cascade, not just Rule 1", () => {
  it("does not let Rule 2 re-merge what Rule 1 rejected", () => {
    // An exact name is also a substring, and Rule 2 has no distance test — so
    // without the cascade-wide guard this pair merges under name+molecule.
    verified.push(eco({
      id: "v12", name: "Green Hydrogen Project", lat: -53.1600, lng: -70.9100,
      moleculeType: "hydrogen", owner: "HIF Global", country: "Chile",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "de2", name: "Green Hydrogen Project",
      lat: 53.5500, lng: 9.9900, country: "Germany",
      fuelType: "Hydrogen", owner: "Hamburger Energiewerke",
    });
    expect(match).toBeNull();
  });

  it("does not let Rule 3 match across a country contradiction", () => {
    verified.push(eco({
      id: "v13", name: "Humber Hydrogen", lat: 53.7000, lng: -0.4000,
      moleculeType: "hydrogen", owner: "Equinor", country: "United Kingdom",
    }));
    const match = findExistingEcosystemMatchDetailed({
      slug: "hh2", name: "Humber Hydrogen Phase 2", country: "Norway",
      fuelType: "Hydrogen", owner: "Equinor",
    });
    expect(match).toBeNull();
  });
});
