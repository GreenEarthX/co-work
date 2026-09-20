/**
 * Persistence hook for per-equipment equation configurations.
 *
 * WAS: `supabase.from("equipment_equations")` under the anon key shipped in
 * the bundle, with the user id supplied by the browser — and a delete that
 * carried no user scoping at all (`.delete().eq("id", id)`), so it removed any
 * row by id for anybody. CLAUDE_HANDOFF §8.16.
 *
 * NOW: `/api/v1/equipment-equations`. The owner comes from the session token,
 * so no call names a user, and a delete aimed at someone else's row matches
 * nothing and answers 404.
 */
import { useCallback, useEffect, useState } from "react";
import { getAuthToken } from "@/lib/authToken";
import type { VariableBinding } from "@/lib/equations/sourceResolver";

const API_PREFIX = "/api/v1/equipment-equations";

export interface StoredEquipmentEquation {
  id: string;
  equation_id: string;
  equation_expression: string;
  output_param: string;
  variable_bindings: Record<string, VariableBinding>;
}

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export function useEquipmentEquations(plantSlug: string, nodeId: string, equipmentLabel: string) {
  const [items, setItems] = useState<StoredEquipmentEquation[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!plantSlug || !nodeId) return;
    setLoading(true);
    try {
      const q = `?plant_slug=${encodeURIComponent(plantSlug)}&node_id=${encodeURIComponent(nodeId)}`;
      const res = await fetch(`${API_PREFIX}${q}`, { headers: authHeaders() });
      if (res.ok) setItems((await res.json()) as StoredEquipmentEquation[]);
    } catch {
      /* leave the last good list in place */
    } finally {
      setLoading(false);
    }
  }, [plantSlug, nodeId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const upsert = useCallback(
    async (payload: {
      equation_id: string;
      equation_expression: string;
      output_param: string;
      variable_bindings: Record<string, VariableBinding>;
    }) => {
      try {
        const res = await fetch(API_PREFIX, {
          method: "PUT",
          headers: authHeaders(),
          body: JSON.stringify({
            plant_slug: plantSlug,
            equipment_node_id: nodeId,
            equipment_label: equipmentLabel,
            ...payload,
          }),
        });
        if (!res.ok) return { error: new Error(`HTTP ${res.status}`) };
        await refresh();
        return { error: null };
      } catch (e) {
        return { error: e instanceof Error ? e : new Error("save failed") };
      }
    },
    [plantSlug, nodeId, equipmentLabel, refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      try {
        // No user id in this call, and none accepted: the server deletes the
        // row only if it belongs to the caller, and answers 404 otherwise.
        const res = await fetch(`${API_PREFIX}/${encodeURIComponent(id)}`, {
          method: "DELETE",
          headers: authHeaders(),
        });
        if (!res.ok) return { error: new Error(`HTTP ${res.status}`) };
        await refresh();
        return { error: null };
      } catch (e) {
        return { error: e instanceof Error ? e : new Error("delete failed") };
      }
    },
    [refresh],
  );

  return { items, loading, upsert, remove, refresh };
}
