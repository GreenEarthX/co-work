// Screen: Project profile — power-attribution contradiction rules
//
// Off-grid behind-the-meter is not an exemption from power evidence. These
// tests pin the direct-line route's requirements so the rules cannot silently
// regress back to "BTM owns its generation, so nothing is owed":
//   - RFNBO DA (EU) 2023/1184 Art. 3 — additionality, correlation, and a
//     zero-grid-import metering condition the PPA route does not carry
//   - RFNBO DA Art. 5 — aid-disqualified generators
//   - US 45V final regulations (Jan 2025) — EACs required for captive,
//     co-located behind-the-meter power
//   - RED III Art. 2 — a renewables PPA is defined contractually, so a direct
//     line between separate legal entities is still a PPA
import { describe, it, expect } from "vitest";
import { detectContradictions } from "../ProjectProfilePage";
import {
  CUSTOMER_PROJECTS,
  type CustomerProject,
} from "@/data/customerProjects";

const BASE = CUSTOMER_PROJECTS.find((p) => p.id === "proj_etf_pecos1")!;

/** Off-grid project with a live 45V claim, overridable per test. */
function offGrid(
  attribution: NonNullable<
    NonNullable<CustomerProject["energy_input"]>["power_attribution"]
  > | null,
  overrides: Partial<CustomerProject> = {},
): CustomerProject {
  return {
    ...BASE,
    ...overrides,
    energy_input: {
      power_mw: 340,
      source: "wind",
      power_model: "OFF_GRID_BTM",
      ppas: [],
      ...(attribution ? { power_attribution: attribution } : {}),
      ...(overrides.energy_input ?? {}),
    },
  };
}

const ids = (p: CustomerProject) => detectContradictions(p).map((f) => f.id);
const flag = (p: CustomerProject, id: string) =>
  detectContradictions(p).find((f) => f.id === id);

describe("off-grid BTM is not exempt from power evidence", () => {
  it("flags a missing attribution record entirely", () => {
    expect(ids(offGrid(null))).toContain("CONTRA_BTM_NO_ATTRIBUTION_RECORD");
  });

  it("keeps the missing-record flag a WARN pre-COD and a DEAL_KILLER once producing", () => {
    expect(
      flag(
        offGrid(null, { status: "development" }),
        "CONTRA_BTM_NO_ATTRIBUTION_RECORD",
      )?.severity,
    ).toBe("WARN");
    expect(
      flag(
        offGrid(null, { status: "operating" }),
        "CONTRA_BTM_NO_ATTRIBUTION_RECORD",
      )?.severity,
    ).toBe("DEAL_KILLER");
  });

  it("does not exempt off-grid from the PPA question the way the old rule did", () => {
    // Regression guard: the previous engine skipped the whole PPA block for
    // OFF_GRID_BTM, so an off-grid project raised nothing at all here.
    const flags = ids(offGrid(null));
    expect(flags.some((id) => id.startsWith("CONTRA_BTM_"))).toBe(true);
  });
});

describe("additionality — 36-month window (DA Art. 3)", () => {
  it("flags a generator commissioned more than 36 months before production", () => {
    const p = offGrid(
      { generator_cod_year: 2026 },
      {
        timeline: {
          construction_start_year: 2027,
          production_start_year: 2030,
        },
      },
    );
    expect(ids(p)).toContain("CONTRA_BTM_ADDITIONALITY");
  });

  it("accepts a generator commissioned inside the window", () => {
    const p = offGrid(
      { generator_cod_year: 2028 },
      {
        timeline: {
          construction_start_year: 2027,
          production_start_year: 2030,
        },
      },
    );
    expect(ids(p)).not.toContain("CONTRA_BTM_ADDITIONALITY");
  });
});

describe("aid-disqualified generator (DA Art. 5)", () => {
  it("is a deal-killer while an RFNBO or 45V claim is live", () => {
    const p = offGrid({ generator_received_aid: true });
    expect(flag(p, "CONTRA_BTM_GENERATOR_AID")?.severity).toBe("DEAL_KILLER");
  });

  it("does not fire when no attribution claim is made", () => {
    const p = offGrid(
      { generator_received_aid: true },
      {
        certifications: [],
        incentives: [],
      },
    );
    expect(ids(p)).not.toContain("CONTRA_BTM_GENERATOR_AID");
  });
});

