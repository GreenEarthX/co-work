// Screen: Shared component — Dashboard, Production screens
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";
import { useSelectedProject } from "@/contexts/ProjectContext";
import { useUserRole } from "@/contexts/UserRoleContext";
import { canAccessGate } from "@/config/gateAccess";

// ═══════════════════════════════════════════════════════════════
// GANTT ITEM → ROUTE NAVIGATION MAP
// ═══════════════════════════════════════════════════════════════
// Maps Gantt item IDs to the screen the user should land on when clicking.
// Only items the user has role-rights to view will render as clickable.

const GANTT_NAV: Record<string, string> = {
  G0: "/projects",                 // Site Rights → Project detail
  G1: "/projects",                 // Grid Connection → Project detail
  G2: "/cert-readiness",           // RFNBO Certification → Cert Readiness
  G3: "/offtaker-supply",          // Feedstock & Logistics → Purchase
  G4: "/offtake-quality",          // Binding Offtake → Offtake Quality
  G5: "/projects",                 // EPC & Construction → Project detail
  G7: "/insurance-schedule",       // Insurance Program → Insurance Schedule
  G8: "/finance-dashboard",        // Financial Model → Finance Dashboard
  G9: "/projects",                 // Permits & Regulatory → Project detail
  G10: "/finance-dashboard",       // Financial Close → Finance Dashboard
  G11: "/projects",                // COD → Project detail
  MS_DFI: "/finance-dashboard",    // DFI Mandate → Finance Dashboard
  MS_TERM_SHEET: "/term-sheet",    // Term Sheet Executed → Term Sheet Tracker
  MS_FID: "/finance-dashboard",    // FID Decision → Finance Dashboard
  MS_NTP: "/projects",             // NTP Issued → Project detail
  MS_COMM_OPS: "/marketplace",     // Commercial Operations → Commercial Overview
  MS_FIRST_GOO: "/cert-readiness", // First GoO → Cert Readiness
};

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

export type WorkspaceId =
  | "producer"
  | "finance"
  | "trader"
  | "regulator"
  | "executive";

interface GanttItem {
  id: string;
  name: string;
  phase: "ADVISORY" | "BUILD" | "FIN_CLOSE" | "CONSTRUCTION" | "OPERATIONS";
  startQ: number; // 0-based quarter index (0 = Q1 2026)
  durationQ: number;
  type: "gate" | "milestone";
  gateId?: string; // matches BankabilityGate.id in customerProjects.ts
  defaultCompletion: number; // fallback if no gate data
}

// ═══════════════════════════════════════════════════════════════
// MODULE-LEVEL CONSTANTS
// ═══════════════════════════════════════════════════════════════

