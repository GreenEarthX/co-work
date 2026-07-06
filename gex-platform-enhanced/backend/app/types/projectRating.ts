// ─── Rating scale ─────────────────────────────────────────────────────────────

export type RatingLetter = "AAA" | "AA" | "A" | "BBB" | "BB" | "B" | "CCC" | "CC" | "C" | "D";
export type RatingOutlook = "Positive" | "Stable" | "Negative";
export type ReviewerType = "internal" | "qualified_third_party";
export type ReviewState = "draft_screening" | "analyst_reviewed" | "qualified_opinion" | "archived";

// ─── Request shapes ───────────────────────────────────────────────────────────

export interface GateStatusIn {
  land_and_permits_ok:  boolean;
  technology_wrap_ok:   boolean;
  regulatory_path_ok:   boolean;
  funding_path_ok:      boolean;
  revenue_path_ok:      boolean;
  traceability_ok:      boolean;
}

export interface ProjectInputsIn {
  project_id?:                    string;
  project_name:                   string;
  phase:                          string;
  business_market:                number;
  construction_technology:        number;
  legal_structural_counterparty:  number;
  sustainability_certification:   number;
  jurisdiction_notch?:            number;
  sponsor_support_notch?:         number;
  structure_notch?:               number;
  market_exposure_notch?:         number;
  data_confidence_notch?:         number;
  payment_default?:               boolean;
  distressed_exchange?:           boolean;
  outlook_bias?:                  number;
}

export interface QuantitativeInputsIn {
  downside_min_dscr:                number;
  base_case_dscr:                   number;
  llcr:                             number;
  contracted_revenue_pct:           number;
  merchant_exposure_pct:            number;
  equity_committed_pct_of_capex:    number;
  subsidy_dependence_pct_of_ebitda: number;
  schedule_buffer_months:           number;
  dsra_months:                      number;
  certification_confidence_pct:     number;
}

/** What we POST to /api/v1/project-ratings */
export interface ProjectRatingCreateRequest {
  project:             ProjectInputsIn;
  gates:               GateStatusIn;
  quantitative:        QuantitativeInputsIn;
  peer_scores_desc?:   number[];
  methodology_name?:   string;
  methodology_version?: string;
  reviewer_type?:      ReviewerType;
  review_state?:       ReviewState;
}

/** Alias used by the hook (same shape, different name for ergonomics) */
export type ProjectRatingRequest = ProjectRatingCreateRequest;

// ─── Response shape (matches RatingResult from the Python engine) ─────────────

export interface ProjectRatingResponse {
  project_name:          string;
  phase:                 string;
  base_score:            number;
  modifier_points:       number;
  preliminary_score:     number;
  final_score:           number;
  rating:                RatingLetter;
  outlook:               RatingOutlook;
  cap_reason:            string;
  displayed_scale:       RatingLetter[];
  current_rank:          number;
  peer_count:            number;
  anonymous_peer_scores: number[];
  quantitative_inputs:   Record<string, number>;
  pillar_scores:         Record<string, number>;
  gate_status:           Record<string, boolean>;
  key_strengths:         string[];
  key_constraints:       string[];
  methodology_label:     string;
  methodology_name:      string;
  methodology_version:   string;
  reviewer_type:         ReviewerType;
  review_state:          ReviewState;
  project_id?:           string;
}
