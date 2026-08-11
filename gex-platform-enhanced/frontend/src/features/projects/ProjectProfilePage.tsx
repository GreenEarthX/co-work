/**
 * ProjectProfilePage — Bloomberg-density verification workbench.
 *
 * Principles:
 *  - Verification state is first-class (UNVERIFIED → SUBMITTED → CONFIRMED → AUDITED)
 *  - Deal-killers override percentages
 *  - Contradictions surfaced inline
 *  - Information density > decoration — zero field icons
 *  - Direct manipulation: click value → edit in place, no modal
 */

import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import {
  CUSTOMER_PROJECTS,
  type CustomerProject,
} from "@/data/customerProjects";
import { renderNarrative, type RenderedNarrative } from "@/lib/narrative";
import { useUserRole } from "@/contexts/UserRoleContext";
import {
  MENU_TABS,
  isVisible,
  consultItemsForRole,
  type MenuItem,
} from "@/config/menuArchitecture";
import {
  CAPACITY_UNITS,
  capacityDisplayValue,
  capacityInputToMtpd,
  type CapacityUnit,
} from "@/lib/capacityUnits";
import type { VerificationState } from "@/types/deal";

// ── Data model ───────────────────────────────────────────────────────────────

// Derived from CustomerProject rather than imported, so the overlay's unions
// stay pinned to the canonical shape if it changes.
type EnergyInputGroup = NonNullable<CustomerProject["energy_input"]>;
type ElectrolyserGroup = NonNullable<CustomerProject["electrolyser"]>;
type PowerAttributionGroup = NonNullable<EnergyInputGroup["power_attribution"]>;

interface VerifiedField<T> {
  value: T;
  verification: VerificationState;
  source?: string;
  unit?: string;
  derived?: boolean;
  lastVerifiedAt?: string;
  lastUpdatedAt: string;
}

type ContradictionSeverity = "WARN" | "DEAL_KILLER";

interface ContradictionFlag {
  id: string;
  severity: ContradictionSeverity;
  message: string;
  involvedFields: string[];
  detectedAt: string;
}