const ALL_GANTT_ITEMS: GanttItem[] = [
  // ── ADVISORY PHASE ──────────────────────────────────────────
  {
    id: "G0",
    name: "Site Rights (G0)",
    phase: "ADVISORY",
    startQ: 0,
    durationQ: 2,
    type: "gate",
    gateId: "G0_SITE_RIGHTS",
    defaultCompletion: 90,
  },
  {
    id: "G1",
    name: "Grid Connection (G1)",
    phase: "ADVISORY",
    startQ: 1,
    durationQ: 4,
    type: "gate",
    gateId: "G1_GRID_UTILITIES",
    defaultCompletion: 60,
  },
  {
    id: "G2",
    name: "RFNBO Certification (G2)",
    phase: "ADVISORY",
    startQ: 1,
    durationQ: 5,
    type: "gate",
    gateId: undefined,
    defaultCompletion: 55,
  },
  {
    id: "G3",
    name: "Feedstock & Logistics (G3)",
    phase: "ADVISORY",
    startQ: 0,
    durationQ: 3,
    type: "gate",
    gateId: undefined,
    defaultCompletion: 75,
  },
  {
    id: "G4",
    name: "Binding Offtake (G4)",
    phase: "ADVISORY",
    startQ: 2,
    durationQ: 4,
    type: "gate",
    gateId: undefined,
    defaultCompletion: 65,
  },
  {
    id: "G9",
    name: "Permits & Regulatory (G9)",
    phase: "ADVISORY",
    startQ: 0,
    durationQ: 6,
    type: "gate",
    gateId: undefined,
    defaultCompletion: 80,
  },
  {
    id: "MS_DFI",
    name: "DFI Mandate Letter",
    phase: "ADVISORY",
    startQ: 1,
    durationQ: 2,
    type: "milestone",
    gateId: undefined,
    defaultCompletion: 50,
  },
  // ── BUILD PHASE ─────────────────────────────────────────────
  {
    id: "G5",
    name: "EPC & Construction (G5)",
    phase: "BUILD",
    startQ: 3,
    durationQ: 5,
    type: "gate",
    gateId: "G5_EPC_RISK_PRICED",
    defaultCompletion: 40,
  },
  {
    id: "G6",
    name: "IE Signoff (G6)",
    phase: "BUILD",
    startQ: 4,
    durationQ: 3,
    type: "gate",
    gateId: undefined,
    defaultCompletion: 20,
  },
  {
    id: "G7",
    name: "Insurance Program (G7)",
    phase: "BUILD",
    startQ: 3,
    durationQ: 2,
    type: "gate",
    gateId: undefined,
    defaultCompletion: 35,
  },
  {
    id: "MS_EPC_EXEC",
    name: "EPC Contract Executed",
    phase: "BUILD",
    startQ: 3,
    durationQ: 1,
    type: "milestone",
    gateId: undefined,
    defaultCompletion: 45,
  },
  {
    id: "MS_INSURANCE",
    name: "CAR/DSU Insurance Placed",
    phase: "BUILD",
    startQ: 4,
    durationQ: 1,
    type: "milestone",
    gateId: undefined,
    defaultCompletion: 30,
  },
  // ── FINANCIAL CLOSE PHASE ───────────────────────────────────
  {
    id: "G8",
    name: "Financial Model (G8)",
    phase: "FIN_CLOSE",
    startQ: 4,
    durationQ: 3,
    type: "gate",
    gateId: undefined,
    defaultCompletion: 50,
  },
  {
    id: "G10",
    name: "Financial Close (G10)",
    phase: "FIN_CLOSE",
    startQ: 6,
    durationQ: 2,
    type: "gate",
    gateId: undefined,
    defaultCompletion: 10,
  },
  {
    id: "MS_TERM_SHEET",
    name: "Term Sheet Executed",
    phase: "FIN_CLOSE",
    startQ: 5,
    durationQ: 1,
    type: "milestone",
    gateId: undefined,
    defaultCompletion: 0,
  },
  {
    id: "MS_FID",
    name: "FID Decision",
    phase: "FIN_CLOSE",
    startQ: 6,
    durationQ: 1,
    type: "milestone",
    gateId: undefined,
    defaultCompletion: 0,
  },
  // ── CONSTRUCTION PHASE ──────────────────────────────────────
  {
    id: "MS_NTP",
    name: "NTP Issued",
    phase: "CONSTRUCTION",
    startQ: 7,
    durationQ: 1,
    type: "milestone",
    gateId: undefined,
    defaultCompletion: 0,
  },
  {
    id: "MS_ELECTRO",
    name: "Electrolyser Delivery",
    phase: "CONSTRUCTION",
    startQ: 8,
    durationQ: 1,
    type: "milestone",
    gateId: undefined,
    defaultCompletion: 0,
  },
  {
    id: "MS_FAT",
    name: "Factory Acceptance Test",
    phase: "CONSTRUCTION",
    startQ: 9,
    durationQ: 1,
    type: "milestone",
    gateId: undefined,
    defaultCompletion: 0,
  },
  // ── OPERATIONS PHASE ────────────────────────────────────────
  {
    id: "G11",
    name: "COD (G11)",
    phase: "OPERATIONS",
    startQ: 10,
    durationQ: 1,
    type: "gate",
    gateId: undefined,
    defaultCompletion: 0,
  },
  {
    id: "MS_COMM_OPS",
    name: "Commercial Operations",
    phase: "OPERATIONS",
    startQ: 10,
    durationQ: 1,
    type: "milestone",
    gateId: undefined,
    defaultCompletion: 0,
  },
  {
    id: "MS_FIRST_GOO",
    name: "First GoO Issuance",
    phase: "OPERATIONS",
    startQ: 11,
    durationQ: 1,
    type: "milestone",
    gateId: undefined,
    defaultCompletion: 0,
  },
];

