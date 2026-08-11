// Screen: Shared component — Main dashboard screen
import { type ReactNode, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { projectTruthAPI } from "@/lib/api";
import { useSelectedProject } from "@/contexts/ProjectContext";
import { useUserRole } from "@/contexts/UserRoleContext";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";

interface TruthBlocker {
  id: string;
  gate: string;
  severity: string;
  plain_language: string;
  action: string;
  page: string;
}

interface TruthGate {
  gate_id: string;
  gate_name: string;
  owners: string[];
  status: string;
}

interface TruthOwner {
  owner: string;
  scope_topics: number;
  blocked_topics: number;
  gates: string[];
}

interface TruthInstrument {
  id: string;
  name: string;
  type: string;
  provider: string;
  coverage_pct: number;
  rate_reduction_bps: number;
}

interface ProjectTruthResponse {
  project_id: string;
  project_name: string;
  molecule: string;
  location: string;
  status: string;
  objective: string;
  scope_readiness: string;
  overall_readiness: string;
  scope_note: string;
  top_blocker: {
    id: string | null;
    gate: string | null;
    severity: string | null;
    plain_language: string;
    action: string;
    page: string;
    owner: string;
  };
  next_action: {
    label: string;
    page: string;
    owner: string;
  };
  evidence: {
    confirmed_pct: number;
    audited_count: number;
    total_count: number;
  };
  gate_scope: {
    visible_count: number;
    items: TruthGate[];
  };
  blockers: {
    fatal_count: number;
    critical_count: number;
    hidden_count: number;
    items: TruthBlocker[];
  };
  owners: TruthOwner[];
  eligible_instruments: TruthInstrument[];
  capital_path: {
    status: string;
    headline: string;
    detail: string;
  };
}

const READINESS_STYLE: Record<string, string> = {
  READY: "bg-white text-slate-900 border-slate-300",
  CONDITIONAL: "bg-white text-amber-700 border-amber-300",
  NOT_READY: "bg-white text-red-700 border-red-300",
  IN_PROGRESS: "bg-white text-slate-900 border-slate-300",
};

const ALL_PROJECTS_ID = "all";

export function ProjectInFocusSelector() {
  const { projects: visibleProjects } = useVisibleProjects();
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject();

  if (visibleProjects.length === 0) {
    return null;
  }

  const selected = visibleProjects.find((p) => p.id === selectedProjectId);

  // Banner facts — the label and the choice read as one line, and the spare
  // horizontal space carries the project's identity rather than sitting empty.
  const facts = selected
    ? [
        selected.molecule,
        selected.capacity_kt_yr != null
          ? `${selected.capacity_kt_yr} kt/yr`
          : null,
        [selected.location, selected.country].filter(Boolean).join(", "),
        selected.status,
      ].filter(Boolean)
    : [`${visibleProjects.length} projects in scope`];

  return (
    <label className="flex w-full cursor-pointer items-center gap-4 rounded-xl border border-slate-200 bg-white px-4 py-2.5">
      <span className="shrink-0 text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">
        Project in Focus
      </span>
      <select
        value={selectedProjectId}
        onChange={(event) => setSelectedProjectId(event.target.value)}
        className="min-w-0 max-w-[460px] shrink cursor-pointer truncate border-0 bg-transparent p-0 text-2xl font-black text-slate-900 focus:outline-none focus:ring-0"
      >
        <option value={ALL_PROJECTS_ID}>All Projects</option>
        {visibleProjects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name}
          </option>
        ))}
      </select>
      <span className="ml-auto hidden min-w-0 items-center gap-2 truncate text-xs text-slate-500 md:flex">
        {facts.map((fact, i) => (
          <span key={fact} className="flex items-center gap-2 truncate">
            {i > 0 && <span className="text-slate-300">·</span>}
            <span className="truncate uppercase tracking-[0.08em]">{fact}</span>
          </span>
        ))}
      </span>
    </label>
  );
}

function ChainCard({
  step,
  title,
  headline,
  detail,
  children,
}: {
  step: string;
  title: string;
  headline: string;
  detail?: string;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3 min-h-[184px]">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[10px] text-slate-900 uppercase font-semibold tracking-[0.18em]">
          {title}
        </span>
        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-900">
          {step}
        </span>
      </div>
      <div className="text-base font-semibold text-slate-900 leading-tight">
        {headline}
      </div>
      {detail && (
        <div className="text-sm text-slate-600 leading-5">{detail}</div>
      )}
      {children}
    </div>
  );
}

