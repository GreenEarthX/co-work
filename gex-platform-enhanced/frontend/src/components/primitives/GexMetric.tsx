import type { HTMLAttributes, ReactNode } from 'react'
import { clsx } from 'clsx'

export interface GexMetricProps extends HTMLAttributes<HTMLDivElement> {
  label: ReactNode
  value: ReactNode
  subtext?: ReactNode
  trend?: ReactNode
  align?: 'left' | 'right'
}

export function GexMetric({
  label,
  value,
  subtext,
  trend,
  align = 'left',
  className,
  ...props
}: GexMetricProps) {
  return (
    <div
      className={clsx(
        'min-w-0 rounded-md border border-neutral-border bg-neutral-surface px-3 py-2',
        align === 'right' && 'text-right',
        className,
      )}
      {...props}
    >
      <div className="truncate text-[10px] font-bold uppercase tracking-caps text-neutral-muted">
        {label}
      </div>
      <div className="mt-0.5 flex min-w-0 items-baseline gap-2">
        <div className="truncate font-mono text-xl font-semibold tabular-nums text-neutral-primary">
          {value}
        </div>
        {trend && (
          <div className="shrink-0 text-[11px] font-semibold text-neutral-muted">
            {trend}
          </div>
        )}
      </div>
      {subtext && (
        <div className="mt-0.5 truncate text-xs text-neutral-muted">{subtext}</div>
      )}
    </div>
  )
}
