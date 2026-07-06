// Screen: Evidence hierarchy screen (/evidence-hierarchy, /finance/evidence-hierarchy)
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Info } from "lucide-react";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { HELP } from "@/config/helpText";
import { useSelectedProject } from "@/contexts/ProjectContext";
import { useUserRole } from "@/contexts/UserRoleContext";
import {
  type CustomerProject,
  getProjectById,
  CUSTOMER_PROJECTS,
} from "@/data/customerProjects";
import {
  DealKillerBanner,
  useActiveKillers,
} from "@/components/DealKillerBanner";
import { getVisibleGateShortIds } from "@/config/gateAccess";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";

type VerificationState = "AUDITED" | "CONFIRMED" | "SUBMITTED" | "UNVERIFIED";
type ProjectDataFilter = "all" | "with_active_data" | "without_active_data";

interface GateSummaryRow {
  gate_id: string;
  AUDITED: number;
  CONFIRMED: number;
  SUBMITTED: number;
  UNVERIFIED: number;
  total: number;
  raw_score: number;
  effective_score: number;
}

interface GateOwner {
  name: string;
  role: string;
}

interface ProjectGateDrilldown {
  projectId: string;
  projectName: string;
  molecule: CustomerProject["molecule"];
  geography: string;
  projectSizeMt: number;
  owners: GateOwner[];
  statusCounts: Record<VerificationState, number>;
  rawScore: number;
  effectiveScore: number;
  solved: number;
  pending: number;
  unresolved: number;
  blockers: string[];
}

interface GateAggregateRow extends GateSummaryRow {
  gateLabel: string;
  projectCount: number;
  molecules: string[];
  geographies: string[];
  owners: GateOwner[];
  solved: number;
  pending: number;
  unresolved: number;
  projects: ProjectGateDrilldown[];
}

interface ManagementOwnerLoad {
  name: string;
  role: string;
  openItems: number;
  gateCount: number;
  projectCount: number;
}

interface ManagementPriorityGate {
  gateId: string;
  gateLabel: string;
  unresolved: number;
  projectCount: number;
  owners: GateOwner[];
}

interface ManagementSummary {
  gatesRequiringIntervention: number;
  projectsWithIssues: number;
  unresolvedTopics: number;
  priorityGates: ManagementPriorityGate[];
  priorityOwners: ManagementOwnerLoad[];
}

const GATE_NAMES: Record<string, string> = {
  G0: "Site & Rights",
  G1: "Grid & Utilities",
  G2: "Certification Path",
  G3: "Key Inputs",
  G4: "Offtake Bankable",
  G5: "EPC Risk Priced",
  G6: "IE Sign-off",
  G7: "Insurance Bound",
  G8: "Audit-Grade Model",
  G9: "Permits Complete",
  G10: "Financial Close",
  G11: "COD / Stabilization",
};

const GATE_OWNER_MAP: Record<string, GateOwner[]> = {
  G0: [
    { name: "Elena Bauer", role: "Permitting Lead" },
    { name: "Marco Silva", role: "Project Counsel" },
  ],
  G1: [
    { name: "Thomas Adler", role: "Grid Manager" },
    { name: "Claire Moreau", role: "Infrastructure Lead" },
  ],
  G2: [
    { name: "Sofia Klein", role: "Certification Lead" },
    { name: "Jonas Iversen", role: "Sustainability Manager" },
  ],
  G3: [
    { name: "Luc Martin", role: "Supply Manager" },
    { name: "Nina Costa", role: "Logistics Lead" },
  ],
  G4: [
    { name: "Marie Dupont", role: "Commercial Lead" },
    { name: "Ahmed Al-Rashid", role: "Offtake Manager" },
  ],
  G5: [
    { name: "Stefan Koch", role: "EPC Lead" },
    { name: "Laura Neri", role: "Risk Engineer" },
  ],
  G6: [
    { name: "David Hofer", role: "Independent Engineer" },
    { name: "Anne Fischer", role: "Technical Reviewer" },
  ],
  G7: [
    { name: "Julien Mercier", role: "Insurance Lead" },
    { name: "Hannah Ortiz", role: "Broker Coordinator" },
  ],
  G8: [
    { name: "Peter Novak", role: "Model Owner" },
    { name: "Sarah Lang", role: "Finance Controller" },
  ],
  G9: [
    { name: "Marta Ruiz", role: "Regulatory Counsel" },
    { name: "Jonas Iversen", role: "Compliance Lead" },
  ],
  G10: [
    { name: "Claire Moreau", role: "Transaction Lead" },
    { name: "Peter Novak", role: "Treasury Sponsor" },
  ],
  G11: [
    { name: "Thomas Adler", role: "Operations Sponsor" },
    { name: "Elena Bauer", role: "Commissioning Lead" },
  ],
};