const DEFAULT_WORKSPACE_VISIBILITY: Record<WorkspaceId, string[]> = {
  producer: [
    "G0",
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "G7",
    "G8",
    "G9",
    "G10",
    "G11",
    "MS_DFI",
    "MS_EPC_EXEC",
    "MS_INSURANCE",
    "MS_TERM_SHEET",
    "MS_FID",
    "MS_NTP",
    "MS_ELECTRO",
    "MS_FAT",
    "MS_COMM_OPS",
    "MS_FIRST_GOO",
  ],
  finance: [
    "G4",
    "G7",
    "G8",
    "G9",
    "G10",
    "G11",
    "MS_DFI",
    "MS_TERM_SHEET",
    "MS_FID",
    "MS_NTP",
    "MS_COMM_OPS",
  ],
  trader: [
    "G4",
    "G11",
    "MS_TERM_SHEET",
    "MS_NTP",
    "MS_COMM_OPS",
    "MS_FIRST_GOO",
  ],
  regulator: ["G2", "G9", "G11", "MS_FAT", "MS_COMM_OPS", "MS_FIRST_GOO"],
  executive: [
    "G5",
    "G8",
    "G10",
    "G11",
    "MS_DFI",
    "MS_TERM_SHEET",
    "MS_FID",
    "MS_COMM_OPS",
  ],
};

const PHASE_CONFIG = {
  ADVISORY: {
    label: "Advisory",
    color: "bg-stone-100",
    border: "border-stone-200",
    text: "text-stone-700",
  },
  BUILD: {
    label: "Build",
    color: "bg-slate-100",
    border: "border-slate-200",
    text: "text-slate-700",
  },
  FIN_CLOSE: {
    label: "Financial Close",
    color: "bg-zinc-100",
    border: "border-zinc-200",
    text: "text-zinc-700",
  },
  CONSTRUCTION: {
    label: "Construction",
    color: "bg-neutral-100",
    border: "border-neutral-200",
    text: "text-neutral-700",
  },
  OPERATIONS: {
    label: "Operations",
    color: "bg-stone-100",
    border: "border-stone-200",
    text: "text-stone-700",
  },
};

const PHASE_ORDER: Array<GanttItem["phase"]> = [
  "ADVISORY",
  "BUILD",
  "FIN_CLOSE",
  "CONSTRUCTION",
  "OPERATIONS",
];

const QUARTERS = [
  "Q1'26",
  "Q2'26",
  "Q3'26",
  "Q4'26",
  "Q1'27",
  "Q2'27",
  "Q3'27",
  "Q4'27",
  "Q1'28",
  "Q2'28",
  "Q3'28",
  "Q4'28",
];
const TOTAL_Q = QUARTERS.length; // 12

// Current quarter index: Q1 2026 = index 0
const CURRENT_Q_INDEX = 0;

// ═══════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════

