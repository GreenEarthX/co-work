/**
 * Lifecycle is two fields, and old records are in one.
 *
 * `ProjectStatus` used to be "concept | planned | construction | operational |
 * cancelled" — phase and status in one list, so a cancelled project had no
 * recordable phase and a planned one had no recordable status. The split is
 * only safe if every legacy row still reads, which is what these pin.
 */
import { describe, expect, it } from "vitest";

import {
  PRE_CONSTRUCTION_PHASES,
  isProjectPhase,
  isProjectStatus,
  normaliseLifecycle,
} from "../types";
import { mapMaturityToPhase } from "../userProjects";

describe("normaliseLifecycle — legacy rows", () => {
  it("splits each legacy value into a phase and a status", () => {
    expect(normaliseLifecycle({ status: "concept" })).toEqual({ phase: "concept", status: "active" });
    expect(normaliseLifecycle({ status: "construction" })).toEqual({ phase: "construction", status: "active" });
    expect(normaliseLifecycle({ status: "operational" })).toEqual({ phase: "operation", status: "active" });
  });

  it("does not invent a phase for values that never recorded one", () => {
    // "planned" said only that building had not started; "cancelled" never said
    // how far the project got. Guessing here would manufacture evidence.
    expect(normaliseLifecycle({ status: "planned" })).toEqual({ phase: "unknown", status: "active" });
    expect(normaliseLifecycle({ status: "cancelled" })).toEqual({ phase: "unknown", status: "cancelled" });
  });

  it("does not let a stored 'unknown' phase shadow a legacy status", () => {
    // What a pre-split row looks like after the server's additive migration:
    // phase defaulted to "unknown", the meaning still in the legacy status.
    // Reading the phase first here would silently drop "operational".
    expect(normaliseLifecycle({ phase: "unknown", status: "operational" }))
      .toEqual({ phase: "operation", status: "active" });
    expect(normaliseLifecycle({ phase: "unknown", status: "concept" }))
      .toEqual({ phase: "concept", status: "active" });
  });

  it("keeps a recorded phase when the status is legacy", () => {
    expect(normaliseLifecycle({ phase: "feed", status: "planned" }))
      .toEqual({ phase: "feed", status: "active" });
  });

  it("keeps a cancelled project's phase when the row records one", () => {
    // The whole point of the split: cancelled *at* FEED is expressible now.
    expect(normaliseLifecycle({ phase: "feed", status: "cancelled" }))
      .toEqual({ phase: "feed", status: "cancelled" });
  });
});

describe("normaliseLifecycle — current rows and rubbish", () => {
  it("passes a valid pair through untouched", () => {
    expect(normaliseLifecycle({ phase: "financing", status: "on_hold" }))
      .toEqual({ phase: "financing", status: "on_hold" });
  });

  it("defaults a missing status to active, and a missing phase to unknown", () => {
    expect(normaliseLifecycle({ phase: "commissioning" })).toEqual({ phase: "commissioning", status: "active" });
    expect(normaliseLifecycle({ status: "mothballed" })).toEqual({ phase: "unknown", status: "mothballed" });
  });

  it("never throws on third-party rubbish", () => {
    expect(normaliseLifecycle({ phase: "banana", status: "nonsense" }))
      .toEqual({ phase: "unknown", status: "active" });
    expect(normaliseLifecycle(null)).toEqual({ phase: "unknown", status: "active" });
    expect(normaliseLifecycle(undefined)).toEqual({ phase: "unknown", status: "active" });
    expect(normaliseLifecycle({})).toEqual({ phase: "unknown", status: "active" });
  });

  it("does not accept a legacy value as a current one", () => {
    // Guards against the two vocabularies quietly merging back together.
    expect(isProjectStatus("planned")).toBe(false);
    expect(isProjectStatus("operational")).toBe(false);
    expect(isProjectPhase("planned")).toBe(false);
    // "concept" and "cancelled" survive the split, but on different axes.
    expect(isProjectPhase("concept")).toBe(true);
    expect(isProjectStatus("concept")).toBe(false);
    expect(isProjectStatus("cancelled")).toBe(true);
    expect(isProjectPhase("cancelled")).toBe(false);
  });

  it("lists the pre-construction phases, which is what 'planned' used to mean", () => {
    expect([...PRE_CONSTRUCTION_PHASES]).toEqual(["concept", "pre_feasibility", "feed", "financing"]);
  });
});

describe("mapMaturityToPhase — the plant builder's own ladder", () => {
  it("maps the stages the plant builder offers", () => {
    expect(mapMaturityToPhase("Concept")).toBe("concept");
    expect(mapMaturityToPhase("Pre Feasibility")).toBe("pre_feasibility");
    expect(mapMaturityToPhase("Feasibility")).toBe("pre_feasibility");
    expect(mapMaturityToPhase("Pre FEED")).toBe("pre_feasibility");
    expect(mapMaturityToPhase("FEED")).toBe("feed");
    expect(mapMaturityToPhase("Pre FID")).toBe("financing");
    expect(mapMaturityToPhase("FID")).toBe("financing");
    expect(mapMaturityToPhase("Construction")).toBe("construction");
    expect(mapMaturityToPhase("Commissioning")).toBe("commissioning");
    expect(mapMaturityToPhase("Operating")).toBe("operation");
  });

  it("treats permitting as a workstream, not a phase of its own", () => {
    expect(mapMaturityToPhase("Permitting")).toBe("financing");
  });

  it("reads an unrecognised or absent stage as unknown rather than rounding it", () => {
    expect(mapMaturityToPhase("design")).toBe("unknown");
    expect(mapMaturityToPhase("")).toBe("unknown");
    expect(mapMaturityToPhase(undefined)).toBe("unknown");
  });

  it("does not confuse Pre FEED with FEED", () => {
    // Substring order matters: "pre feed" contains "feed".
    expect(mapMaturityToPhase("Pre-FEED")).toBe("pre_feasibility");
    expect(mapMaturityToPhase("FEED complete")).toBe("feed");
  });
});