describe("zero-grid-import metering (DA Art. 3(b))", () => {
  it("flags anything short of VERIFIED", () => {
    expect(ids(offGrid({ grid_import_metering: "INSTALLED" }))).toContain(
      "CONTRA_BTM_NO_METERING",
    );
    expect(ids(offGrid({ grid_import_metering: "NONE" }))).toContain(
      "CONTRA_BTM_NO_METERING",
    );
  });

  it("clears once metering is verified", () => {
    expect(ids(offGrid({ grid_import_metering: "VERIFIED" }))).not.toContain(
      "CONTRA_BTM_NO_METERING",
    );
  });
});

describe("certificate attribution — 45V requires EACs behind the meter", () => {
  it("flags an absent mechanism while a claim is live", () => {
    expect(ids(offGrid({ certificate_matching: "NONE" }))).toContain(
      "CONTRA_BTM_NO_CERTIFICATES",
    );
  });

  it("says nothing is owed yet pre-COD, but hardens once producing", () => {
    const dev = flag(
      offGrid({ certificate_matching: "NONE" }, { status: "development" }),
      "CONTRA_BTM_NO_CERTIFICATES",
    );
    expect(dev?.severity).toBe("WARN");
    expect(dev?.message).toMatch(/nothing is owed yet/);

    const live = flag(
      offGrid({ certificate_matching: "NONE" }, { status: "operating" }),
      "CONTRA_BTM_NO_CERTIFICATES",
    );
    expect(live?.severity).toBe("DEAL_KILLER");
  });

  it("flags annual matching against a post-2028 start under 45V", () => {
    const p = offGrid(
      { certificate_matching: "ANNUAL" },
      {
        timeline: {
          construction_start_year: 2027,
          production_start_year: 2030,
        },
      },
    );
    expect(ids(p)).toContain("CONTRA_BTM_TEMPORAL_GRANULARITY");
  });

  it("accepts hourly matching", () => {
    const p = offGrid(
      { certificate_matching: "HOURLY" },
      {
        timeline: {
          construction_start_year: 2027,
          production_start_year: 2030,
        },
      },
    );
    expect(ids(p)).not.toContain("CONTRA_BTM_TEMPORAL_GRANULARITY");
    expect(ids(p)).not.toContain("CONTRA_BTM_NO_CERTIFICATES");
  });
});

describe("a direct line between separate entities is still a PPA (RED III Art. 2)", () => {
  it("treats third-party generation with no contract as uncontracted power", () => {
    const p = offGrid({ generator_ownership: "THIRD_PARTY" });
    expect(flag(p, "CONTRA_BTM_UNCONTRACTED_SUPPLY")?.severity).toBe(
      "DEAL_KILLER",
    );
  });

  it("warns on affiliate generation with no contract — related-party pricing", () => {
    const p = offGrid({ generator_ownership: "AFFILIATE" });
    expect(flag(p, "CONTRA_BTM_AFFILIATE_SUPPLY")?.severity).toBe("WARN");
  });

  it("asks for ownership when it is undeclared — it decides whether a PPA is owed", () => {
    expect(ids(offGrid({ grid_import_metering: "NONE" }))).toContain(
      "CONTRA_BTM_OWNERSHIP_UNDECLARED",
    );
  });

  it("raises no supply-contract flag when one entity owns both assets", () => {
    const p = offGrid({ generator_ownership: "SAME_ENTITY" });
    const f = ids(p);
    expect(f).not.toContain("CONTRA_BTM_UNCONTRACTED_SUPPLY");
    expect(f).not.toContain("CONTRA_BTM_AFFILIATE_SUPPLY");
    expect(f).not.toContain("CONTRA_BTM_OWNERSHIP_UNDECLARED");
    // ...but it still owes certificate attribution under 45V.
    expect(f).toContain("CONTRA_BTM_NO_CERTIFICATES");
  });
});

describe("on-grid rules are unchanged", () => {
  it("still demands a PPA when grid-connected", () => {
    const p: CustomerProject = {
      ...BASE,
      energy_input: {
        power_mw: 340,
        source: "wind",
        power_model: "GRID_CONNECTED",
        ppas: [],
      },
    };
    expect(ids(p)).toContain("CONTRA_GRID_NO_PPA");
  });

  it("does not apply the direct-line rules to grid-connected projects", () => {
    const p: CustomerProject = {
      ...BASE,
      energy_input: {
        power_mw: 340,
        source: "wind",
        power_model: "GRID_CONNECTED",
        ppas: [],
      },
    };
    expect(ids(p).some((id) => id.startsWith("CONTRA_BTM_"))).toBe(false);
  });
});
