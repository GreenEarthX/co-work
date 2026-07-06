// Screen: API client (no screen)
// API Client for GreenEarthX Platform
const API_BASE_URL = "/api/v1";

// Pull the bearer token from the stored session so EVERY shared-client call is
// authenticated. Without this, /api/v1/bankability/* and /finance-model/* return
// 401 — the list silently fails to load and action buttons become dead-ends.
function authHeader(): Record<string, string> {
  try {
    const raw = localStorage.getItem("gex_auth_session");
    const token = raw ? (JSON.parse(raw) as { token?: string }).token : null;
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const url = `${API_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...authHeader(),
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
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
  create: (data: any) =>
    fetchAPI("/capacities/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  list: () => fetchAPI("/capacities/"),
  get: (id: string) => fetchAPI(`/capacities/${id}`),
  delete: (id: string) => fetchAPI(`/capacities/${id}`, { method: "DELETE" }),
};

// ═══════════════════════════════════════════════════════════════
// Offers API — prefix: /api/v1/marketplace
// ═══════════════════════════════════════════════════════════════
export const offersAPI = {
  create: (data: any) =>
    fetchAPI("/marketplace/offers", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  list: (params?: { molecule?: string; status?: string }) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(`/marketplace/offers${query ? `?${query}` : ""}`);
  },
  get: (id: string) => fetchAPI(`/marketplace/offers/${id}`),
  updateStatus: (id: string, status: string) =>
    fetchAPI(`/marketplace/offers/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
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
  get: (id: string) => fetchAPI(`/matching/rfqs/${id}`),
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
    fetchAPI(`/contracts/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  getAcceptedMatches: () => fetchAPI("/contracts/accepted-matches/available"),
};

// ═══════════════════════════════════════════════════════════════
// Tokens API — prefix: /api/v1/tokens
// ═══════════════════════════════════════════════════════════════
export const tokensAPI = {
  create: (data: any) =>
    fetchAPI("/tokens/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  list: (params?: { capacity_id?: string }) => {
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

  updateEvidence: (data: {
    project_id?: string;
    evidence_key: string;
    new_status: string;
    submitted_by?: string;
    notes?: string;
  }) =>
    fetchAPI("/bankability/evidence", {
      method: "POST",
      body: JSON.stringify({ project_id: "default", ...data }),
    }),

  listEvidence: (projectId: string = "default") =>
    fetchAPI(`/bankability/evidence?project_id=${projectId}`),

  seedDemo: (projectId: string = "default") =>
    fetchAPI(`/bankability/evidence/seed?project_id=${projectId}`, {
      method: "POST",
    }),

  checkRegression: (projectId: string = "default") =>
    fetchAPI(`/bankability/regression/check?project_id=${projectId}`),

  health: () => fetchAPI("/bankability/health"),
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

  dscrHeatmap: (params: {
    assetId: string;
    fromDate?: string;
    toDate?: string;
    annualDebtService?: number;
    covenantFloor?: number;
  }) => {
    const q = new URLSearchParams();
    if (params.fromDate) q.set("from_date", params.fromDate);
    if (params.toDate) q.set("to_date", params.toDate);
    if (params.annualDebtService != null) q.set("annual_debt_service", String(params.annualDebtService));
    if (params.covenantFloor != null) q.set("covenant_floor", String(params.covenantFloor));
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

  greenmeshRollup: (params: Record<string, any>) =>
    fetchAPI("/pricing/offtake/rollup", {
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

  evaluate: (params: {
    initiator_user_id: string;
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

  getPending: (params?: { company_id?: string; project_id?: string }) => {
    const query = new URLSearchParams(params as any).toString();
    return fetchAPI(`/approvals/pending${query ? `?${query}` : ""}`);
  },

  getRequest: (requestId: string) => fetchAPI(`/approvals/${requestId}`),

  decide: (
    requestId: string,
    params: {
      approver_user_id: string;
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
    initiator_user_id: string;
    initiator_company_id: string;
    action_type: string;
    project_id: string;
    payload: Record<string, any>;
    approval_request_id?: string;
    approver_snapshots?: Record<string, any>[];
  }) =>
    fetchAPI("/commitments/sign", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  countersign: (
    commitmentId: string,
    params: {
      counterparty_user_id: string;
      counterparty_company_id: string;
    },
  ) =>
    fetchAPI(`/commitments/${commitmentId}/countersign`, {
      method: "POST",
      body: JSON.stringify(params),
    }),

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

  getDemoData: (projectId: string) => fetchAPI(`/plant-data/demo/${projectId}`),

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