export function ProjectTruthChain() {
  const navigate = useNavigate();
  const { projects: visibleProjects } = useVisibleProjects();
  const { selectedProjectId } = useSelectedProject();
  const { role } = useUserRole();
  const focusedProjects =
    selectedProjectId === ALL_PROJECTS_ID
      ? visibleProjects
      : visibleProjects.filter((project) => project.id === selectedProjectId);
  const [data, setData] = useState<ProjectTruthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedProjectId) return;

    if (selectedProjectId === ALL_PROJECTS_ID) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    projectTruthAPI
      .get(selectedProjectId, {
        company_type: role.company_type,
        business_function: role.business_function,
        service_type: role.service_type,
        capabilities: role.capabilities,
      })
      .then((response) => setData(response))
      .catch((err) =>
        setError(
          err instanceof Error ? err.message : "Unable to load project truth",
        ),
      )
      .finally(() => setLoading(false));
  }, [
    selectedProjectId,
    role.company_type,
    role.business_function,
    role.service_type,
    role.capabilities,
  ]);

  if (visibleProjects.length === 0) {
    return null;
  }

  if (selectedProjectId === ALL_PROJECTS_ID) {
    const avgReadiness =
      focusedProjects.length > 0
        ? Math.round(
            focusedProjects.reduce(
              (sum, project) => sum + project.bankability.overall_completion,
              0,
            ) / focusedProjects.length,
          )
        : 0;
    const blockers = focusedProjects.filter(
      (project) => project.bankability.overall_completion < 40,
    ).length;

    return (
      <section className="rounded-2xl border border-slate-200 bg-stone-50 p-6 space-y-5">
        <div className="space-y-2">
          <h2 className="text-2xl font-black text-slate-900">
            Critical Path & Blocker Isolation.
          </h2>
        </div>
        <div className="grid gap-3 lg:grid-cols-3">
          <ChainCard
            step="Portfolio"
            title="Projects in scope"
            headline={`${focusedProjects.length} projects`}
            detail="All visible projects are included in the dashboard scope."
          />
          <ChainCard
            step="Readiness"
            title="Average bankability"
            headline={`${avgReadiness}%`}
            detail="Average completion across the visible project portfolio."
          />
          <ChainCard
            step="Blockers"
            title="Projects below 40%"
            headline={`${blockers}`}
            detail="Switch to a single project to isolate its blockers and next action."
          />
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-stone-50 p-6 space-y-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          {/* <div className="text-[11px] font-bold uppercase tracking-[0.24em] text-slate-500">
            Diagnostic Workspace
          </div> */}
          <h2 className="text-2xl font-black text-slate-900">
            Critical Path & Blocker Isolation.
          </h2>
          {/* <p className="max-w-3xl text-sm text-slate-600">
            Single-project dependency tracking. Maps source evidence against compliance gate scopes,
            isolates blocker ownership, and identifies mitigation workflows required for next capital allocation.
          </p> */}
        </div>
      </div>

      {loading && (
        <div className="rounded-2xl border border-slate-200 bg-white px-5 py-8 text-sm text-slate-600">
          Loading project truth...
        </div>
      )}

      {!loading && error && (
        <div className="rounded-2xl border border-red-200 bg-white px-5 py-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && data && (
        <>
          <div className="grid gap-3 lg:grid-cols-3">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
                  Readiness
                </div>
                <div
                  className={`inline-flex rounded-full border px-3 py-1 text-sm font-bold ${READINESS_STYLE[data.scope_readiness] ?? READINESS_STYLE.READY}`}
                >
                  {data.scope_readiness.replace("_", " ")}
                </div>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="min-w-0 text-sm text-slate-700">
                  {data.scope_note}
                </div>
                <div className="min-w-0 text-xs text-slate-500 sm:text-right">
                  Overall project status:{" "}
                  {data.overall_readiness.replace("_", " ")}
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
                Blocking Truth
              </div>
              <div className="text-base font-semibold text-slate-900 leading-tight">
                {data.top_blocker.plain_language}
              </div>
              <div className="text-sm text-slate-600">
                Owner: {data.top_blocker.owner}
                {data.top_blocker.gate ? ` · ${data.top_blocker.gate}` : ""}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
                  Next Action
                </div>
                <button
                  onClick={() => navigate(data.next_action.page)}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-900 hover:bg-slate-100"
                >
                  Open action
                </button>
              </div>
              <div className="text-base font-semibold text-slate-900 leading-tight">
                {data.next_action.label}
              </div>
              <div className="text-sm text-slate-600">
                Owner: {data.next_action.owner}
              </div>
            </div>
          </div>

          <div className="grid gap-3 xl:grid-cols-6">
            <ChainCard
              step="01"
              title="Evidence"
              headline={`${Math.round(data.evidence.confirmed_pct)}% confirmed+`}
              detail={`${data.evidence.audited_count} audited of ${data.evidence.total_count} evidence items.`}
            />

            <ChainCard
              step="02"
              title="Gate Scope"
              headline={`${data.gate_scope.visible_count} gate(s) in view`}
              detail={
                data.gate_scope.items.map((item) => item.gate_id).join(" · ") ||
                "No gate visibility."
              }
            >
              <div className="space-y-1.5">
                {data.gate_scope.items.slice(0, 3).map((item) => (
                  <div key={item.gate_id} className="text-xs text-slate-600">
                    <span className="font-semibold text-slate-900">
                      {item.gate_id}
                    </span>{" "}
                    {item.gate_name}
                  </div>
                ))}
              </div>
            </ChainCard>

            <ChainCard
              step="03"
              title="Blockers"
              headline={`${data.blockers.fatal_count} fatal · ${data.blockers.critical_count} critical`}
              detail={
                data.blockers.hidden_count > 0
                  ? `${data.blockers.hidden_count} blocker(s) remain outside this user scope.`
                  : "No hidden blockers outside this user scope."
              }
            >
              <div className="space-y-1.5">
                {data.blockers.items.slice(0, 2).map((item) => (
                  <div key={item.id} className="text-xs text-slate-600">
                    <span className="font-semibold text-slate-900">
                      {item.gate}
                    </span>{" "}
                    {item.severity.toLowerCase()}
                  </div>
                ))}
              </div>
            </ChainCard>

            <ChainCard
              step="04"
              title="Owners"
              headline={
                data.owners[0]
                  ? `${data.owners[0].owner} carries the heaviest load`
                  : "No owner pressure in current scope"
              }
              detail="Current accountability across visible gates."
            >
              <div className="space-y-1.5">
                {data.owners.slice(0, 3).map((owner) => (
                  <div key={owner.owner} className="text-xs text-slate-600">
                    <span className="font-semibold text-slate-900">
                      {owner.owner}
                    </span>{" "}
                    {owner.blocked_topics}/{owner.scope_topics} blocked topics
                  </div>
                ))}
              </div>
            </ChainCard>

            <ChainCard
              step="05"
              title="Mitigants"
              headline={
                data.eligible_instruments[0]
                  ? `${data.eligible_instruments.length} immediate levers`
                  : "No instrument suggestion"
              }
              detail="Eligible instruments ranked by rate relief and coverage."
            >
              <div className="space-y-1.5">
                {data.eligible_instruments.slice(0, 2).map((item) => (
                  <div key={item.id} className="text-xs text-slate-600">
                    <span className="font-semibold text-slate-900">
                      {item.type}
                    </span>{" "}
                    {item.provider}
                  </div>
                ))}
              </div>
            </ChainCard>

            <ChainCard
              step="06"
              title="Capital Path"
              headline={data.capital_path.headline}
              detail={data.capital_path.detail}
            />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
                  Actionable Blockers
                </div>
                <div className="text-lg font-bold text-slate-900">
                  {data.project_name} · {data.molecule}
                </div>
                <div className="text-sm text-slate-600">{data.location}</div>
              </div>
              <div className="text-sm text-slate-600">{data.objective}</div>
            </div>

            {data.blockers.items.length === 0 ? (
              <div className="text-sm text-slate-600">
                No blocker is currently active in this user scope.
              </div>
            ) : (
              <div className="space-y-3">
                {data.blockers.items.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-xl border border-slate-200 bg-stone-50 px-4 py-4"
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="space-y-2">
                        <div className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500">
                          {item.gate} · {item.severity.toLowerCase()}
                        </div>
                        <div className="text-sm font-semibold text-slate-900 leading-6">
                          {item.plain_language}
                        </div>
                        <div className="text-sm text-slate-600">
                          {item.action}
                        </div>
                      </div>
                      <button
                        onClick={() => navigate(item.page)}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100"
                      >
                        Open route
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
