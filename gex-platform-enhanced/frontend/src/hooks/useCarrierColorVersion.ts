/**
 * useCarrierColorVersion — returns a counter that bumps every time a carrier
 * color override is changed. Components that resolve colors via
 * `getColorFromResource` should depend on this so they re-render live when
 * the user edits Legend Recolor.
 */
import { useEffect, useState } from "react";
import { subscribeCarrierOverrides } from "@/lib/carrierColorOverrides";

export function useCarrierColorVersion(): number {
  const [v, setV] = useState(0);
  useEffect(() => subscribeCarrierOverrides(() => setV((n) => n + 1)), []);
  return v;
}