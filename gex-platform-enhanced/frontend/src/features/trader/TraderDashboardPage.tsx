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
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  marketAPI,
  type MarketContract,
  type MarketMatch,
  type MarketRFQ,
} from "@/api";
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

  // The real path through the market (2026-10-23): no figures here — volumes,
  // prices and dates come from the company's own RFQs, listings and matches.
  const closePath = [
    {
      title: "Raise a request",
      detail: "Your molecule, volume, delivery window and maximum price, as an RFQ",
      cta: "Open RFQs",
      route: "/rfqs",
      Icon: FileText,
    },
    {
      title: "Find a counterpart",
      detail: "Browse anonymised listings and propose one of yours to a specific one",
      cta: "Market discovery",
      route: "/market-discovery",
      Icon: Layers3,
    },
    {
      title: "Justify price",
      detail: "Check the price against the spot reference and the Gabillon forward curve",
      cta: "Open pricing",
      route: "/pricing-curves",
      Icon: LineChart,
    },
    {
      title: "Close contract",
      detail: "Both parties accept the match; either writes the contract from its terms",
      cta: "Your matches",
      route: "/matching",
      Icon: FileCheck2,
    },
  ];

  // Live, from the market engine (/api/v1/market) — the company's own RFQs,
  // matches and contracts. Before 2026-10-23 these tiles were constants
  // ("3 active deals", "7 open RFQs"); gap register G-04.
  const [rfqs, setRfqs] = useState<MarketRFQ[]>([]);
  const [matches, setMatches] = useState<MarketMatch[]>([]);
  const [contracts, setContracts] = useState<MarketContract[]>([]);
  const [marketError, setMarketError] = useState<string | null>(null);

  const loadMarket = useCallback(async () => {
    try {
      const [r, m, c] = await Promise.all([
        marketAPI.myRFQs(),
        marketAPI.myMatches(),
        marketAPI.myContracts(),
      ]);
      setRfqs(r.rfqs);
      setMatches(m.matches);
      setContracts(c.contracts);
      setMarketError(null);
    } catch (e) {
      setMarketError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    loadMarket();
  }, [loadMarket]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await loadMarket();
    } catch (e) {
      setMarketError((e as Error).message);
    }
  };

  const contracted = new Set(contracts.map((c) => c.match_id));
  const myAcceptance = (m: MarketMatch) =>
    m.side === "seller" ? m.seller_accepted_by : m.buyer_accepted_by;
  const toAccept = matches.filter((m) => m.status === "pending" && !myAcceptance(m));
  const awaitingThem = matches.filter((m) => m.status === "pending" && myAcceptance(m));
  const toContract = matches.filter((m) => m.status === "accepted" && !contracted.has(m.id));
  const openRfqs = rfqs.filter((r) => r.status === "open");

  const kpis = [
    { label: "Matches to accept", value: String(toAccept.length),
      sub: `${awaitingThem.length} awaiting the counterparty`, icon: Zap },
    { label: "Open RFQs", value: String(openRfqs.length),
      sub: `${rfqs.filter((r) => r.status === "draft").length} in draft`, icon: FileText },
    { label: "Agreed, no contract", value: String(toContract.length),
      sub: "both parties accepted", icon: AlertTriangle },
    { label: "Contracts", value: String(contracts.length),
      sub: `${contracts.filter((c) => c.status === "active").length} active`, icon: Package },
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
              From request to signed contract
            </h2>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Every step below acts on your company's own RFQs, listings and
              matches; the figures on this page are read from them.
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
                curve before an offtaker can justify LOIs, LC-backed pricing,
                or credit committee discussion.
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

      {marketError && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {marketError}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="gex-card rounded-xl p-6">
          <h2 className="mb-1 text-base font-bold text-[var(--text-primary)]">
            Matches — your move
          </h2>
          <p className="mb-4 text-xs text-[var(--text-secondary)]">
            A match binds only when both parties accept. Names are shown to the two parties only.
          </p>
          {toAccept.length + toContract.length === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">
              Nothing waiting on you.{" "}
              <button className="font-semibold underline" onClick={() => navigate("/market-discovery")}>
                Find matches
              </button>
            </p>
          ) : (
            <div className="space-y-3">
              {[...toAccept, ...toContract].map((m) => (
                <div key={m.id}
                     className="flex items-center justify-between gap-3 rounded-lg bg-[var(--surface-muted)] p-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                      {m.molecule} · {m.volume_mtpd} MTPD · €{m.price_eur_kg}/kg
                    </div>
                    <div className="text-xs text-[var(--text-secondary)]">
                      You {m.side === "seller" ? "sell to" : "buy from"}{" "}
                      {(m.side === "seller" ? m.buyer_name : m.seller_company_name) ?? "—"} ·
                      score {Math.round(m.match_score)} · {m.delivery_start} → {m.delivery_end}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {m.status === "pending" ? (
                      <>
                        <button onClick={() => act(() => marketAPI.acceptMatch(m.id))}
                                className="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-bold text-white">
                          Accept
                        </button>
                        <button onClick={() => act(() => marketAPI.declineMatch(m.id))}
                                className="rounded-lg border px-3 py-1.5 text-xs font-semibold">
                          Decline
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => {
                          const delivery = window.prompt("Delivery terms (e.g. FOB Rotterdam, monthly)");
                          if (!delivery) return;
                          const payment = window.prompt("Payment terms (e.g. 30 days from invoice)");
                          if (!payment) return;
                          act(() => marketAPI.createContract(m.id, delivery, payment));
                        }}
                        className="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-bold text-white">
                        Write contract
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="gex-card rounded-xl p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-bold text-[var(--text-primary)]">Your open RFQs</h2>
            <button onClick={() => navigate("/rfqs")} className="text-xs font-semibold underline">
              Manage RFQs
            </button>
          </div>
          {openRfqs.length === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">No open RFQ.</p>
          ) : (
            <div className="space-y-3">
              {openRfqs.map((rfq) => (
                <div key={rfq.id}
                     className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] p-3">
                  <div>
                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                      {rfq.molecule} · {rfq.volume_mtpd} MTPD
                    </div>
                    <div className="text-xs text-[var(--text-secondary)]">
                      {rfq.delivery_start} → {rfq.delivery_end}
                      {rfq.max_price_eur_kg != null && ` · max €${rfq.max_price_eur_kg}/kg`}
                    </div>
                  </div>
                  <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-semibold text-gray-700">
                    {matches.filter((m) => m.status === "pending").length ? "MATCHING" : "OPEN"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="gex-card rounded-xl p-4">
        <ProductionRoadmapGantt workspaceId="trader" compact />
      </div>
    </div>
  );
}
