/**
 * Persistence hook for per-equipment equation configurations.
 * Stored in Supabase table `equipment_equations`, scoped by user/plant/node.
 */
import { useCallback, useEffect, useState } from "react";
import { supabase } from "@/lib/backendClient";
import { useAuth } from "@/contexts/AuthContext";
import type { VariableBinding } from "@/lib/equations/sourceResolver";

export interface StoredEquipmentEquation {
  id: string;
  equation_id: string;
  equation_expression: string;
  output_param: string;
  variable_bindings: Record<string, VariableBinding>;
}

export function useEquipmentEquations(plantSlug: string, nodeId: string, equipmentLabel: string) {
  const { user } = useAuth();
  const userId = user?.id ?? "anonymous";
  const [items, setItems] = useState<StoredEquipmentEquation[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!plantSlug || !nodeId) return;
    setLoading(true);
    const { data, error } = await supabase
      .from("equipment_equations")
      .select("id, equation_id, equation_expression, output_param, variable_bindings")
      .eq("user_id", userId)
      .eq("plant_slug", plantSlug)
      .eq("equipment_node_id", nodeId);
    if (!error && data) {
      setItems(
        data.map((d: Record<string, unknown>) => ({
          id: d.id as string,
          equation_id: d.equation_id as string,
          equation_expression: d.equation_expression as string,
          output_param: d.output_param as string,
          variable_bindings: (d.variable_bindings ?? {}) as unknown as Record<string, VariableBinding>,
        })),
      );
    }
    setLoading(false);
  }, [userId, plantSlug, nodeId]);

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
      const { error } = await supabase
        .from("equipment_equations")
        .upsert(
          [
            {
              user_id: userId,
              plant_slug: plantSlug,
              equipment_node_id: nodeId,
              equipment_label: equipmentLabel,
              equation_id: payload.equation_id,
              equation_expression: payload.equation_expression,
              output_param: payload.output_param,
              variable_bindings: JSON.parse(JSON.stringify(payload.variable_bindings)),
            },
          ],
          { onConflict: "user_id,plant_slug,equipment_node_id,equation_id" },
        );
      if (!error) await refresh();
      return { error };
    },
    [userId, plantSlug, nodeId, equipmentLabel, refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      const { error } = await supabase.from("equipment_equations").delete().eq("id", id);
      if (!error) await refresh();
      return { error };
    },
    [refresh],
  );

  return { items, loading, upsert, remove, refresh };
}