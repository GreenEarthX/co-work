/**
 * Soft compatibility rules — surfaced as warnings, never as hard blockers.
 * Each rule inspects the per-slot picks of a configuration.
 */
import type { Configuration, CompatibilityWarning } from "./simulatorTypes";
import { technologyForEntry } from "./technologyMap";

type Rule = (slots: Configuration["slots"]) => CompatibilityWarning[];

function findSlots(slots: Configuration["slots"], keyword: string) {
  return slots.filter((s) => s.label.toLowerCase().includes(keyword));
}

const RULES: Rule[] = [
  // 1. PEM electrolyzer requires ultrapure water treatment downstream.
  (slots) => {
    const out: CompatibilityWarning[] = [];
    const electrolyzers = findSlots(slots, "electrolyzer");
    const water = findSlots(slots, "water");
    const purif = findSlots(slots, "purif");
    const hasUltrapure = [...water, ...purif].some((s) => {
      if (!s.pick) return false;
      const fam = technologyForEntry(s.pick);
      return fam === "EDI" || fam === "RO" || /ultrapure|deionization|CDI/i.test(s.pick.model);
    });
    for (const s of electrolyzers) {
      if (!s.pick) continue;
      if (technologyForEntry(s.pick) === "PEM" && water.length > 0 && !hasUltrapure) {
        out.push({
          nodeId: s.nodeId,
          message:
            "PEM electrolyzer typically requires ultrapure water (RO + EDI) downstream.",
        });
      }
    }
    return out;
  },

  // 2. SOEC benefits from heat integration.
  (slots) => {
    const out: CompatibilityWarning[] = [];
    const electrolyzers = findSlots(slots, "electrolyzer");
    const hx = findSlots(slots, "heat exchanger");
    for (const s of electrolyzers) {
      if (!s.pick) continue;
      if (technologyForEntry(s.pick) === "SOEC" && hx.length === 0) {
        out.push({
          nodeId: s.nodeId,
          message:
            "SOEC operates at 700–850 °C and is best paired with a high-temperature heat-recovery exchanger.",
        });
      }
    }
    return out;
  },

  // 3. Methanol / synthesis reactor needs H₂ compressor upstream.
  (slots) => {
    const out: CompatibilityWarning[] = [];
    const reactors = findSlots(slots, "reactor");
    const compressors = findSlots(slots, "compressor");
    for (const s of reactors) {
      if (!s.pick) continue;
      if (
        /methanol|synthesis|fischer|ammonia/i.test(s.label) &&
        compressors.length === 0
      ) {
        out.push({
          nodeId: s.nodeId,
          message:
            "Synthesis reactor requires an upstream H₂ compressor (≥ 80 bar typical).",
        });
      }
    }
    return out;
  },

  // 4. High-pressure storage needs a multi-stage compressor.
  (slots) => {
    const out: CompatibilityWarning[] = [];
    const tanks = findSlots(slots, "tank");
    const compressors = findSlots(slots, "compressor");
    for (const t of tanks) {
      if (!t.pick) continue;
      if (/350|700|900|high.?pressure/i.test(t.pick.model)) {
        const hasMultiStage = compressors.some(
          (c) => c.pick && /multi|stage|reciprocating|ionic/i.test(c.pick.model),
        );
        if (!hasMultiStage) {
          out.push({
            nodeId: t.nodeId,
            message:
              "High-pressure storage requires a multi-stage compressor (reciprocating or ionic).",
          });
        }
      }
    }
    return out;
  },

  // 5. Alkaline electrolyzer: KOH-compatible piping expected (informational).
  (slots) => {
    const out: CompatibilityWarning[] = [];
    const electrolyzers = findSlots(slots, "electrolyzer");
    for (const s of electrolyzers) {
      if (!s.pick) continue;
      if (technologyForEntry(s.pick) === "Alkaline") {
        out.push({
          nodeId: s.nodeId,
          message:
            "Alkaline electrolyzer: downstream piping and seals must be KOH-resistant (Hastelloy / EPDM).",
        });
      }
    }
    return out;
  },
];

export function evaluateCompatibility(slots: Configuration["slots"]): CompatibilityWarning[] {
  return RULES.flatMap((rule) => rule(slots));
}