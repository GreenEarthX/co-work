/**
 * Checks whether the frontend has a usable backend client configuration.
 * Falls back to the project's runtime-safe publishable config when env injection is missing.
 */
import { isBackendConfigured as backendConfigured } from "@/lib/backendClient";

export function isBackendConfigured(): boolean {
  return backendConfigured();
}
