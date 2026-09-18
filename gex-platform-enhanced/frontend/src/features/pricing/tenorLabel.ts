/** Tenor display label: whole years as "NY", everything else in months ("18M").
 *  Mirrors tenor_label() in gex_pf_engine pf_engine/core/gabillon.py — keep in step. */
export function tenorLabel(months: number): string {
  return months >= 12 && months % 12 === 0 ? `${months / 12}Y` : `${months}M`;
}