interface ProjectProfileIntelligence {
  project_id: string;
  record_id: string;
  narrative: string;
  source_scope: string;
  access_tier: string;
  backend_store: string;
  linked_records: string[];
  updated_at: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const MOLECULE_OPTIONS = [
  "H2",
  "NH3",
  "e-Methanol",
  "SAF",
  "e-NG",
  "e-Methane",
  "e-NH3",
  "HVO",
  "e-Gasoline",
  "e-LG",
  "e-Naphtha",
] as const;

const STATUS_OPTIONS = [
  "development",
  "construction",
  "commissioning",
  "operating",
] as const;

/**
 * Shared column model for every data row in the workbench.
 *
 * Each row is its own grid, so the tracks only line up across rows if they are
 * all fixed. The unit track is therefore reserved at a fixed width and rendered
 * empty when a field has no unit — an `auto` track would size to that row's own
 * content and shift the value + state columns left by the unit width, which is
 * what used to make TECHNICAL look ragged next to unit-free IDENTITY.
 *
 *   [ label 112 ][ value 1fr ][ state 78 ][ unit 56 ]
 */
const DATA_ROW_GRID =
  "grid grid-cols-[112px_minmax(0,1fr)_78px_56px] items-center gap-1";

/** Evidence + access chips share one geometry so the right edge never jitters. */
const CHIP_BASE =
  "justify-self-end inline-flex h-[15px] w-[74px] items-center justify-center px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none";

function fmtNum(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/** Years are ordinals, not quantities — no thousands separator. */
function fmtYear(value: string | number): string {
  const n = Number(value);
  return Number.isFinite(n) && n !== 0 ? String(Math.trunc(n)) : "—";
}

/** Signed decimal degrees → hemisphere notation (-103.49 → 103.49° W). */
function fmtLat(value: string | number): string {
  const n = Number(value);
  return Number.isFinite(n)
    ? `${fmtNum(Math.abs(n))}° ${n < 0 ? "S" : "N"}`
    : "—";
}

function fmtLng(value: string | number): string {
  const n = Number(value);
  return Number.isFinite(n)
    ? `${fmtNum(Math.abs(n))}° ${n < 0 ? "W" : "E"}`
    : "—";
}

function fmtDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

const MENU_ITEMS = MENU_TABS.flatMap((tab) => tab.items);

function menuItemForPath(path: string): MenuItem | undefined {
  return MENU_ITEMS.find((item) => item.path === path);
}

/** Build verified fields from static CustomerProject data (demo shim). */
function buildVerifiedFields(
  p: CustomerProject,
): Record<string, VerifiedField<unknown>> {
  const now = new Date().toISOString();
  const mk = <T,>(
    value: T,
    verification: VerificationState = "UNVERIFIED",
    opts: Partial<VerifiedField<T>> = {},
  ): VerifiedField<T> => ({
    value,
    verification,
    lastUpdatedAt: now,
    ...opts,
  });

  // Gates with evidence → CONFIRMED; all evidence verified → AUDITED
  const gateCompletion = p.bankability.overall_completion;
  const projectVerif: VerificationState =
    gateCompletion >= 90
      ? "AUDITED"
      : gateCompletion >= 60
        ? "CONFIRMED"
        : gateCompletion >= 30
          ? "SUBMITTED"
          : "UNVERIFIED";

  return {
    name: mk(p.name, "CONFIRMED", {
      source: "Onboarding",
      lastVerifiedAt: "2026-01-15",
    }),
    molecule: mk(p.molecule, projectVerif, { source: "FEED study" }),
    owner_company: mk(p.owner_company, "CONFIRMED", {
      source: "KYC check",
      lastVerifiedAt: "2026-02-01",
    }),
    associated_companies: mk(p.associated_companies.join(", "), "SUBMITTED"),
    location: mk(p.location, "CONFIRMED", {
      source: "Site survey",
      lastVerifiedAt: "2025-11-20",
    }),
    country: mk(p.country, "CONFIRMED", { source: "Jurisdiction filing" }),
    lat: mk(p.lat, "CONFIRMED", { unit: "deg N" }),
    lng: mk(p.lng, "CONFIRMED", { unit: "deg E/W" }),
    capacity_mtpd: mk(p.capacity_mtpd, projectVerif, {
      unit: "MTPD",
      source: "FEED Class 3",
    }),
    capex_eur: mk(p.capex_eur, projectVerif, {
      unit: p.capex_currency ?? "EUR",
      source: "AACE Class 3 estimate",
    }),
    capex_currency: mk(
      p.capex_currency ?? "EUR",
      p.capex_currency ? "CONFIRMED" : "UNVERIFIED",
      { source: "Project filing" },
    ),
    status: mk(p.status, "CONFIRMED"),
    phase: mk(p.phase, projectVerif, { source: "Project manager attestation" }),
    completion_date: mk(
      p.completion_date,
      p.status === "operating" ? "AUDITED" : "SUBMITTED",
    ),
    description: mk(p.description, "UNVERIFIED"),
    // ── Structured narrative source-of-truth fields (Option A) ──
    power_mw: mk(
      p.energy_input?.power_mw ?? 0,
      p.energy_input ? "CONFIRMED" : "UNVERIFIED",
      { unit: "MW", source: "FEED Class 3" },
    ),
    power_source: mk(
      p.energy_input?.source ?? "",
      p.energy_input ? "CONFIRMED" : "UNVERIFIED",
      { source: "Energy supply agreement" },
    ),
    // Grid topology — drives G1 evidence requirements and the PPA rule.
    power_model: mk(
      p.energy_input?.power_model ?? "",
      p.energy_input?.power_model ? "CONFIRMED" : "UNVERIFIED",
      { source: "Power sourcing strategy" },
    ),
    // PPA portfolio summary (structured editor is a follow-up; the rule reads the array).
    //
    // Off-grid behind-the-meter is NOT an exemption. The direct-line route under
    // RFNBO DA Art. 3 still owes additionality, temporal and geographic
    // correlation, and adds a zero-grid-import metering condition a PPA route
    // does not have; 45V final rules extend the EAC requirement expressly to
    // captive co-located power. Where generation sits in a separate SPV the
    // supply contract is a PPA by RED III's own definition ("purchase renewable
    // electricity directly from an electricity producer" — a contractual, not a
    // topological, test). So an empty register is an open evidence item on every
    // grid model; only the satisfying instrument changes.
    ppas: mk(
      (() => {
        const ppas = p.energy_input?.ppas ?? [];
        if (ppas.length === 0) return "none";
        const mw = ppas.reduce((s, x) => s + x.volume_mw, 0);
        const signed = ppas.filter((x) => x.status === "SIGNED").length;
        return `${ppas.length} PPA · ${signed} signed · ${mw} MW`;
      })(),
      (p.energy_input?.ppas ?? []).some((x) => x.status === "SIGNED")
        ? "CONFIRMED"
        : "UNVERIFIED",
      {
        source:
          p.energy_input?.power_model === "OFF_GRID_BTM"
            ? "PPA register — direct-line route: captive-power attribution (EAC/GO) evidence owed in place of a grid PPA"
            : "PPA register",
      },
    ),
    // ── Power attribution — the direct-line / captive-power evidence set ──
    generator_ownership: mk(
      p.energy_input?.power_attribution?.generator_ownership ?? "",
      p.energy_input?.power_attribution?.generator_ownership
        ? "SUBMITTED"
        : "UNVERIFIED",
      {
        source:
          "Ownership of the generating asset — anything but SAME_ENTITY needs a supply contract (RED III Art. 2)",
      },
    ),
    generator_cod_year: mk(
      p.energy_input?.power_attribution?.generator_cod_year ?? 0,
      p.energy_input?.power_attribution?.generator_cod_year
        ? "SUBMITTED"
        : "UNVERIFIED",
      {
        source:
          "Generator commissioning year — additionality: ≤36 months before production start",
      },
    ),
    generator_aid: mk(
      p.energy_input?.power_attribution?.generator_received_aid == null
        ? ""
        : p.energy_input.power_attribution.generator_received_aid
          ? "yes"
          : "no",
      p.energy_input?.power_attribution?.generator_received_aid == null
        ? "UNVERIFIED"
        : "SUBMITTED",
      {
        source:
          "Operating or investment aid to the generator — disqualifying for RFNBO additionality unless repaid (DA Art. 5)",
      },
    ),
    grid_import_metering: mk(
      p.energy_input?.power_attribution?.grid_import_metering ?? "",
      p.energy_input?.power_attribution?.grid_import_metering === "VERIFIED"
        ? "CONFIRMED"
        : "UNVERIFIED",
      {
        source:
          "Smart metering attesting zero grid import — required by DA Art. 3(b); any import voids the direct-line route",
      },
    ),
    certificate_matching: mk(
      p.energy_input?.power_attribution?.certificate_matching ?? "",
      p.energy_input?.power_attribution?.certificate_matching === "HOURLY"
        ? "CONFIRMED"
        : p.energy_input?.power_attribution?.certificate_matching &&
            p.energy_input.power_attribution.certificate_matching !== "NONE"
          ? "SUBMITTED"
          : "UNVERIFIED",
      {
        source:
          "EAC / GO retirement granularity — 45V requires hourly from 2028, RFNBO from 2030",
      },
    ),
    electrolyser_mw: mk(
      p.electrolyser?.capacity_mw ?? 0,
      p.electrolyser ? "CONFIRMED" : "UNVERIFIED",
      { unit: "MW", source: "Electrolyser OEM spec" },
    ),
    electrolyser_tech: mk(
      p.electrolyser?.technology ?? "",
      p.electrolyser ? "CONFIRMED" : "UNVERIFIED",
      { source: "Electrolyser OEM spec" },
    ),
    capacity_kt_yr: mk(
      p.capacity_kt_yr ?? Math.round((p.capacity_mtpd * 365) / 1000),
      "CONFIRMED",
      { unit: "kt/yr", source: "Derived from capacity_mtpd × 365" },
    ),
    construction_start: mk(
      p.timeline?.construction_start_year ?? 0,
      p.timeline?.construction_start_year ? "SUBMITTED" : "UNVERIFIED",
      { source: "Project schedule" },
    ),
  };
}

/** Detect contradictions from project data. */
export function detectContradictions(p: CustomerProject): ContradictionFlag[] {
  const flags: ContradictionFlag[] = [];
  const now = new Date().toISOString();

  // Status=Construction + Phase starts with FEED → DEAL_KILLER (upgraded per verification report 2026-05-21)
  if (p.status === "construction" && p.phase.toUpperCase().startsWith("FEED")) {
    flags.push({
      id: "CONTRA_STATUS_PHASE",
      severity: "DEAL_KILLER",
      message: `Status "${p.status}" contradicts phase "${p.phase}" — FEED is pre-construction. Lenders cannot price risk if basic project phase is wrong.`,
      involvedFields: ["status", "phase"],
      detectedAt: now,
    });
  }

  // Related-party offtake detection — owner is also offtaker
  if (p.offtakes && p.offtakes.length > 0) {
    const relatedParty = p.offtakes.filter((o) => o.is_related_party);
    const thirdPartyBinding = p.offtakes.filter(
      (o) => !o.is_related_party && o.binding_status === "BINDING",
    );
    if (relatedParty.length > 0 && thirdPartyBinding.length === 0) {
      flags.push({
        id: "CONTRA_RELATED_PARTY_ONLY",
        severity: "DEAL_KILLER",
        message:
          "All offtake is related-party (owner = offtaker) with no binding third-party contract — lenders discount or exclude related-party offtake from bankability",
        involvedFields: ["owner_company"],
        detectedAt: now,
      });
    }
    const anyBinding = p.offtakes.filter((o) => o.binding_status === "BINDING");
    if (anyBinding.length === 0) {
      flags.push({
        id: "CONTRA_NO_BINDING_OFFTAKE",
        severity: "DEAL_KILLER",
        message:
          "No binding offtake agreement — all offtakes are LOI, MOU, or indicative. Project cannot reach financial close without a bankable binding contract.",
        involvedFields: ["owner_company"],
        detectedAt: now,
      });
    }
  }

  // CAPEX currency vs jurisdiction convention.
  // Local-currency CAPEX removes the FX surcharge in lender models. When the
  // user changes capex_currency to the conventional one, this flag disappears.
  const CONVENTIONAL_CCY: Record<string, string> = {
    US: "USD",
    CA: "CAD",
    GB: "GBP",
    JP: "JPY",
    CH: "CHF",
    AU: "AUD",
    DE: "EUR",
    FR: "EUR",
    ES: "EUR",
    NL: "EUR",
    BE: "EUR",
    IT: "EUR",
    PT: "EUR",
    FI: "EUR",
    IE: "EUR",
    AT: "EUR",
    GR: "EUR",
    LU: "EUR",
  };
  const expected = CONVENTIONAL_CCY[p.country];
  const actual = p.capex_currency ?? "EUR";
  if (expected && expected !== actual) {
    flags.push({
      id: "CONTRA_CAPEX_FX",
      severity: "WARN",
      message: `CAPEX denominated in ${actual} but project jurisdiction is ${p.country} — local convention is ${expected}, FX exposure not surfaced`,
      involvedFields: ["capex_eur", "capex_currency", "country"],
      detectedAt: now,
    });
  }

  // No binding offtake (G4 incomplete) at advanced phase
  const g4 = p.bankability.gates.find((g) => g.id === "G4_OFFTAKE_BANKABLE");
  if (
    g4 &&
    !g4.is_complete &&
    (p.status === "construction" || p.phase.includes("FID"))
  ) {
    flags.push({
      id: "CONTRA_NO_OFFTAKE",
      severity: "DEAL_KILLER",
      message: "No bankable offtake agreement at construction/FID maturity",
      involvedFields: ["status", "phase"],
      detectedAt: now,
    });
  }

  // 45V claim unverified
  if (p.description.includes("45V") && p.bankability.overall_completion < 80) {
    flags.push({
      id: "CONTRA_45V_UNVERIFIED",
      severity: "DEAL_KILLER",
      message:
        "45V Tier 1 subsidy claim referenced but certification not AUDITED",
      involvedFields: ["description"],
      detectedAt: now,
    });
  }

  // ── Power model ⇒ power-evidence rules ────────────────────────────────────
  // Every topology owes evidence that the electricity qualifies the molecule.
  // On-grid (GRID_CONNECTED / HYBRID) satisfies it with ≥1 PPA. Off-grid BTM
  // satisfies it with the direct-line route — additionality, zero-grid-import
  // metering and retired attribute certificates — which is a different, and in
  // places stricter, burden. It is NOT an exemption: 45V final rules require
  // EACs for captive co-located power, and RFNBO DA Art. 3 adds the metering
  // condition on top of the same three pillars.
  const ei = p.energy_input;
  const att = ei?.power_attribution;

  // Is a regulatory attribution claim live? Certificates and credits are what
  // convert a power arrangement from a commercial matter into a compliance one.
  const attributionClaimed =
    (p.certifications ?? []).some(
      (c) =>
        (c.scheme === "RFNBO" ||
          c.scheme === "45V" ||
          c.scheme === "RED_III") &&
        c.status !== "WITHDRAWN",
    ) ||
    (p.incentives ?? []).some(
      (i) => i.kind === "IRA_45V" && i.status !== "DECLINED",
    );
  // Past FID the record has to stand up; before it, gaps are normal.
  const capitalAtWork =
    p.status === "construction" ||
    p.status === "commissioning" ||
    p.status === "operating";
  // Certificates are retired AGAINST PRODUCTION and metering attests actual
  // flows — neither can exist before the plant runs. Pre-COD the question is
  // whether a mechanism is contracted, not whether it has been exercised, so
  // these rules only harden once the plant is producing.
  const producing = p.status === "commissioning" || p.status === "operating";

  if (ei?.power_model === "OFF_GRID_BTM") {
    if (!att) {
      flags.push({
        id: "CONTRA_BTM_NO_ATTRIBUTION_RECORD",
        severity: producing ? "DEAL_KILLER" : "WARN",
        message:
          `Power model is OFF_GRID_BTM but no power-attribution record exists. ` +
          `The direct-line route (RFNBO DA Art. 3) owes additionality, temporal and ` +
          `geographic correlation AND zero-grid-import metering; 45V requires EACs for ` +
          `captive co-located power. Off-grid changes the instrument, not the obligation.` +
          (attributionClaimed
            ? " A certification or 45V claim is live against this project."
            : ""),
        involvedFields: ["power_model", "ppas"],
        detectedAt: now,
      });
    } else {
      // Additionality — generator must come into operation no more than 36
      // months before the fuel plant starts producing (DA Art. 3(a) / Art. 4).
      const prodStart = p.timeline?.production_start_year;
      if (att.generator_cod_year && prodStart) {
        const lead = prodStart - att.generator_cod_year;
        if (lead > 3) {
          flags.push({
            id: "CONTRA_BTM_ADDITIONALITY",
            severity: attributionClaimed ? "DEAL_KILLER" : "WARN",
            message:
              `Generating asset commissioned ${att.generator_cod_year}, production starts ${prodStart} — ` +
              `a ${lead}-year lead breaches the 36-month additionality window. The electricity cannot ` +
              `be counted as additional renewable generation for RFNBO purposes.`,
            involvedFields: ["power_model", "generator_cod_year"],
            detectedAt: now,
          });
        }
      }

      // Aid-disqualified generator (DA Art. 5).
      if (att.generator_received_aid && attributionClaimed) {
        flags.push({
          id: "CONTRA_BTM_GENERATOR_AID",
          severity: "DEAL_KILLER",
          message:
            `Generating asset received operating or investment aid — disqualified for RFNBO ` +
            `additionality under DA Art. 5 unless the aid was fully repaid. Repayment evidence is required.`,
          involvedFields: ["generator_aid"],
          detectedAt: now,
        });
      }

      // Zero-grid-import metering (DA Art. 3(b)). Any import voids the route.
      if (att.grid_import_metering !== "VERIFIED") {
        flags.push({
          id: "CONTRA_BTM_NO_METERING",
          severity: producing ? "DEAL_KILLER" : "WARN",
          message:
            `Grid-import metering is ${att.grid_import_metering ?? "not declared"} — the direct-line route ` +
            `requires smart metering attesting that NO electricity was taken from the grid (DA Art. 3(b)). ` +
            `Any import voids the route for the whole period, including auxiliary and black-start load.` +
            (producing
              ? ""
              : " Pre-COD this is a design commitment to evidence, not yet a breach."),
          involvedFields: ["grid_import_metering"],
          detectedAt: now,
        });
      }

      // Certificate attribution — 45V requires EACs even behind the meter.
      if (
        (!att.certificate_matching || att.certificate_matching === "NONE") &&
        attributionClaimed
      ) {
        flags.push({
          id: "CONTRA_BTM_NO_CERTIFICATES",
          severity: producing ? "DEAL_KILLER" : "WARN",
          message: producing
            ? `No attribute certificates (EAC / GO) are retired against production while a 45V or RFNBO ` +
              `claim is live. The 45V final regulations extend the EAC requirement to captive, co-located ` +
              `behind-the-meter power — being off-grid does not remove it.`
            : `No certificate-attribution mechanism is declared while a 45V or RFNBO claim is live. ` +
              `Certificates are retired against production, so nothing is owed yet — but the 45V final rules ` +
              `require EACs for captive co-located power, so the registry, metering granularity and issuing ` +
              `body have to be contracted before COD, not after.`,
          involvedFields: ["certificate_matching"],
          detectedAt: now,
        });
      }

      // Temporal granularity — hourly matching: 45V from 2028, RFNBO from 2030.
      const hourlyDue =
        (p.certifications ?? []).some(
          (c) => c.scheme === "45V" && c.status !== "WITHDRAWN",
        ) ||
        (p.incentives ?? []).some(
          (i) => i.kind === "IRA_45V" && i.status !== "DECLINED",
        )
          ? 2028
          : 2030;
      if (
        (att.certificate_matching === "ANNUAL" ||
          att.certificate_matching === "MONTHLY") &&
        (p.timeline?.production_start_year ?? 0) >= hourlyDue
      ) {
        flags.push({
          id: "CONTRA_BTM_TEMPORAL_GRANULARITY",
          severity: "WARN",
          message:
            `Certificates are matched ${att.certificate_matching.toLowerCase()} but production starts ` +
            `${p.timeline?.production_start_year} — hourly matching is required from ${hourlyDue}. ` +
            `The claim will lapse at that date unless metering and retirement move to hourly.`,
          involvedFields: ["certificate_matching"],
          detectedAt: now,
        });
      }

      // A direct line between two legal entities IS a PPA (RED III Art. 2 —
      // "purchase renewable electricity directly from an electricity producer").
      const ppaCount = (ei.ppas ?? []).length;
      if (!att.generator_ownership) {
        flags.push({
          id: "CONTRA_BTM_OWNERSHIP_UNDECLARED",
          severity: capitalAtWork ? "DEAL_KILLER" : "WARN",
          message:
            `Ownership of the generating asset is not declared. This is what decides whether a supply ` +
            `contract is owed at all: only single-entity ownership of both the generation and the plant ` +
            `escapes a PPA — a direct line between separate entities is a renewables PPA by RED III's ` +
            `definition, and an affiliate structure additionally needs transfer-pricing evidence.`,
          involvedFields: ["generator_ownership", "ppas"],
          detectedAt: now,
        });
      }
      if (att.generator_ownership === "THIRD_PARTY" && ppaCount === 0) {
        flags.push({
          id: "CONTRA_BTM_UNCONTRACTED_SUPPLY",
          severity: "DEAL_KILLER",
          message:
            `Generating asset is third-party owned but no supply contract is recorded — the plant's entire ` +
            `power input is uncontracted. A direct line between separate legal entities is a renewables PPA ` +
            `by RED III's definition; the contract is required whatever the physical topology.`,
          involvedFields: ["ppas", "generator_ownership"],
          detectedAt: now,
        });
      }
      if (att.generator_ownership === "AFFILIATE" && ppaCount === 0) {
        flags.push({
          id: "CONTRA_BTM_AFFILIATE_SUPPLY",
          severity: "WARN",
          message:
            `Generating asset sits in an affiliate entity with no supply contract recorded. Lenders will ` +
            `treat the intercompany power price as related-party and stress it; arm's-length transfer-pricing ` +
            `evidence or a documented intercompany PPA is required to hold the LCOF assumption.`,
          involvedFields: ["ppas", "generator_ownership"],
          detectedAt: now,
        });
      }
    }
  } else if (ei?.power_model) {
    const ppas = ei.ppas ?? [];
    const signed = ppas.filter((x) => x.status === "SIGNED");
    // Milestone proximity: a development-phase gap stops being "normal" when
    // declared construction start is this year or next — capital is about to
    // be committed against an unhedged premise.
    const currentYear = new Date().getFullYear();
    const constructionImminent =
      p.timeline?.construction_start_year != null &&
      p.timeline.construction_start_year <= currentYear + 1;
    if (ppas.length === 0) {
      flags.push({
        id: "CONTRA_GRID_NO_PPA",
        // Normal gap in early development; a deal-killer once capital is at
        // work OR when the declared construction start is imminent.
        severity:
          p.status === "development" && !constructionImminent
            ? "WARN"
            : "DEAL_KILLER",
        message:
          `Power model is ${ei.power_model} but no PPA is recorded — grid electricity ` +
          `price is unhedged (dominant OPEX) and RFNBO/45V additionality cannot be evidenced. ` +
          `On-grid requires ≥1 PPA.` +
          (p.status === "development" && constructionImminent
            ? ` Escalated: declared construction start ${p.timeline!.construction_start_year} is imminent.`
            : ""),
        involvedFields: ["power_model", "ppas"],
        detectedAt: now,
      });
    } else if (
      signed.length === 0 &&
      (p.status === "construction" || p.status === "operating")
    ) {
      flags.push({
        id: "CONTRA_GRID_PPA_UNSIGNED",
        severity: "DEAL_KILLER",
        message:
          `${ppas.length} PPA(s) recorded but none SIGNED at ${p.status} stage — ` +
          `term sheets do not hedge power price for lender models.`,
        involvedFields: ["ppas"],
        detectedAt: now,
      });
    }

    // PPA quality — existence is not sufficiency. Mechanical checks on data
    // GEX already holds; deeper tests (counterparty credit, bidding zone,
    // temporal correlation) remain evidence items until structured data exists.
    // Coverage target: GRID_CONNECTED = full plant load; HYBRID = only the
    // declared grid-imported share (the BTM share needs no PPA).
    const coverageTargetMw =
      ei.power_model === "HYBRID" && ei.grid_import_mw != null
        ? ei.grid_import_mw
        : ei.power_model === "GRID_CONNECTED"
          ? ei.power_mw
          : 0;
    if (signed.length > 0 && coverageTargetMw > 0) {
      const signedMw = signed.reduce((sum, x) => sum + (x.volume_mw || 0), 0);
      const coveragePct = Math.round((signedMw / coverageTargetMw) * 100);
      if (signedMw < coverageTargetMw) {
        flags.push({
          id: "CONTRA_PPA_COVERAGE_GAP",
          severity: p.status === "development" ? "WARN" : "DEAL_KILLER",
          message:
            `Signed PPA volume covers ${signedMw} of ${coverageTargetMw} MW ` +
            `${ei.power_model === "HYBRID" ? "grid-imported load" : "plant load"} (${coveragePct}%) — ` +
            `the uncovered balance is unhedged grid exposure and weakens RFNBO/45V hourly matching.`,
          involvedFields: [
            "ppas",
            ei.power_model === "HYBRID" ? "grid_import_mw" : "power_mw",
          ],
          detectedAt: now,
        });
      }
    }
    // Internal sleeved supply (prosumer structure): normal for a balance-sheet
    // owner consuming its own generation; a related-party pricing risk when
    // external lenders are being asked to rely on it.
    const internalSigned = signed.filter(
      (x) => x.counterparty_type === "INTERNAL_AFFILIATE",
    );
    if (
      internalSigned.length > 0 &&
      (p.financing_model ?? "PROJECT_FINANCE") !== "BALANCE_SHEET"
    ) {
      flags.push({
        id: "CONTRA_PPA_RELATED_PARTY",
        severity: "WARN",
        message:
          `${internalSigned.length} signed PPA(s) are internal-affiliate sleeved supply on a ` +
          `project-financed structure — lenders will treat the power price as related-party. ` +
          `Arm's-length transfer-pricing evidence or a market PPA is required.`,
        involvedFields: ["ppas"],
        detectedAt: now,
      });
    }
    if (signed.length > 0) {
      // Tenor screen: short PPA against a debt-funded project. True tenor
      // matching needs the debt tenor (PPA Tenor vs Debt Comparison evidence);
      // this is a screening check against the registered capital stack.
      const hasSeniorDebt = p.bankability.capital_status.some(
        (c) =>
          c.type === "SENIOR_DEBT_COMMITMENT" || c.type === "DEBT_DRAWDOWN",
      );
      const maxTenor = Math.max(...signed.map((x) => x.tenor_years || 0));
      if (hasSeniorDebt && maxTenor > 0 && maxTenor < 10) {
        flags.push({
          id: "CONTRA_PPA_TENOR_SHORT",
          severity: "WARN",
          message:
            `Longest signed PPA tenor is ${maxTenor}y against a senior-debt-funded project — ` +
            `likely shorter than debt tenor. Confirm via PPA Tenor vs Debt Comparison evidence (G1).`,
          involvedFields: ["ppas"],
          detectedAt: now,
        });
      }
    }
  }
  // Declared off-grid but power source says "grid" — incoherent data.
  if (ei?.power_model === "OFF_GRID_BTM" && ei.source === "grid") {
    flags.push({
      id: "CONTRA_OFFGRID_GRID_SOURCE",
      severity: "WARN",
      message:
        'Power model OFF_GRID_BTM contradicts power source "grid" — one of the two is wrong.',
      involvedFields: ["power_model", "power_source"],
      detectedAt: now,
    });
  }

  return flags;
}

// ── Verification Pill ───────────────────────────────────────────────────────

function VerificationPill({
  state,
  isDraft,
  source,
  lastVerifiedAt,
  onConfirm,
}: {
  state: VerificationState;
  isDraft?: boolean;
  source?: string;
  lastVerifiedAt?: string;
  onConfirm?: () => void;
}) {
  const effectiveState: VerificationState = isDraft ? "SUBMITTED" : state;
  const canConfirm =
    !isDraft && effectiveState !== "CONFIRMED" && effectiveState !== "AUDITED";

  const tip = [
    isDraft
      ? "Modified by user — verification required"
      : canConfirm
        ? "Click to confirm client-reviewed data"
        : effectiveState,
    source ? `Source: ${source}` : null,
    lastVerifiedAt ? `Verified: ${fmtDate(lastVerifiedAt)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <span
      title={tip}
      onClick={canConfirm ? onConfirm : undefined}
      className={`${CHIP_BASE} border border-l-2 ${
        effectiveState === "AUDITED"
          ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
          : effectiveState === "CONFIRMED"
            ? "border-slate-300 border-l-emerald-600 bg-white text-slate-700 dark:bg-slate-950 dark:text-slate-200"
            : effectiveState === "SUBMITTED"
              ? "border-slate-300 border-l-sky-600 bg-[#F8FAFC] text-sky-800 dark:bg-slate-900 dark:text-sky-300"
              : "border-slate-300 border-l-slate-400 bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400"
      } ${canConfirm ? "cursor-pointer hover:border-slate-500 hover:bg-slate-100" : "cursor-default"}`}
    >
      {effectiveState}
    </span>
  );
}

// ── Inline Editable Field ────────────────────────────────────────────────────

function InlineField({
  fieldKey,
  label,
  value,
  unit,
  verification,
  source,
  lastVerifiedAt,
  type = "text",
  options,
  highlighted,
  isDraft,
  onConfirm,
  onChange,
}: {
  fieldKey: string;
  label: string;
  value: string | number;
  unit?: string;
  verification: VerificationState;
  source?: string;
  lastVerifiedAt?: string;
  type?: "text" | "number" | "year" | "date" | "select" | "textarea";
  options?: readonly string[];
  highlighted?: boolean;
  isDraft?: boolean;
  onConfirm?: (key: string) => void;
  onChange: (key: string, val: string | number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(value));
  const inputRef = useRef<
    HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
  >(null);

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      if ("select" in inputRef.current && type !== "select") {
        (inputRef.current as HTMLInputElement).select();
      }
    }
  }, [editing, type]);

  const commit = useCallback(() => {
    setEditing(false);
    const parsed = type === "number" ? parseFloat(draft) || 0 : draft;
    if (parsed !== value) onChange(fieldKey, parsed);
  }, [draft, fieldKey, onChange, type, value]);

  const cancel = useCallback(() => {
    setEditing(false);
    setDraft(String(value));
  }, [value]);

  const handleKey = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") cancel();
      if (e.key === "Enter" && type !== "textarea") commit();
    },
    [cancel, commit, type],
  );

  const displayValue =
    type === "number"
      ? fmtNum(value as number)
      : type === "year"
        ? fmtYear(value)
        : type === "date"
          ? fmtDate(String(value))
          : String(value);
  const valueTone =
    verification === "UNVERIFIED" && !isDraft ? "opacity-60" : "";

  // Textarea keeps a full-row layout.
  if (type === "textarea") {
    return (
      <div
        className={`col-span-full grid grid-cols-1 gap-0.5 border border-transparent px-1 py-[2px] transition-colors ${
          highlighted
            ? "border-slate-300 bg-[#F8FAFC] dark:bg-slate-900/40"
            : "hover:bg-[#F8FAFC]"
        }`}
      >
        <div className={DATA_ROW_GRID}>
          <span className="w-[112px] shrink-0 text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
            {label}
          </span>
          <span />
          <VerificationPill
            state={verification}
            isDraft={isDraft}
            source={source}
            lastVerifiedAt={lastVerifiedAt}
            onConfirm={() => onConfirm?.(fieldKey)}
          />
          <span />
        </div>
        {editing ? (
          <textarea
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            title={label}
            aria-label={label}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={handleKey}
            rows={3}
            className="font-mono text-[11px] leading-tight bg-white border border-slate-400 rounded-none px-1 py-[2px] text-[var(--text-primary)] focus:outline-none w-full resize-y"
          />
        ) : (
          <div
            onClick={() => setEditing(true)}
            className={`font-mono text-[11px] leading-tight text-[var(--text-primary)] cursor-text hover:bg-slate-100 px-1 py-[2px] transition-colors ${valueTone}`}
            title="Click to edit"
          >
            {displayValue || "—"}
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      className={`${DATA_ROW_GRID} border border-transparent px-1 py-[2px] transition-colors ${
        highlighted
          ? "border-slate-300 bg-[#F8FAFC] dark:bg-slate-900/40"
          : "hover:bg-[#F8FAFC]"
      }`}
    >
      <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)] whitespace-nowrap">
        {label}
      </span>

      {editing ? (
        type === "select" && options ? (
          <select
            ref={inputRef as React.RefObject<HTMLSelectElement>}
            title={label}
            aria-label={label}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
            }}
            onBlur={commit}
            onKeyDown={handleKey}
            className="justify-self-end font-mono text-[11px] tabular-nums bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] focus:outline-none"
          >
            {options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        ) : (
          <input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            title={label}
            aria-label={label}
            type={
              type === "date"
                ? "date"
                : type === "number" || type === "year"
                  ? "number"
                  : "text"
            }
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={handleKey}
            className="justify-self-end font-mono text-[11px] tabular-nums bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] text-right focus:outline-none w-auto max-w-[180px]"
          />
        )
      ) : (
        <span
          onClick={() => setEditing(true)}
          className={`justify-self-end max-w-full overflow-hidden text-ellipsis font-mono text-[11px] tabular-nums font-semibold text-[var(--text-primary)] text-right cursor-text hover:bg-slate-100 px-0.5 transition-colors whitespace-nowrap ${valueTone}`}
          title={
            displayValue ? `${displayValue} — click to edit` : "Click to edit"
          }
        >
          {displayValue || "—"}
        </span>
      )}

      <VerificationPill
        state={verification}
        isDraft={isDraft}
        source={source}
        lastVerifiedAt={lastVerifiedAt}
        onConfirm={() => onConfirm?.(fieldKey)}
      />

      {unit ? (
        <span className="justify-self-start text-[9px] font-mono text-[var(--text-muted)] border border-slate-300 bg-[#F8FAFC] px-0.5 select-none leading-none py-[1px]">
          {unit}
        </span>
      ) : (
        <span />
      )}
    </div>
  );
}

// ── Location Pair ────────────────────────────────────────────────────────────

function LocationPair({
  location,
  country,
  lat,
  lng,
  locationVerification,
  latVerification,
  locationDraft,
  countryDraft,
  latDraft,
  lngDraft,
  onConfirm,
  onChange,
}: {
  location: string | number;
  country: string | number;
  lat: string | number;
  lng: string | number;
  locationVerification: VerificationState;
  latVerification: VerificationState;
  locationDraft?: boolean;
  countryDraft?: boolean;
  latDraft?: boolean;
  lngDraft?: boolean;
  onConfirm?: (key: string) => void;
  onChange: (key: string, val: string | number) => void;
}) {
  const [editingPlace, setEditingPlace] = useState(false);
  const [editingCoords, setEditingCoords] = useState(false);
  const [placeDraft, setPlaceDraft] = useState({
    location: String(location),
    country: String(country),
  });
  const [coordDraft, setCoordDraft] = useState({
    lat: String(lat),
    lng: String(lng),
  });
  const placeRef = useRef<HTMLDivElement>(null);
  const coordsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPlaceDraft({ location: String(location), country: String(country) });
  }, [location, country]);

  useEffect(() => {
    setCoordDraft({ lat: String(lat), lng: String(lng) });
  }, [lat, lng]);

  const commitPlace = useCallback(() => {
    setEditingPlace(false);
    if (placeDraft.location !== String(location))
      onChange("location", placeDraft.location);
    if (placeDraft.country !== String(country))
      onChange("country", placeDraft.country);
  }, [country, location, onChange, placeDraft]);

  const commitCoords = useCallback(() => {
    setEditingCoords(false);
    const nextLat = parseFloat(coordDraft.lat) || 0;
    const nextLng = parseFloat(coordDraft.lng) || 0;
    if (nextLat !== Number(lat)) onChange("lat", nextLat);
    if (nextLng !== Number(lng)) onChange("lng", nextLng);
  }, [coordDraft, lat, lng, onChange]);

  return (
    <div className="col-span-full grid grid-cols-1 xl:grid-cols-2 gap-x-6 gap-y-0">
      <div
        ref={placeRef}
        onBlur={(e) => {
          if (!placeRef.current?.contains(e.relatedTarget as Node | null))
            commitPlace();
        }}
        className={`${DATA_ROW_GRID} border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]`}
      >
        <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
          Location
        </span>
        {editingPlace ? (
          <div className="justify-self-end flex flex-wrap items-center gap-1">
            <input
              title="Location"
              aria-label="Location"
              value={placeDraft.location}
              onChange={(e) =>
                setPlaceDraft((prev) => ({ ...prev, location: e.target.value }))
              }
              onKeyDown={(e) => {
                if (e.key === "Enter") commitPlace();
              }}
              className="font-mono text-[11px] bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] focus:outline-none max-w-[180px]"
              autoFocus
            />
            <span className="font-mono text-[11px] text-[var(--text-muted)]">
              ,
            </span>
            <input
              title="Country"
              aria-label="Country"
              value={placeDraft.country}
              onChange={(e) =>
                setPlaceDraft((prev) => ({ ...prev, country: e.target.value }))
              }
              onKeyDown={(e) => {
                if (e.key === "Enter") commitPlace();
              }}
              className="font-mono text-[11px] bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] focus:outline-none w-16"
            />
          </div>
        ) : (
          <div
            onClick={() => setEditingPlace(true)}
            className={`justify-self-end font-mono text-[11px] font-semibold text-[var(--text-primary)] cursor-text hover:bg-slate-100 px-0.5 transition-colors ${
              locationVerification === "UNVERIFIED" &&
              !locationDraft &&
              !countryDraft
                ? "opacity-60"
                : ""
            }`}
            title="Click to edit location"
          >
            {location || "—"}, {country || "—"}
          </div>
        )}
        <VerificationPill
          state={locationVerification}
          isDraft={locationDraft || countryDraft}
          onConfirm={() => {
            onConfirm?.("location");
            onConfirm?.("country");
          }}
        />
        <span />
      </div>
      <div
        ref={coordsRef}
        onBlur={(e) => {
          if (!coordsRef.current?.contains(e.relatedTarget as Node | null))
            commitCoords();
        }}
        className={`${DATA_ROW_GRID} border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]`}
      >
        <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
          Coordinates
        </span>
        {editingCoords ? (
          <div className="justify-self-end flex items-center gap-1 whitespace-nowrap">
            <input
              type="number"
              title="Latitude"
              aria-label="Latitude"
              value={coordDraft.lat}
              onChange={(e) =>
                setCoordDraft((prev) => ({ ...prev, lat: e.target.value }))
              }
              onKeyDown={(e) => {
                if (e.key === "Enter") commitCoords();
              }}
              className="font-mono text-[11px] tabular-nums bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] text-right focus:outline-none w-20"
              autoFocus
            />
            <span className="font-mono text-[11px] text-[var(--text-muted)]">
              &deg; lat /
            </span>
            <input
              type="number"
              title="Longitude"
              aria-label="Longitude"
              value={coordDraft.lng}
              onChange={(e) =>
                setCoordDraft((prev) => ({ ...prev, lng: e.target.value }))
              }
              onKeyDown={(e) => {
                if (e.key === "Enter") commitCoords();
              }}
              className="font-mono text-[11px] tabular-nums bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] text-right focus:outline-none w-24"
            />
            <span className="font-mono text-[11px] text-[var(--text-muted)]">
              &deg; lng
            </span>
          </div>
        ) : (
          <div
            onClick={() => setEditingCoords(true)}
            className={`justify-self-end font-mono text-[11px] font-semibold tabular-nums text-[var(--text-primary)] whitespace-nowrap cursor-text hover:bg-slate-100 px-0.5 transition-colors ${
              latVerification === "UNVERIFIED" && !latDraft && !lngDraft
                ? "opacity-60"
                : ""
            }`}
            title="Click to edit coordinates"
          >
            {fmtLat(lat)} / {fmtLng(lng)}
          </div>
        )}
        <VerificationPill
          state={latVerification}
          isDraft={latDraft || lngDraft}
          onConfirm={() => {
            onConfirm?.("lat");
            onConfirm?.("lng");
          }}
        />
        <span />
      </div>
    </div>
  );
}

// ── Capacity Field ───────────────────────────────────────────────────────────

function CapacityField({
  valueMtpd,
  unit,
  verification,
  isDraft,
  onUnitChange,
  onConfirm,
  onChange,
}: {
  valueMtpd: string | number;
  unit: CapacityUnit;
  verification: VerificationState;
  isDraft?: boolean;
  onUnitChange: (unit: CapacityUnit) => void;
  onConfirm?: (key: string) => void;
  onChange: (key: string, val: string | number) => void;
}) {
  const mtpd = Number(valueMtpd) || 0;
  const displayValue = capacityDisplayValue(mtpd, unit);
  const [editing, setEditing] = useState(false);
  const [draftValue, setDraftValue] = useState(String(displayValue));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setDraftValue(String(displayValue));
  }, [displayValue]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const commit = useCallback(() => {
    setEditing(false);
    const parsed = parseFloat(draftValue) || 0;
    const nextMtpd = capacityInputToMtpd(parsed, unit);
    if (nextMtpd !== mtpd) onChange("capacity_mtpd", nextMtpd);
  }, [draftValue, mtpd, onChange, unit]);

  return (
    <div
      className={`${DATA_ROW_GRID} border border-transparent px-1 py-[2px] transition-colors hover:bg-[#F8FAFC]`}
    >
      <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)] whitespace-nowrap">
        Capacity
      </span>
      {editing ? (
        <input
          ref={inputRef}
          title="Capacity"
          aria-label="Capacity"
          type="number"
          value={draftValue}
          onChange={(e) => setDraftValue(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
          }}
          className="justify-self-end font-mono text-[11px] tabular-nums bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] text-right focus:outline-none w-28"
        />
      ) : (
        <span
          onClick={() => setEditing(true)}
          className="justify-self-end font-mono text-[11px] tabular-nums font-semibold text-[var(--text-primary)] text-right cursor-text hover:bg-slate-100 px-0.5 transition-colors whitespace-nowrap"
          title="Click to edit capacity"
        >
          {fmtNum(displayValue)}
        </span>
      )}
      <VerificationPill
        state={verification}
        isDraft={isDraft}
        onConfirm={() => onConfirm?.("capacity_mtpd")}
      />
      <select
        value={unit}
        onChange={(e) => onUnitChange(e.target.value as CapacityUnit)}
        className="justify-self-start w-full font-mono text-[9px] text-[var(--text-muted)] border border-slate-300 bg-[#F8FAFC] px-0.5 py-0 leading-none focus:outline-none"
        title="Capacity unit"
      >
        {CAPACITY_UNITS.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

// ── Detail Links ─────────────────────────────────────────────────────────────

/**
 * State chip rendered on the right side of the link cell.
 *  - `tone` drives the left border colour band (Bloomberg-style)
 *  - `text` is short, mono, uppercase — 2-3 tokens
 * Used to surface data freshness for telemetry / cost-basis class / wiring state.
 */
type ChipTone = "live" | "warn" | "none" | "info";

function StateChip({
  text,
  tone,
  title,
}: {
  text: string;
  tone: ChipTone;
  title?: string;
}) {
  const cls =
    tone === "live"
      ? "border-l-emerald-600 text-emerald-800 dark:text-emerald-300"
      : tone === "warn"
        ? "border-l-amber-600  text-amber-800  dark:text-amber-300"
        : tone === "info"
          ? "border-l-sky-600    text-sky-800    dark:text-sky-300"
          : "border-l-slate-400  text-slate-500  dark:text-slate-400";
  return (
    <span
      title={title}
      className={`inline-flex h-[15px] min-w-[76px] items-center justify-center border border-l-2 border-slate-300 bg-white dark:bg-slate-950 px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none whitespace-nowrap ${cls}`}
    >
      {text}
    </span>
  );
}

/**
 * Access chip — answers "may this user open this tool", a different axis from
 * the evidence state of a claim. Same geometry as VerificationPill so the right
 * edge stays coherent, but deliberately NOT the same visual language: evidence
 * chips carry a coloured left accent bar on white, access chips carry a tinted
 * body and no accent. That keeps emerald meaning "confirmed" and nothing else.
 */
function AccessChip({
  hasAccess,
  reason,
}: {
  hasAccess: boolean;
  reason?: string;
}) {
  return (
    <span
      title={reason}
      className={`${CHIP_BASE} gap-[3px] border ${
        hasAccess
          ? "border-slate-300 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300"
          : "border-amber-300 bg-amber-50 text-amber-800 cursor-help dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-300"
      }`}
    >
      {!hasAccess && (
        <svg
          viewBox="0 0 8 10"
          className="h-[7px] w-[6px] shrink-0"
          aria-hidden="true"
        >
          <path
            d="M2 4V2.6a2 2 0 0 1 4 0V4"
            stroke="currentColor"
            strokeWidth="1.1"
            fill="none"
          />
          <rect x="1" y="4" width="6" height="5" fill="currentColor" />
        </svg>
      )}
      {hasAccess ? "ENABLED" : "RESTRICTED"}
    </span>
  );
}

/**
 * Derive a human-readable restriction reason from a MenuItem's visibility rules.
 * Compresses the rule set to the smallest descriptor a user can act on.
 * (Hidalgo: lower entropy than the bare word "Restricted".)
 */
function restrictionReason(item: MenuItem | undefined): string {
  if (!item) return "Path not registered in nav architecture";
  const rules = item.visible_to;
  if (rules.length === 0) return "No visibility rule defined";
  const cts = new Set<string>();
  const fns = new Set<string>();
  const sts = new Set<string>();
  for (const r of rules) {
    if (r.company_type && r.company_type !== "ALL") cts.add(r.company_type);
    if (r.function && r.function !== "ALL") fns.add(r.function);
    if (r.service_type && r.service_type !== "ALL") sts.add(r.service_type);
  }
  const parts: string[] = [];
  if (cts.size) parts.push(`company_type ∈ {${Array.from(cts).join(", ")}}`);
  if (fns.size)
    parts.push(`business_function ∈ {${Array.from(fns).join(", ")}}`);
  if (sts.size) parts.push(`service_type ∈ {${Array.from(sts).join(", ")}}`);
  return parts.length
    ? `Requires ${parts.join(" or ")}`
    : "Available to all roles (check session)";
}

/**
 * Append `?project=<id>` so the destination can hydrate to the same project
 * the user was editing. Eliminates context loss on navigation.
 */
function withProject(path: string, projectId: string): string {
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}project=${encodeURIComponent(projectId)}`;
}

function DetailLinkRow({
  kind,
  path,
  projectId,
  hasAccess,
  description,
  chip,
}: {
  kind: string; // column-1 action verb e.g. "COST BASIS"
  path: string; // canonical route
  projectId: string; // active project — appended as ?project=
  hasAccess: boolean;
  description: string; // gloss in column 2 after the link
  chip?: { text: string; tone: ChipTone; title?: string };
}) {
  const item = menuItemForPath(path);
  // Canonical label sourced from menuArchitecture — single source of truth.
  const value = item?.label ?? path;
  const target = withProject(path, projectId);
  const reason = !hasAccess ? restrictionReason(item) : undefined;

  return (
    <div className="col-span-full grid grid-cols-[112px_minmax(0,1fr)_78px] items-center gap-1 border border-transparent px-1 py-[2px] transition-colors hover:bg-[#F8FAFC]">
      <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)] whitespace-nowrap">
        <span aria-hidden className="mr-[3px] text-slate-400">
          &rsaquo;
        </span>
        {kind}
      </span>
      <div className="min-w-0 flex items-center gap-2">
        {hasAccess ? (
          <Link
            to={target}
            className="font-mono text-[11px] font-semibold text-slate-900 underline decoration-slate-300 underline-offset-2 hover:decoration-slate-900 dark:text-slate-100 truncate"
            title={`${value} — opens with project=${projectId}`}
          >
            {value}
          </Link>
        ) : (
          <span
            className="font-mono text-[11px] font-semibold text-slate-400 truncate cursor-help"
            title={reason}
          >
            {value}
          </span>
        )}
        <span className="font-mono text-[10px] text-[var(--text-muted)] truncate">
          {description}
        </span>
        {chip && (
          <StateChip text={chip.text} tone={chip.tone} title={chip.title} />
        )}
      </div>
      <AccessChip hasAccess={hasAccess} reason={reason} />
    </div>
  );
}

/**
 * Banded container for a section's navigation rows.
 *
 * Data rows answer "what is this value and how well is it evidenced"; tool rows
 * answer "where do I go to work on it". They are two different row species and
 * used to share the data grid with no signal, which read as broken alignment
 * rather than as a deliberate change of register. The hairline makes the break
 * explicit, so the tool rows' full-width layout is legible as intent.
 */
function ToolGroup({ children }: { children: React.ReactNode }) {
  return (
    <div className="col-span-full mt-[3px] border-t border-slate-200 pt-[3px] dark:border-slate-800">
      {children}
    </div>
  );
}

// ── Per-project state derivations for chips ──────────────────────────────────

function costBasisChip(p: CustomerProject): {
  text: string;
  tone: ChipTone;
  title?: string;
} {
  // Cost-basis class derived from project phase — until development_packages
  // AACE history is wired to the frontend.
  const phase = String((p as any).phase || "").toUpperCase();
  if (
    phase.includes("FEED 3") ||
    phase.includes("CLASS 3") ||
    phase.includes("FEED-3")
  )
    return {
      text: "AACE 3",
      tone: "live",
      title: "FEED Class 3 cost basis on file",
    };
  if (phase.includes("FEED"))
    return {
      text: "AACE 4",
      tone: "info",
      title: "FEED-stage cost basis (Class 4)",
    };
  if (phase.includes("PRE-FEED") || phase.includes("CONCEPT"))
    return {
      text: "AACE 5",
      tone: "warn",
      title: "Pre-FEED estimate (Class 5)",
    };
  return {
    text: "ESTIMATE",
    tone: "warn",
    title: "No AACE class on file — estimate only",
  };
}

function certificationChip(p: CustomerProject): {
  text: string;
  tone: ChipTone;
  title?: string;
} {
  const certs = p.certifications ?? [];
  if (certs.length === 0)
    return { text: "NONE", tone: "none", title: "No certifications declared" };
  const active = certs.filter((c) => c.status === "ACTIVE").length;
  const review = certs.filter((c) => c.status === "UNDER_REVIEW").length;
  const text = `${active}/${certs.length} ACTIVE`;
  const tone: ChipTone =
    active === certs.length
      ? "live"
      : active > 0
        ? "info"
        : review > 0
          ? "warn"
          : "none";
  return {
    text,
    tone,
    title: `${active} active, ${review} under review, ${certs.length - active - review} other`,
  };
}

function telemetryChip(p: CustomerProject): {
  text: string;
  tone: ChipTone;
  title?: string;
} {
  // Telemetry availability strictly follows construction lifecycle.
  switch (p.status) {
    case "operating":
      return {
        text: "LIVE",
        tone: "live",
        title: "Telemetry expected from registered OT gateways",
      };
    case "commissioning":
      return {
        text: "INTERMITTENT",
        tone: "info",
        title: "Commissioning runs only — gaps expected",
      };
    case "construction":
      return { text: "NO FEED", tone: "warn", title: "No telemetry until COD" };
    default:
      return {
        text: "PRE-COD",
        tone: "none",
        title: "Pre-COD project — no telemetry contracted",
      };
  }
}

function NarrativeSourceLine({
  intelligence,
}: {
  intelligence: ProjectProfileIntelligence | null;
}) {
  if (!intelligence) return null;

  return (
    <div className="col-span-full grid grid-cols-[112px_minmax(0,1fr)_78px] items-center gap-1 border border-transparent px-1 py-[2px]">
      <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)] whitespace-nowrap">
        Source
      </span>
      <span className="font-mono text-[10px] text-[var(--text-muted)] truncate">
        {intelligence.backend_store} · {intelligence.record_id} ·{" "}
        {intelligence.linked_records.length} linked records
      </span>
      <span
        className={`${CHIP_BASE} border border-l-2 border-slate-300 border-l-sky-600 bg-[#F8FAFC] text-sky-800`}
      >
        BACKEND
      </span>
    </div>
  );
}

// ── Rendered narrative block (Option A — derived from structured fields) ───
/**
 * Replaces the legacy free-text narrative textarea.
 *
 * Doctrine:
 *  - Structured fields are the source of truth (Hidalgo causal compression).
 *  - The prose is a deterministic render: same fields → same string, always.
 *  - User cannot edit the prose; they edit the structured fields, which appear
 *    as field labels next to each clause and link to where they live.
 *
 * Backward compatibility:
 *  - When the project has none of the narrative-feeding fields, we fall back
 *    to the legacy `descriptionFallback` text so older seed records still render.
 *  - A small banner names whichever mode is in use, so reviewers know which
 *    source the prose came from.
 */
function RenderedNarrativeBlock({
  rendered,
  fallbackText,
  structuredFieldCount,
}: {
  rendered: RenderedNarrative;
  fallbackText: string;
  structuredFieldCount: number;
}) {
  const usingStructured = rendered.clauses.length > 0;
  const text = usingStructured ? rendered.text : fallbackText;

  return (
    <div className="col-span-full space-y-1.5">
      {/* Banner — names the source of truth */}
      <div className="flex items-center justify-between gap-2 border border-slate-200 bg-slate-50 px-2 py-1 dark:border-slate-800 dark:bg-slate-900">
        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-slate-700 dark:text-slate-300">
          {usingStructured
            ? `Generated from ${structuredFieldCount} structured fields — edit those instead`
            : `Legacy free-text — no structured fields yet on this project`}
        </span>
        <span
          className={`inline-flex h-[15px] items-center justify-center border border-l-2 border-slate-300 bg-white dark:bg-slate-950 px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none whitespace-nowrap ${
            usingStructured
              ? "border-l-emerald-600 text-emerald-800 dark:text-emerald-300"
              : "border-l-amber-600 text-amber-800 dark:text-amber-300"
          }`}
          title={
            usingStructured
              ? "Every clause traces to a field path. Edit fields to change prose."
              : "Project has not been migrated to structured narrative fields yet."
          }
        >
          {usingStructured ? "DERIVED" : "FREE TEXT"}
        </span>
      </div>

      {/* Rendered prose — read-only */}
      <p className="font-serif text-[12px] leading-relaxed text-[var(--text-primary)] px-1">
        {text || (
          <span className="italic text-[var(--text-muted)]">
            No narrative — add structured fields.
          </span>
        )}
      </p>

      {/* Clause → field lineage (only in DERIVED mode) */}
      {usingStructured && (
        <details className="px-1">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)] hover:text-[var(--brand)]">
            Clause → field lineage ({rendered.clauses.length} clauses)
          </summary>
          <table className="mt-1 w-full border border-slate-200 dark:border-slate-800 text-[11px]">
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {rendered.clauses.map((c, i) => (
                <tr key={i}>
                  <td className="px-2 py-1 text-[var(--text-secondary)] align-top">
                    {c.text}.
                  </td>
                  <td className="px-2 py-1 font-mono text-[10px] text-[var(--text-muted)] whitespace-nowrap align-top text-right">
                    {c.sources.join("  ·  ")}
                  </td>
                </tr>
              ))}
              {rendered.missing_fields.length > 0 && (
                <tr>
                  <td className="px-2 py-1 italic text-amber-700 dark:text-amber-400">
                    Missing — would extend the prose if filled
                  </td>
                  <td className="px-2 py-1 font-mono text-[10px] text-amber-700 dark:text-amber-400 whitespace-nowrap text-right">
                    {rendered.missing_fields.join("  ·  ")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export function ProjectProfilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const project = useMemo(
    () => CUSTOMER_PROJECTS.find((p) => p.id === id),
    [id],
  );

  if (!project) {
    return (
      <div className="max-w-3xl mx-auto py-12 text-center">
        <p className="text-sm font-mono text-[var(--text-muted)]">
          No project with ID "{id}".
        </p>
        <button
          onClick={() => navigate("/projects")}
          className="mt-2 text-xs font-semibold text-[var(--brand)] hover:underline"
        >
          Back to Projects
        </button>
      </div>
    );
  }

  return (
    <ProfileWorkbench project={project} onBack={() => navigate("/projects")} />
  );
}

function ProfileWorkbench({
  project,
  onBack,
}: {
  project: CustomerProject;
  onBack: () => void;
}) {
  const { role, authSession } = useUserRole();
  const verifiedFields = useMemo(() => buildVerifiedFields(project), [project]);

  // Editable state — keyed by field name
  const [edits, setEdits] = useState<Record<string, string | number>>({});
  const [verificationOverrides, setVerificationOverrides] = useState<
    Record<string, VerificationState>
  >({});
  const [capacityUnit, setCapacityUnit] = useState<CapacityUnit>("MTPD");
  const [profileIntelligence, setProfileIntelligence] =
    useState<ProjectProfileIntelligence | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);

  const fieldVal = (key: string) =>
    key in edits
      ? edits[key]
      : ((verifiedFields[key]?.value as string | number) ?? "");
  const isDraft = (key: string) => key in edits;

  const handleChange = useCallback((key: string, val: string | number) => {
    setEdits((prev) => ({ ...prev, [key]: val }));
    setVerificationOverrides((prev) => ({ ...prev, [key]: "SUBMITTED" }));
    setDirty(true);
    setSaved(false);
  }, []);

  const handleConfirm = useCallback((key: string) => {
    setVerificationOverrides((prev) => ({ ...prev, [key]: "CONFIRMED" }));
    setDirty(true);
    setSaved(false);
  }, []);

  const handleSave = useCallback(() => {
    setDirty(false);
    setSaved(true);
  }, []);

  useEffect(() => {
    const token = authSession?.token;
    if (!token) return;

    let cancelled = false;
    fetch(`/api/v1/projects/${project.id}/profile-intelligence`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: ProjectProfileIntelligence | null) => {
        if (!cancelled) setProfileIntelligence(data);
      })
      .catch(() => {
        if (!cancelled) setProfileIntelligence(null);
      });

    return () => {
      cancelled = true;
    };
  }, [authSession?.token, project.id]);

  // Cmd+S / Ctrl+S global save
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (dirty) handleSave();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [dirty, handleSave]);

  // Effective project — raw seed values overlaid with the user's in-flight edits.
  // Contradictions re-evaluate against THIS so a currency change clears the FX
  // warn immediately, not on next page load.
  //
  // Nested groups (energy_input, electrolyser, timeline) are rebuilt whole from
  // the current object rather than shallow-merged at the top level: a top-level
  // spread would replace the group and drop the sibling keys the rules read —
  // notably energy_input.ppas, which every PPA rule depends on.
  const effectiveProject = useMemo<CustomerProject>(() => {
    const overlay: Partial<CustomerProject> = {};
    const has = (k: string) => k in edits;
    const str = (k: string) => String(edits[k]);
    const num = (k: string) => Number(edits[k]);

    // ── Flat fields ──
    if (has("name")) overlay.name = str("name");
    if (has("molecule"))
      overlay.molecule = edits.molecule as CustomerProject["molecule"];
    if (has("owner_company")) overlay.owner_company = str("owner_company");
    if (has("associated_companies"))
      overlay.associated_companies = str("associated_companies")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    if (has("location")) overlay.location = str("location");
    if (has("country")) overlay.country = str("country");
    if (has("lat")) overlay.lat = num("lat");
    if (has("lng")) overlay.lng = num("lng");
    if (has("capacity_mtpd")) overlay.capacity_mtpd = num("capacity_mtpd");
    if (has("capacity_kt_yr")) overlay.capacity_kt_yr = num("capacity_kt_yr");
    if (has("capex_eur")) overlay.capex_eur = num("capex_eur");
    if (has("capex_currency"))
      overlay.capex_currency =
        edits.capex_currency as CustomerProject["capex_currency"];
    if (has("status"))
      overlay.status = edits.status as CustomerProject["status"];
    if (has("phase")) overlay.phase = str("phase");
    if (has("completion_date"))
      overlay.completion_date = str("completion_date");
    if (has("description")) overlay.description = str("description");

    // ── Nested: energy_input (+ its own nested power_attribution) ──
    // power_mw and source are required on the group, so they fall back to the
    // current values (or type defaults) when only a sibling was edited.
    const attrKeys = [
      "generator_ownership",
      "generator_cod_year",
      "generator_aid",
      "grid_import_metering",
      "certificate_matching",
    ];
    const attrEdited = attrKeys.some(has);
    if (
      has("power_mw") ||
      has("power_source") ||
      has("power_model") ||
      attrEdited
    ) {
      const current = project.energy_input;
      const attr = current?.power_attribution;
      overlay.energy_input = {
        ...current,
        power_mw: has("power_mw") ? num("power_mw") : (current?.power_mw ?? 0),
        source: (has("power_source")
          ? str("power_source")
          : (current?.source ?? "grid")) as EnergyInputGroup["source"],
        power_model: (has("power_model")
          ? str("power_model")
          : current?.power_model) as EnergyInputGroup["power_model"],
        ...(attrEdited
          ? {
              power_attribution: {
                ...attr,
                generator_ownership: (has("generator_ownership")
                  ? str("generator_ownership")
                  : attr?.generator_ownership) as PowerAttributionGroup["generator_ownership"],
                generator_cod_year: has("generator_cod_year")
                  ? num("generator_cod_year")
                  : attr?.generator_cod_year,
                generator_received_aid: has("generator_aid")
                  ? str("generator_aid") === "yes"
                  : attr?.generator_received_aid,
                grid_import_metering: (has("grid_import_metering")
                  ? str("grid_import_metering")
                  : attr?.grid_import_metering) as PowerAttributionGroup["grid_import_metering"],
                certificate_matching: (has("certificate_matching")
                  ? str("certificate_matching")
                  : attr?.certificate_matching) as PowerAttributionGroup["certificate_matching"],
              },
            }
          : {}),
      };
    }

    // ── Nested: electrolyser ──
    if (has("electrolyser_mw") || has("electrolyser_tech")) {
      const current = project.electrolyser;
      overlay.electrolyser = {
        ...current,
        capacity_mw: has("electrolyser_mw")
          ? num("electrolyser_mw")
          : (current?.capacity_mw ?? 0),
        technology: (has("electrolyser_tech")
          ? str("electrolyser_tech")
          : (current?.technology ?? "PEM")) as ElectrolyserGroup["technology"],
      };
    }

    // ── Nested: timeline ──
    if (has("construction_start")) {
      overlay.timeline = {
        ...project.timeline,
        construction_start_year: num("construction_start"),
      };
    }

    return { ...project, ...overlay };
  }, [project, edits]);

  const contradictions = useMemo(
    () => detectContradictions(effectiveProject),
    [effectiveProject],
  );

  const dealKillers = contradictions.filter(
    (c) => c.severity === "DEAL_KILLER",
  );
  const warnings = contradictions.filter((c) => c.severity === "WARN");

  // Completion — gated by deal-killers
  const totalFields = Object.keys(verifiedFields).length;
  const filledFields = Object.values(verifiedFields).filter(
    (f) => f.value !== "" && f.value !== null && f.value !== undefined,
  ).length;
  const blockedByDealKillers = dealKillers.length > 0;

  // Fields involved in contradictions — for highlight
  const contradictionFields = new Set(
    contradictions.flatMap((c) => c.involvedFields),
  );

  // Consult-only screens for this role (two-layer model): demoted from the
  // global top-nav, surfaced here as project-scoped "Analytics & Truth" links.
  const consultItems = useMemo(() => consultItemsForRole(role), [role]);

  // Verification helper
  const vf = (key: string) => {
    const field = verifiedFields[key] ?? {
      verification: "UNVERIFIED" as VerificationState,
      source: undefined,
      lastVerifiedAt: undefined,
      unit: undefined,
    };
    return {
      ...field,
      verification: verificationOverrides[key] ?? field.verification,
    };
  };

  const hasPathAccess = useCallback(
    (path: string) => {
      const item = menuItemForPath(path);
      return item ? isVisible(item, role) : true;
    },
    [role],
  );
  // Option A: render the narrative deterministically from structured fields.
  // Falls back to legacy free text only when structured fields are absent.
  // Reads the effective project so the prose tracks in-flight edits — the whole
  // point of deriving it is that the structured fields ARE the narrative.
  const renderedNarrative = useMemo(
    () => renderNarrative(effectiveProject),
    [effectiveProject],
  );
  const structuredFieldCount =
    (effectiveProject.energy_input ? 2 : 0) +
    (effectiveProject.electrolyser ? 2 : 0) +
    (effectiveProject.capacity_kt_yr != null ||
    effectiveProject.capacity_mtpd != null
      ? 1
      : 0) +
    (effectiveProject.offtakes?.length ?? 0) +
    (effectiveProject.certifications?.length ?? 0) +
    (effectiveProject.incentives?.length ?? 0) +
    (effectiveProject.timeline?.construction_start_year ? 1 : 0) +
    (effectiveProject.timeline?.production_start_year ? 1 : 0);
  const legacyFallback =
    profileIntelligence?.narrative ?? fieldVal("description");

  return (
    <div className="animate-fade-in">
      {/* ── Status line (replaces old card header) ── max 60px ── */}
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={onBack}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors shrink-0"
          >
            <span className="font-mono text-sm">&larr;</span>
          </button>
          <div className="font-mono text-[12px] text-[var(--text-primary)] truncate">
            <span className="font-bold">{project.name}</span>
            <span className="text-[var(--text-muted)]">
              {" "}
              &middot; {filledFields}/{totalFields} fields
              {!blockedByDealKillers && (
                <>
                  {" "}
                  &middot; {project.bankability.overall_completion}% complete
                </>
              )}{" "}
              &middot; contradictions: {contradictions.length}
            </span>
            {dirty && <span className="text-amber-500 ml-2">unsaved</span>}
            {saved && <span className="text-emerald-500 ml-2">saved</span>}
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={!dirty}
          className="font-mono text-[11px] font-bold uppercase tracking-[0.1em] px-3 py-1 rounded border border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)] disabled:opacity-30 transition-colors shrink-0"
        >
          save
        </button>
      </div>

      {/* ── BLOCKED banner (deal-killers override completion) ── */}
      {blockedByDealKillers && (
        <div className="mb-3 border border-slate-300 bg-[#F8FAFC] px-3 py-1.5 font-mono text-[11px] text-slate-900 dark:bg-slate-900 dark:text-slate-100">
          <span className="font-bold">BLOCKED</span> &middot;{" "}
          {dealKillers.length} deal-killer flag
          {dealKillers.length > 1 ? "s" : ""} unresolved
        </div>
      )}

      {/* ── Two-column layout: fields left, contradictions right ── */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
        {/* ── LEFT: Field sections ── */}
        <div className="border border-slate-300 bg-white divide-y divide-slate-200 dark:bg-slate-950 dark:divide-slate-800">
          {/* Identity */}
          <FieldSection title="Identity">
            <InlineField
              fieldKey="name"
              label="Project Name"
              value={fieldVal("name")}
              verification={vf("name").verification}
              source={vf("name").source}
              lastVerifiedAt={vf("name").lastVerifiedAt}
              isDraft={isDraft("name")}
              highlighted={contradictionFields.has("name")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="molecule"
              label="Molecule"
              value={fieldVal("molecule")}
              verification={vf("molecule").verification}
              source={vf("molecule").source}
              type="select"
              options={MOLECULE_OPTIONS}
              isDraft={isDraft("molecule")}
              highlighted={contradictionFields.has("molecule")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="owner_company"
              label="Owner"
              value={fieldVal("owner_company")}
              verification={vf("owner_company").verification}
              source={vf("owner_company").source}
              lastVerifiedAt={vf("owner_company").lastVerifiedAt}
              isDraft={isDraft("owner_company")}
              highlighted={contradictionFields.has("owner_company")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="associated_companies"
              label="Associated"
              value={fieldVal("associated_companies")}
              verification={vf("associated_companies").verification}
              isDraft={isDraft("associated_companies")}
              highlighted={contradictionFields.has("associated_companies")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
          </FieldSection>

          {/* Location */}
          <FieldSection title="Location">
            <LocationPair
              location={fieldVal("location")}
              country={fieldVal("country")}
              lat={fieldVal("lat")}
              lng={fieldVal("lng")}
              locationVerification={vf("location").verification}
              latVerification={vf("lat").verification}
              locationDraft={isDraft("location")}
              countryDraft={isDraft("country")}
              latDraft={isDraft("lat")}
              lngDraft={isDraft("lng")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
          </FieldSection>

          {/* Technical */}
          <FieldSection title="Technical" collapsible>
            <CapacityField
              valueMtpd={fieldVal("capacity_mtpd")}
              unit={capacityUnit}
              verification={vf("capacity_mtpd").verification}
              isDraft={isDraft("capacity_mtpd")}
              onUnitChange={setCapacityUnit}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            {/* Annual product output — derived, read-only chip (audit trail surfaced in source) */}
            <InlineField
              fieldKey="capacity_kt_yr"
              label="Annual"
              value={fieldVal("capacity_kt_yr")}
              verification={vf("capacity_kt_yr").verification}
              source={vf("capacity_kt_yr").source}
              unit="kt/yr"
              type="number"
              isDraft={isDraft("capacity_kt_yr")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            {/* Upstream energy — narrative source-of-truth, editable */}
            <InlineField
              fieldKey="power_mw"
              label="Power"
              value={fieldVal("power_mw")}
              verification={vf("power_mw").verification}
              source={vf("power_mw").source}
              unit="MW"
              type="number"
              isDraft={isDraft("power_mw")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="power_source"
              label="Source"
              value={fieldVal("power_source")}
              verification={vf("power_source").verification}
              type="select"
              options={["wind", "solar", "hybrid", "hydro", "nuclear", "grid"]}
              isDraft={isDraft("power_source")}
              highlighted={contradictionFields.has("power_source")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            {/* Grid topology: off-grid BTM needs grid-independence evidence; on-grid needs ≥1 PPA */}
            <InlineField
              fieldKey="power_model"
              label="Grid model"
              value={fieldVal("power_model")}
              verification={vf("power_model").verification}
              source={vf("power_model").source}
              type="select"
              options={["OFF_GRID_BTM", "GRID_CONNECTED", "HYBRID"]}
              isDraft={isDraft("power_model")}
              highlighted={contradictionFields.has("power_model")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="ppas"
              label="PPAs"
              value={fieldVal("ppas")}
              verification={vf("ppas").verification}
              source={vf("ppas").source}
              isDraft={isDraft("ppas")}
              highlighted={contradictionFields.has("ppas")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            {/* Power attribution — the evidence that qualifies the electricity.
                Owed on every topology; off-grid swaps the instrument, not the
                obligation (RFNBO DA Art. 3–5, 45V final rules, RED III Art. 2). */}
            <InlineField
              fieldKey="generator_ownership"
              label="Gen. owner"
              value={fieldVal("generator_ownership")}
              verification={vf("generator_ownership").verification}
              source={vf("generator_ownership").source}
              type="select"
              options={["", "SAME_ENTITY", "AFFILIATE", "THIRD_PARTY"]}
              isDraft={isDraft("generator_ownership")}
              highlighted={contradictionFields.has("generator_ownership")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="generator_cod_year"
              label="Gen. COD"
              value={fieldVal("generator_cod_year")}
              verification={vf("generator_cod_year").verification}
              source={vf("generator_cod_year").source}
              type="year"
              isDraft={isDraft("generator_cod_year")}
              highlighted={contradictionFields.has("generator_cod_year")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="generator_aid"
              label="Gen. aid"
              value={fieldVal("generator_aid")}
              verification={vf("generator_aid").verification}
              source={vf("generator_aid").source}
              type="select"
              options={["", "no", "yes"]}
              isDraft={isDraft("generator_aid")}
              highlighted={contradictionFields.has("generator_aid")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="grid_import_metering"
              label="Import meter"
              value={fieldVal("grid_import_metering")}
              verification={vf("grid_import_metering").verification}
              source={vf("grid_import_metering").source}
              type="select"
              options={["", "NONE", "INSTALLED", "VERIFIED"]}
              isDraft={isDraft("grid_import_metering")}
              highlighted={contradictionFields.has("grid_import_metering")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="certificate_matching"
              label="EAC match"
              value={fieldVal("certificate_matching")}
              verification={vf("certificate_matching").verification}
              source={vf("certificate_matching").source}
              type="select"
              options={["", "NONE", "ANNUAL", "MONTHLY", "HOURLY"]}
              isDraft={isDraft("certificate_matching")}
              highlighted={contradictionFields.has("certificate_matching")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            {/* Electrolyser — narrative source-of-truth, editable */}
            <InlineField
              fieldKey="electrolyser_mw"
              label="Electrolyser"
              value={fieldVal("electrolyser_mw")}
              verification={vf("electrolyser_mw").verification}
              source={vf("electrolyser_mw").source}
              unit="MW"
              type="number"
              isDraft={isDraft("electrolyser_mw")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="electrolyser_tech"
              label="Tech"
              value={fieldVal("electrolyser_tech")}
              verification={vf("electrolyser_tech").verification}
              type="select"
              options={["PEM", "AEM", "SOEC", "alkaline"]}
              isDraft={isDraft("electrolyser_tech")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="status"
              label="Status"
              value={fieldVal("status")}
              verification={vf("status").verification}
              type="select"
              options={STATUS_OPTIONS}
              isDraft={isDraft("status")}
              highlighted={contradictionFields.has("status")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="phase"
              label="Phase"
              value={fieldVal("phase")}
              verification={vf("phase").verification}
              source={vf("phase").source}
              isDraft={isDraft("phase")}
              highlighted={contradictionFields.has("phase")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="construction_start"
              label="Const. start"
              value={fieldVal("construction_start")}
              verification={vf("construction_start").verification}
              type="year"
              isDraft={isDraft("construction_start")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="completion_date"
              label="Target COD"
              value={fieldVal("completion_date")}
              verification={vf("completion_date").verification}
              type="date"
              isDraft={isDraft("completion_date")}
              highlighted={contradictionFields.has("completion_date")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <ToolGroup>
              {/* Certification readiness — links to /finance/cert-readiness, chips show count + worst-status */}
              <DetailLinkRow
                kind="CERTIFICATION"
                path="/finance/cert-readiness"
                projectId={project.id}
                hasAccess={hasPathAccess("/finance/cert-readiness")}
                description={
                  (project.certifications ?? [])
                    .map(
                      (c) =>
                        `${c.scheme}${c.status === "ACTIVE" ? "" : ` (${c.status.toLowerCase()})`}`,
                    )
                    .join(" · ") || "No certifications declared"
                }
                chip={certificationChip(project)}
              />
              <DetailLinkRow
                kind="COST BASIS"
                path="/finance-plant-builder"
                projectId={project.id}
                hasAccess={hasPathAccess("/finance-plant-builder")}
                description="Equipment, process model, CAPEX / LCOF"
                chip={costBasisChip(project)}
              />
              <DetailLinkRow
                kind="TELEMETRY"
                path="/plant-data"
                projectId={project.id}
                hasAccess={hasPathAccess("/plant-data")}
                description="OT gateway feed governed by engineering / operations"
                chip={telemetryChip(project)}
              />
            </ToolGroup>
          </FieldSection>

          {/* Financial */}
          <FieldSection title="Financial" collapsible>
            <InlineField
              fieldKey="capex_eur"
              label="CAPEX"
              value={fieldVal("capex_eur")}
              verification={vf("capex_eur").verification}
              source={vf("capex_eur").source}
              unit={String(fieldVal("capex_currency"))}
              type="number"
              isDraft={isDraft("capex_eur")}
              highlighted={contradictionFields.has("capex_eur")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <InlineField
              fieldKey="capex_currency"
              label="Currency"
              value={fieldVal("capex_currency")}
              verification={vf("capex_currency").verification}
              type="select"
              options={["EUR", "USD", "GBP", "JPY", "CHF", "CAD", "AUD"]}
              isDraft={isDraft("capex_currency")}
              highlighted={contradictionFields.has("capex_currency")}
              onConfirm={handleConfirm}
              onChange={handleChange}
            />
            <ToolGroup>
              <DetailLinkRow
                kind="READINESS"
                path="/finance/bankability"
                projectId={project.id}
                hasAccess={hasPathAccess("/finance/bankability")}
                description="Bankability cockpit, role-scoped evidence"
                chip={{
                  text: `${project.bankability.overall_completion}%`,
                  tone:
                    project.bankability.overall_completion >= 80
                      ? "live"
                      : project.bankability.overall_completion >= 50
                        ? "info"
                        : "warn",
                  title: `Overall gate completion: ${project.bankability.overall_completion}%`,
                }}
              />
              <DetailLinkRow
                kind="CAPITAL"
                path="/capital-stack"
                projectId={project.id}
                hasAccess={hasPathAccess("/capital-stack")}
                description="Debt / equity stack"
                chip={{
                  text: `${project.bankability.capital_status.filter((c) => c.is_unlocked).length}/${project.bankability.capital_status.length} UNLOCKED`,
                  tone: project.bankability.capital_status.every(
                    (c) => c.is_unlocked,
                  )
                    ? "live"
                    : project.bankability.capital_status.some(
                          (c) => c.is_unlocked,
                        )
                      ? "info"
                      : "warn",
                  title: "Capital tranches with their gating gates satisfied",
                }}
              />
              <DetailLinkRow
                kind="MODEL"
                path="/dscr-sensitivity"
                projectId={project.id}
                hasAccess={hasPathAccess("/dscr-sensitivity")}
                description="DSCR & financing sensitivities"
                chip={{
                  text: project.status === "operating" ? "POST-COD" : "PRE-COD",
                  tone: project.status === "operating" ? "live" : "info",
                  title:
                    project.status === "operating"
                      ? "Realized DSCR is the primary covenant metric post-COD"
                      : "Projected / scenario DSCR — a first-class pre-COD bankability metric for financial-close assessment. Restricted because it is debt-fragility sensitive, not because it is irrelevant pre-COD.",
                }}
              />
            </ToolGroup>
          </FieldSection>

          {/* Analytics & Truth — consult-only screens demoted from the top-nav
              for this role, kept fully reachable here, scoped to this project. */}
          {consultItems.length > 0 && (
            <FieldSection title="Analytics & Truth" collapsible>
              {consultItems.map((it) => (
                <DetailLinkRow
                  key={it.id}
                  kind="CONSULT"
                  path={it.path}
                  projectId={project.id}
                  hasAccess={true}
                  description={
                    it.tooltip ??
                    "Read-only analytics — not a top-nav action for your role"
                  }
                />
              ))}
            </FieldSection>
          )}

          {/* Description — derived from structured fields (Option A) */}
          <FieldSection title="Description">
            <RenderedNarrativeBlock
              rendered={renderedNarrative}
              fallbackText={String(legacyFallback ?? "")}
              structuredFieldCount={structuredFieldCount}
            />
            <NarrativeSourceLine intelligence={profileIntelligence} />
          </FieldSection>

          {/* Bankability (read-only summary) */}
          <FieldSection title="Bankability">
            <div className="grid grid-cols-[112px_minmax(0,1fr)] items-center gap-1 border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]">
              <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-muted)]">
                Completion
              </span>
              <span className="font-mono text-[12px] font-bold tabular-nums text-[var(--text-primary)]">
                {blockedByDealKillers ? (
                  <span className="text-rose-500">BLOCKED</span>
                ) : (
                  <>{project.bankability.overall_completion}%</>
                )}
              </span>
            </div>
            <div className="grid grid-cols-[112px_minmax(0,1fr)] items-center gap-1 border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]">
              <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-muted)]">
                Gates
              </span>
              <span className="font-mono text-[12px] tabular-nums text-[var(--text-primary)]">
                {project.bankability.gates.filter((g) => g.is_complete).length}/
                {project.bankability.gates.length}
              </span>
            </div>
            <div className="grid grid-cols-[112px_minmax(0,1fr)] items-center gap-1 border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]">
              <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-muted)]">
                Capital tranches
              </span>
              <span className="font-mono text-[12px] tabular-nums text-[var(--text-primary)]">
                {project.bankability.capital_status.length}
              </span>
            </div>
            <div className="grid grid-cols-[112px_minmax(0,1fr)] items-center gap-1 border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]">
              <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-muted)]">
                Next milestone
              </span>
              <span className="font-mono text-[11px] text-[var(--text-secondary)] truncate">
                {project.bankability.next_milestone}
              </span>
            </div>
          </FieldSection>
        </div>

        {/* ── RIGHT: Contradiction surface ── */}
        <div className="space-y-2">
          <div className="text-[9px] font-bold uppercase tracking-[0.15em] text-[var(--text-muted)]">
            Contradictions ({contradictions.length})
          </div>

          {contradictions.length === 0 && (
            <div className="border border-slate-300 bg-[#F8FAFC] px-3 py-1.5 font-mono text-[11px] text-slate-700 dark:bg-slate-900 dark:text-slate-200">
              No contradictions detected
            </div>
          )}

          {dealKillers.map((c) => (
            <div
              key={c.id}
              className="border border-slate-300 bg-[#F8FAFC] px-3 py-1.5 dark:bg-slate-900"
            >
              <div className="font-mono text-[10px] font-bold text-rose-600 dark:text-rose-400 uppercase tracking-[0.08em] mb-0.5">
                deal-killer
              </div>
              <div className="font-mono text-[11px] text-rose-800 dark:text-rose-300 leading-snug">
                {c.message}
              </div>
              <div className="font-mono text-[9px] text-rose-500/70 mt-1">
                {c.involvedFields.join(", ")}
              </div>
            </div>
          ))}

          {warnings.map((c) => (
            <div
              key={c.id}
              className="border border-slate-300 bg-[#F8FAFC] px-3 py-1.5 dark:bg-slate-900"
            >
              <div className="font-mono text-[10px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-[0.08em] mb-0.5">
                warn
              </div>
              <div className="font-mono text-[11px] text-amber-800 dark:text-amber-300 leading-snug">
                {c.message}
              </div>
              <div className="font-mono text-[9px] text-amber-500/70 mt-1">
                {c.involvedFields.join(", ")}
              </div>
            </div>
          ))}

          {/* Risk alerts from bankability */}
          {project.bankability.risk_alerts.length > 0 && (
            <>
              <div className="text-[9px] font-bold uppercase tracking-[0.15em] text-[var(--text-muted)] mt-3">
                Risk Alerts ({project.bankability.risk_alerts.length})
              </div>
              {project.bankability.risk_alerts.map((a) => (
                <div
                  key={a}
                  className="border border-slate-300 bg-[#F8FAFC] px-3 py-1.5 font-mono text-[11px] text-[var(--text-secondary)] leading-snug dark:bg-slate-900"
                >
                  {a}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function FieldSection({
  title,
  children,
  collapsible = false,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  collapsible?: boolean;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="px-2 py-1">
      <button
        type="button"
        onClick={() => collapsible && setOpen((o) => !o)}
        className={[
          "flex w-full items-center gap-1 text-left mb-[2px] pl-1",
          collapsible ? "cursor-pointer select-none group" : "cursor-default",
        ].join(" ")}
      >
        {collapsible && (
          <svg
            viewBox="0 0 10 10"
            className="w-[9px] h-[9px] shrink-0 text-[var(--text-muted)] transition-transform duration-150"
            style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
            aria-hidden="true"
          >
            <path
              d="M3 2 L7 5 L3 8"
              stroke="currentColor"
              strokeWidth="1.5"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
        <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-black dark:text-white">
          {title}
        </span>
      </button>
      {(!collapsible || open) && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-x-6 gap-y-0">
          {children}
        </div>
      )}
    </div>
  );
}
