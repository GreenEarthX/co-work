/**
 * Team directory — teams, roles, members, permission gates, gate holdings.
 *
 * WAS: five `supabase.from(...)` reads, five round trips, no authentication.
 * The anon key that authorised them ships in the bundle, so every one of those
 * tables answered anybody who asked (measured 2026-09-19).
 *
 * NOW: one authenticated call to `GET /api/v1/directory/overview`. The two
 * refetches this hook has always exposed hit the narrow endpoints so a caller
 * refreshing one collection does not re-pull the other four, and write their
 * result back into the same cache entry.
 *
 * The row shapes did not change — `TeamUserRow` and friends are re-exported
 * from `@/lib/directoryApi` so existing imports from this module keep working
 * — with one exception that is not cosmetic: `email` and `phone` are now
 * OPTIONAL, because the server omits them for anyone who is not GEX staff.
 */
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchDirectoryGateStatus,
  fetchDirectoryMembers,
  fetchDirectoryOverview,
  type DirectoryOverview,
  type GateStatusRow,
  type TeamUserRow,
} from "@/lib/directoryApi";

export type {
  GateStatusRow,
  PermissionGate,
  RoleRow,
  TeamRow,
  TeamUserRow,
} from "@/lib/directoryApi";

const DIRECTORY_KEY = ["directory", "overview"] as const;

export function useTeamData() {
  const queryClient = useQueryClient();

  const overviewQ = useQuery({
    queryKey: DIRECTORY_KEY,
    queryFn: fetchDirectoryOverview,
  });

  const patch = useCallback(
    (fields: Partial<DirectoryOverview>) => {
      queryClient.setQueryData<DirectoryOverview>(DIRECTORY_KEY, (prev) =>
        prev ? { ...prev, ...fields } : prev,
      );
    },
    [queryClient],
  );

  const refetchUsers = useCallback(async (): Promise<TeamUserRow[]> => {
    const members = await fetchDirectoryMembers();
    patch({ members });
    return members;
  }, [patch]);

  const refetchGateStatuses = useCallback(async (): Promise<GateStatusRow[]> => {
    const gate_statuses = await fetchDirectoryGateStatus();
    patch({ gate_statuses });
    return gate_statuses;
  }, [patch]);

  return {
    teams: overviewQ.data?.teams ?? [],
    roles: overviewQ.data?.roles ?? [],
    users: overviewQ.data?.members ?? [],
    gates: overviewQ.data?.gates ?? [],
    gateStatuses: overviewQ.data?.gate_statuses ?? [],
    /** False when the caller is not GEX staff — `email`/`phone` are absent. */
    personalDataIncluded: overviewQ.data?.personal_data_included ?? false,
    /**
     * True when the server refused this caller the directory: not an error,
     * a decision. GEX's internal directory is staff-only, so a customer's
     * user gets empty collections and a screen with no @mention suggestions.
     */
    forbidden: overviewQ.data?.forbidden ?? false,
    isLoading: overviewQ.isLoading,
    isError: overviewQ.isError,
    refetchUsers,
    refetchGateStatuses,
  };
}