export function ProductionRoadmapGantt({
  workspaceId,
  compact,
}: {
  workspaceId: WorkspaceId;
  compact?: boolean;
}) {
  const navigate = useNavigate();
  const { selectedProjectId } = useSelectedProject();
  const { role } = useUserRole();
  const { projects: visibleProjects } = useVisibleProjects();
  const project =
    visibleProjects.find((p) => p.id === selectedProjectId) ??
    visibleProjects[visibleProjects.length - 1];

  const [visibility, setVisibility] = useState<Record<WorkspaceId, string[]>>(
    DEFAULT_WORKSPACE_VISIBILITY,
  );
  const [collapsedPhases, setCollapsedPhases] = useState<Set<string>>(
    new Set(),
  );
  const [tooltip, setTooltip] = useState<{
    id: string;
    x: number;
    y: number;
  } | null>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("gex_gantt_visibility");
      if (saved) setVisibility(JSON.parse(saved));
    } catch {}
  }, []);

  const visibleIds =
    visibility[workspaceId] ?? DEFAULT_WORKSPACE_VISIBILITY[workspaceId];

  const canViewItem = useMemo(() => {
    const visibleMilestonesByRole = new Set<string>();

    if (
      role.business_function === "EXECUTIVE" ||
      role.business_function === "FINANCE_TREASURY" ||
      role.business_function === "ENGINEERING"
    ) {
      ALL_GANTT_ITEMS.filter((item) => item.type === "milestone").forEach(
        (item) => visibleMilestonesByRole.add(item.id),
      );
    }

    if (role.company_type === "OFFTAKER") {
      ["MS_TERM_SHEET", "MS_COMM_OPS", "MS_FIRST_GOO"].forEach((id) =>
        visibleMilestonesByRole.add(id),
      );
    }

    if (role.company_type === "PRODUCER") {
      [
        "MS_DFI",
        "MS_EPC_EXEC",
        "MS_INSURANCE",
        "MS_TERM_SHEET",
        "MS_FID",
        "MS_NTP",
        "MS_ELECTRO",
        "MS_FAT",
        "MS_COMM_OPS",
        "MS_FIRST_GOO",
      ].forEach((id) => visibleMilestonesByRole.add(id));
    }

    return (item: GanttItem) => {
      if (!visibleIds.includes(item.id)) return false;
      if (item.type === "milestone")
        return visibleMilestonesByRole.has(item.id);
      if (item.gateId) return canAccessGate(role, item.gateId);
      return canAccessGate(role, item.id);
    };
  }, [role, visibleIds]);

  const canViewCompletion = useMemo(() => {
    const permittedMilestones = new Set<string>();

    if (
      role.business_function === "EXECUTIVE" ||
      role.business_function === "FINANCE_TREASURY" ||
      role.business_function === "ENGINEERING"
    ) {
      ALL_GANTT_ITEMS.filter((item) => item.type === "milestone").forEach(
        (item) => permittedMilestones.add(item.id),
      );
    }

    if (role.company_type === "OFFTAKER") {
      ["MS_TERM_SHEET", "MS_COMM_OPS", "MS_FIRST_GOO"].forEach((id) =>
        permittedMilestones.add(id),
      );
    }

    return (item: GanttItem) => {
      if (item.type === "milestone") return permittedMilestones.has(item.id);
      if (
        role.business_function === "EXECUTIVE" ||
        role.business_function === "FINANCE_TREASURY" ||
        role.business_function === "ENGINEERING"
      ) {
        return true;
      }
      if (item.gateId) return canAccessGate(role, item.gateId);
      return canAccessGate(role, item.id);
    };
  }, [role]);

  const items = ALL_GANTT_ITEMS.filter(canViewItem).sort(
    (a, b) => a.startQ - b.startQ,
  );

  // Group by phase preserving canonical order
  const grouped = PHASE_ORDER.reduce<Record<string, GanttItem[]>>(
    (acc, phase) => {
      const phaseItems = items.filter((i) => i.phase === phase);
      if (phaseItems.length > 0) acc[phase] = phaseItems;
      return acc;
    },
    {},
  );

  function getCompletion(item: GanttItem): number {
    if (item.gateId) {
      const gate = project.bankability.gates.find((g) => g.id === item.gateId);
      if (gate) return gate.completion_pct;
    }
    return Math.round(
      item.defaultCompletion * (project.bankability.overall_completion / 75),
    );
  }

  const rightsSummary =
    role.company_type === "OFFTAKER" && role.business_function === "COMMERCIAL"
      ? "Task percentages and drilldown are limited to offtake-relevant milestones and visible gates."
      : "Percent complete and task drilldown follow the current user role.";

  function togglePhase(phase: string) {
    setCollapsedPhases((prev) => {
      const next = new Set(prev);
      if (next.has(phase)) next.delete(phase);
      else next.add(phase);
      return next;
    });
  }

  const LEFT_COL_W = compact ? 180 : 220;
  const BAR_H = compact ? 20 : 28;
  const ROW_H = compact ? 28 : 36;
  const PHASE_HEADER_H = compact ? 24 : 32;
  const FONT_SIZE = compact ? "text-xs" : "text-sm";
  const LABEL_FONT = compact ? "text-[10px]" : "text-xs";

  // Workspace badge colour
  const workspaceBadgeColour: Record<WorkspaceId, string> = {
    producer: "bg-stone-100 text-stone-700 border-stone-200",
    finance: "bg-slate-100 text-slate-700 border-slate-200",
    trader: "bg-zinc-100 text-zinc-700 border-zinc-200",
    regulator: "bg-neutral-100 text-neutral-700 border-neutral-200",
    executive: "bg-slate-100 text-slate-800 border-slate-300",
  };

  return (
    <div className="flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden select-none">
      {/* ── Header ── */}
      <div
        className={`flex items-center justify-between px-4 ${compact ? "py-2" : "py-3"} border-b border-slate-200 bg-slate-50`}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`font-semibold text-slate-800 truncate ${compact ? "text-sm" : "text-base"}`}
          >
            {project.name}
          </span>
          <span className="text-slate-400 hidden sm:inline">·</span>
          <span
            className={`hidden sm:inline font-medium text-slate-500 ${compact ? "text-xs" : "text-sm"}`}
          >
            Production Roadmap
          </span>
          <span
            className={`ml-1 px-1.5 py-0.5 rounded border font-medium uppercase tracking-wide ${LABEL_FONT} ${workspaceBadgeColour[workspaceId]}`}
          >
            {workspaceId}
          </span>
        </div>

        {/* Legend */}
        {!compact && (
          <div className="flex items-center gap-3 shrink-0">
            <LegendItem
              swatch={
                <div className="w-8 h-3 rounded-sm bg-gray-200 border border-gray-300" />
              }
              label="Not started"
            />
            <LegendItem
              swatch={
                <div
                  className="w-8 h-3 rounded-sm border border-gray-300"
                  style={{
                    background:
                      "linear-gradient(to right, #a8d5a2 50%, #e5e7eb 50%)",
                  }}
                />
              }
              label="In progress"
            />
            <LegendItem
              swatch={
                <div
                  className="w-8 h-3 rounded-sm border border-green-500"
                  style={{ background: "#a8d5a2" }}
                />
              }
              label="Complete"
            />
            <LegendItem
              swatch={
                <span className="text-amber-500 font-bold text-base leading-none">
                  ◆
                </span>
              }
              label="Milestone"
            />
          </div>
        )}
      </div>

      <div className="px-4 py-2 border-b border-slate-200 bg-white text-[11px] text-slate-600">
        {rightsSummary}
      </div>

      {/* ── Chart body ── */}
      <div className="overflow-x-auto">
        <div style={{ minWidth: LEFT_COL_W + 600 }}>
          {/* Quarter header row */}
          <div className="flex border-b border-slate-200 bg-slate-50">
            <div
              className={`shrink-0 border-r border-slate-200 ${LABEL_FONT} font-semibold text-slate-500 flex items-center px-3`}
              style={{ width: LEFT_COL_W, minHeight: compact ? 28 : 36 }}
            >
              TASK
            </div>
            <div className="flex-1 relative flex">
              {QUARTERS.map((q) => (
                <div
                  key={q}
                  className={`flex-1 text-center border-r border-slate-100 last:border-r-0 ${LABEL_FONT} font-medium text-slate-500 py-1`}
                >
                  {q}
                </div>
              ))}
            </div>
          </div>

          {/* Phase groups */}
          {PHASE_ORDER.filter((phase) => grouped[phase]).map((phase) => {
            const cfg = PHASE_CONFIG[phase];
            const isCollapsed = collapsedPhases.has(phase);
            const phaseItems = grouped[phase];

            return (
              <div key={phase}>
                {/* Phase group header */}
                <div
                  className={`flex items-center cursor-pointer ${cfg.color} border-b ${cfg.border}`}
                  style={{ minHeight: PHASE_HEADER_H }}
                  onClick={() => togglePhase(phase)}
                >
                  <div
                    className={`shrink-0 flex items-center gap-1 px-3 border-r ${cfg.border}`}
                    style={{ width: LEFT_COL_W }}
                  >
                    <span className={`${cfg.text} ${LABEL_FONT}`}>
                      {isCollapsed ? (
                        <ChevronRight className="w-3.5 h-3.5 inline" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5 inline" />
                      )}
                    </span>
                    {!compact && (
                      <span
                        className={`font-semibold uppercase tracking-wide ${cfg.text} text-xs ml-0.5`}
                      >
                        {cfg.label}
                      </span>
                    )}
                  </div>
                  <div className="flex-1" />
                </div>

                {/* Items */}
                {!isCollapsed &&
                  phaseItems.map((item) => {
                    const completion = getCompletion(item);
                    const leftPct = (item.startQ / TOTAL_Q) * 100;
                    const widthPct = (item.durationQ / TOTAL_Q) * 100;
                    const showPct = widthPct > 6 && canViewCompletion(item);
                    const tooltipAllowed = canViewCompletion(item);
                    const tooltipText = tooltipAllowed
                      ? `${item.name} — ${completion}% complete`
                      : `${item.name} — detail restricted by role`;

                    return (
                      <div
                        key={item.id}
                        className="flex items-center border-b border-slate-100 hover:bg-slate-50 group relative"
                        style={{ minHeight: ROW_H }}
                      >
                        {/* Task name column — clickable when route exists */}
                        <div
                          className={`shrink-0 flex items-center px-3 border-r border-slate-200 ${FONT_SIZE} font-medium truncate ${GANTT_NAV[item.id] ? "text-slate-900 hover:underline cursor-pointer" : "text-slate-700"}`}
                          style={{ width: LEFT_COL_W, height: ROW_H }}
                          title={GANTT_NAV[item.id] ? `Open ${item.name}` : item.name}
                          onClick={() => { const route = GANTT_NAV[item.id]; if (route) navigate(route); }}
                        >
                          <span className="truncate">{item.name}</span>
                          {GANTT_NAV[item.id] && <ChevronRight className="w-3 h-3 ml-auto shrink-0 text-slate-400" />}
                        </div>

                        {/* Timeline column */}
                        <div
                          className="flex-1 relative"
                          style={{ height: ROW_H }}
                        >
                          {/* Quarter grid lines */}
                          {QUARTERS.map((_, qi) => (
                            <div
                              key={qi}
                              className="absolute top-0 bottom-0 border-r border-slate-100"
                              style={{ left: `${((qi + 1) / TOTAL_Q) * 100}%` }}
                            />
                          ))}

                          {/* Current quarter marker (Q1 2026) */}
                          <div
                            className="absolute top-0 bottom-0 border-l-2 border-blue-400 border-dashed z-10"
                            style={{
                              left: `${(CURRENT_Q_INDEX / TOTAL_Q) * 100}%`,
                            }}
                          />

                          {/* Bar or Milestone diamond */}
                          {item.type === "milestone" ? (
                            <MilestoneDiamond
                              item={item}
                              leftPct={leftPct}
                              widthPct={widthPct}
                              completion={completion}
                              barH={BAR_H}
                              rowH={ROW_H}
                              compact={!!compact}
                              navigable={!!GANTT_NAV[item.id]}
                              onClick={() => { const route = GANTT_NAV[item.id]; if (route) navigate(route); }}
                              onMouseEnter={(e) => {
                                if (!compact) {
                                  setTooltip({
                                    id: item.id,
                                    x: e.clientX,
                                    y: e.clientY,
                                  });
                                }
                              }}
                              onMouseMove={(e) => {
                                if (!compact && tooltip?.id === item.id) {
                                  setTooltip({
                                    id: item.id,
                                    x: e.clientX,
                                    y: e.clientY,
                                  });
                                }
                              }}
                              onMouseLeave={() => setTooltip(null)}
                              tooltipText={tooltipText}
                            />
                          ) : (
                            <GanttBar
                              item={item}
                              leftPct={leftPct}
                              widthPct={widthPct}
                              completion={completion}
                              barH={BAR_H}
                              rowH={ROW_H}
                              showPct={showPct}
                              compact={!!compact}
                              navigable={!!GANTT_NAV[item.id]}
                              onClick={() => { const route = GANTT_NAV[item.id]; if (route) navigate(route); }}
                              onMouseEnter={(e) => {
                                if (!compact) {
                                  setTooltip({
                                    id: item.id,
                                    x: e.clientX,
                                    y: e.clientY,
                                  });
                                }
                              }}
                              onMouseMove={(e) => {
                                if (!compact && tooltip?.id === item.id) {
                                  setTooltip({
                                    id: item.id,
                                    x: e.clientX,
                                    y: e.clientY,
                                  });
                                }
                              }}
                              onMouseLeave={() => setTooltip(null)}
                              tooltipText={tooltipText}
                            />
                          )}
                        </div>
                      </div>
                    );
                  })}
              </div>
            );
          })}
        </div>
      </div>

      {/* Floating tooltip */}
      {tooltip && !compact && (
        <TooltipOverlay
          tooltipId={tooltip.id}
          x={tooltip.x}
          y={tooltip.y}
          items={items}
          getCompletion={getCompletion}
          canViewCompletion={canViewCompletion}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════════════

interface BarProps {
  item: GanttItem;
  leftPct: number;
  widthPct: number;
  completion: number;
  barH: number;
  rowH: number;
  showPct: boolean;
  compact: boolean;
  navigable: boolean;
  onClick?: () => void;
  onMouseEnter: (e: React.MouseEvent) => void;
  onMouseMove: (e: React.MouseEvent) => void;
  onMouseLeave: () => void;
  tooltipText: string;
}

function GanttBar({
  leftPct,
  widthPct,
  completion,
  barH,
  rowH,
  showPct,
  compact,
  navigable,
  onClick,
  onMouseEnter,
  onMouseMove,
  onMouseLeave,
}: BarProps) {
  const barStyle: React.CSSProperties = {
    position: "absolute",
    left: `${leftPct}%`,
    width: `${widthPct}%`,
    height: barH,
    top: (rowH - barH) / 2,
    background:
      completion === 0
        ? "#e5e7eb"
        : `linear-gradient(to right, #a8d5a2 ${completion}%, #e5e7eb ${completion}%)`,
    border: completion === 100 ? "1px solid #6abf69" : "1px solid #d1d5db",
    borderRadius: 4,
    overflow: "hidden",
    display: "flex",
    alignItems: "center",
    paddingLeft: 4,
    paddingRight: 4,
    cursor: navigable ? "pointer" : "default",
    transition: "opacity 0.15s",
    zIndex: 5,
  };

  return (
    <div
      style={barStyle}
      onClick={navigable ? onClick : undefined}
      onMouseEnter={onMouseEnter}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
    >
      {showPct && (
        <span
          className="truncate font-medium text-slate-700 leading-none pointer-events-none"
          style={{ fontSize: compact ? 9 : 10 }}
        >
          {completion}%
        </span>
      )}
    </div>
  );
}

interface DiamondProps {
  item: GanttItem;
  leftPct: number;
  widthPct: number;
  completion: number;
  barH: number;
  rowH: number;
  compact: boolean;
  navigable: boolean;
  onClick?: () => void;
  onMouseEnter: (e: React.MouseEvent) => void;
  onMouseMove: (e: React.MouseEvent) => void;
  onMouseLeave: () => void;
  tooltipText: string;
}

function MilestoneDiamond({
  leftPct,
  widthPct,
  completion,
  rowH,
  compact,
  navigable,
  onClick,
  onMouseEnter,
  onMouseMove,
  onMouseLeave,
}: DiamondProps) {
  const diamondColor =
    completion === 100 ? "#6abf69" : completion > 0 ? "#f59e0b" : "#9ca3af";

  const centerLeftPct = leftPct + widthPct / 2;
  const size = compact ? 14 : 18;

  return (
    <div
      style={{
        position: "absolute",
        left: `calc(${centerLeftPct}% - ${size / 2}px)`,
        top: (rowH - size) / 2,
        width: size,
        height: size,
        transform: "rotate(45deg)",
        background: diamondColor,
        border: `1.5px solid ${completion === 100 ? "#4a9e48" : completion > 0 ? "#d97706" : "#6b7280"}`,
        borderRadius: 2,
        cursor: navigable ? "pointer" : "default",
        zIndex: 5,
      }}
      onClick={navigable ? onClick : undefined}
      onMouseEnter={onMouseEnter}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
    />
  );
}

function LegendItem({
  swatch,
  label,
}: {
  swatch: React.ReactNode;
  label: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex items-center justify-center">{swatch}</div>
      <span className="text-xs text-slate-500">{label}</span>
    </div>
  );
}

function TooltipOverlay({
  tooltipId,
  x,
  y,
  items,
  getCompletion,
  canViewCompletion,
}: {
  tooltipId: string;
  x: number;
  y: number;
  items: GanttItem[];
  getCompletion: (item: GanttItem) => number;
  canViewCompletion: (item: GanttItem) => boolean;
}) {
  const item = items.find((i) => i.id === tooltipId);
  if (!item) return null;
  const completion = getCompletion(item);

  return (
    <div
      className="fixed z-50 pointer-events-none"
      style={{ left: x + 12, top: y - 36 }}
    >
      <div className="bg-white text-black text-xs rounded-md px-2.5 py-1.5 shadow-lg whitespace-nowrap border border-slate-200">
        {canViewCompletion(item)
          ? `${item.name} — ${completion}% complete`
          : `${item.name} — detail restricted by role`}
      </div>
    </div>
  );
}
