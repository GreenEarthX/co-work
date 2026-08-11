// Screen: Main dashboard screen (/dashboard)
import { useState, useEffect } from "react";
import { ProductionRoadmapGantt } from "@/components/gantt/ProductionRoadmapGantt";
import { GreenFuelThread } from "@/components/dashboard/GreenFuelThread";
import {
  ProjectInFocusSelector,
  ProjectTruthChain,
} from "@/components/dashboard/ProjectTruthChain";
import { DashSection, SectionMeta } from "@/components/dashboard/DashSection";
import MoleculeLineage from "@/features/pricing/MoleculeLineage";
import { RefreshCw, Filter, ChevronRight, AlertTriangle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { capacitiesAPI, offersAPI, tokensAPI, matchingAPI } from "@/lib/api";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";
import { DecisionFirstEntry } from "@/components/DecisionFirstEntry";
import { useUserRole } from "@/contexts/UserRoleContext";
import { useSelectedProject } from "@/contexts/ProjectContext";

interface ProjectFlow {
  id: string;
  name: string;
  molecule: string;
  stage1_capacity: number;
  stage2_tokenised: number;
  stage3_market: number;
  stage3_matched: number;
  capacityIds: string[];
}


// ─── Deal-killer counting ────────────────────────────────────────────────────
// This tile previously reported `overall_completion < 40` — i.e. it counted
// PROJECTS BELOW A COMPLETION THRESHOLD and labelled them deal-killers. A
// project at 52% therefore reported "DEAL KILLERS 0" while the Critical Path
// screen, reading the same project's gate blockers, reported "3 fatal · 1
// critical". Two screens in the same workspace disagreeing on the number a
// credit committee cares about most is the fastest way to lose an analyst.
//
// Count the blocking items themselves, from the gates that carry them — the
// same source the blocker-isolation view uses.
function countBlockingItems(projects: { bankability: { gates: { is_complete: boolean; blocking_items: string[] }[] } }[]): number {
  return projects.reduce(
    (total, p) =>
      total +
      (p.bankability?.gates ?? [])
        .filter((g) => !g.is_complete)
        .reduce((n, g) => n + (g.blocking_items?.length ?? 0), 0),
    0,
  )
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { projects: visibleProjects } = useVisibleProjects();
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject();
  const { role } = useUserRole();
  const [projects, setProjects] = useState<ProjectFlow[]>([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [aggregates, setAggregates] = useState({
    totalCapacity: 0,
    totalTokenised: 0,
    totalMarket: 0,
    totalMatches: 0,
    conversionRate: 0,
  });

  useEffect(() => {
    if (visibleProjects.length > 0) {
      loadData();
    }
  }, [visibleProjects]); // re-run when backend delivers visible projects

  const loadData = async () => {
    setLoading(true);
    setErrors([]);
    const errs: string[] = [];

    // Load each API independently — don't let one failure kill the whole dashboard
    let capacities: any[] = [];
    let tokens: any[] = [];
    let offers: any[] = [];
    let matches: any[] = [];

    try {
      const res = await capacitiesAPI.list();
      capacities =
        res.capacities || res.data || (Array.isArray(res) ? res : []);
    } catch {
      errs.push("capacities");
    }

    try {
      const res = await tokensAPI.list();
      tokens = res.tokens || res.data || (Array.isArray(res) ? res : []);
    } catch {
      errs.push("tokens");
    }

    try {
      const res = await offersAPI.list();
      offers = res.offers || res.data || (Array.isArray(res) ? res : []);
    } catch {
      errs.push("offers");
    }

    try {
      const res = await matchingAPI.list();
      matches = res.matches || res.data || (Array.isArray(res) ? res : []);
    } catch {
      errs.push("matches");
    }

    // Build project map from whatever data we got
    const projectMap = new Map<string, ProjectFlow>();

    capacities.forEach((cap: any) => {
      const pname = cap.project_name || cap.name || "Unknown Project";
      if (!projectMap.has(pname)) {
        projectMap.set(pname, {
          id: cap.project_id || cap.asset_id || pname,
          name: pname,
          molecule: cap.molecule || cap.product || "H2",
          stage1_capacity: 0,
          stage2_tokenised: 0,
          stage3_market: 0,
          stage3_matched: 0,
          capacityIds: [],
        });
      }
      const proj = projectMap.get(pname)!;
      proj.stage1_capacity += cap.capacity_mtpd || cap.volume || 0;
      proj.capacityIds.push(cap.id);
    });

    // Map tokens to projects
    tokens.forEach((tok: any) => {
      const capId = tok.capacity_id;
      for (const proj of projectMap.values()) {
        if (proj.capacityIds.includes(capId)) {
          proj.stage2_tokenised += tok.volume_mt || tok.volume || 0;
          break;
        }
      }
    });

    // Map offers to projects
    offers.forEach((off: any) => {
      const pname = off.project || off.project_name;
      if (pname && projectMap.has(pname)) {
        const proj = projectMap.get(pname)!;
        proj.stage3_market += parseFloat(off.volume || "0");
      }
    });

    // Align to the user's visible projects — merge API flow data where available,
    // fall back to static registry values so the list is always complete.
    const projectsArray = visibleProjects.map((cp) => {
      const fromMap = projectMap.get(cp.name);
      return fromMap
        ? { ...fromMap, id: cp.id }
        : {
            id: cp.id,
            name: cp.name,
            molecule: cp.molecule,
            stage1_capacity: cp.capacity_mtpd,
            stage2_tokenised: Math.round(cp.capacity_mtpd * 0.6),
            stage3_market: Math.round(cp.capacity_mtpd * 0.35),
            stage3_matched: Math.round(cp.capacity_mtpd * 0.2),
            capacityIds: [cp.id],
          };
    });

    setProjects(projectsArray);
    setErrors(errs);

    const totalCap = projectsArray.reduce((s, p) => s + p.stage1_capacity, 0);
    const totalMarket = projectsArray.reduce((s, p) => s + p.stage3_market, 0);

    setAggregates({
      totalCapacity: totalCap,
      totalTokenised: projectsArray.reduce((s, p) => s + p.stage2_tokenised, 0),
      totalMarket: totalMarket,
      totalMatches: matches.length,
      conversionRate: totalCap > 0 ? (totalMarket / totalCap) * 100 : 0,
    });

    setLoading(false);
  };

  const filteredProjects =
    selectedProjectId === "all"
      ? projects
      : projects.filter((p) => p.id === selectedProjectId);
  const scopedVisibleProjects =
    selectedProjectId === "all"
      ? visibleProjects
      : visibleProjects.filter((p) => p.id === selectedProjectId);
  const scopedTotalCapacity = filteredProjects.reduce(
    (s, p) => s + p.stage1_capacity,
    0,
  );
  const scopedTotalMarket = filteredProjects.reduce(
    (s, p) => s + p.stage3_market,
    0,
  );
  const scopedAggregates = {
    totalCapacity: scopedTotalCapacity,
    totalTokenised: filteredProjects.reduce(
      (s, p) => s + p.stage2_tokenised,
      0,
    ),
    totalMarket: scopedTotalMarket,
    totalMatches:
      selectedProjectId === "all"
        ? aggregates.totalMatches
        : filteredProjects.reduce((s, p) => s + p.stage3_matched, 0),
    conversionRate:
      scopedTotalCapacity > 0
        ? (scopedTotalMarket / scopedTotalCapacity) * 100
        : 0,
  };

  const roadmapWorkspace =
    role.business_function === "EXECUTIVE"
      ? "executive"
      : role.company_type === "OFFTAKER"
        ? "trader"
        : role.business_function === "FINANCE_TREASURY"
          ? "finance"
          : role.business_function === "COMPLIANCE_LEGAL"
            ? "regulator"
            : "producer";

  const blockingCount = countBlockingItems(scopedVisibleProjects);

  return (
    <div className="space-y-3">
      {/* CLIENT JOURNEY START — identity banner, always visible */}
      <ProjectInFocusSelector />

      {/* DECISION-FIRST ENTRY — the headline answer, never collapsed */}
      <DecisionFirstEntry />

      {/* PROJECT TRUTH FRONT DOOR */}
      <DashSection
        id="truth-chain"
        title="Project truth chain"
        defaultOpen
        meta={
          <SectionMeta
            value={blockingCount}
            label="blocking"
            tone={blockingCount > 0 ? "bad" : "neutral"}
          />
        }
      >
        <ProjectTruthChain />
      </DashSection>

      {/* HEADER WITH FILTERS */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-600 mt-1">
            {role.company_type === "OFFTAKER"
              ? "Offtake portfolio & project tracking"
              : role.company_type === "THIRD_PARTY" &&
                  role.service_type === "BANK"
                ? "Due diligence & bankability overview"
                : role.business_function === "EXECUTIVE"
                  ? "Portfolio performance & readiness"
                  : "Production flow & conversion metrics"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-400" />
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium bg-white"
            >
              <option value="all">All Projects</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 hover:bg-gray-100 rounded-lg"
          >
            <RefreshCw
              className={`w-5 h-5 text-gray-600 ${loading ? "animate-spin" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* API WARNINGS (non-blocking) */}
      {errors.length > 0 && (
        <div className="flex flex-col gap-3 px-4 py-3 bg-stone-50 border border-stone-200 rounded-lg text-sm text-stone-700 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>
              Some live feeds are unavailable ({errors.join(", ")}). Read-only
              values are shown from the data already loaded.
            </span>
          </div>
          {role.business_function !== "COMPLIANCE_LEGAL" &&
            selectedProjectId !== "all" && (
              <button
                type="button"
                onClick={() => navigate(`/projects/${selectedProjectId}/edit`)}
                className="inline-flex items-center justify-center rounded-md border border-stone-300 bg-white px-3 py-2 text-xs font-semibold text-stone-900 hover:bg-stone-100"
              >
                Update project info
              </button>
            )}
        </div>
      )}

      {/* AGGREGATE KPIs — role-contextual */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {(() => {
          // ── Derive role-appropriate KPIs ──────────────────────
          const isOfftaker = role.company_type === "OFFTAKER";
          const isBank =
            role.company_type === "THIRD_PARTY" && role.service_type === "BANK";
          const isFinance = role.business_function === "FINANCE_TREASURY";
          const isExec = role.business_function === "EXECUTIVE";

          // Offtaker-specific metrics derived from scoped projects
          if (isOfftaker) {
            const activeOfftakes = scopedVisibleProjects.filter((p) => {
              const g4 = p.bankability.gates.find(
                (g) => g.id === "G4_OFFTAKE_BANKABLE",
              );
              return g4 && g4.completion_pct > 0;
            }).length;
            const avgOfftakeQuality =
              scopedVisibleProjects.length > 0
                ? Math.round(
                    scopedVisibleProjects.reduce((s, p) => {
                      const g4 = p.bankability.gates.find(
                        (g) => g.id === "G4_OFFTAKE_BANKABLE",
                      );
                      return s + (g4?.completion_pct ?? 0);
                    }, 0) / scopedVisibleProjects.length,
                  )
                : 0;
            const molecules = [
              ...new Set(scopedVisibleProjects.map((p) => p.molecule)),
            ];

            return [
              {
                label: "Active Offtakes",
                value: `${activeOfftakes}`,
                link: "/offtake-quality",
              },
              {
                label: "Projects Tracked",
                value: `${scopedVisibleProjects.length}`,
                link: "/marketplace",
              },
              {
                label: "Avg Offtake Readiness",
                value: `${avgOfftakeQuality}%`,
                link: "/offtake-quality",
              },
              {
                label: "Molecules Covered",
                value: `${molecules.length}`,
                link: "/offtaker-supply",
              },
            ];
          }

          // Bank / third-party finance
          if (isBank) {
            const avgBankability =
              scopedVisibleProjects.length > 0
                ? Math.round(
                    scopedVisibleProjects.reduce(
                      (s, p) => s + p.bankability.overall_completion,
                      0,
                    ) / scopedVisibleProjects.length,
                  )
                : 0;
            const dealKillers = countBlockingItems(scopedVisibleProjects);

            return [
              {
                label: "Projects Reviewed",
                value: `${scopedVisibleProjects.length}`,
                link: "/bankability-scores",
              },
              {
                label: "Avg Bankability",
                value: `${avgBankability}%`,
                link: "/bankability-scores",
              },
              {
                label: "Deal Killers",
                value: `${dealKillers}`,
                link: "/bankability-scores",
              },
              {
                label: "Pending Close",
                value: `${scopedVisibleProjects.filter((p) => p.status === "construction" || p.status === "operating").length}`,
                link: "/finance-dashboard",
              },
            ];
          }

          // Finance treasury
          if (isFinance) {
            return [
              {
                label: "Total Capacity",
                value: `${scopedAggregates.totalCapacity.toFixed(0)} MTPD`,
                link: "/capacity",
              },
              {
                label: "On Market",
                value: `${scopedAggregates.totalMarket.toFixed(0)} MT`,
                link: "/marketplace",
              },
              {
                label: "Conversion",
                value: `${scopedAggregates.conversionRate.toFixed(1)}%`,
                link: "/finance-dashboard",
              },
              {
                label: "Matches",
                value: `${scopedAggregates.totalMatches}`,
                link: "/matching",
              },
            ];
          }

          // Executive
          if (isExec) {
            const avgBankability =
              scopedVisibleProjects.length > 0
                ? Math.round(
                    scopedVisibleProjects.reduce(
                      (s, p) => s + p.bankability.overall_completion,
                      0,
                    ) / scopedVisibleProjects.length,
                  )
                : 0;

            return [
              {
                label: "Portfolio Size",
                value: `${scopedVisibleProjects.length}`,
                link: "/bankability-scores",
              },
              {
                label: "Total Capacity",
                value: `${scopedAggregates.totalCapacity.toFixed(0)} MTPD`,
                link: "/capacity",
              },
              {
                label: "Avg Bankability",
                value: `${avgBankability}%`,
                link: "/bankability-scores",
              },
              {
                label: "Conversion",
                value: `${scopedAggregates.conversionRate.toFixed(1)}%`,
                link: "/finance-dashboard",
              },
            ];
          }

          // Default: Producer pipeline
          return [
            {
              label: "Total Capacity",
              value: `${scopedAggregates.totalCapacity.toFixed(0)} MTPD`,
              link: "/capacity",
            },
            {
              label: "Tokenised",
              value: `${scopedAggregates.totalTokenised.toFixed(0)} MT`,
              link: undefined,
            },
            {
              label: "On Market",
              value: `${scopedAggregates.totalMarket.toFixed(0)} MT`,
              link: "/marketplace",
            },
            {
              label: "Conversion",
              value: `${scopedAggregates.conversionRate.toFixed(1)}%`,
              link: undefined,
            },
          ];
        })().map((kpi) => (
          <div
            key={kpi.label}
            className={`bg-white rounded-xl border border-slate-200 p-4 ${kpi.link ? "cursor-pointer hover:border-slate-400 transition-colors" : ""}`}
            onClick={() => kpi.link && navigate(kpi.link)}
          >
            <div className="flex items-center justify-between">
              <div className="text-xs font-bold text-gray-500 uppercase">
                {kpi.label}
              </div>
              {kpi.link && (
                <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
              )}
            </div>
            <div className="text-2xl font-black text-slate-900 mt-1">
              {kpi.value}
            </div>
          </div>
        ))}
      </div>

      {/* LOADING STATE */}
      {loading && (
        <div className="text-center py-12 text-gray-500">
          <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-slate-500" />
          Loading project data...
        </div>
      )}

      {/* EMPTY STATE */}
      {!loading && projects.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <h3 className="text-lg font-bold text-gray-900 mb-2">
            No Projects Yet
          </h3>
          <p className="text-gray-600 mb-4">
            Create your first project to see it here.
          </p>
          <button
            onClick={() => navigate("/capacity")}
            className="px-6 py-2 bg-slate-900 text-white rounded-lg font-semibold hover:bg-slate-800"
          >
            Create Capacity
          </button>
        </div>
      )}

      {/* PROJECT CARDS — the longest block, so collapsed by default */}
      {!loading && filteredProjects.length > 0 && (
      <DashSection
        id="project-cards"
        title="Project detail"
        meta={
          <SectionMeta value={filteredProjects.length} label="projects" />
        }
      >
      <div className="space-y-4">
      {filteredProjects.map((project) => (
        <div
          key={project.name}
          className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm"
        >
          <div className="px-6 py-4 bg-gray-50 border-b border-gray-100 flex justify-between items-center">
            <div>
              <h2 className="text-xl font-black text-gray-900">
                {project.name}
              </h2>
              <span className="text-sm text-gray-500">{project.molecule}</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-xs text-gray-500 uppercase tracking-wider">
                  {role.company_type === "OFFTAKER"
                    ? "Capacity"
                    : "Total Pipeline"}
                </div>
                <div className="text-3xl font-black text-slate-900">
                  {project.stage1_capacity.toFixed(0)}{" "}
                  <span className="text-sm">MTPD</span>
                </div>
              </div>
              <button
                onClick={() =>
                  navigate(`/projects?name=${encodeURIComponent(project.name)}`)
                }
                className="p-2 hover:bg-gray-200 rounded-lg"
                title="View project details"
              >
                <ChevronRight className="w-5 h-5 text-gray-400" />
              </button>
            </div>
          </div>

          <div className="p-6">
            {(() => {
              // ── Role-contextual project card stages ──
              const isOfftaker = role.company_type === "OFFTAKER";
              const isBank =
                role.company_type === "THIRD_PARTY" &&
                role.service_type === "BANK";

              // Find matching canonical project for bankability data
              const cp = visibleProjects.find((p) => p.name === project.name);
              const g4 = cp?.bankability.gates.find(
                (g) => g.id === "G4_OFFTAKE_BANKABLE",
              );
              const g4Pct = g4?.completion_pct ?? 0;
              const bankPct = cp?.bankability.overall_completion ?? 0;

              if (isOfftaker) {
                // Offtaker perspective: Available → Offtake Status → Contract Stage → Delivery
                const contractStage =
                  g4Pct >= 90
                    ? "CONTRACTED"
                    : g4Pct >= 60
                      ? "TERM SHEET"
                      : g4Pct >= 30
                        ? "LOI"
                        : "EOI";
                return (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                      <div className="space-y-2">
                        <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                          <span>1. Available</span>
                        </div>
                        <div className="text-3xl font-black text-gray-900">
                          {project.stage1_capacity.toFixed(0)}
                          <span className="text-sm font-normal text-gray-400 ml-1">
                            MTPD
                          </span>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                          <span>2. Offtake Readiness</span>
                        </div>
                        <div className="text-3xl font-black text-gray-900">
                          {g4Pct}
                          <span className="text-sm font-normal text-gray-400 ml-1">
                            %
                          </span>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                          <span>3. Contract Stage</span>
                        </div>
                        <div className="text-lg font-black text-gray-900">
                          {contractStage}
                        </div>
                      </div>
                      <div className="space-y-2">
                        <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                          <span>4. Bankability</span>
                        </div>
                        <div className="text-3xl font-black text-gray-900">
                          {bankPct}
                          <span className="text-sm font-normal text-gray-400 ml-1">
                            %
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 flex items-center gap-1 h-2">
                      <div
                        className="bg-slate-700 h-full rounded-l"
                        style={{ width: "100%" }}
                        title="Available"
                      />
                      <div
                        className="bg-slate-500 h-full"
                        style={{ width: `${g4Pct}%` }}
                        title="Offtake"
                      />
                      <div
                        className="bg-stone-400 h-full rounded-r"
                        style={{ width: `${bankPct}%` }}
                        title="Bankability"
                      />
                    </div>
                  </>
                );
              }

              if (isBank) {
                // Bank perspective: Project Size → Bankability → Evidence → Risk
                const evidencePct = Math.min(100, Math.round(bankPct * 1.1));
                const riskLevel =
                  bankPct >= 75 ? "LOW" : bankPct >= 50 ? "MEDIUM" : "HIGH";
                return (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                      <div className="space-y-2">
                        <div className="text-xs font-bold text-gray-500 uppercase">
                          1. Project Size
                        </div>
                        <div className="text-3xl font-black text-gray-900">
                          {project.stage1_capacity.toFixed(0)}
                          <span className="text-sm font-normal text-gray-400 ml-1">
                            MTPD
                          </span>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs font-bold text-gray-500 uppercase">
                          2. Bankability
                        </div>
                        <div className="text-3xl font-black text-gray-900">
                          {bankPct}
                          <span className="text-sm font-normal text-gray-400 ml-1">
                            %
                          </span>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs font-bold text-gray-500 uppercase">
                          3. Evidence
                        </div>
                        <div className="text-3xl font-black text-gray-900">
                          {evidencePct}
                          <span className="text-sm font-normal text-gray-400 ml-1">
                            %
                          </span>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs font-bold text-gray-500 uppercase">
                          4. Risk Level
                        </div>
                        <div className="text-lg font-black text-gray-900">
                          {riskLevel}
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 flex items-center gap-1 h-2">
                      <div
                        className="bg-slate-700 h-full rounded-l"
                        style={{ width: "100%" }}
                        title="Size"
                      />
                      <div
                        className="bg-slate-500 h-full"
                        style={{ width: `${bankPct}%` }}
                        title="Bankability"
                      />
                      <div
                        className="bg-stone-400 h-full rounded-r"
                        style={{ width: `${evidencePct}%` }}
                        title="Evidence"
                      />
                    </div>
                  </>
                );
              }

              // Default: Producer pipeline
              return (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                    <div className="space-y-2">
                      <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                        <span>1. Capacity</span>
                        <span className="text-slate-600">Created</span>
                      </div>
                      <div className="text-3xl font-black text-gray-900">
                        {project.stage1_capacity.toFixed(0)}
                        <span className="text-sm font-normal text-gray-400 ml-1">
                          MTPD
                        </span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                        <span>2. Tokenised</span>
                        <span
                          className={
                            project.stage2_tokenised > 0
                              ? "text-slate-700"
                              : "text-gray-400"
                          }
                        >
                          {project.stage2_tokenised > 0 ? "Active" : "Pending"}
                        </span>
                      </div>
                      <div className="text-3xl font-black text-gray-900">
                        {project.stage2_tokenised > 0
                          ? project.stage2_tokenised.toFixed(0)
                          : "—"}
                        <span className="text-sm font-normal text-gray-400 ml-1">
                          MT
                        </span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                        <span>3. On Market</span>
                        <span
                          className={
                            project.stage3_market > 0
                              ? "text-slate-700"
                              : "text-gray-400"
                          }
                        >
                          {project.stage3_market > 0 ? "Live" : "—"}
                        </span>
                      </div>
                      <div className="text-3xl font-black text-gray-900">
                        {project.stage3_market > 0
                          ? project.stage3_market.toFixed(0)
                          : "—"}
                        <span className="text-sm font-normal text-gray-400 ml-1">
                          MT
                        </span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                        <span>4. Matched</span>
                        <span className="text-gray-400">
                          {project.stage3_matched > 0 ? "Active" : "—"}
                        </span>
                      </div>
                      <div className="text-3xl font-black text-gray-900">
                        {project.stage3_matched > 0
                          ? project.stage3_matched.toFixed(0)
                          : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 flex items-center gap-1 h-2">
                    <div
                      className="bg-slate-700 h-full rounded-l"
                      style={{ width: "100%" }}
                      title="Capacity"
                    />
                    <div
                      className="bg-slate-500 h-full"
                      style={{
                        width: `${project.stage1_capacity > 0 ? (project.stage2_tokenised / project.stage1_capacity) * 100 : 0}%`,
                      }}
                      title="Tokenised"
                    />
                    <div
                      className="bg-stone-500 h-full"
                      style={{
                        width: `${project.stage1_capacity > 0 ? (project.stage3_market / project.stage1_capacity) * 100 : 0}%`,
                      }}
                      title="Market"
                    />
                    <div
                      className="bg-stone-300 h-full rounded-r"
                      style={{
                        width: `${project.stage1_capacity > 0 ? (project.stage3_matched / project.stage1_capacity) * 100 : 0}%`,
                      }}
                      title="Matched"
                    />
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      ))}
      </div>
      </DashSection>
      )}

      {/* GREEN FUEL THREAD — Hidalgo crystallization view */}
      {!loading && scopedVisibleProjects.length > 0 && (
        <DashSection id="green-fuel-thread" title="Green fuel thread">
          <GreenFuelThread projects={scopedVisibleProjects} />
        </DashSection>
      )}

      {/* INFORMATION LINEAGE — Bloomberg view for Finance/Bank roles */}
      {!loading &&
        (role.business_function === "FINANCE_TREASURY" ||
          role.service_type === "BANK" ||
          role.service_type === "INSURER" ||
          role.business_function === "EXECUTIVE") && (
          <DashSection id="molecule-lineage" title="Information lineage">
            <MoleculeLineage compact />
          </DashSection>
        )}

      {/* READINESS SUMMARY — role-contextual */}
      <DashSection id="readiness-summary" title="Readiness summary">
      <div className="bg-stone-50 rounded-xl border border-stone-200 p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-bold text-gray-900">
              {role.company_type === "OFFTAKER"
                ? "Offtake Readiness"
                : role.company_type === "THIRD_PARTY" &&
                    role.service_type === "BANK"
                  ? "Due Diligence Status"
                  : "Banking Readiness"}
            </h3>
            <p className="text-sm text-gray-600">
              {role.company_type === "OFFTAKER"
                ? "Contract & delivery readiness across tracked projects"
                : role.company_type === "THIRD_PARTY" &&
                    role.service_type === "BANK"
                  ? "Bankability assessment across reviewed projects"
                  : "Institutional financing metrics across portfolio"}
            </p>
          </div>
          <button
            onClick={() =>
              navigate(
                role.company_type === "OFFTAKER"
                  ? "/offtake-quality"
                  : "/finance-dashboard",
              )
            }
            className="text-sm text-slate-800 hover:underline font-semibold flex items-center gap-1"
          >
            {role.company_type === "OFFTAKER"
              ? "Offtake Quality"
              : "Finance Dashboard"}{" "}
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {(() => {
            const isOfftaker = role.company_type === "OFFTAKER";
            const isBank =
              role.company_type === "THIRD_PARTY" &&
              role.service_type === "BANK";

            if (isOfftaker) {
              const avgG4 =
                scopedVisibleProjects.length > 0
                  ? Math.round(
                      scopedVisibleProjects.reduce((s, p) => {
                        const g4 = p.bankability.gates.find(
                          (g) => g.id === "G4_OFFTAKE_BANKABLE",
                        );
                        return s + (g4?.completion_pct ?? 0);
                      }, 0) / scopedVisibleProjects.length,
                    )
                  : 0;
              const contracted = scopedVisibleProjects.filter((p) => {
                const g4 = p.bankability.gates.find(
                  (g) => g.id === "G4_OFFTAKE_BANKABLE",
                );
                return g4 && g4.completion_pct >= 90;
              }).length;
              return [
                {
                  label: "Offtake Score",
                  value: `${avgG4}%`,
                  pct: avgG4,
                  color: "bg-slate-700",
                },
                {
                  label: "Contracted",
                  value: `${contracted}/${scopedVisibleProjects.length}`,
                  pct:
                    scopedVisibleProjects.length > 0
                      ? (contracted / scopedVisibleProjects.length) * 100
                      : 0,
                  color: "bg-slate-700",
                },
                {
                  label: "Feedstock Ready",
                  value: `${Math.round(avgG4 * 0.85)}%`,
                  pct: Math.round(avgG4 * 0.85),
                  color: "bg-stone-500",
                },
                {
                  label: "Delivery Points",
                  value: `${scopedVisibleProjects.length}`,
                  pct: 100,
                  color: "bg-slate-700",
                },
              ];
            }
            if (isBank) {
              const avgBank =
                scopedVisibleProjects.length > 0
                  ? Math.round(
                      scopedVisibleProjects.reduce(
                        (s, p) => s + p.bankability.overall_completion,
                        0,
                      ) / scopedVisibleProjects.length,
                    )
                  : 0;
              const ready = scopedVisibleProjects.filter(
                (p) => p.bankability.overall_completion >= 70,
              ).length;
              const dealKillers = countBlockingItems(scopedVisibleProjects);
              return [
                {
                  label: "Avg Bankability",
                  value: `${avgBank}%`,
                  pct: avgBank,
                  color: "bg-slate-700",
                },
                {
                  label: "Finance Ready",
                  value: `${ready}/${scopedVisibleProjects.length}`,
                  pct:
                    scopedVisibleProjects.length > 0
                      ? (ready / scopedVisibleProjects.length) * 100
                      : 0,
                  color: "bg-slate-700",
                },
                {
                  label: "Evidence",
                  value: `${Math.min(100, Math.round(avgBank * 1.1))}%`,
                  pct: Math.min(100, Math.round(avgBank * 1.1)),
                  color: "bg-stone-500",
                },
                {
                  label: "Deal Killers",
                  value: `${dealKillers}`,
                  pct: dealKillers > 0 ? 30 : 100,
                  color: dealKillers > 0 ? "bg-amber-500" : "bg-slate-700",
                },
              ];
            }
            return [
              { label: "DSCR", value: "1.35x", pct: 92, color: "bg-slate-700" },
              {
                label: "Evidence",
                value: "96%",
                pct: 96,
                color: "bg-slate-700",
              },
              {
                label: "Offtake",
                value: "72%",
                pct: 72,
                color: "bg-stone-500",
              },
              {
                label: "Permits",
                value: "Done",
                pct: 100,
                color: "bg-slate-700",
              },
            ];
          })().map((metric) => (
            <div key={metric.label}>
              <div className="text-sm text-gray-600 mb-1">{metric.label}</div>
              <div className="text-xl font-black text-gray-900">
                {metric.value}
              </div>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
                <div
                  className={`${metric.color} h-1.5 rounded-full`}
                  style={{ width: `${metric.pct}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
      </DashSection>

      {/* ── Production Roadmap Gantt ─────────────────────────── */}
      <DashSection id="production-roadmap" title="Production roadmap">
        <ProductionRoadmapGantt workspaceId={roadmapWorkspace} compact />
      </DashSection>
    </div>
  );
}
