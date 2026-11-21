/**
 * GEX house style for result and parameter tables (docs/GEX_UI_Reform_Project_Edit.md):
 * Bloomberg density, no icons, uppercase muted labels, numbers right-aligned in tabular
 * figures with their unit beside them, a rule under each row and a heavier rule over a total.
 */
export const th = 'border-b border-slate-400 px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-500'
export const thr = `${th} text-right`
export const td = 'border-b border-slate-200 px-2 py-0.5 align-top'
export const tdr = `${td} text-right font-mono tabular-nums`
export const tdt = `${td} border-t border-t-slate-700 font-semibold`
export const foot = 'text-[11px] text-slate-500'
export const label = 'text-[10px] font-semibold uppercase tracking-wide text-slate-500'
export const statusLine = 'flex flex-wrap items-baseline gap-x-2 gap-y-1 border-b border-slate-400 pb-1 font-mono text-[11px] text-slate-700'

export const nf = (n: number | null | undefined, d = 0) =>
  n == null || !Number.isFinite(n) ? '—' : n.toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d })
