// Screen: API client (no screen)
// API Client for GreenEarthX Platform
// Bearer token comes from lib/authToken — the single reader of the stored
// session. Without it, /api/v1/bankability/* and /finance-model/* return 401
// and the list silently fails to load.
import { getAuthHeader as authHeader } from "@/lib/authToken";

const API_BASE_URL = "/api/v1";

async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const url = `${API_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    // After `...options`: a caller's own headers (e.g. Idempotency-Key) are added to the
    // auth and content-type headers, never replace them.
    headers: {
      // A FormData body sets its own multipart boundary; forcing JSON breaks it.
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...authHeader(),
      ...(options.headers as Record<string, string> | undefined),
    },
  });

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    // Structured refusals ({code, message}) must reach the user as their
    // message, not as "[object Object]".
    const detail = error.detail;
    const failure = new Error(
      (detail && typeof detail === "object" && detail.message) ||
        (typeof detail === "string" && detail) ||
        `HTTP ${response.status}`,
    ) as Error & { status?: number };
    // Screens show a refusal's reason (4xx) to the user, but not an outage's
    // (5xx): those carry internals such as "engine unavailable (port 8001)".
    failure.status = response.status;
    throw failure;
  }

  return response.json();
}

// ═══════════════════════════════════════════════════════════════
// Projects API — prefix: /api/v1/projects
// ═══════════════════════════════════════════════════════════════
export interface ProjectCreateInput {
  name: string;
  molecule: string;
  location: string;
  country: string;
  capacity_mtpd: number;
  capex_eur: number;
  power_model: "OFF_GRID_BTM" | "GRID_CONNECTED" | "HYBRID";
  financing_model: "PROJECT_FINANCE" | "BALANCE_SHEET";
  phase: "development" | "construction" | "commissioning" | "operating";
}

export const projectsAPI = {
  create: (data: ProjectCreateInput) =>
    fetchAPI("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  visible: () => fetchAPI("/projects/visible"),
};

// ═══════════════════════════════════════════════════════════════
// Development Packages API — prefix: /api/v1/packages
// The bridge unit: package → spend → evidence → risk removed → capital.
// ═══════════════════════════════════════════════════════════════
export interface PackageCreateInput {
  project_id: string;
  package_name: string;
  package_type: string;
  phase_required: string;
  discipline_owner: string;
  cost_amount: number;
  estimate_class: string;
  risk_removed: string[];        // ≥1 required server-side
  capital_eligible: string[];
  drawdown_method: string;
  notes?: string;
}

export interface PackageUpdateInput {
  changed_by: string;
  cost_amount?: number;
  cost_p10?: number;
  cost_p90?: number;
  estimate_class?: string;
  gex_gate?: string;
  downstream_effect?: string[];
  unlock_condition?: string[];
  notes?: string;
}

export interface PackageTransitionInput {
  new_state: string;
  changed_by: string;
  actor_type: string;
  justification: string;        // ≥10 chars server-side
  approved_by?: string;
  approver_actor_type?: string;
}

export interface PackageCapitalTransitionInput {
  new_status: string;
  changed_by: string;
  actor_type: string;
  justification: string;
  approved_by?: string;
  approver_actor_type?: string;
}

export const packagesAPI = {
  listForProject: (projectId: string) =>
    fetchAPI(`/packages/project/${encodeURIComponent(projectId)}`),
  summary: (projectId: string) =>
    fetchAPI(`/packages/project/${encodeURIComponent(projectId)}/summary`),
  create: (data: PackageCreateInput) =>
    fetchAPI("/packages", { method: "POST", body: JSON.stringify(data) }),
  update: (packageId: string, data: PackageUpdateInput) =>
    fetchAPI(`/packages/${encodeURIComponent(packageId)}`, { method: "PATCH", body: JSON.stringify(data) }),
  transition: (packageId: string, data: PackageTransitionInput) =>
    fetchAPI(`/packages/${encodeURIComponent(packageId)}/transition`, { method: "POST", body: JSON.stringify(data) }),
  capitalTransition: (packageId: string, data: PackageCapitalTransitionInput) =>
    fetchAPI(`/packages/${encodeURIComponent(packageId)}/capital-transition`, { method: "POST", body: JSON.stringify(data) }),
  events: (packageId: string) =>
    fetchAPI(`/packages/${encodeURIComponent(packageId)}/events`),
  listEvidence: (packageId: string) =>
    fetchAPI(`/packages/${encodeURIComponent(packageId)}/evidence`),
  // Multipart upload — must NOT set Content-Type (browser sets the boundary).
  uploadEvidence: async (packageId: string, file: File, title: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("title", title);
    const res = await fetch(`${API_BASE_URL}/packages/${encodeURIComponent(packageId)}/evidence`, {
      method: "POST",
      headers: { ...authHeader() },
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
};

// ═══════════════════════════════════════════════════════════════
// Capacities API — prefix: /api/v1/capacities
// ═══════════════════════════════════════════════════════════════
export const capacitiesAPI = {
  // An idempotency key (one per form) makes a repeated submit replay, never create twice.
  create: (data: any, idempotencyKey?: string) =>
    fetchAPI("/capacities/", {
      method: "POST",
      body: JSON.stringify(data),
      ...(idempotencyKey ? { headers: { "Idempotency-Key": idempotencyKey } } : {}),
    }),
  list: (params?: { molecule?: string; project_id?: string }) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(`/capacities/${query ? `?${query}` : ""}`);
  },
  get: (id: string) => fetchAPI(`/capacities/${id}`),
  delete: (id: string) => fetchAPI(`/capacities/${id}`, { method: "DELETE" }),
};

// ═══════════════════════════════════════════════════════════════
// Offers API — prefix: /api/v1/marketplace
// ═══════════════════════════════════════════════════════════════
export const offersAPI = {
  // An idempotency key (one per form) makes a repeated submit replay, never create twice.
  create: (data: any, idempotencyKey?: string) =>
    fetchAPI("/marketplace/offers", {
      method: "POST",
      body: JSON.stringify(data),
      ...(idempotencyKey ? { headers: { "Idempotency-Key": idempotencyKey } } : {}),
    }),
  list: (params?: { molecule?: string; status?: string; listing_state?: string }) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(`/marketplace/offers${query ? `?${query}` : ""}`);
  },
  get: (id: string) => fetchAPI(`/marketplace/offers/${id}`),
  // The seller opens or withdraws its listing; MATCHED and SETTLED are set by
  // the market (the old PATCH .../status answers 409 USE_TRANSITION).
  transition: (id: string, new_state: "OPEN" | "WITHDRAWN" | "EXPIRED") =>
    fetchAPI(`/marketplace/offers/${id}/transition`, {
      method: "POST",
      body: JSON.stringify({ new_state }),
    }),
  delete: (id: string) =>
    fetchAPI(`/marketplace/offers/${id}`, { method: "DELETE" }),
};

// ═══════════════════════════════════════════════════════════════
// RFQs API — prefix: /api/v1/matching
// ═══════════════════════════════════════════════════════════════
export const rfqsAPI = {
  create: (data: any) =>
    fetchAPI("/matching/rfqs", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  list: (params?: { molecule?: string; status?: string }) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(`/matching/rfqs${query ? `?${query}` : ""}`);
  },
};

// ═══════════════════════════════════════════════════════════════
// Matching API — prefix: /api/v1/matching
// ═══════════════════════════════════════════════════════════════
export const matchingAPI = {
  run: (data?: any) =>
    fetchAPI("/matching/run", {
      method: "POST",
      body: data ? JSON.stringify(data) : "{}",
    }),
  list: (params?: { molecule?: string }) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(`/matching/${query ? `?${query}` : ""}`);
  },
  get: (id: string) => fetchAPI(`/matching/${id}`),
  accept: (id: string) =>
    fetchAPI(`/matching/${id}/accept`, { method: "POST" }),
};

// ═══════════════════════════════════════════════════════════════
// Contracts API — prefix: /api/v1/contracts
// ═══════════════════════════════════════════════════════════════
export const contractsAPI = {
  create: (data: any) =>
    fetchAPI("/contracts/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  list: (params?: { status?: string }) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(`/contracts/${query ? `?${query}` : ""}`);
  },
  get: (id: string) => fetchAPI(`/contracts/${id}`),
  updateStatus: (id: string, status: string) =>
    fetchAPI(`/contracts/${id}/status?new_status=${encodeURIComponent(status)}`, {
      method: "PATCH",
    }),
  getAcceptedMatches: () => fetchAPI("/contracts/accepted-matches/available"),
};

// ═══════════════════════════════════════════════════════════════
// Market API — prefix: /api/v1/market (backend core/market_engine.py)
// Listings are anonymised: no company, project, token or location. Names
// appear only on a match, to its two parties. A match needs BOTH to accept.
// ═══════════════════════════════════════════════════════════════
export interface OfferListing {
  id: string;
  molecule: string;
  volume_mtpd: number;
  price_eur_kg: number;
  delivery_start: string;
  delivery_end: string;
  delivery_type?: string | null;
  delivery_basis?: string | null;
  price_basis?: string | null;
  certification_pathway_required?: string | null;
  certification_pathway?: string | null;
  min_order_kg?: number | null;
  carbon_intensity_gco2e_mj?: number | null;
  esg_tier?: string | null;
  created_at: string;
  mine: boolean;
  project_id?: string; // present only on the caller's own listings
  // D-C (Phase 1): what an anonymous member may see. Never the company, site or contact.
  offer_type?: "firm" | "indicative" | null;
  valid_until?: string | null;
  incoterm?: string | null;
  named_place?: string | null;
  shipment_point?: string | null;
  production_country?: string | null;
  seller_role?: string | null;
  seller_vetting?: "vetted" | "not_yet_vetted" | null;
  product?: ListingProduct;
}

/** The product behind a listing, with the evidence status of each claim (backend product_record.listing_summary). */
export interface ListingProduct {
  production_pathway?: string | null;
  physical_form?: string | null;
  specification_standard?: string | null;
  carbon_intensity?: { value_gco2e_mj: number; method?: string; system_boundary?: string; basis: string } | null;
  quality?: { parameter: string; value: number; unit: string; basis: string }[];
  certificates?: { kind: string; scheme: string; body: string; scope: string; covers: string; status: string }[];
}

/** A non-binding enquiry (backend core/enquiry.py, alembic 119). */
export interface Enquiry {
  id: string; role: "sent" | "received";
  status: "open" | "contact_shared" | "declined" | "withdrawn" | "closed";
  subject: { kind: "listing" | "rfq"; id: string; molecule: string; volume_mtpd: number; price_eur_kg?: number;
             max_price_eur_kg?: number; delivery_start: string; delivery_end: string; [k: string]: unknown };
  subject_state: string;
  counterparty: { role: string | null; vetting: string | null;
                  identity?: { company_name: string | null; person: { name: string; email: string } | null;
                               details?: Record<string, string | null> } };
  about_rfq_id: string | null; assessment_id: string | null; created_at: string; decided_at: string | null;
  can: { reply: boolean; share_contact: boolean; decline: boolean; withdraw: boolean };
  messages?: { side: "you" | "them"; body: string; evidence_request: string | null; at: string }[];
}

/** One requirement's outcome for one listing (backend core/compatibility.py). */
export interface Outcome {
  requirement: string; label: string; outcome: "compatible" | "incompatible" | "needs_evidence";
  reason: string; mandatory: boolean;
}
export interface Assessment {
  status: "compatible" | "incompatible" | "needs_evidence"; eligible: boolean;
  counts: Record<"compatible" | "incompatible" | "needs_evidence", number>; outcomes: Outcome[];
}
export interface Candidate { listing: OfferListing; assessment: Assessment }

/** A buyer's requirements on an RFQ (backend core/requirements.py, alembic 117). */
export interface RfqRequirements {
  max_ci_gco2e_mj?: number;
  ci_min_basis?: "estimate" | "calculated" | "measured";
  regimes?: string[];
  accepted_schemes?: string[];
  min_evidence_state?: "submitted" | "verified";
  physical_form?: string;
  quality_limits?: Record<string, { min?: number; max?: number }>;
  incoterms?: string[];
  named_place?: string;
  delivery_country?: string;
  mandatory?: string[];
}

export interface RFQListing {
  id: string;
  molecule: string;
  volume_mtpd: number;
  max_price_eur_kg: number | null;
  delivery_start: string;
  delivery_end: string;
  compliance_requirements?: string | null;
  created_at: string;
  mine: boolean;
  requirements?: RfqRequirements;
  valid_until?: string | null;
  buyer_role?: string | null;
  buyer_vetting?: "vetted" | "not_yet_vetted" | null;
}

export interface MarketRFQ extends RFQListing {
  status: string;
  buyer_company_id: string;
  buyer_name?: string | null;
  location?: string | null;
  correlation_id?: string | null;
}

export interface MarketMatch {
  id: string;
  project_id?: string | null;
  status: string;
  side: "seller" | "buyer";
  match_score: number;
  molecule: string;
  volume_mtpd: number;
  price_eur_kg: number;
  delivery_start: string;
  delivery_end: string;
  seller_company_name?: string | null;
  buyer_name?: string | null;
  seller_accepted_by?: string | null;
  buyer_accepted_by?: string | null;
  correlation_id?: string | null;
  created_at: string;
}

export interface ContractConfirmation {
  id: string;
  initiator_user_id: string;
  status: string;            // PENDING | APPROVED | REJECTED
  created_at: string;
  version?: number;
  terms_hash?: string;
}

export interface MarketContract {
  id: string;
  match_id: string;
  contract_id_external?: string | null;  // the record's reference, GEX-TB-<year>-<n>
  delivery_terms?: string | null;
  payment_terms?: string | null;
  verification_state?: string | null;
  version?: number;
  molecule: string;
  volume_mtpd: number;
  price_eur_kg: number;
  counterparty?: string | null;
  status: string;
  seller_company_id: string;
  buyer_company_id: string;
  correlation_id?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  created_at: string;
}

export interface TrailEvent {
  id: string;
  event_type: string;
  aggregate_type?: string | null;
  aggregate_id?: string | null;
  correlation_id?: string | null;
  timestamp?: string | null;
  previous_state?: string | null;
  new_state?: string | null;
  event_hash?: string | null;
  metadata?: { user_id?: string } & Record<string, unknown>;
  data?: Record<string, unknown>;
}

const q = (params?: Record<string, string | undefined>) => {
  const clean = Object.fromEntries(Object.entries(params ?? {}).filter(([, v]) => v));
  const query = new URLSearchParams(clean as Record<string, string>).toString();
  return query ? `?${query}` : "";
};

export interface Commodity {
  code: string;
  name: string;
  default_unit: string;
  market_molecule: string | null;
}

// Marketplace records (alembic 066) — moved out of MarketplacePage's code on
// 2026-10-23, every one UNVERIFIED until its source is confirmed.
export interface SpotPrice {
  molecule: string;
  value_base: number;
  unit: string;             // EUR/t, EUR/kg or EUR/MWh — NOT interchangeable
  currency: string;
  state: string;            // registry state: approved | proposed
  source_name: string;
  /** `value_base` normalised to EUR per tonne by the backend, where the fuel's
   *  energy content is known. NULL when the conversion cannot be made — never a
   *  guess. Use THIS for anything per-tonne; `value_base` is the raw registry row
   *  and is only per-tonne when `unit` says so. */
  eur_per_t: number | null;
  /** How `eur_per_t` was derived, or why it could not be. */
  eur_per_t_basis: string;
}
export interface SalesDetailRecord {
  project_id: string;
  region: string | null;
  e_source: string | null;
  green_energy_pct: number | null;
  certifier: string | null;
  breakeven_price: number | null;
  available: { start: string; end: string; volume_mtpd: number; basePrice: number; pct: number; status: string } | null;
  tokenised: { start: string; end: string; volume_mtpd: number; price: number; pct: number; status: string } | null;
  in_market: { start: string; end: string; volume_mtpd: number; targetPrice: number; pct: number;
    status: "open" | "pending" | "sold"; counterparty: string | null }[];
  verification_state: string;
  source: string;
}
export interface InputLineRecord {
  project_id: string;
  seq: number;
  feedstock: string;
  supplier: string | null;
  ratio: number;
  ratio_unit: string;
  unit_price: number;
  price_unit: string;
  status: "contracted" | "planned" | "spot";
  is_utility: boolean;
  capacity_factor: number | null;
  firming_cost: number | null;
  verification_state: string;
  source: string;
}
export interface InputClassRecord {
  feedstock: string;
  cert_relevance: string[];
  capital_relevance: string;
  item_type: string;
  verification_state: string;
}
export interface ProjectEconomics {
  spot_prices: Record<string, SpotPrice>;
  sales_detail: Record<string, SalesDetailRecord>;
  input_lines: Record<string, InputLineRecord[]>;
  input_classification: Record<string, InputClassRecord>;
}

// Product records (Phase 1, alembic 116): quality, carbon intensity with its basis, and
// certificates, as the seller declares them. Nothing here can mark a claim verified: only an
// appointed independent reviewer decides a certificate (D-F).
export const productsAPI = {
  parameters: (): Promise<{ parameters: { parameter: string; unit: string; label: string }[] }> =>
    fetchAPI("/products/parameters"),
  addQuality: (tokenId: string, data: { parameter: string; value: number; basis: string }) =>
    fetchAPI(`/products/tokens/${tokenId}/quality`, { method: "POST", body: JSON.stringify(data) }),
  addCarbonIntensity: (tokenId: string, data: { value_gco2e_mj: number; method: string; system_boundary: string;
                                                calculation_date: string; basis: string }) =>
    fetchAPI(`/products/tokens/${tokenId}/carbon-intensity`, { method: "POST", body: JSON.stringify(data) }),
  submitCertificate: (data: { project_id: string; kind: string; scheme: string; body: string; reference: string;
                              scope: string; valid_from: string; valid_until?: string;
                              covers?: { token_id: string }[] }) =>
    fetchAPI("/products/certificates", { method: "POST", body: JSON.stringify(data) }),
  // What an anonymous member will see of this token's product once listed (owner only).
  listingPreview: (tokenId: string): Promise<{ token_id: string; product: ListingProduct }> =>
    fetchAPI(`/products/tokens/${tokenId}/listing-preview`),
};

export const marketAPI = {
  projectEconomics: (): Promise<ProjectEconomics> => fetchAPI("/market/project-economics"),
  // tb_commodity (PostgreSQL) — the only source of molecule lists on screen.
  commodities: (): Promise<{ commodities: Commodity[] }> => fetchAPI("/market/commodities"),
  // D-B: what the signed-in user may do in the market (backend core/market_policy).
  policy: (): Promise<{ business_function: string | null; allowed: string[] }> => fetchAPI("/market/policy"),
  offerListings: (molecule?: string): Promise<{ offers: OfferListing[] }> =>
    fetchAPI(`/market/listings/offers${q({ molecule })}`),
  rfqListings: (molecule?: string): Promise<{ rfqs: RFQListing[] }> =>
    fetchAPI(`/market/listings/rfqs${q({ molecule })}`),
  createRFQ: (data: {
    molecule: string;
    volume_mtpd: number;
    delivery_start: string;
    delivery_end: string;
    max_price_eur_kg?: number | null;
    location?: string | null;
    buyer_contact?: string | null;
    compliance_requirements?: string[] | null;
    status?: "draft" | "open";
    requirements?: RfqRequirements;
    valid_until?: string | null;
  }, idempotencyKey?: string): Promise<MarketRFQ> =>
    // One key per filled-in form: a double click or a retry returns the first RFQ (backend F12).
    fetchAPI("/market/rfqs", { method: "POST", body: JSON.stringify(data),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined }),
  myRFQs: (): Promise<{ rfqs: MarketRFQ[] }> => fetchAPI("/market/rfqs/mine"),
  // R9 (D-D): a non-binding enquiry about one listing or one RFQ. Identities are released only
  // when the receiving party shares contact.
  sendEnquiry: (data: { listing_id?: string; rfq_id?: string; about_rfq_id?: string; body: string;
                        evidence_request?: string }, idempotencyKey?: string): Promise<Enquiry> =>
    fetchAPI("/market/enquiries", { method: "POST", body: JSON.stringify(data),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined }),
  myEnquiries: (): Promise<{ enquiries: Enquiry[] }> => fetchAPI("/market/enquiries/mine"),
  enquiry: (id: string): Promise<Enquiry> => fetchAPI(`/market/enquiries/${id}`),
  replyEnquiry: (id: string, body: string, evidence_request?: string): Promise<Enquiry> =>
    fetchAPI(`/market/enquiries/${id}/messages`, { method: "POST", body: JSON.stringify({ body, evidence_request }) }),
  decideEnquiry: (id: string, decision: "share-contact" | "decline" | "withdraw"): Promise<Enquiry> =>
    fetchAPI(`/market/enquiries/${id}/${decision}`, { method: "POST" }),
  // R7: open listings assessed against the caller's own RFQ, eligibility first (core/compatibility).
  // offerIds (at most four) for Compare.
  rfqCompatibility: (rfqId: string, offerIds?: string[]): Promise<{ candidates: Candidate[] }> =>
    fetchAPI(`/market/rfqs/${rfqId}/compatibility${offerIds?.length ? `?offer_ids=${offerIds.join(",")}` : ""}`),
  setRFQStatus: (id: string, status: string): Promise<MarketRFQ> =>
    fetchAPI(`/market/rfqs/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }),
  openOffer: (id: string) => fetchAPI(`/market/offers/${id}/open`, { method: "POST" }),
  withdrawOffer: (id: string) => fetchAPI(`/market/offers/${id}/withdraw`, { method: "POST" }),
  // Automated matching is suspended (JML 2026-10-23, spec decision 2B): a party
  // proposes a match to a specific listing; it binds only when both accept.
  // The delivery and payment terms are agreed WITH the proposal (2026-11-06, Phase 0 Q6):
  // when both accept, the contract is made from exactly that, and nothing is typed after.
  proposeMatch: (offer_id: string, rfq_id: string,
                 terms: { delivery_terms?: string; payment_terms?: string } = {}): Promise<MarketMatch> =>
    fetchAPI("/market/matches", { method: "POST", body: JSON.stringify({ offer_id, rfq_id, ...terms }) }),
  myMatches: (): Promise<{ matches: MarketMatch[] }> => fetchAPI("/market/matches/mine"),
  acceptMatch: (id: string): Promise<MarketMatch> =>
    fetchAPI(`/market/matches/${id}/accept`, { method: "POST" }),
  declineMatch: (id: string): Promise<MarketMatch> =>
    fetchAPI(`/market/matches/${id}/decline`, { method: "POST" }),
  // Compatibility: the contract already exists once both sides accept; this returns it.
  createContract: (match_id: string): Promise<MarketContract> =>
    fetchAPI("/market/contracts", { method: "POST", body: JSON.stringify({ match_id }) }),
  myContracts: (): Promise<{ contracts: MarketContract[] }> => fetchAPI("/market/contracts/mine"),
  // TRADE_CONFIRM — four eyes inside each party: one person raises, a colleague approves.
  requestConfirmation: (contractId: string): Promise<{ request_id: string; terms_hash: string }> =>
    fetchAPI(`/market/contracts/${contractId}/confirm`, { method: "POST" }),
  approveConfirmation: (contractId: string, requestId: string): Promise<{ trade_status?: string }> =>
    fetchAPI(`/market/contracts/${contractId}/confirm/${requestId}/approve`, { method: "POST" }),
  confirmations: (contractId: string): Promise<{ confirmations: ContractConfirmation[] }> =>
    fetchAPI(`/market/contracts/${contractId}/confirmations`),
  trail: (correlationId: string): Promise<{ correlation_id: string; events: TrailEvent[] }> =>
    fetchAPI(`/market/trail/${encodeURIComponent(correlationId)}`),
};

