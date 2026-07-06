// Screen: RFQ Management screen (/trader-dashboard)
// Renamed from "Trader Dashboard": GEX has no position book / P&L / VaR engine,
// so trading-desk framing (and the fabricated "Active Positions" / "P&L MTD"
// tiles) over-promised a CTRM that does not exist. This screen is the RFQ /
// origination desk; risk-book KPIs were removed (see audit-menu.mjs §9).
import {
  Zap,
  FileText,
  Package,
  AlertTriangle,
  ArrowRight,
  LineChart,
  Layers3,
  FileCheck2,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { ProductionRoadmapGantt } from "@/components/gantt/ProductionRoadmapGantt";
import { useSelectedProject } from "@/contexts/ProjectContext";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";
import { AdversarialReviewEntryCard } from "@/components/AdversarialReviewEntryCard";

export function TraderDashboardPage() {
  const navigate = useNavigate();
  const { selectedProjectId } = useSelectedProject();
  const { projects: visibleProjects } = useVisibleProjects();
  const project = visibleProjects.find(p => p.id === selectedProjectId) ?? visibleProjects[0];
  const riskAlerts = project.bankability.risk_alerts ?? [];
  const hasPricingTrustGap = riskAlerts.some((alert) =>
    /gabillon|spot reference|pricing reference/i.test(alert),
  );
  const hasOfftakeGap = project.bankability.gates.some(
    (g) => g.id === "G4_OFFTAKE_BANKABLE" && !g.is_complete,
  );

  const closePath = [
    {
      title: "Define mandate",
      detail:
        "Target molecule, 10,000 MT/month, certifications, first delivery window",
      cta: "Set demand",
      route: "/onboarding",
      Icon: FileText,
    },
    {
      title: "Pool supply",
      detail:
        "Aggregate at least 4 producer offers through GreenMesh / FlowFusion",
      cta: "Open marketplace",
      route: "/marketplace",
      Icon: Layers3,
    },
    {
      title: "Justify price",
      detail: "Use clean token lead spot reference plus Gabillon forward curve",
      cta: "Open pricing",
      route: "/pricing-curves",
      Icon: LineChart,
    },
    {
      title: "Close contract",
      detail: "Issue RFQ and move to term sheet with LC-ready price rationale",
      cta: "Run matching",
      route: "/matching",
      Icon: FileCheck2,
    },
  ];

  // Honest KPIs only — things GEX actually tracks (deals, RFQs, matched volume,
  // contracts). Removed "Active Positions" (no position book) and "P&L MTD"
  // (no mark-to-market / P&L engine) — they fabricated a CTRM risk book. See
  // audit-menu.mjs §9 CTRM-completeness manifest.
  const kpis = [
    {
      label: "Active Deals",
      value: "3",
      sub: "2 H2 · 1 NH3",
      icon: Package,
    },
    {
      label: "Open RFQs",
      value: "7",
      sub: "3 closing this week",
      icon: FileText,
    },
    {
      label: "Matched Volume",
      value: "12,400 t",
      sub: "MTD vs 15,000 t target",
      icon: Zap,
    },
    {
      label: "Expiring Contracts",
      value: "2",
      sub: "Within 90 days",
      icon: AlertTriangle,
    },
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-[var(--text-primary)]">
            RFQ Management
          </h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            RFQs · matching · contract close path · commercial milestones
          </p>
        </div>
      </div>

      <div className="gex-card rounded-2xl p-5">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-black uppercase tracking-widest text-[var(--text-muted)]">
              Objective
            </div>
            <h2 className="mt-1 text-lg font-bold text-[var(--text-primary)]">
              Close a defensible Q1 2027 contract path
            </h2>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Turn pooled producer volume into a buyer-ready contract with
              reference pricing that treasury, banks, and ratings teams can
              defend.
            </p>
          </div>
          <button
            onClick={() => navigate("/matching")}
            className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-[var(--text-primary)] px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90"
          >
            Continue path <ArrowRight className="h-4 w-4" />
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          {closePath.map((step) => (
            <button
              key={step.title}
              type="button"
              onClick={() => navigate(step.route)}
              className="rounded-xl border border-gray-200 bg-white p-4 text-left transition-shadow hover:shadow-sm"
            >
              <div className="inline-flex items-center gap-2 rounded-lg border bg-gray-100 text-gray-700 border-gray-200 px-2.5 py-1 text-xs font-bold">
                <step.Icon className="h-3.5 w-3.5" />
                {step.title}
              </div>
              <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">
                {step.cta}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                {step.detail}
              </p>
            </button>
          ))}
        </div>
      </div>

      {(hasPricingTrustGap || hasOfftakeGap) && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-bold text-amber-900">
                Current blocker to contract close
              </h3>
              <p className="mt-1 text-sm text-amber-800">
                Counterparties do not yet have a defensible price backbone. GEX
                must show a clean spot reference and Gabillon-based forward
                curve before RotterdamOfftake4 can justify LOIs, LC-backed
                pricing, or credit committee discussion.
              </p>
              <div className="mt-3">
                <button
                  onClick={() => navigate("/pricing-curves")}
                  className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-3 py-2 text-xs font-bold text-white hover:bg-gray-800"
                >
                  Open price reference <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        {kpis.map((kpi) => (
          <div
            key={kpi.label}
            className="bg-white rounded-xl border border-gray-200 p-4"
          >
            <div className="mb-2 flex items-center gap-2">
              <kpi.icon className="h-4 w-4 text-gray-400" />
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {kpi.label}
              </span>
            </div>
            <div className="text-xl font-black text-gray-900">{kpi.value}</div>
            <div className="mt-1 text-xs text-[var(--text-secondary)]">
              {kpi.sub}
            </div>
          </div>
        ))}
      </div>

      <AdversarialReviewEntryCard
        projectId={project.id}
        actorType="OFFTAKER"
        title="Offtaker challenge review"
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="gex-card rounded-xl p-6">
          <h2 className="mb-4 text-base font-bold text-[var(--text-primary)]">
            Active Offtake Positions
          </h2>
          <div className="space-y-3">
            {[
              {
                project: "Le Havre e-NG",
                product: "e-NG",
                buyer: "GRTgaz",
                volume: "92%",
                tenor: "20y",
                status: "SIGNED",
              },
              {
                project: "Bremen H2",
                product: "H2",
                buyer: "Vattenfall",
                volume: "78%",
                tenor: "15y",
                status: "PARTIAL",
              },
              {
                project: "Helios MeOH",
                product: "MeOH",
                buyer: "Maersk",
                volume: "60%",
                tenor: "12y",
                status: "PARTIAL",
              },
            ].map((row) => (
              <div
                key={row.project}
                className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] p-3"
              >
                <div>
                  <div className="text-sm font-semibold text-[var(--text-primary)]">
                    {row.project}
                  </div>
                  <div className="text-xs text-[var(--text-secondary)]">
                    {row.product} · {row.buyer} · {row.tenor}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-[var(--text-primary)]">
                    {row.volume}
                  </span>
                  <span
                    className={
                      row.status === "SIGNED"
                        ? "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold text-emerald-600"
                        : "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-gray-100 text-gray-700"
                    }
                  >
                    {row.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="gex-card rounded-xl p-6">
          <h2 className="mb-4 text-base font-bold text-[var(--text-primary)]">
            Open RFQs
          </h2>
          <div className="space-y-3">
            {[
              {
                id: "RFQ-2026-014",
                product: "NH3 500t/mo",
                deadline: "25 Mar",
                status: "BIDS_IN",
                bids: 4,
              },
              {
                id: "RFQ-2026-015",
                product: "H2 120t/mo",
                deadline: "28 Mar",
                status: "OPEN",
                bids: 1,
              },
              {
                id: "RFQ-2026-016",
                product: "SAF 200t/mo",
                deadline: "02 Apr",
                status: "OPEN",
                bids: 0,
              },
              {
                id: "RFQ-2026-017",
                product: "H2 80t/mo",
                deadline: "05 Apr",
                status: "DRAFTING",
                bids: 0,
              },
            ].map((rfq) => (
              <div
                key={rfq.id}
                className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] p-3"
              >
                <div>
                  <div className="text-sm font-semibold text-[var(--text-primary)]">
                    {rfq.id}
                  </div>
                  <div className="text-xs text-[var(--text-secondary)]">
                    {rfq.product} · closes {rfq.deadline}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-[var(--text-secondary)]">
                    {rfq.bids} bid{rfq.bids !== 1 ? "s" : ""}
                  </span>
                  <span
                    className={
                      rfq.status === "BIDS_IN"
                        ? "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold bg-gray-100 text-gray-900"
                        : "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-gray-100 text-gray-600"
                    }
                  >
                    {rfq.status.replace("_", " ")}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="gex-card rounded-xl p-4">
        <ProductionRoadmapGantt workspaceId="trader" compact />
      </div>
    </div>
  );
}
