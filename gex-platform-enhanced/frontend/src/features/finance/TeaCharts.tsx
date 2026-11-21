// Screen part: the three graphs of a TEA run's results view (JML, 21 Nov 2026).
/**
 * Drawn from the run's record only (tea_inputs.analysis), like every table beside them:
 *   1. CostPerKgBar       where the required price comes from (parts of a whole, one stacked bar)
 *   2. CostByYearChart    what the plant costs each year, by component (stacked columns, M EUR)
 *   3. GabillonPriceChart the product's Gabillon price by operating year against the required price
 * Plain SVG, no chart library: deterministic, printable, testable. House style: slate inks, one
 * accent for the figure that matters (the required price), units on every axis, no gridline noise.
 */
import { nf } from '@/lib/houseStyle'

/* eslint-disable @typescript-eslint/no-explicit-any */
const INK = '#0f172a', MUTED = '#64748b', RULE = '#cbd5e1', ACCENT = '#b45309'
const SHADES = ['#1e293b', '#475569', '#64748b', '#94a3b8', '#cbd5e1', '#e2e8f0']
const FONT = { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 10 }

function niceMax(v: number): number {
  if (v <= 0) return 1
  const p = 10 ** Math.floor(Math.log10(v)), r = v / p
  return (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * p
}

/** 1 — the required price split into its parts, which add back to it. */
export function CostPerKgBar({ pk, ccy }: { pk: any; ccy: string }) {
  const parts: [string, number][] = [
    ['Capital', pk.capital],
    ...Object.entries(pk.variable as Record<string, number>).map(([k, v]) => [k, v] as [string, number]),
    ['Fixed operating', Object.values(pk.fixed as Record<string, number>).reduce((s, v) => s + v, 0)],
  ].filter(([, v]) => v > 0) as [string, number][]
  const total = parts.reduce((s, [, v]) => s + v, 0) || 1
  const W = 640, x0 = 8, bw = W - 16
  let x = x0
  return (
    <figure data-testid="chart-cost-per-kg" className="m-0" style={{ maxWidth: 760 }}>
      <svg viewBox={`0 0 ${W} 96`} width="100%" role="img" aria-label={`Required price ${nf(pk.levelized_cost, 3)} ${ccy}/kg by part`} style={FONT}>
        {parts.map(([k, v], i) => {
          const w = (v / total) * bw, cx = x + w / 2, seg = (
            <g key={k}>
              <rect x={x} y={8} width={Math.max(w - 1, 0)} height={28} fill={SHADES[i % SHADES.length]} />
              {w > 44 && <text x={cx} y={26} textAnchor="middle" fill={i < 3 ? '#fff' : INK}>{nf(v, 3)}</text>}
            </g>)
          x += w
          return seg
        })}
        {(() => { let lx = x0; return parts.map(([k, v], i) => {
          const el = <g key={`l-${k}`}><rect x={lx} y={50} width={9} height={9} fill={SHADES[i % SHADES.length]} />
            <text x={lx + 13} y={58} fill={INK}>{k} {nf(v / total * 100, 0)}%</text></g>
          lx += 13 + (k.length + 5) * 6.4 + 14
          return el
        }) })()}
        <text x={x0} y={84} fill={MUTED}>{ccy}/kg · parts of the required price {nf(pk.levelized_cost, 3)}; they add back to it</text>
      </svg>
    </figure>
  )
}

/** 2 — cost per year by component (constant cost-base money), construction years included. */
export function CostByYearChart({ years, ccy }: { years: any[]; ccy: string }) {
  const comps: [string, string, string][] = [['capital', 'Capital', SHADES[0]], ['fixed_opex', 'Fixed', SHADES[2]], ['variable_opex', 'Variable', SHADES[3]]]
  const stack = (y: any) => comps.reduce((s, [k]) => s + Math.max(y[k] ?? 0, 0), 0)
  const max = niceMax(Math.max(...years.map(stack), 1) / 1e6)
  const W = 640, H = 200, L = 44, R = 8, T = 10, B = 28, pw = W - L - R, ph = H - T - B
  const bw = pw / years.length, yv = (v: number) => T + ph - (v / max) * ph
  const ticks = [0, max / 2, max]
  const credit = years.some(y => (y.by_product_revenue ?? 0) > 0)
  return (
    <figure data-testid="chart-cost-by-year" className="m-0" style={{ maxWidth: 760 }}>
      <svg viewBox={`0 0 ${W} ${H + 20}`} width="100%" role="img" aria-label={`Cost by year, M ${ccy}`} style={FONT}>
        {ticks.map(t => <g key={t}><line x1={L} x2={W - R} y1={yv(t)} y2={yv(t)} stroke={RULE} strokeWidth={0.5} />
          <text x={L - 4} y={yv(t) + 3} textAnchor="end" fill={MUTED}>{nf(t, max < 10 ? 1 : 0)}</text></g>)}
        {years.map((y, i) => {
          let acc = 0
          return <g key={y.year}>{comps.map(([k, , c]) => {
            const v = Math.max(y[k] ?? 0, 0) / 1e6
            const r = <rect key={k} x={L + i * bw + bw * 0.15} y={yv(acc + v)} width={bw * 0.7} height={yv(acc) - yv(acc + v)} fill={c} />
            acc += v
            return r
          })}
            {(i % Math.ceil(years.length / 13) === 0) && <text x={L + i * bw + bw / 2} y={H - B + 12} textAnchor="middle" fill={MUTED}>{y.year}</text>}
          </g>
        })}
        <text x={L} y={H - 2} fill={MUTED}>year · M {ccy} per year, constant cost-base money{credit ? '; by-product credit not drawn (in the table)' : ''}</text>
        {comps.map(([, label, c], i) => <g key={label}><rect x={W - R - 210 + i * 72} y={H + 6} width={9} height={9} fill={c} />
          <text x={W - R - 197 + i * 72} y={H + 14} fill={INK}>{label}</text></g>)}
      </svg>
    </figure>
  )
}

/** Right-hand labels at their line's height, pushed apart so none overlaps (12 units apart). */
function endLabels(items: [string, number, string][], x: number, top: number, bottom: number) {
  const sorted = [...items].sort((a, b) => a[1] - b[1]).map(([t, y, c]) => ({ t, y: y + 3, c }))
  for (let i = 1; i < sorted.length; i++) sorted[i].y = Math.max(sorted[i].y, sorted[i - 1].y + 12)
  const over = sorted.length ? sorted[sorted.length - 1].y - bottom : 0
  if (over > 0) sorted.forEach(l => { l.y = Math.max(l.y - over, top) })
  return sorted.map(l => <text key={l.t} x={x} y={l.y} fill={l.c}>{l.t}</text>)
}

/** 3 — the product's Gabillon price per operating year against the run's required price. */
export function GabillonPriceChart({ mr }: { mr: any }) {
  const ys: any[] = mr.years ?? []
  if (!ys.length) return null
  const vals = [...ys.map(y => y.price_real), ...ys.map(y => y.price_nominal), mr.required_price, mr.levelised_price]
  const max = niceMax(Math.max(...vals))
  const W = 640, H = 200, L = 44, R = 150, T = 10, B = 28, pw = W - L - R, ph = H - T - B
  const xv = (i: number) => L + (ys.length === 1 ? pw / 2 : (i / (ys.length - 1)) * pw)
  const yv = (v: number) => T + ph - (v / max) * ph
  const line = (k: string) => ys.map((y, i) => `${i ? 'L' : 'M'}${xv(i)} ${yv(y[k])}`).join('')
  const ticks = [0, max / 2, max]
  const last = ys[ys.length - 1]
  return (
    <figure data-testid="chart-gabillon" className="m-0" style={{ maxWidth: 760 }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Gabillon price against the required price, EUR/kg" style={FONT}>
        {ticks.map(t => <g key={t}><line x1={L} x2={L + pw} y1={yv(t)} y2={yv(t)} stroke={RULE} strokeWidth={0.5} />
          <text x={L - 4} y={yv(t) + 3} textAnchor="end" fill={MUTED}>{nf(t, 2)}</text></g>)}
        <line x1={L} x2={L + pw} y1={yv(mr.required_price)} y2={yv(mr.required_price)} stroke={ACCENT} strokeWidth={1.5} />
        <path d={line('price_nominal')} fill="none" stroke={SHADES[3]} strokeWidth={1} />
        <path d={line('price_real')} fill="none" stroke={SHADES[0]} strokeWidth={1.5} />
        <line x1={L} x2={L + pw} y1={yv(mr.levelised_price)} y2={yv(mr.levelised_price)} stroke={SHADES[0]} strokeDasharray="4 3" strokeWidth={1} />
        {endLabels([
          [`Required ${nf(mr.required_price, 3)}`, yv(mr.required_price), ACCENT],
          [`Nominal ${nf(last.price_nominal, 3)}`, yv(last.price_nominal), MUTED],
          [`Real ${nf(last.price_real, 3)}`, yv(last.price_real), INK],
          [`Levelised ${nf(mr.levelised_price, 3)}`, yv(mr.levelised_price), INK],
        ], L + pw + 6, T + 4, T + ph + 3)}
        {ys.map((y, i) => (i % Math.ceil(ys.length / 12) === 0) &&
          <text key={y.year} x={xv(i)} y={H - B + 12} textAnchor="middle" fill={MUTED}>{y.operating_year}</text>)}
        <text x={L} y={H - 2} fill={MUTED}>operating year · EUR/kg · Gabillon {mr.molecule}, {mr.calibration_status}{mr.calibration_status === 'SEED' ? ' (expert priors, not a market quote)' : ''}</text>
      </svg>
    </figure>
  )
}
