// Screen: API client (no screen)
// Re-export all API clients from the centralized api.ts
// This file exists so that both `@/lib/api` and `@/api` imports work.
export {
  capacitiesAPI,
  offersAPI,
  rfqsAPI,
  matchingAPI,
  contractsAPI,
  tokensAPI,
  financeAPI,
  bankabilityAPI,
  financeModelAPI,
  pricingAPI,
  projectTruthAPI,
} from "../api";