// ═══════════════════════════════════════════════════════════════
// Trading book — prefix: /api/v1/trading-book (PostgreSQL, alembic 064/065)
// ═══════════════════════════════════════════════════════════════
export interface Counterparty {
  id: string;
  legal_name: string;
  lei: string | null;
  country_code: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export const tradingBookAPI = {
  counterparties: (): Promise<Counterparty[]> => fetchAPI("/trading-book/counterparties"),
  addCounterparty: (data: { legal_name: string; lei?: string | null; country_code: string }): Promise<Counterparty> =>
    fetchAPI("/trading-book/counterparties", { method: "POST", body: JSON.stringify(data) }),
};

// ═══════════════════════════════════════════════════════════════
// Tokens API — prefix: /api/v1/tokens
// ═══════════════════════════════════════════════════════════════
export const tokensAPI = {
  // An idempotency key (one per form) makes a repeated submit replay, never create twice.
  create: (data: any, idempotencyKey?: string) =>
    fetchAPI("/tokens/", {
      method: "POST",
      body: JSON.stringify(data),
      ...(idempotencyKey ? { headers: { "Idempotency-Key": idempotencyKey } } : {}),
    }),
  list: (params?: { capacity_id?: string; project_id?: string }) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(`/tokens/${query ? `?${query}` : ""}`);
  },
  get: (id: string) => fetchAPI(`/tokens/${id}`),
  updateCompliance: (id: string, data: any) =>
    fetchAPI(`/tokens/${id}/compliance`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) => fetchAPI(`/tokens/${id}`, { method: "DELETE" }),
};

