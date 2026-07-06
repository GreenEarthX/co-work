import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/lib/backendClient";

export interface TeamRow {
  id: string;
  name: string;
  description: string;
  primary_modules: string;
}

export interface RoleRow {
  id: string;
  role_code: string;
  role_name: string;
  permission_tier: string;
  is_default_admin: boolean;
  team_id: string;
}

export interface TeamUserRow {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  organisation: string | null;
  status: string;
  primary_team_id: string;
  primary_role_id: string;
  secondary_team_id: string | null;
  secondary_role_id: string | null;
}

export interface GateStatusRow {
  user_id: string;
  gate_id: string;
  status: string;
}

export interface PermissionGate {
  id: string;
  gate_name: string;
  trigger_description: string;
}

export function useTeamData() {
  const teamsQ = useQuery({
    queryKey: ["teams"],
    queryFn: async () => {
      // Order by name so the T01 → T08 prefix surfaces in sequence.
      const { data, error } = await supabase.from("teams").select("*").order("name");
      if (error) throw error;
      return data as TeamRow[];
    },
  });

  const rolesQ = useQuery({
    queryKey: ["roles"],
    queryFn: async () => {
      const { data, error } = await supabase.from("roles").select("*").order("role_code");
      if (error) throw error;
      return data as RoleRow[];
    },
  });

  const usersQ = useQuery({
    queryKey: ["team_users"],
    queryFn: async () => {
      const { data, error } = await supabase.from("team_users").select("*").order("full_name");
      if (error) throw error;
      return data as TeamUserRow[];
    },
  });

  const gatesQ = useQuery({
    queryKey: ["permission_gates"],
    queryFn: async () => {
      const { data, error } = await supabase.from("permission_gates").select("*").order("id");
      if (error) throw error;
      return data as PermissionGate[];
    },
  });

  const gateStatusQ = useQuery({
    queryKey: ["user_gate_status"],
    queryFn: async () => {
      const { data, error } = await supabase.from("user_gate_status").select("user_id, gate_id, status");
      if (error) throw error;
      return data as GateStatusRow[];
    },
  });

  const isLoading = teamsQ.isLoading || rolesQ.isLoading || usersQ.isLoading || gatesQ.isLoading || gateStatusQ.isLoading;
  const isError = teamsQ.isError || rolesQ.isError || usersQ.isError || gatesQ.isError || gateStatusQ.isError;

  return {
    teams: teamsQ.data ?? [],
    roles: rolesQ.data ?? [],
    users: usersQ.data ?? [],
    gates: gatesQ.data ?? [],
    gateStatuses: gateStatusQ.data ?? [],
    isLoading,
    isError,
    refetchUsers: usersQ.refetch,
    refetchGateStatuses: gateStatusQ.refetch,
  };
}