const STATUS_WEIGHT: Record<VerificationState, number> = {
  AUDITED: 1,
  CONFIRMED: 0.85,
  SUBMITTED: 0.5,
  UNVERIFIED: 0.25,
};

function shortGateId(gateId: string): string {
  const match = gateId.match(/^G\d+/);
  return match ? match[0] : gateId;
}

function uniqueBy<T>(items: T[], keyFn: (item: T) => string): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = keyFn(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function deriveStatusCounts(
  totalEvidence: number,
  verifiedCount: number,
  blockers: string[],
  isComplete: boolean,
): Record<VerificationState, number> {
  const audited =
    verifiedCount === 0 ? 0 : isComplete ? Math.min(2, verifiedCount) : 1;
  const confirmed = Math.max(verifiedCount - audited, 0);
  const unresolved = Math.min(
    Math.max(totalEvidence - verifiedCount, 0),
    Math.max(blockers.length, 1),
  );
  const submitted = Math.max(
    totalEvidence - audited - confirmed - unresolved,
    0,
  );

  return {
    AUDITED: audited,
    CONFIRMED: confirmed,
    SUBMITTED: submitted,
    UNVERIFIED: Math.max(totalEvidence - audited - confirmed - submitted, 0),
  };
}

function computeEffectiveScore(
  rawScore: number,
  counts: Record<VerificationState, number>,
): number {
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  if (total === 0) return 0;

  const weighted =
    counts.AUDITED * STATUS_WEIGHT.AUDITED +
    counts.CONFIRMED * STATUS_WEIGHT.CONFIRMED +
    counts.SUBMITTED * STATUS_WEIGHT.SUBMITTED +
    counts.UNVERIFIED * STATUS_WEIGHT.UNVERIFIED;

  return Math.round(rawScore * (weighted / total));
}

function gateRawScore(
  project: CustomerProject,
  gate: CustomerProject["bankability"]["gates"][number],
): number {
  const baseScore = gate.completion_pct;
  const projectModifier =
    project.bankability.overall_completion >= 70
      ? 6
      : project.bankability.overall_completion >= 50
        ? 3
        : 0;
  return Math.min(100, baseScore + projectModifier);
}

function buildGateRows(
  projects: CustomerProject[],
  visibleGateIds: Set<string>,
): GateAggregateRow[] {
  const aggregate = new Map<string, GateAggregateRow>();

  projects.forEach((project) => {
    project.bankability.gates.forEach((gate) => {
      const gateId = shortGateId(gate.id);
      if (!visibleGateIds.has(gateId)) return;
      const statusCounts = deriveStatusCounts(
        gate.total_evidence,
        gate.verified_count,
        gate.blocking_items,
        gate.is_complete,
      );
      const rawScore = gateRawScore(project, gate);
      const effectiveScore = computeEffectiveScore(rawScore, statusCounts);
      const projectOwners = GATE_OWNER_MAP[gateId] ?? [
        { name: "Project Team", role: "Gate Owner" },
      ];
      const projectRow: ProjectGateDrilldown = {
        projectId: project.id,
        projectName: project.name,
        molecule: project.molecule,
        geography: project.country,
        projectSizeMt: project.capacity_mtpd,
        owners: projectOwners,
        statusCounts,
        rawScore,
        effectiveScore,
        solved: statusCounts.AUDITED + statusCounts.CONFIRMED,
        pending: statusCounts.SUBMITTED,
        unresolved: statusCounts.UNVERIFIED,
        blockers: gate.blocking_items,
      };

      if (!aggregate.has(gateId)) {
        aggregate.set(gateId, {
          gate_id: gateId,
          gateLabel: GATE_NAMES[gateId] ?? gateId,
          AUDITED: 0,
          CONFIRMED: 0,
          SUBMITTED: 0,
          UNVERIFIED: 0,
          total: 0,
          raw_score: 0,
          effective_score: 0,
          projectCount: 0,
          molecules: [],
          geographies: [],
          owners: [],
          solved: 0,
          pending: 0,
          unresolved: 0,
          projects: [],
        });
      }

      const row = aggregate.get(gateId)!;
      row.AUDITED += statusCounts.AUDITED;
      row.CONFIRMED += statusCounts.CONFIRMED;
      row.SUBMITTED += statusCounts.SUBMITTED;
      row.UNVERIFIED += statusCounts.UNVERIFIED;
      row.total += gate.total_evidence;
      row.projectCount += 1;
      row.raw_score += rawScore;
      row.effective_score += effectiveScore;
      row.solved += projectRow.solved;
      row.pending += projectRow.pending;
      row.unresolved += projectRow.unresolved;
      row.molecules.push(project.molecule);
      row.geographies.push(project.country);
      row.owners.push(...projectOwners);
      row.projects.push(projectRow);
    });
  });

  Object.entries(GATE_NAMES).forEach(([gateId, gateLabel]) => {
    if (!visibleGateIds.has(gateId)) return;
    if (!aggregate.has(gateId)) {
      aggregate.set(gateId, {
        gate_id: gateId,
        gateLabel,
        AUDITED: 0,
        CONFIRMED: 0,
        SUBMITTED: 0,
        UNVERIFIED: 0,
        total: 0,
        raw_score: 0,
        effective_score: 0,
        projectCount: 0,
        molecules: [],
        geographies: [],
        owners: GATE_OWNER_MAP[gateId] ?? [],
        solved: 0,
        pending: 0,
        unresolved: 0,
        projects: [],
      });
    }
  });

  return Array.from(aggregate.values())
    .map((row) => ({
      ...row,
      molecules: Array.from(new Set(row.molecules)).sort(),
      geographies: Array.from(new Set(row.geographies)).sort(),
      owners: uniqueBy(row.owners, (owner) => `${owner.name}-${owner.role}`),
      raw_score:
        row.projectCount > 0 ? Math.round(row.raw_score / row.projectCount) : 0,
      effective_score:
        row.projectCount > 0
          ? Math.round(row.effective_score / row.projectCount)
          : 0,
    }))
    .sort((a, b) => a.effective_score - b.effective_score);
}

function metricTone(value: number, warnAt: number): string {
  if (value >= warnAt) return "text-[var(--text-primary)]";
  return "text-amber-700";
}

function buildManagementSummary(
  gateRows: GateAggregateRow[],
): ManagementSummary {
  const priorityRows = gateRows.filter(
    (row) => row.unresolved > 0 || row.effective_score < 45,
  );
  const impactedProjects = new Set<string>();
  const ownerLoad = new Map<
    string,
    ManagementOwnerLoad & { projectIds: Set<string> }
  >();

  priorityRows.forEach((row) => {
    row.projects.forEach((project) => {
      const issueLoad =
        project.unresolved + (project.effectiveScore < 45 ? 1 : 0);
      if (issueLoad <= 0) return;

      impactedProjects.add(project.projectId);
      project.owners.forEach((owner) => {
        const key = `${owner.name}-${owner.role}`;
        const current = ownerLoad.get(key);
        if (current) {
          current.openItems += issueLoad;
          current.gateCount += 1;
          current.projectIds.add(project.projectId);
          return;
        }

        ownerLoad.set(key, {
          name: owner.name,
          role: owner.role,
          openItems: issueLoad,
          gateCount: 1,
          projectCount: 1,
          projectIds: new Set([project.projectId]),
        });
      });
    });
  });

  const priorityOwners = Array.from(ownerLoad.values())
    .map(({ projectIds, ...owner }) => ({
      ...owner,
      projectCount: projectIds.size,
    }))
    .sort((a, b) => {
      if (b.openItems !== a.openItems) return b.openItems - a.openItems;
      if (b.gateCount !== a.gateCount) return b.gateCount - a.gateCount;
      return a.name.localeCompare(b.name);
    })
    .slice(0, 4);

  const priorityGates = priorityRows
    .map((row) => ({
      gateId: row.gate_id,
      gateLabel: row.gateLabel,
      unresolved: row.unresolved,
      projectCount: row.projectCount,
      owners: row.owners.slice(0, 2),
    }))
    .slice(0, 4);

  return {
    gatesRequiringIntervention: priorityRows.length,
    projectsWithIssues: impactedProjects.size,
    unresolvedTopics: priorityRows.reduce(
      (sum, row) => sum + row.unresolved,
      0,
    ),
    priorityGates,
    priorityOwners,
  };
}

function hasActiveProjectData(project: CustomerProject): boolean {
  return project.bankability.gates.some(
    (gate) =>
      gate.total_evidence > 0 ||
      gate.verified_count > 0 ||
      gate.blocking_items.length > 0 ||
      gate.completion_pct > 0,
  );
}

export default function EvidenceHierarchy() {
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject();
  const { role } = useUserRole();
  const selectedProject =
    getProjectById(selectedProjectId) ?? CUSTOMER_PROJECTS[0];
  const { projects: visibleProjects } = useVisibleProjects();
  const baseProjects =
    visibleProjects.length > 0 ? visibleProjects : [selectedProject];
  const isExecutive = role.business_function === "EXECUTIVE";
  const visibleGateIds = useMemo(() => getVisibleGateShortIds(role), [role]);
  const visibleGateLabel =
    visibleGateIds.size === Object.keys(GATE_NAMES).length
      ? "G0-G11"
      : Array.from(visibleGateIds)
          .sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)))
          .join(", ");
  const initialScope = isExecutive ? "ALL" : selectedProjectId;
  const [projectDataFilter, setProjectDataFilter] =
    useState<ProjectDataFilter>("all");
  const [scopeProjectId, setScopeProjectId] = useState<string>(initialScope);
  const [expandedGate, setExpandedGate] = useState<string | null>(null);

  const projects = useMemo(() => {
    if (projectDataFilter === "with_active_data") {
      return baseProjects.filter(hasActiveProjectData);
    }
    if (projectDataFilter === "without_active_data") {
      return baseProjects.filter((project) => !hasActiveProjectData(project));
    }
    return baseProjects;
  }, [baseProjects, projectDataFilter]);

  useEffect(() => {
    if (!isExecutive) {
      setScopeProjectId(selectedProjectId);
    }
  }, [isExecutive, selectedProjectId, projectDataFilter]);

  useEffect(() => {
    if (scopeProjectId === "ALL") return;
    const stillVisible = projects.some(
      (project) => project.id === scopeProjectId,
    );
    if (!stillVisible) {
      setScopeProjectId(
        isExecutive ? "ALL" : (projects[0]?.id ?? selectedProjectId),
      );
    }
  }, [projects, scopeProjectId, isExecutive, selectedProjectId]);

  const scopedProjects = useMemo(() => {
    if (scopeProjectId === "ALL") return projects;
    return projects.filter((project) => project.id === scopeProjectId);
  }, [projects, scopeProjectId]);

  const activeProject =
    scopeProjectId === "ALL"
      ? selectedProject
      : (scopedProjects[0] ?? selectedProject);

  const gateRows = useMemo(
    () => buildGateRows(scopedProjects, visibleGateIds),
    [scopedProjects, visibleGateIds],
  );
  const { killers } = useActiveKillers(activeProject.id);

  const totals = gateRows.reduce(
    (acc, row) => ({
      AUDITED: acc.AUDITED + row.AUDITED,
      CONFIRMED: acc.CONFIRMED + row.CONFIRMED,
      SUBMITTED: acc.SUBMITTED + row.SUBMITTED,
      UNVERIFIED: acc.UNVERIFIED + row.UNVERIFIED,
      total: acc.total + row.total,
      solved: acc.solved + row.solved,
      pending: acc.pending + row.pending,
      unresolved: acc.unresolved + row.unresolved,
    }),
    {
      AUDITED: 0,
      CONFIRMED: 0,
      SUBMITTED: 0,
      UNVERIFIED: 0,
      total: 0,
      solved: 0,
      pending: 0,
      unresolved: 0,
    },
  );

  const verifiedPct =
    totals.total > 0
      ? Math.round(((totals.AUDITED + totals.CONFIRMED) / totals.total) * 100)
      : 0;

  const scopeMeta = {
    geographies: Array.from(
      new Set(scopedProjects.map((project) => project.country)),
    ).sort(),
    molecules: Array.from(
      new Set(scopedProjects.map((project) => project.molecule)),
    ).sort(),
    projectSizes: scopedProjects.map((project) => project.capacity_mtpd),
  };

  const averageProjectSize =
    scopeMeta.projectSizes.length > 0
      ? Math.round(
          scopeMeta.projectSizes.reduce((sum, size) => sum + size, 0) /
            scopeMeta.projectSizes.length,
        )
      : 0;
  const managementSummary = useMemo(
    () => buildManagementSummary(gateRows),
    [gateRows],
  );
  const showManagementSummary =
    isExecutive && scopeProjectId === "ALL" && scopedProjects.length > 1;
  const introCopy = isExecutive
    ? "Management view for rights-scoped portfolio, accountable owners, and gate escalation."
    : role.company_type === "OFFTAKER" &&
        role.business_function === "COMMERCIAL"
      ? "Offtake readiness and supply risk across your rights-scoped projects."
      : "Gate drilldown for ABAC-scoped projects and actor-visible gates.";

  const scopeLabel =
    scopedProjects.length === 0
      ? "0 visible projects"
      : scopeProjectId === "ALL" || projectDataFilter !== "all"
        ? `${scopedProjects.length} visible project${scopedProjects.length > 1 ? "s" : ""}${scopedProjects.length === 1 ? ` · ${activeProject.name}` : ""}`
        : activeProject.name;

  return (
    <div className="max-w-7xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-lg font-bold text-[var(--text-primary)]">
            Evidence Hierarchy
          </h1>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            {introCopy}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-right">
          <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Access scope
          </div>
          <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {scopeLabel}
          </div>
          <div className="text-[11px] text-[var(--text-secondary)]">
            {role.company_type} · {role.business_function.replace(/_/g, " ")}
          </div>
          <div className="text-[11px] text-[var(--text-secondary)]">
            Gate scope · {visibleGateLabel || "none"}
          </div>
        </div>
      </div>

      {showManagementSummary ? (
        <ManagementSummaryPanel summary={managementSummary} />
      ) : (
        <DealKillerBanner killers={killers} projectName={activeProject.name} />
      )}

      <div className="gex-card rounded-2xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Project coverage
            </div>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Rights-scoped project set. Use filters to separate active and
              inactive data.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              { id: "all", label: "All data states" },
              { id: "with_active_data", label: "With active data" },
              { id: "without_active_data", label: "Without active data" },
            ].map((filter) => (
              <button
                key={filter.id}
                type="button"
                onClick={() =>
                  setProjectDataFilter(filter.id as ProjectDataFilter)
                }
                className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                  projectDataFilter === filter.id
                    ? "border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]"
                    : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)]"
                }`}
              >
                {filter.label}
              </button>
            ))}
            {isExecutive && (
              <button
                type="button"
                onClick={() => setScopeProjectId("ALL")}
                className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                  scopeProjectId === "ALL"
                    ? "border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]"
                    : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)]"
                }`}
              >
                All visible
              </button>
            )}
            {projects.map((project) => (
              <button
                key={project.id}
                type="button"
                onClick={() => {
                  setScopeProjectId(project.id);
                  setSelectedProjectId(project.id);
                }}
                className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                  scopeProjectId === project.id
                    ? "border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]"
                    : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)]"
                }`}
              >
                {project.name}
              </button>
            ))}
          </div>
        </div>

        {projects.length === 0 && (
          <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-secondary)]">
            No visible projects match the current data filter.
          </div>
        )}

        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Projects
            </div>
            <div className="mt-1 text-xl font-bold text-[var(--text-primary)]">
              {scopedProjects.length}
            </div>
            <div className="mt-1 text-xs text-[var(--text-secondary)]">
              Geographies: {scopeMeta.geographies.join(", ") || "N/A"}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Molecules
            </div>
            <div className="mt-1 text-xl font-bold text-[var(--text-primary)]">
              {scopeMeta.molecules.length}
            </div>
            <div className="mt-1 text-xs text-[var(--text-secondary)]">
              {scopeMeta.molecules.join(", ") || "N/A"}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Average Size
            </div>
            <div className="mt-1 text-xl font-bold text-[var(--text-primary)]">
              {averageProjectSize} MTPD
            </div>
            <div className="mt-1 text-xs text-[var(--text-secondary)]">
              Current rights-scoped portfolio
            </div>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Verified Share
            </div>
            <div
              className={`mt-1 text-xl font-bold ${metricTone(verifiedPct, 70)}`}
            >
              {verifiedPct}%
            </div>
            <div className="mt-1 text-xs text-[var(--text-secondary)]">
              Audited + confirmed evidence
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-5">
        {[
          { label: "Audited", count: totals.AUDITED, note: "x1.00" },
          { label: "Confirmed", count: totals.CONFIRMED, note: "x0.85" },
          { label: "Submitted", count: totals.SUBMITTED, note: "x0.50" },
          { label: "Unverified", count: totals.UNVERIFIED, note: "x0.25" },
          {
            label: "Open issues",
            count: totals.unresolved,
            note: "gate blockers",
          },
        ].map((item) => (
          <div
            key={item.label}
            className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3"
          >
            <div className="text-lg font-bold tabular-nums text-[var(--text-primary)]">
              {item.count}
            </div>
            <div className="text-xs font-semibold text-[var(--text-secondary)]">
              {item.label}
            </div>
            <div className="text-[10px] text-[var(--text-muted)]">
              {item.note}
            </div>
          </div>
        ))}
      </div>

      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[var(--border)] bg-[var(--surface-muted)]">
              <th className="w-10 px-3 py-3" />
              <th className="px-4 py-3 text-left font-semibold text-[var(--text-secondary)]">
                Gate
              </th>
              <th className="px-3 py-3 text-right font-semibold text-[var(--text-secondary)]">
                Projects
              </th>
              <th className="px-3 py-3 text-right font-semibold text-[var(--text-secondary)]">
                Solved
              </th>
              <th className="px-3 py-3 text-right font-semibold text-[var(--text-secondary)]">
                Pending
              </th>
              <th className="px-3 py-3 text-right font-semibold text-[var(--text-secondary)]">
                Unresolved
              </th>
              <th className="px-3 py-3 text-right font-semibold text-[var(--text-secondary)]">
                Audited
              </th>
              <th className="px-3 py-3 text-right font-semibold text-[var(--text-secondary)]">
                Confirmed
              </th>
              <th className="px-3 py-3 text-right font-semibold text-[var(--text-secondary)]">
                Submitted
              </th>
              <th className="px-3 py-3 text-right font-semibold text-[var(--text-secondary)]">
                Unverified
              </th>
              <th className="px-4 py-3 text-right font-semibold text-[var(--text-secondary)]">
                <div className="flex items-center justify-end gap-1">
                  Effective
                  <InfoTooltip text={HELP.EVIDENCE_HIERARCHY_EFFECTIVE} />
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            {gateRows.map((row) => {
              const isExpanded = expandedGate === row.gate_id;
              const effectiveTone =
                row.effective_score >= 70
                  ? "text-[var(--text-primary)]"
                  : row.effective_score >= 45
                    ? "text-amber-700"
                    : "text-red-700";

              return (
                <FragmentRow
                  key={row.gate_id}
                  row={row}
                  isExpanded={isExpanded}
                  effectiveTone={effectiveTone}
                  onToggle={() =>
                    setExpandedGate(isExpanded ? null : row.gate_id)
                  }
                />
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t border-[var(--border)] bg-[var(--surface-muted)]">
              <td />
              <td className="px-4 py-3 font-bold text-[var(--text-primary)]">
                Portfolio total
              </td>
              <td className="px-3 py-3 text-right font-bold tabular-nums text-[var(--text-primary)]">
                {scopedProjects.length}
              </td>
              <td className="px-3 py-3 text-right font-bold tabular-nums text-[var(--text-primary)]">
                {totals.solved}
              </td>
              <td className="px-3 py-3 text-right font-bold tabular-nums text-[var(--text-primary)]">
                {totals.pending}
              </td>
              <td className="px-3 py-3 text-right font-bold tabular-nums text-[var(--text-primary)]">
                {totals.unresolved}
              </td>
              <td className="px-3 py-3 text-right font-bold tabular-nums text-[var(--text-primary)]">
                {totals.AUDITED}
              </td>
              <td className="px-3 py-3 text-right font-bold tabular-nums text-[var(--text-primary)]">
                {totals.CONFIRMED}
              </td>
              <td className="px-3 py-3 text-right font-bold tabular-nums text-[var(--text-primary)]">
                {totals.SUBMITTED}
              </td>
              <td className="px-3 py-3 text-right font-bold tabular-nums text-[var(--text-primary)]">
                {totals.UNVERIFIED}
              </td>
              <td className="px-4 py-3 text-right font-bold text-[var(--text-primary)]">
                {verifiedPct}% verified
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="flex items-start gap-2 text-[10px] text-[var(--text-muted)]">
        <Info className="mt-0.5 h-3 w-3 flex-shrink-0" />
        <p>
          Table as drilldown entry. Expand a row to see project-level issues,
          person in charge, molecule and geography coverage, pending or
          unresolved topics.
        </p>
      </div>
    </div>
  );
}

function ManagementSummaryPanel({ summary }: { summary: ManagementSummary }) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Management view
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Portfolio summary for escalation, ownership, and cross-project gate
            concentration.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {[
          {
            label: "Gates requiring intervention",
            value: summary.gatesRequiringIntervention,
            note: "unresolved topics or weak effective score",
          },
          {
            label: "Projects carrying issues",
            value: summary.projectsWithIssues,
            note: "rights-scoped projects with open load",
          },
          {
            label: "Unresolved topics",
            value: summary.unresolvedTopics,
            note: "current blocker volume across visible gates",
          },
        ].map((item) => (
          <div
            key={item.label}
            className="rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3"
          >
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {item.label}
            </div>
            <div className="mt-1 text-xl font-bold text-[var(--text-primary)]">
              {item.value}
            </div>
            <div className="mt-1 text-xs text-[var(--text-secondary)]">
              {item.note}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-4">
          <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Priority gates
          </div>
          <div className="mt-3 space-y-2">
            {summary.priorityGates.length > 0 ? (
              summary.priorityGates.map((gate) => (
                <div
                  key={gate.gateId}
                  className="rounded-lg bg-[var(--surface)] px-3 py-2 text-xs"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold text-[var(--text-primary)]">
                      {gate.gateId} · {gate.gateLabel}
                    </div>
                    <div className="text-[var(--text-secondary)]">
                      {gate.unresolved} unresolved
                    </div>
                  </div>
                  <div className="mt-1 text-[var(--text-secondary)]">
                    {gate.projectCount} project
                    {gate.projectCount > 1 ? "s" : ""}
                    {" · "}
                    {gate.owners.map((owner) => owner.name).join(", ") ||
                      "Owner pending"}
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-lg bg-[var(--surface)] px-3 py-2 text-xs text-[var(--text-secondary)]">
                No management escalation required in the current scope.
              </div>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-4">
          <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Priority owners
          </div>
          <div className="mt-3 space-y-2">
            {summary.priorityOwners.length > 0 ? (
              summary.priorityOwners.map((owner) => (
                <div
                  key={`${owner.name}-${owner.role}`}
                  className="rounded-lg bg-[var(--surface)] px-3 py-2 text-xs"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold text-[var(--text-primary)]">
                      {owner.name}
                    </div>
                    <div className="text-[var(--text-secondary)]">
                      {owner.openItems} open items
                    </div>
                  </div>
                  <div className="mt-1 text-[var(--text-secondary)]">
                    {owner.role} · {owner.gateCount} gate
                    {owner.gateCount > 1 ? "s" : ""} · {owner.projectCount}{" "}
                    project
                    {owner.projectCount > 1 ? "s" : ""}
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-lg bg-[var(--surface)] px-3 py-2 text-xs text-[var(--text-secondary)]">
                No owner escalation required in the current scope.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function FragmentRow({
  row,
  isExpanded,
  effectiveTone,
  onToggle,
}: {
  row: GateAggregateRow;
  isExpanded: boolean;
  effectiveTone: string;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="border-b border-[var(--border)] hover:bg-[var(--surface-hover)]">
        <td className="px-3 py-3">
          <button
            type="button"
            onClick={onToggle}
            className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)]"
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="font-bold text-[var(--text-primary)]">
              {row.gate_id}
            </span>
            <span className="text-[var(--text-secondary)]">
              {row.gateLabel}
            </span>
          </div>
          <div className="mt-1 text-[10px] text-[var(--text-muted)]">
            {row.molecules.join(", ")} · {row.geographies.join(", ")}
          </div>
        </td>
        <td className="px-3 py-3 text-right font-semibold tabular-nums text-[var(--text-primary)]">
          {row.projectCount}
        </td>
        <td className="px-3 py-3 text-right font-semibold tabular-nums text-[var(--text-primary)]">
          {row.solved}
        </td>
        <td className="px-3 py-3 text-right font-semibold tabular-nums text-[var(--text-primary)]">
          {row.pending}
        </td>
        <td className="px-3 py-3 text-right font-semibold tabular-nums text-amber-700">
          {row.unresolved}
        </td>
        <td className="px-3 py-3 text-right font-semibold tabular-nums text-[var(--text-primary)]">
          {row.AUDITED}
        </td>
        <td className="px-3 py-3 text-right font-semibold tabular-nums text-[var(--text-primary)]">
          {row.CONFIRMED}
        </td>
        <td className="px-3 py-3 text-right font-semibold tabular-nums text-[var(--text-primary)]">
          {row.SUBMITTED}
        </td>
        <td className="px-3 py-3 text-right font-semibold tabular-nums text-amber-700">
          {row.UNVERIFIED}
        </td>
        <td
          className={`px-4 py-3 text-right font-bold tabular-nums ${effectiveTone}`}
        >
          {row.effective_score}
          <span className="ml-1 font-normal text-[var(--text-muted)]">
            / {row.raw_score}
          </span>
        </td>
      </tr>

      {isExpanded && (
        <tr className="border-b border-[var(--border)] bg-[var(--surface-muted)]">
          <td />
          <td colSpan={10} className="px-4 py-4">
            <div className="grid gap-3">
              {row.projects.map((project) => (
                <div
                  key={`${row.gate_id}-${project.projectId}`}
                  className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-[var(--text-primary)]">
                        {project.projectName}
                      </div>
                      <div className="mt-1 text-xs text-[var(--text-secondary)]">
                        {project.molecule} · {project.geography} ·{" "}
                        {project.projectSizeMt} MTPD
                      </div>
                    </div>
                    <div className="text-right text-xs">
                      <div className="font-semibold text-[var(--text-primary)]">
                        Effective {project.effectiveScore} / {project.rawScore}
                      </div>
                      <div className="text-[var(--text-secondary)]">
                        Solved {project.solved} · Pending {project.pending} ·
                        Unresolved {project.unresolved}
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 grid gap-3 md:grid-cols-[1.2fr_1fr_1fr]">
                    <div>
                      <div className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        People in charge
                        <InfoTooltip text="Person in gate scope." />
                      </div>
                      <div className="mt-2 space-y-1.5">
                        {project.owners.map((owner) => (
                          <div
                            key={`${owner.name}-${owner.role}`}
                            className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] px-3 py-2 text-xs"
                          >
                            <span className="font-medium text-[var(--text-primary)]">
                              {owner.name}
                            </span>
                            <span className="text-[var(--text-secondary)]">
                              {owner.role}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        Coverage and verification
                        <InfoTooltip
                          text={HELP.EVIDENCE_HIERARCHY_GATE_COVERAGE}
                        />
                      </div>
                      <div className="mt-2 space-y-1.5">
                        <div className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] px-3 py-2 text-xs">
                          <span className="text-[var(--text-secondary)]">
                            Coverage
                          </span>
                          <span className="font-semibold text-[var(--text-primary)]">
                            {project.molecule} · {project.geography}
                          </span>
                        </div>
                        {(
                          [
                            "AUDITED",
                            "CONFIRMED",
                            "SUBMITTED",
                            "UNVERIFIED",
                          ] as VerificationState[]
                        ).map((state) => (
                          <div
                            key={state}
                            className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] px-3 py-2 text-xs"
                          >
                            <span className="text-[var(--text-secondary)]">
                              {state}
                            </span>
                            <span className="font-semibold text-[var(--text-primary)] tabular-nums">
                              {project.statusCounts[state]}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        Blocking topics
                      </div>
                      <div className="mt-2 space-y-1.5">
                        {project.blockers.length > 0 ? (
                          project.blockers.map((blocker) => (
                            <div
                              key={blocker}
                              className="rounded-lg bg-[var(--surface-muted)] px-3 py-2 text-xs text-[var(--text-secondary)]"
                            >
                              {blocker.replace(/_/g, " ")}
                            </div>
                          ))
                        ) : (
                          <div className="rounded-lg bg-[var(--surface-muted)] px-3 py-2 text-xs text-[var(--text-secondary)]">
                            No active blocker recorded
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