// ═══════════════════════════════════════════════════════════════
// Finance API — prefix: /api/v1/finance
// ═══════════════════════════════════════════════════════════════
export const financeAPI = {
  getStageGates: () => fetchAPI("/finance/stage-gates"),
  getCovenants: () => fetchAPI("/finance/covenants"),
  getInsurance: () => fetchAPI("/finance/insurance"),
  getGuarantees: () => fetchAPI("/finance/guarantees"),
  getContracts: () => fetchAPI("/finance/contracts"),
  getRisks: () => fetchAPI("/finance/risks"),
};

// ═══════════════════════════════════════════════════════════════
// Bankability API — prefix: /api/v1/bankability
// Live engine integration (platform proxies to gex_pf_engine)
// ═══════════════════════════════════════════════════════════════
export const bankabilityAPI = {
  evaluate: (projectId: string = "default") =>
    fetchAPI(`/bankability/evaluate?project_id=${projectId}`),

  evaluateForPersona: (persona: string, projectId: string = "default") =>
    fetchAPI(
      `/bankability/evaluate/persona?persona=${persona}&project_id=${projectId}`,
    ),

  getGates: () => fetchAPI("/bankability/gates"),

  getRules: () => fetchAPI("/bankability/rules"),

  // `maturity` (INTENT | INDICATIVE | AGREED | EXECUTED | EFFECTIVE) is declared
  // on submission. Under evidence rules 3.0.0 a VERIFIED instrument counts only
  // at or above its required maturity. The backend refuses a reviewer-side status
  // that raises it, and refuses retired or unknown evidence keys with a 422
  // naming what to submit instead.
  // Who acted is the session's user — the backend ignores any name sent. A
  // reviewer status (UNDER_REVIEW, VERIFIED, REJECTED, EXPIRED) is accepted
  // only from an independent reviewer, and VERIFIED must name the sha256 of a
  // document on file for the item (Attack A, 2026-09-30).
  updateEvidence: (data: {
    project_id?: string;
    evidence_key: string;
    new_status: string;
    notes?: string;
    maturity?: string;
    document_sha256?: string;
    valid_until?: string;
  }) =>
    fetchAPI("/bankability/evidence", {
      method: "POST",
      body: JSON.stringify({ project_id: "default", ...data }),
    }),

  // Stores the file with its sha256 and moves the item to SUBMITTED, with the
  // uploader as its submitter. What a reviewer later opens and verifies.
  uploadEvidenceDocument: (projectId: string, evidenceKey: string, file: File) => {
    const form = new FormData();
    form.append("project_id", projectId);
    form.append("evidence_key", evidenceKey);
    form.append("file", file);
    return fetchAPI("/bankability/evidence/document", { method: "POST", body: form });
  },

  // Documents on file for one item, newest first.
  listEvidenceDocuments: (projectId: string, evidenceKey: string) =>
    fetchAPI(
      `/bankability/evidence/documents?project_id=${encodeURIComponent(projectId)}&evidence_key=${encodeURIComponent(evidenceKey)}`,
    ),

  // The download needs the bearer, which a plain link does not send.
  openEvidenceDocument: async (sha256: string) => {
    const response = await fetch(
      `${API_BASE_URL}/bankability/evidence/document/${encodeURIComponent(sha256)}/download`,
      { headers: { ...authHeader() } },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const url = URL.createObjectURL(await response.blob());
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },

  // Name the person who must produce an evidence item (owner company or
  // platform admin only; assignee must be an active account of the owner).
  // Reassignment clears the due date: a date is the assignee's own commitment.
  assignEvidence: (data: {
    project_id: string;
    evidence_key: string;
    assignee_user_id: string | null;
  }) =>
    fetchAPI("/bankability/evidence/assign", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Only the assignee can commit; the date must be today or later.
  commitEvidence: (data: { project_id: string; evidence_key: string; due_date: string }) =>
    fetchAPI("/bankability/evidence/commit", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  assignableAccounts: (projectId: string) =>
    fetchAPI(`/bankability/evidence/assignable?project_id=${encodeURIComponent(projectId)}`),

  myEvidenceRequests: () => fetchAPI("/bankability/evidence/assigned-to-me"),

  // Commitment cards (rules 4.0.0): structured offtake / EPC / schedule /
  // supply / model terms. The engine grades the offtake (O0–O7) and EPC (E0–E6)
  // ladders and runs coherence checks from them. Owner company or platform
  // admin only; a save replaces the whole card and is audited.
  getTerms: (projectId: string) =>
    fetchAPI(`/bankability/terms?project_id=${encodeURIComponent(projectId)}`),

  saveTerms: (data: { project_id: string; card_type: string; terms: Record<string, unknown> }) =>
    fetchAPI("/bankability/terms", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  listEvidence: (projectId: string = "default") =>
    fetchAPI(`/bankability/evidence?project_id=${projectId}`),

  checkRegression: (projectId: string = "default") =>
    fetchAPI(`/bankability/regression/check?project_id=${projectId}`),

  health: () => fetchAPI("/bankability/health"),

  // The engine's readout for one project, all twelve gates. Runs the engine and
  // writes nothing — unlike evaluate(), which rewrites the stored snapshot. The
  // shared source for /projects, State & Blockers and Capital Eligibility.
  readout: (projectId: string) =>
    fetchAPI(
      `/bankability/projects/${encodeURIComponent(projectId)}/bankability/EXECUTIVE`,
    ),
};

// ═══════════════════════════════════════════════════════════════
// Vocabulary API — prefix: /api/v1/vocabulary
// The platform's one home for user-facing labels (app/core/vocabulary.py).
// ═══════════════════════════════════════════════════════════════
export const vocabularyAPI = {
  concept: (name: string) => fetchAPI(`/vocabulary/${encodeURIComponent(name)}`),
};

// ═══════════════════════════════════════════════════════════════
// Finance Model API — prefix: /api/v1/finance-model
// Proxied to gex_pf_engine (port 8001)
// ═══════════════════════════════════════════════════════════════
export const financeModelAPI = {
  health: () => fetchAPI("/finance-model/health"),

  calculateCfads: (params: {
    production_mtpd: number;
    offtake_price_eur_kg: number;
    opex_eur_kg: number;
    subsidies?: Record<string, number>;
    maintenance_capex?: number;
    period_days?: number;
  }) =>
    fetchAPI("/finance-model/cfads", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  modelLifetime: (params: {
    capacity_mtpd: number;
    price_eur_kg: number;
    opex_eur_kg: number;
    total_capex: number;
    senior_debt_amount: number;
    interest_rate: number;
    tenor_years: number;
    operations_start_year?: number;
  }) =>
    fetchAPI("/finance-model/lifetime", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  checkCovenants: (params: {
    dscr: number;
    dsra_funded: boolean;
    completion_guarantee: boolean;
    covenant_requirements: Record<string, any>;
  }) =>
    fetchAPI("/finance-model/covenants", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  executeWaterfall: (params: {
    cfads: number;
    senior_debt_service: number;
    junior_debt_service?: number;
    mezzanine_service?: number;
    dsra_required?: number;
    maintenance_reserve?: number;
  }) =>
    fetchAPI("/finance-model/waterfall", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  calculateMetrics: (params: {
    revenue: number;
    opex: number;
    capex: number;
    debt_service: number;
    period: string;
  }) =>
    fetchAPI("/finance-model/metrics", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  // ── Concessional / DFI-aware endpoints (proxied to pf_engine) ──

  calculateCfadsWithFinancing: (params: {
    production_mtpd: number;
    offtake_price_eur_kg: number;
    opex_eur_kg: number;
    year?: number;
    subsidies?: Record<string, number>;
    maintenance_capex?: number;
    tranches: Array<{
      name: string;
      tranche_type: string;
      amount: number;
      rate: number;
      tenor: number;
      grace_period_years?: number;
      dfi_provider?: string;
      is_first_loss?: boolean;
    }>;
    equity_amount: number;
    equity_cost?: number;
    grants_amount?: number;
  }) =>
    fetchAPI("/finance-model/cfads-with-financing", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  executeWaterfallStructured: (params: {
    cfads: number;
    year?: number;
    tranches: Array<{
      name: string;
      tranche_type: string;
      amount: number;
      rate: number;
      tenor: number;
      grace_period_years?: number;
      dfi_provider?: string;
    }>;
    equity_amount: number;
    grants_amount?: number;
  }) =>
    fetchAPI("/finance-model/waterfall-structured", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  evaluateSovereignCert: (params: {
    molecule: string;
    country: string;
    ghg_intensity: number;
    renewable_electricity_pct: number;
    dfi_provider?: string;
    concessional_share?: number;
    esg_score?: number;
    project_id?: string;
  }) =>
    fetchAPI("/decision-twin/evaluate/sovereign-certification", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  // `powerOpexShare` is REQUIRED for heatmapCells / sensitivityRows /
  // breakevenMetrics to come back populated. Both stress axes act on the power
  // component of OPEX, and the trading book projection carries one
  // undifferentiated OPEX total, so without the share there is no honest basis
  // for the grid. Omit it and those three arrays are empty with
  // sensitivityBasis="none_power_opex_split_not_supplied" — render that reason
  // rather than an empty chart. (The backend previously assumed 0.73 for every
  // project on earth, which silently set every cell and every break-even.)
  dscrHeatmap: (params: {
    assetId: string;
    fromDate?: string;
    toDate?: string;
    annualDebtService?: number;
    covenantFloor?: number;
    powerOpexShare?: number;
    baseEfficiencyPct?: number;
  }) => {
    const q = new URLSearchParams();
    if (params.fromDate) q.set("from_date", params.fromDate);
    if (params.toDate) q.set("to_date", params.toDate);
    if (params.annualDebtService != null) q.set("annual_debt_service", String(params.annualDebtService));
    if (params.covenantFloor != null) q.set("covenant_floor", String(params.covenantFloor));
    if (params.powerOpexShare != null) q.set("power_opex_share", String(params.powerOpexShare));
    if (params.baseEfficiencyPct != null) q.set("base_efficiency_pct", String(params.baseEfficiencyPct));
    const qs = q.toString();
    return fetchAPI(`/finance-model/dscr-heatmap/${params.assetId}${qs ? `?${qs}` : ""}`);
  },
};

// ═══════════════════════════════════════════════════════════════
// Pricing API — prefix: /api/v1/pricing
// Proxied to gex_pf_engine (port 8001)
// ═══════════════════════════════════════════════════════════════
export const pricingAPI = {
  molecules: () => fetchAPI("/pricing/molecules"),

  spotPrice: (molecule: string) => fetchAPI(`/pricing/spot/${molecule}`),

  termCurve: (molecule: string) => fetchAPI(`/pricing/term-curve/${molecule}`),

  decomposition: (params: {
    molecule: string;
    tenor_months?: number;
    spot_override?: number;
    tranches?: Array<{
      name: string;
      tranche_type: string;
      amount: number;
      rate: number;
      tenor: number;
      grace_period_years?: number;
      dfi_provider?: string;
      is_first_loss?: boolean;
    }>;
    equity_amount?: number;
    equity_cost?: number;
    grants_amount?: number;
    subsidies?: Record<string, number>;
    insurance_annual_eur?: number;
    insurance_provider?: string;
    annual_production_tonnes?: number;
    certifications?: string[];
    correlation_id?: string;
  }) =>
    fetchAPI("/pricing/decomposition", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  decompositionMultiTenor: (params: {
    molecule: string;
    tranches?: Array<{
      name: string;
      tranche_type: string;
      amount: number;
      rate: number;
      tenor: number;
      grace_period_years?: number;
      dfi_provider?: string;
    }>;
    equity_amount?: number;
    grants_amount?: number;
    subsidies?: Record<string, number>;
    insurance_annual_eur?: number;
    insurance_provider?: string;
    annual_production_tonnes?: number;
  }) =>
    fetchAPI("/pricing/decomposition/multi-tenor", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  calibrateCurve: (params: Record<string, any>) =>
    fetchAPI("/pricing/curve/calibrate", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  pricingCurve: (params: Record<string, any> & { taus?: number[] }) =>
    fetchAPI("/pricing/curve/pricing", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  forecastCone: (params: Record<string, any>) =>
    fetchAPI("/pricing/curve/forecast", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  calibrationMemory: (projectId: string) =>
    fetchAPI(`/pricing/curve/${projectId}/memory`),

  offtakeValue: (params: Record<string, any>) =>
    fetchAPI("/pricing/offtake/value", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  portfolioRollup: (params: Record<string, any>) =>
    fetchAPI("/pricing/offtake/portfolio-rollup", {
      method: "POST",
      body: JSON.stringify(params),
    }),
};

// ═══════════════════════════════════════════════════════════════
// WAE Approvals API — prefix: /api/v1/approvals
// Workflow Authorization Engine — countersignature + quorum
// ═══════════════════════════════════════════════════════════════
export const approvalsAPI = {
  health: () => fetchAPI("/approvals/health"),

  // The initiator, approver and signer are the signed-in account (server-side,
  // from the token) — never a field of the request.
  evaluate: (params: {
    action_type: string;
    resource_id?: string;
    project_id?: string;
    payload?: Record<string, any>;
    amount?: number;
    volume?: number;
  }) =>
    fetchAPI("/approvals/evaluate", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  getPending: (params?: { project_id?: string }) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(`/approvals/pending${query ? `?${query}` : ""}`);
  },

  getRequest: (requestId: string) => fetchAPI(`/approvals/${requestId}`),

  decide: (
    requestId: string,
    params: {
      decision: "APPROVE" | "REJECT";
      reason_text?: string;
    },
  ) =>
    fetchAPI(`/approvals/${requestId}/decide`, {
      method: "POST",
      body: JSON.stringify(params),
    }),

  getAuditTrail: (resourceId: string) =>
    fetchAPI(`/approvals/audit-trail/${resourceId}`),

  listPolicies: () => fetchAPI("/approvals/policies/list"),

  getSodPairs: () => fetchAPI("/approvals/sod/pairs"),
};

// ═══════════════════════════════════════════════════════════════
// Commitments API — prefix: /api/v1/commitments
// CSS — Commitment Signature Service (non-repudiation)
// ═══════════════════════════════════════════════════════════════
export const commitmentsAPI = {
  health: () => fetchAPI("/commitments/health"),

  sign: (params: {
    action_type: string;
    project_id: string;
    payload: Record<string, any>;
    approval_request_id?: string;
  }) =>
    fetchAPI("/commitments/sign", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  // The counterparty is the signed-in account (server-side, from the token).
  countersign: (commitmentId: string) =>
    fetchAPI(`/commitments/${commitmentId}/countersign`, { method: "POST" }),

  verify: (commitmentId: string) =>
    fetchAPI(`/commitments/${commitmentId}/verify`),

  listForProject: (projectId: string) =>
    fetchAPI(`/commitments/project/${projectId}`),

  get: (commitmentId: string) => fetchAPI(`/commitments/${commitmentId}`),
};

// ═══════════════════════════════════════════════════════════════
// Project Activity API — prefix: /api/v1/project-activity
// Cross-functional handoff and trust feed
// ═══════════════════════════════════════════════════════════════
export const projectActivityAPI = {
  listForProject: (projectId: string, params?: { limit?: number }) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(
      `/project-activity/${projectId}${query ? `?${query}` : ""}`,
    );
  },
};

// ═══════════════════════════════════════════════════════════════
// Project Truth API — prefix: /api/v1/project-truth
// One dashboard-ready truth object per project
// ═══════════════════════════════════════════════════════════════
// Reviewer appointments — GEX staff appoint evidence reviewers on instruction (JML, 2026-10-21).
export interface ReviewerAppointment {
  user_id: string;
  user_name: string;
  company_id: string;
  company_name: string;
  role: string;
  gates: string[];
}

export interface ProjectReviewers {
  project_id: string;
  reviewers: ReviewerAppointment[];
  can_appoint: boolean;
  roles: Record<string, string[]>;
}

export const reviewersAPI = {
  list: (projectId: string): Promise<ProjectReviewers> =>
    fetchAPI(`/projects/${encodeURIComponent(projectId)}/reviewers`),

  appoint: (
    projectId: string,
    body: { user_id: string; role: string; instructed_by: string; instruction_sha256: string },
  ) =>
    fetchAPI(`/projects/${encodeURIComponent(projectId)}/reviewers`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  revoke: (projectId: string, userId: string, role: string, reason: string) =>
    fetchAPI(
      `/projects/${encodeURIComponent(projectId)}/reviewers/${encodeURIComponent(userId)}?role=${encodeURIComponent(role)}`,
      { method: "DELETE", body: JSON.stringify({ reason }) },
    ),
};

export const projectTruthAPI = {
  get: (
    projectId: string,
    params?: {
      company_type?: string;
      business_function?: string;
      service_type?: string | null;
      capabilities?: string[];
    },
  ) => {
    const query = new URLSearchParams();
    if (params?.company_type) query.set("company_type", params.company_type);
    if (params?.business_function)
      query.set("business_function", params.business_function);
    if (params?.service_type) query.set("service_type", params.service_type);
    if (params?.capabilities?.length)
      query.set("capabilities", params.capabilities.join(","));
    const suffix = query.toString();
    return fetchAPI(`/project-truth/${projectId}${suffix ? `?${suffix}` : ""}`);
  },
};

// ═══════════════════════════════════════════════════════════════
// Plant Data API — prefix: /api/v1/plant-data
// OT/IT Boundary — inbound telemetry from registered gateways
// ═══════════════════════════════════════════════════════════════
export const plantDataAPI = {
  health: () => fetchAPI("/plant-data/health"),

  getForProject: (
    projectId: string,
    params?: { data_type?: string; limit?: number },
  ) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(`/plant-data/data/${projectId}${query ? `?${query}` : ""}`);
  },

  listGateways: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : "";
    return fetchAPI(`/plant-data/gateways${query}`);
  },

  getGateway: (gatewayId: string) =>
    fetchAPI(`/plant-data/gateways/${gatewayId}`),
};

// ═══════════════════════════════════════════════════════════════
// CISO Security Extension API — prefix: /api/v1/ciso
// Barriers, Residency, Gateways (Domains 3, 4, 5)
// ═══════════════════════════════════════════════════════════════
export const cisoSecurityAPI = {
  listBarriers: () => fetchAPI("/ciso/barriers"),
  getBarrier: (barrierId: string) => fetchAPI(`/ciso/barriers/${barrierId}`),
  createBarrier: (params: {
    side_a: string;
    side_b: string;
    barrier_type?: string;
    applies_to_data?: string[];
    description?: string;
  }) =>
    fetchAPI("/ciso/barriers", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  listResidencyPolicies: () => fetchAPI("/ciso/residency/policies"),
  upsertResidencyPolicy: (params: {
    data_category: string;
    required_jurisdiction: string;
    storage_zone: string;
    note?: string;
  }) =>
    fetchAPI("/ciso/residency/policies", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  getResidencyAudit: () => fetchAPI("/ciso/residency/audit"),

  listGateways: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : "";
    return fetchAPI(`/ciso/gateways${query}`);
  },
};
