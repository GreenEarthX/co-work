// Screen: Project rating view screen
import { useMemo } from "react";
import GexProjectRatingCard from "@/components/ratings/GexProjectRatingCard";
import { useProjectRating } from "@/hooks/useProjectRating";
import type { ProjectRatingRequest } from "@/types/projectRating";

/**
 * Demo view — Project Helios e-Methanol.
 * Replace with dynamic payload from route params / workspace context.
 */
export default function ProjectRatingView() {
  const payload: ProjectRatingRequest = useMemo(
    () => ({
      project: {
        project_name:                  "Project Helios e-Methanol",
        phase:                         "Pre-COD / late construction",
        business_market:               3.9,
        construction_technology:       3.8,
        legal_structural_counterparty: 4.1,
        sustainability_certification:  4.3,
        jurisdiction_notch:            0,
        sponsor_support_notch:         1,
        structure_notch:               1,
        market_exposure_notch:         -1,
        data_confidence_notch:         0,
        payment_default:               false,
        distressed_exchange:           false,
        outlook_bias:                  0,
      },
      gates: {
        land_and_permits_ok: true,
        technology_wrap_ok:  true,
        regulatory_path_ok:  true,
        funding_path_ok:     true,
        revenue_path_ok:     true,
        traceability_ok:     true,
      },
      quantitative: {
        downside_min_dscr:                1.27,
        base_case_dscr:                   1.61,
        llcr:                             1.78,
        contracted_revenue_pct:           72.0,
        merchant_exposure_pct:            28.0,
        equity_committed_pct_of_capex:    34.0,
        subsidy_dependence_pct_of_ebitda: 24.0,
        schedule_buffer_months:           3.0,
        dsra_months:                      6.0,
        certification_confidence_pct:     86.0,
      },
    }),
    []
  );

  const { data, isLoading, error } = useProjectRating(payload);

  if (isLoading) {
    return (
      <div className="animate-fade-in rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 text-[var(--text-secondary)] shadow-card">
        Computing project rating…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-red-200 bg-white p-6 text-red-700 shadow-card dark:bg-slate-900 dark:border-red-800 dark:text-red-400">
        Rating error: {error}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-display text-lg font-bold text-[var(--text-primary)]">Project Rating</h1>
        <p className="text-sm text-[var(--text-secondary)]">GEX Project Quality Rating · {data.methodology_version}</p>
      </div>
      <GexProjectRatingCard data={data} />
    </div>
  );
}
