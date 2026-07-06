// Pricing workbench hooks.
import { useMutation, useQuery } from "@tanstack/react-query";

import { pricingAPI } from "@/api";

export type PricingPayload = Record<string, any> & { project_id: string };

function enabled(payload: PricingPayload | null | undefined): payload is PricingPayload {
  return Boolean(payload?.project_id);
}

export function useCurveCalibration() {
  return useMutation({
    mutationKey: ["pricing", "curve", "calibrate"],
    mutationFn: (payload: PricingPayload) => pricingAPI.calibrateCurve(payload),
  });
}

export function usePricingCurve(
  payload: (PricingPayload & { taus?: number[] }) | null,
) {
  return useQuery({
    queryKey: ["pricing", "curve", "pricing", payload],
    queryFn: () => pricingAPI.pricingCurve(payload!),
    enabled: enabled(payload),
  });
}

export function useForecastCone(payload: PricingPayload | null) {
  return useQuery({
    queryKey: ["pricing", "curve", "forecast", payload],
    queryFn: () => pricingAPI.forecastCone(payload!),
    enabled: enabled(payload),
  });
}

export function useOfftakeValue() {
  return useMutation({
    mutationKey: ["pricing", "offtake", "value"],
    mutationFn: (payload: PricingPayload) => pricingAPI.offtakeValue(payload),
  });
}

export function useGreenmeshRollup() {
  return useMutation({
    mutationKey: ["pricing", "offtake", "rollup"],
    mutationFn: (payload: PricingPayload) => pricingAPI.greenmeshRollup(payload),
  });
}
