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
import { CUSTOMER_PROJECTS, type CustomerProject } from "@/data/customerProjects";
import { renderNarrative, type RenderedNarrative } from "@/lib/narrative";
import { useUserRole } from "@/contexts/UserRoleContext";
import { MENU_TABS, isVisible, consultItemsForRole, type MenuItem } from "@/config/menuArchitecture";
import {
  CAPACITY_UNITS,
  capacityDisplayValue,
  capacityInputToMtpd,
  type CapacityUnit,
} from "@/lib/capacityUnits";
import type { VerificationState } from "@/types/deal";

// ── Data model ───────────────────────────────────────────────────────────────

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
  "H2", "NH3", "e-Methanol", "SAF", "e-NG", "e-Methane",
  "e-NH3", "HVO", "e-Gasoline", "e-LG", "e-Naphtha",
] as const;

const STATUS_OPTIONS = [
  "development", "construction", "commissioning", "operating",
] as const;

function fmtNum(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function fmtDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

const MENU_ITEMS = MENU_TABS.flatMap((tab) => tab.items);

function menuItemForPath(path: string): MenuItem | undefined {
  return MENU_ITEMS.find((item) => item.path === path);
}

/** Build verified fields from static CustomerProject data (demo shim). */
function buildVerifiedFields(p: CustomerProject): Record<string, VerifiedField<unknown>> {
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
    gateCompletion >= 90 ? "AUDITED" : gateCompletion >= 60 ? "CONFIRMED" : gateCompletion >= 30 ? "SUBMITTED" : "UNVERIFIED";

  return {
    name:                 mk(p.name, "CONFIRMED", { source: "Onboarding", lastVerifiedAt: "2026-01-15" }),
    molecule:             mk(p.molecule, projectVerif, { source: "FEED study" }),
    owner_company:        mk(p.owner_company, "CONFIRMED", { source: "KYC check", lastVerifiedAt: "2026-02-01" }),
    associated_companies: mk(p.associated_companies.join(", "), "SUBMITTED"),
    location:             mk(p.location, "CONFIRMED", { source: "Site survey", lastVerifiedAt: "2025-11-20" }),
    country:              mk(p.country, "CONFIRMED", { source: "Jurisdiction filing" }),
    lat:                  mk(p.lat, "CONFIRMED", { unit: "deg N" }),
    lng:                  mk(p.lng, "CONFIRMED", { unit: "deg E/W" }),
    capacity_mtpd:        mk(p.capacity_mtpd, projectVerif, { unit: "MTPD", source: "FEED Class 3" }),
    capex_eur:            mk(p.capex_eur, projectVerif, { unit: p.capex_currency ?? "EUR", source: "AACE Class 3 estimate" }),
    capex_currency:       mk(p.capex_currency ?? "EUR", p.capex_currency ? "CONFIRMED" : "UNVERIFIED", { source: "Project filing" }),
    status:               mk(p.status, "CONFIRMED"),
    phase:                mk(p.phase, projectVerif, { source: "Project manager attestation" }),
    completion_date:      mk(p.completion_date, p.status === "operating" ? "AUDITED" : "SUBMITTED"),
    description:          mk(p.description, "UNVERIFIED"),
    // ── Structured narrative source-of-truth fields (Option A) ──
    power_mw:             mk(p.energy_input?.power_mw ?? 0,           p.energy_input ? "CONFIRMED" : "UNVERIFIED", { unit: "MW",  source: "FEED Class 3" }),
    power_source:         mk(p.energy_input?.source ?? "",            p.energy_input ? "CONFIRMED" : "UNVERIFIED", { source: "Energy supply agreement" }),
    // Grid topology — drives G1 evidence requirements and the PPA rule.
    power_model:          mk(p.energy_input?.power_model ?? "",       p.energy_input?.power_model ? "CONFIRMED" : "UNVERIFIED", { source: "Power sourcing strategy" }),
    // PPA portfolio summary (structured editor is a follow-up; the rule reads the array).
    ppas:                 mk(
      (() => {
        const ppas = p.energy_input?.ppas ?? [];
        if (ppas.length === 0) return p.energy_input?.power_model === "OFF_GRID_BTM" ? "n/a (off-grid BTM)" : "none";
        const mw = ppas.reduce((s, x) => s + x.volume_mw, 0);
        const signed = ppas.filter(x => x.status === "SIGNED").length;
        return `${ppas.length} PPA · ${signed} signed · ${mw} MW`;
      })(),
      (p.energy_input?.ppas ?? []).some(x => x.status === "SIGNED") ? "CONFIRMED" : "UNVERIFIED",
      { source: "PPA register" },
    ),
    electrolyser_mw:      mk(p.electrolyser?.capacity_mw ?? 0,        p.electrolyser ? "CONFIRMED" : "UNVERIFIED", { unit: "MW",  source: "Electrolyser OEM spec" }),
    electrolyser_tech:    mk(p.electrolyser?.technology ?? "",        p.electrolyser ? "CONFIRMED" : "UNVERIFIED", { source: "Electrolyser OEM spec" }),
    capacity_kt_yr:       mk(p.capacity_kt_yr ?? Math.round((p.capacity_mtpd * 365) / 1000), "CONFIRMED", { unit: "kt/yr", source: "Derived from capacity_mtpd × 365" }),
    construction_start:   mk(p.timeline?.construction_start_year ?? 0, p.timeline?.construction_start_year ? "SUBMITTED" : "UNVERIFIED", { source: "Project schedule" }),
  };
}

/** Detect contradictions from project data. */
function detectContradictions(p: CustomerProject): ContradictionFlag[] {
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
    const relatedParty = p.offtakes.filter(o => o.is_related_party);
    const thirdPartyBinding = p.offtakes.filter(o => !o.is_related_party && o.binding_status === "BINDING");
    if (relatedParty.length > 0 && thirdPartyBinding.length === 0) {
      flags.push({
        id: "CONTRA_RELATED_PARTY_ONLY",
        severity: "DEAL_KILLER",
        message: "All offtake is related-party (owner = offtaker) with no binding third-party contract — lenders discount or exclude related-party offtake from bankability",
        involvedFields: ["owner_company"],
        detectedAt: now,
      });
    }
    const anyBinding = p.offtakes.filter(o => o.binding_status === "BINDING");
    if (anyBinding.length === 0) {
      flags.push({
        id: "CONTRA_NO_BINDING_OFFTAKE",
        severity: "DEAL_KILLER",
        message: "No binding offtake agreement — all offtakes are LOI, MOU, or indicative. Project cannot reach financial close without a bankable binding contract.",
        involvedFields: ["owner_company"],
        detectedAt: now,
      });
    }
  }

  // CAPEX currency vs jurisdiction convention.
  // Local-currency CAPEX removes the FX surcharge in lender models. When the
  // user changes capex_currency to the conventional one, this flag disappears.
  const CONVENTIONAL_CCY: Record<string, string> = {
    US: 'USD', CA: 'CAD', GB: 'GBP', JP: 'JPY', CH: 'CHF', AU: 'AUD',
    DE: 'EUR', FR: 'EUR', ES: 'EUR', NL: 'EUR', BE: 'EUR', IT: 'EUR',
    PT: 'EUR', FI: 'EUR', IE: 'EUR', AT: 'EUR', GR: 'EUR', LU: 'EUR',
  };
  const expected = CONVENTIONAL_CCY[p.country];
  const actual   = p.capex_currency ?? 'EUR';
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
  if (g4 && !g4.is_complete && (p.status === "construction" || p.phase.includes("FID"))) {
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
      message: "45V Tier 1 subsidy claim referenced but certification not AUDITED",
      involvedFields: ["description"],
      detectedAt: now,
    });
  }

  // ── Power model ⇒ PPA structural rule ─────────────────────────────────────
  // On-grid electricity (GRID_CONNECTED / HYBRID) is only bankable with at
  // least one PPA: without it the electricity price — the dominant OPEX of
  // electrolysis — is unhedged, and RFNBO/45V additionality cannot be shown.
  // Off-grid BTM owns its generation, so no PPA is required (G1 demands
  // grid-INDEPENDENCE evidence instead).
  const ei = p.energy_input;
  if (ei?.power_model && ei.power_model !== "OFF_GRID_BTM") {
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
        severity: p.status === "development" && !constructionImminent ? "WARN" : "DEAL_KILLER",
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
    } else if (signed.length === 0 && (p.status === "construction" || p.status === "operating")) {
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
          involvedFields: ["ppas", ei.power_model === "HYBRID" ? "grid_import_mw" : "power_mw"],
          detectedAt: now,
        });
      }
    }
    // Internal sleeved supply (prosumer structure): normal for a balance-sheet
    // owner consuming its own generation; a related-party pricing risk when
    // external lenders are being asked to rely on it.
    const internalSigned = signed.filter((x) => x.counterparty_type === "INTERNAL_AFFILIATE");
    if (internalSigned.length > 0 && (p.financing_model ?? "PROJECT_FINANCE") !== "BALANCE_SHEET") {
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
        (c) => c.type === "SENIOR_DEBT_COMMITMENT" || c.type === "DEBT_DRAWDOWN",
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
      message: 'Power model OFF_GRID_BTM contradicts power source "grid" — one of the two is wrong.',
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
  const canConfirm = !isDraft && effectiveState !== "CONFIRMED" && effectiveState !== "AUDITED";

  const tip = [
    isDraft ? "Modified by user — verification required" : canConfirm ? "Click to confirm client-reviewed data" : effectiveState,
    source ? `Source: ${source}` : null,
    lastVerifiedAt ? `Verified: ${fmtDate(lastVerifiedAt)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <span
      title={tip}
      onClick={canConfirm ? onConfirm : undefined}
      className={`justify-self-end inline-flex h-[15px] min-w-[74px] items-center justify-center border border-l-2 px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none ${
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
  type?: "text" | "number" | "date" | "select" | "textarea";
  options?: readonly string[];
  highlighted?: boolean;
  isDraft?: boolean;
  onConfirm?: (key: string) => void;
  onChange: (key: string, val: string | number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(value));
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(null);

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

  const displayValue = type === "number" ? fmtNum(value as number) : type === "date" ? fmtDate(String(value)) : String(value);
  const valueTone = verification === "UNVERIFIED" && !isDraft ? "opacity-60" : "";

  // Textarea keeps a full-row layout.
  if (type === "textarea") {
    return (
      <div
        className={`col-span-full grid grid-cols-1 gap-0.5 border border-transparent px-1 py-[2px] transition-colors ${
          highlighted ? "border-slate-300 bg-[#F8FAFC] dark:bg-slate-900/40" : "hover:bg-[#F8FAFC]"
        }`}
      >
        <div className="grid grid-cols-[112px_minmax(0,1fr)_78px] items-center gap-1">
          <span className="w-[112px] shrink-0 text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)]">{label}</span>
          <span />
          <VerificationPill state={verification} isDraft={isDraft} source={source} lastVerifiedAt={lastVerifiedAt} onConfirm={() => onConfirm?.(fieldKey)} />
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
      className={`grid grid-cols-[112px_minmax(0,1fr)_78px_auto] items-center gap-1 border border-transparent px-1 py-[2px] transition-colors ${
        highlighted ? "border-slate-300 bg-[#F8FAFC] dark:bg-slate-900/40" : "hover:bg-[#F8FAFC]"
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
            onChange={(e) => { setDraft(e.target.value); }}
            onBlur={commit}
            onKeyDown={handleKey}
            className="justify-self-end font-mono text-[11px] tabular-nums bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] focus:outline-none"
          >
            {options.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        ) : (
          <input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            title={label}
            aria-label={label}
            type={type === "date" ? "date" : type === "number" ? "number" : "text"}
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
          className={`justify-self-end font-mono text-[11px] tabular-nums font-semibold text-[var(--text-primary)] text-right cursor-text hover:bg-slate-100 px-0.5 transition-colors whitespace-nowrap ${valueTone}`}
          title="Click to edit"
        >
          {displayValue || "—"}
        </span>
      )}

      <VerificationPill state={verification} isDraft={isDraft} source={source} lastVerifiedAt={lastVerifiedAt} onConfirm={() => onConfirm?.(fieldKey)} />

      {unit ? (
        <span className="text-[9px] font-mono text-[var(--text-muted)] border border-slate-300 bg-[#F8FAFC] px-0.5 select-none leading-none py-[1px]">
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
  const [placeDraft, setPlaceDraft] = useState({ location: String(location), country: String(country) });
  const [coordDraft, setCoordDraft] = useState({ lat: String(lat), lng: String(lng) });
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
    if (placeDraft.location !== String(location)) onChange("location", placeDraft.location);
    if (placeDraft.country !== String(country)) onChange("country", placeDraft.country);
  }, [country, location, onChange, placeDraft]);

  const commitCoords = useCallback(() => {
    setEditingCoords(false);
    const nextLat = parseFloat(coordDraft.lat) || 0;
    const nextLng = parseFloat(coordDraft.lng) || 0;
    if (nextLat !== Number(lat)) onChange("lat", nextLat);
    if (nextLng !== Number(lng)) onChange("lng", nextLng);
  }, [coordDraft, lat, lng, onChange]);

  const fmtCoord = (value: string | number) => {
    const n = Number(value);
    return Number.isFinite(n) ? fmtNum(n) : "—";
  };

  return (
    <div className="col-span-full grid grid-cols-1 xl:grid-cols-2 gap-x-6 gap-y-0">
      <div
        ref={placeRef}
        onBlur={(e) => {
          if (!placeRef.current?.contains(e.relatedTarget as Node | null)) commitPlace();
        }}
        className="grid grid-cols-[112px_minmax(0,1fr)_78px] items-center gap-1 border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]"
      >
        <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)]">Location</span>
        {editingPlace ? (
          <div className="justify-self-end flex flex-wrap items-center gap-1">
            <input
              title="Location"
              aria-label="Location"
              value={placeDraft.location}
              onChange={(e) => setPlaceDraft((prev) => ({ ...prev, location: e.target.value }))}
              onKeyDown={(e) => { if (e.key === "Enter") commitPlace(); }}
              className="font-mono text-[11px] bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] focus:outline-none max-w-[180px]"
              autoFocus
            />
            <span className="font-mono text-[11px] text-[var(--text-muted)]">,</span>
            <input
              title="Country"
              aria-label="Country"
              value={placeDraft.country}
              onChange={(e) => setPlaceDraft((prev) => ({ ...prev, country: e.target.value }))}
              onKeyDown={(e) => { if (e.key === "Enter") commitPlace(); }}
              className="font-mono text-[11px] bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] focus:outline-none w-16"
            />
          </div>
        ) : (
          <div
            onClick={() => setEditingPlace(true)}
            className={`justify-self-end font-mono text-[11px] font-semibold text-[var(--text-primary)] cursor-text hover:bg-slate-100 px-0.5 transition-colors ${
              locationVerification === "UNVERIFIED" && !locationDraft && !countryDraft ? "opacity-60" : ""
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
      </div>
      <div
        ref={coordsRef}
        onBlur={(e) => {
          if (!coordsRef.current?.contains(e.relatedTarget as Node | null)) commitCoords();
        }}
        className="grid grid-cols-[112px_minmax(0,1fr)_78px] items-center gap-1 border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]"
      >
        <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)]">Coordinates</span>
        {editingCoords ? (
          <div className="justify-self-end flex items-center gap-1 whitespace-nowrap">
            <input
              type="number"
              title="Latitude"
              aria-label="Latitude"
              value={coordDraft.lat}
              onChange={(e) => setCoordDraft((prev) => ({ ...prev, lat: e.target.value }))}
              onKeyDown={(e) => { if (e.key === "Enter") commitCoords(); }}
              className="font-mono text-[11px] tabular-nums bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] text-right focus:outline-none w-20"
              autoFocus
            />
            <span className="font-mono text-[11px] text-[var(--text-muted)]">&deg; N /</span>
            <input
              type="number"
              title="Longitude"
              aria-label="Longitude"
              value={coordDraft.lng}
              onChange={(e) => setCoordDraft((prev) => ({ ...prev, lng: e.target.value }))}
              onKeyDown={(e) => { if (e.key === "Enter") commitCoords(); }}
              className="font-mono text-[11px] tabular-nums bg-white border border-slate-400 rounded-none px-1 py-0 text-[var(--text-primary)] text-right focus:outline-none w-24"
            />
            <span className="font-mono text-[11px] text-[var(--text-muted)]">&deg; E/W</span>
          </div>
        ) : (
          <div
            onClick={() => setEditingCoords(true)}
            className={`justify-self-end font-mono text-[11px] font-semibold tabular-nums text-[var(--text-primary)] whitespace-nowrap cursor-text hover:bg-slate-100 px-0.5 transition-colors ${
              latVerification === "UNVERIFIED" && !latDraft && !lngDraft ? "opacity-60" : ""
            }`}
            title="Click to edit coordinates"
          >
            {fmtCoord(lat)}&deg; N / {fmtCoord(lng)}&deg; E/W
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
    <div className="grid grid-cols-[112px_minmax(0,1fr)_78px_auto] items-center gap-1 border border-transparent px-1 py-[2px] transition-colors hover:bg-[#F8FAFC]">
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
          onKeyDown={(e) => { if (e.key === "Enter") commit(); }}
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
      <VerificationPill state={verification} isDraft={isDraft} onConfirm={() => onConfirm?.("capacity_mtpd")} />
      <select
        value={unit}
        onChange={(e) => onUnitChange(e.target.value as CapacityUnit)}
        className="font-mono text-[9px] text-[var(--text-muted)] border border-slate-300 bg-[#F8FAFC] px-0.5 py-0 leading-none focus:outline-none"
        title="Capacity unit"
      >
        {CAPACITY_UNITS.map((option) => (
          <option key={option} value={option}>{option}</option>
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
type ChipTone = 'live' | 'warn' | 'none' | 'info';

function StateChip({ text, tone, title }: { text: string; tone: ChipTone; title?: string }) {
  const cls =
    tone === 'live' ? 'border-l-emerald-600 text-emerald-800 dark:text-emerald-300'
    : tone === 'warn' ? 'border-l-amber-600  text-amber-800  dark:text-amber-300'
    : tone === 'info' ? 'border-l-sky-600    text-sky-800    dark:text-sky-300'
    :                   'border-l-slate-400  text-slate-500  dark:text-slate-400';
  return (
    <span
      title={title}
      className={`inline-flex h-[15px] items-center justify-center border border-l-2 border-slate-300 bg-white dark:bg-slate-950 px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none whitespace-nowrap ${cls}`}
    >
      {text}
    </span>
  );
}

/**
 * Derive a human-readable restriction reason from a MenuItem's visibility rules.
 * Compresses the rule set to the smallest descriptor a user can act on.
 * (Hidalgo: lower entropy than the bare word "Restricted".)
 */
function restrictionReason(item: MenuItem | undefined): string {
  if (!item) return 'Path not registered in nav architecture';
  const rules = item.visible_to;
  if (rules.length === 0) return 'No visibility rule defined';
  const cts = new Set<string>();
  const fns = new Set<string>();
  const sts = new Set<string>();
  for (const r of rules) {
    if (r.company_type && r.company_type !== 'ALL') cts.add(r.company_type);
    if (r.function && r.function !== 'ALL')         fns.add(r.function);
    if (r.service_type && r.service_type !== 'ALL') sts.add(r.service_type);
  }
  const parts: string[] = [];
  if (cts.size) parts.push(`company_type ∈ {${Array.from(cts).join(', ')}}`);
  if (fns.size) parts.push(`business_function ∈ {${Array.from(fns).join(', ')}}`);
  if (sts.size) parts.push(`service_type ∈ {${Array.from(sts).join(', ')}}`);
  return parts.length ? `Requires ${parts.join(' or ')}` : 'Available to all roles (check session)';
}

/**
 * Append `?project=<id>` so the destination can hydrate to the same project
 * the user was editing. Eliminates context loss on navigation.
 */
function withProject(path: string, projectId: string): string {
  const sep = path.includes('?') ? '&' : '?';
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
  kind: string;                              // column-1 action verb e.g. "COST BASIS"
  path: string;                              // canonical route
  projectId: string;                         // active project — appended as ?project=
  hasAccess: boolean;
  description: string;                       // gloss in column 2 after the link
  chip?: { text: string; tone: ChipTone; title?: string };
}) {
  const item   = menuItemForPath(path);
  // Canonical label sourced from menuArchitecture — single source of truth.
  const value  = item?.label ?? path;
  const target = withProject(path, projectId);
  const reason = !hasAccess ? restrictionReason(item) : undefined;

  return (
    <div className="col-span-full grid grid-cols-[112px_minmax(0,1fr)_78px] items-center gap-1 border border-transparent px-1 py-[2px] transition-colors hover:bg-[#F8FAFC]">
      <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)] whitespace-nowrap">
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
        {chip && <StateChip text={chip.text} tone={chip.tone} title={chip.title} />}
      </div>
      <span
        title={reason}
        className={`justify-self-end inline-flex h-[15px] min-w-[74px] items-center justify-center border border-l-2 px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none ${
          hasAccess
            ? "border-slate-300 border-l-emerald-600 bg-white text-slate-700 dark:bg-slate-950 dark:text-slate-200"
            : "border-slate-300 border-l-slate-400 bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400 cursor-help"
        }`}
      >
        {hasAccess ? "ENABLED" : "RESTRICTED"}
      </span>
    </div>
  );
}

// ── Per-project state derivations for chips ──────────────────────────────────

function costBasisChip(p: CustomerProject): { text: string; tone: ChipTone; title?: string } {
  // Cost-basis class derived from project phase — until development_packages
  // AACE history is wired to the frontend.
  const phase = String((p as any).phase || '').toUpperCase();
  if (phase.includes('FEED 3') || phase.includes('CLASS 3') || phase.includes('FEED-3'))
    return { text: 'AACE 3',  tone: 'live', title: 'FEED Class 3 cost basis on file' };
  if (phase.includes('FEED'))
    return { text: 'AACE 4',  tone: 'info', title: 'FEED-stage cost basis (Class 4)' };
  if (phase.includes('PRE-FEED') || phase.includes('CONCEPT'))
    return { text: 'AACE 5',  tone: 'warn', title: 'Pre-FEED estimate (Class 5)' };
  return { text: 'ESTIMATE', tone: 'warn', title: 'No AACE class on file — estimate only' };
}

function certificationChip(p: CustomerProject): { text: string; tone: ChipTone; title?: string } {
  const certs = p.certifications ?? [];
  if (certs.length === 0) return { text: 'NONE', tone: 'none', title: 'No certifications declared' };
  const active = certs.filter(c => c.status === 'ACTIVE').length;
  const review = certs.filter(c => c.status === 'UNDER_REVIEW').length;
  const text   = `${active}/${certs.length} ACTIVE`;
  const tone: ChipTone = active === certs.length ? 'live' : active > 0 ? 'info' : review > 0 ? 'warn' : 'none';
  return { text, tone, title: `${active} active, ${review} under review, ${certs.length - active - review} other` };
}

function telemetryChip(p: CustomerProject): { text: string; tone: ChipTone; title?: string } {
  // Telemetry availability strictly follows construction lifecycle.
  switch (p.status) {
    case 'operating':
      return { text: 'LIVE',          tone: 'live', title: 'Telemetry expected from registered OT gateways' };
    case 'commissioning':
      return { text: 'INTERMITTENT',  tone: 'info', title: 'Commissioning runs only — gaps expected' };
    case 'construction':
      return { text: 'NO FEED',       tone: 'warn', title: 'No telemetry until COD' };
    default:
      return { text: 'PRE-COD',       tone: 'none', title: 'Pre-COD project — no telemetry contracted' };
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
        {intelligence.backend_store} · {intelligence.record_id} · {intelligence.linked_records.length} linked records
      </span>
      <span className="justify-self-end inline-flex h-[15px] min-w-[74px] items-center justify-center border border-l-2 border-slate-300 border-l-sky-600 bg-[#F8FAFC] px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] text-sky-800">
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
              ? 'border-l-emerald-600 text-emerald-800 dark:text-emerald-300'
              : 'border-l-amber-600 text-amber-800 dark:text-amber-300'
          }`}
          title={usingStructured
            ? 'Every clause traces to a field path. Edit fields to change prose.'
            : 'Project has not been migrated to structured narrative fields yet.'}
        >
          {usingStructured ? 'DERIVED' : 'FREE TEXT'}
        </span>
      </div>

      {/* Rendered prose — read-only */}
      <p className="font-serif text-[12px] leading-relaxed text-[var(--text-primary)] px-1">
        {text || <span className="italic text-[var(--text-muted)]">No narrative — add structured fields.</span>}
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
                  <td className="px-2 py-1 text-[var(--text-secondary)] align-top">{c.text}.</td>
                  <td className="px-2 py-1 font-mono text-[10px] text-[var(--text-muted)] whitespace-nowrap align-top text-right">
                    {c.sources.join('  ·  ')}
                  </td>
                </tr>
              ))}
              {rendered.missing_fields.length > 0 && (
                <tr>
                  <td className="px-2 py-1 italic text-amber-700 dark:text-amber-400">
                    Missing — would extend the prose if filled
                  </td>
                  <td className="px-2 py-1 font-mono text-[10px] text-amber-700 dark:text-amber-400 whitespace-nowrap text-right">
                    {rendered.missing_fields.join('  ·  ')}
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

  return <ProfileWorkbench project={project} onBack={() => navigate("/projects")} />;
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
  const [verificationOverrides, setVerificationOverrides] = useState<Record<string, VerificationState>>({});
  const [capacityUnit, setCapacityUnit] = useState<CapacityUnit>("MTPD");
  const [profileIntelligence, setProfileIntelligence] = useState<ProjectProfileIntelligence | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);

  const fieldVal = (key: string) =>
    key in edits ? edits[key] : (verifiedFields[key]?.value as string | number) ?? "";
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
  const effectiveProject = useMemo<CustomerProject>(() => {
    const overlay: Partial<CustomerProject> = {};
    if ('capex_currency' in edits) overlay.capex_currency = edits.capex_currency as CustomerProject['capex_currency'];
    if ('country'        in edits) overlay.country        = String(edits.country);
    if ('status'         in edits) overlay.status         = edits.status as CustomerProject['status'];
    if ('phase'          in edits) overlay.phase          = String(edits.phase);
    if ('description'    in edits) overlay.description    = String(edits.description);
    if ('capex_eur'      in edits) overlay.capex_eur      = Number(edits.capex_eur);
    if ('capacity_mtpd'  in edits) overlay.capacity_mtpd  = Number(edits.capacity_mtpd);
    return { ...project, ...overlay };
  }, [project, edits]);

  const contradictions = useMemo(() => detectContradictions(effectiveProject), [effectiveProject]);
  const dealKillers   = contradictions.filter((c) => c.severity === "DEAL_KILLER");
  const warnings      = contradictions.filter((c) => c.severity === "WARN");

  // Completion — gated by deal-killers
  const totalFields = Object.keys(verifiedFields).length;
  const filledFields = Object.values(verifiedFields).filter(
    (f) => f.value !== "" && f.value !== null && f.value !== undefined,
  ).length;
  const blockedByDealKillers = dealKillers.length > 0;

  // Fields involved in contradictions — for highlight
  const contradictionFields = new Set(contradictions.flatMap((c) => c.involvedFields));

  // Consult-only screens for this role (two-layer model): demoted from the
  // global top-nav, surfaced here as project-scoped "Analytics & Truth" links.
  const consultItems = useMemo(() => consultItemsForRole(role), [role]);

  // Verification helper
  const vf = (key: string) => {
    const field = verifiedFields[key] ?? { verification: "UNVERIFIED" as VerificationState, source: undefined, lastVerifiedAt: undefined, unit: undefined };
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
  const renderedNarrative = useMemo(() => renderNarrative(project), [project]);
  const structuredFieldCount =
    (project.energy_input ? 2 : 0) +
    (project.electrolyser ? 2 : 0) +
    (project.capacity_kt_yr != null || project.capacity_mtpd != null ? 1 : 0) +
    (project.offtakes?.length ?? 0) +
    (project.certifications?.length ?? 0) +
    (project.incentives?.length ?? 0) +
    (project.timeline?.construction_start_year ? 1 : 0) +
    (project.timeline?.production_start_year ? 1 : 0);
  const legacyFallback = profileIntelligence?.narrative ?? fieldVal("description");

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
              {" "}&middot; {filledFields}/{totalFields} fields
              {!blockedByDealKillers && (
                <>{" "}&middot; {project.bankability.overall_completion}% complete</>
              )}
              {" "}&middot; contradictions: {contradictions.length}
            </span>
            {dirty && (
              <span className="text-amber-500 ml-2">unsaved</span>
            )}
            {saved && (
              <span className="text-emerald-500 ml-2">saved</span>
            )}
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
          <span className="font-bold">BLOCKED</span> &middot; {dealKillers.length} deal-killer flag{dealKillers.length > 1 ? "s" : ""} unresolved
        </div>
      )}

      {/* ── Two-column layout: fields left, contradictions right ── */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
        {/* ── LEFT: Field sections ── */}
        <div className="border border-slate-300 bg-white divide-y divide-slate-200 dark:bg-slate-950 dark:divide-slate-800">
          {/* Identity */}
          <FieldSection title="Identity">
            <InlineField fieldKey="name" label="Project Name" value={fieldVal("name")} verification={vf("name").verification} source={vf("name").source} lastVerifiedAt={vf("name").lastVerifiedAt} isDraft={isDraft("name")} highlighted={contradictionFields.has("name")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="molecule" label="Molecule" value={fieldVal("molecule")} verification={vf("molecule").verification} source={vf("molecule").source} type="select" options={MOLECULE_OPTIONS} isDraft={isDraft("molecule")} highlighted={contradictionFields.has("molecule")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="owner_company" label="Owner" value={fieldVal("owner_company")} verification={vf("owner_company").verification} source={vf("owner_company").source} lastVerifiedAt={vf("owner_company").lastVerifiedAt} isDraft={isDraft("owner_company")} highlighted={contradictionFields.has("owner_company")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="associated_companies" label="Associated" value={fieldVal("associated_companies")} verification={vf("associated_companies").verification} isDraft={isDraft("associated_companies")} highlighted={contradictionFields.has("associated_companies")} onConfirm={handleConfirm} onChange={handleChange} />
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
            <CapacityField valueMtpd={fieldVal("capacity_mtpd")} unit={capacityUnit} verification={vf("capacity_mtpd").verification} isDraft={isDraft("capacity_mtpd")} onUnitChange={setCapacityUnit} onConfirm={handleConfirm} onChange={handleChange} />
            {/* Annual product output — derived, read-only chip (audit trail surfaced in source) */}
            <InlineField fieldKey="capacity_kt_yr" label="Annual" value={fieldVal("capacity_kt_yr")} verification={vf("capacity_kt_yr").verification} source={vf("capacity_kt_yr").source} unit="kt/yr" type="number" isDraft={isDraft("capacity_kt_yr")} onConfirm={handleConfirm} onChange={handleChange} />
            {/* Upstream energy — narrative source-of-truth, editable */}
            <InlineField fieldKey="power_mw" label="Power" value={fieldVal("power_mw")} verification={vf("power_mw").verification} source={vf("power_mw").source} unit="MW" type="number" isDraft={isDraft("power_mw")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="power_source" label="Source" value={fieldVal("power_source")} verification={vf("power_source").verification} type="select" options={["wind","solar","hybrid","hydro","nuclear","grid"]} isDraft={isDraft("power_source")} highlighted={contradictionFields.has("power_source")} onConfirm={handleConfirm} onChange={handleChange} />
            {/* Grid topology: off-grid BTM needs grid-independence evidence; on-grid needs ≥1 PPA */}
            <InlineField fieldKey="power_model" label="Grid model" value={fieldVal("power_model")} verification={vf("power_model").verification} source={vf("power_model").source} type="select" options={["OFF_GRID_BTM","GRID_CONNECTED","HYBRID"]} isDraft={isDraft("power_model")} highlighted={contradictionFields.has("power_model")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="ppas" label="PPAs" value={fieldVal("ppas")} verification={vf("ppas").verification} source={vf("ppas").source} isDraft={isDraft("ppas")} highlighted={contradictionFields.has("ppas")} onConfirm={handleConfirm} onChange={handleChange} />
            {/* Electrolyser — narrative source-of-truth, editable */}
            <InlineField fieldKey="electrolyser_mw" label="Electrolyser" value={fieldVal("electrolyser_mw")} verification={vf("electrolyser_mw").verification} source={vf("electrolyser_mw").source} unit="MW" type="number" isDraft={isDraft("electrolyser_mw")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="electrolyser_tech" label="Tech" value={fieldVal("electrolyser_tech")} verification={vf("electrolyser_tech").verification} type="select" options={["PEM","AEM","SOEC","alkaline"]} isDraft={isDraft("electrolyser_tech")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="status" label="Status" value={fieldVal("status")} verification={vf("status").verification} type="select" options={STATUS_OPTIONS} isDraft={isDraft("status")} highlighted={contradictionFields.has("status")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="phase" label="Phase" value={fieldVal("phase")} verification={vf("phase").verification} source={vf("phase").source} isDraft={isDraft("phase")} highlighted={contradictionFields.has("phase")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="construction_start" label="Const. start" value={fieldVal("construction_start")} verification={vf("construction_start").verification} type="number" isDraft={isDraft("construction_start")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="completion_date" label="Target COD" value={fieldVal("completion_date")} verification={vf("completion_date").verification} type="date" isDraft={isDraft("completion_date")} highlighted={contradictionFields.has("completion_date")} onConfirm={handleConfirm} onChange={handleChange} />
            {/* Certification readiness — links to /finance/cert-readiness, chips show count + worst-status */}
            <DetailLinkRow
              kind="CERTIFICATION"
              path="/finance/cert-readiness"
              projectId={project.id}
              hasAccess={hasPathAccess("/finance/cert-readiness")}
              description={(project.certifications ?? [])
                .map(c => `${c.scheme}${c.status === 'ACTIVE' ? '' : ` (${c.status.toLowerCase()})`}`)
                .join(' · ') || 'No certifications declared'}
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
          </FieldSection>

          {/* Financial */}
          <FieldSection title="Financial" collapsible>
            <InlineField fieldKey="capex_eur" label="CAPEX" value={fieldVal("capex_eur")} verification={vf("capex_eur").verification} source={vf("capex_eur").source} unit={String(fieldVal("capex_currency"))} type="number" isDraft={isDraft("capex_eur")} highlighted={contradictionFields.has("capex_eur")} onConfirm={handleConfirm} onChange={handleChange} />
            <InlineField fieldKey="capex_currency" label="Currency" value={fieldVal("capex_currency")} verification={vf("capex_currency").verification} type="select" options={["EUR","USD","GBP","JPY","CHF","CAD","AUD"]} isDraft={isDraft("capex_currency")} highlighted={contradictionFields.has("capex_currency")} onConfirm={handleConfirm} onChange={handleChange} />
            <DetailLinkRow
              kind="READINESS"
              path="/finance/bankability"
              projectId={project.id}
              hasAccess={hasPathAccess("/finance/bankability")}
              description="Bankability cockpit, role-scoped evidence"
              chip={{
                text: `${project.bankability.overall_completion}%`,
                tone: project.bankability.overall_completion >= 80 ? 'live'
                    : project.bankability.overall_completion >= 50 ? 'info'
                    : 'warn',
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
                text: `${project.bankability.capital_status.filter(c => c.is_unlocked).length}/${project.bankability.capital_status.length} UNLOCKED`,
                tone: project.bankability.capital_status.every(c => c.is_unlocked) ? 'live'
                    : project.bankability.capital_status.some(c => c.is_unlocked) ? 'info'
                    : 'warn',
                title: 'Capital tranches with their gating gates satisfied',
              }}
            />
            <DetailLinkRow
              kind="MODEL"
              path="/dscr-sensitivity"
              projectId={project.id}
              hasAccess={hasPathAccess("/dscr-sensitivity")}
              description="DSCR & financing sensitivities"
              chip={{
                text: project.status === 'operating' ? 'POST-COD' : 'PRE-COD',
                tone: project.status === 'operating' ? 'live' : 'info',
                title: project.status === 'operating'
                  ? 'Realized DSCR is the primary covenant metric post-COD'
                  : 'Projected / scenario DSCR — a first-class pre-COD bankability metric for financial-close assessment. Restricted because it is debt-fragility sensitive, not because it is irrelevant pre-COD.',
              }}
            />
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
                  description={it.tooltip ?? 'Read-only analytics — not a top-nav action for your role'}
                />
              ))}
            </FieldSection>
          )}

          {/* Description — derived from structured fields (Option A) */}
          <FieldSection title="Description">
            <RenderedNarrativeBlock
              rendered={renderedNarrative}
              fallbackText={String(legacyFallback ?? '')}
              structuredFieldCount={structuredFieldCount}
            />
            <NarrativeSourceLine intelligence={profileIntelligence} />
          </FieldSection>

          {/* Bankability (read-only summary) */}
          <FieldSection title="Bankability">
            <div className="grid grid-cols-[112px_minmax(0,1fr)] items-center gap-1 border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]">
              <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-muted)]">Completion</span>
              <span className="font-mono text-[12px] font-bold tabular-nums text-[var(--text-primary)]">
                {blockedByDealKillers ? (
                  <span className="text-rose-500">BLOCKED</span>
                ) : (
                  <>{project.bankability.overall_completion}%</>
                )}
              </span>
            </div>
            <div className="grid grid-cols-[112px_minmax(0,1fr)] items-center gap-1 border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]">
              <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-muted)]">Gates</span>
              <span className="font-mono text-[12px] tabular-nums text-[var(--text-primary)]">
                {project.bankability.gates.filter((g) => g.is_complete).length}/{project.bankability.gates.length}
              </span>
            </div>
            <div className="grid grid-cols-[112px_minmax(0,1fr)] items-center gap-1 border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]">
              <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-muted)]">Capital tranches</span>
              <span className="font-mono text-[12px] tabular-nums text-[var(--text-primary)]">
                {project.bankability.capital_status.length}
              </span>
            </div>
            <div className="grid grid-cols-[112px_minmax(0,1fr)] items-center gap-1 border border-transparent px-1 py-[2px] hover:bg-[#F8FAFC]">
              <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-muted)]">Next milestone</span>
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
            <path d="M3 2 L7 5 L3 8" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
        <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-black dark:text-white">
          {title}
        </span>
      </button>
      {(!collapsible || open) && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-x-6 gap-y-0">{children}</div>
      )}
    </div>
  );
}
