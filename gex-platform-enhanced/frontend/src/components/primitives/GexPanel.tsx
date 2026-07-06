import type { HTMLAttributes, ReactNode } from 'react'
import { clsx } from 'clsx'

export interface GexPanelProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: ReactNode
  eyebrow?: ReactNode
  actions?: ReactNode
  children: ReactNode
  density?: 'compact' | 'normal'
}

export function GexPanel({
  title,
  eyebrow,
  actions,
  children,
  density = 'normal',
  className,
  ...props
}: GexPanelProps) {
  const hasHeader = title || eyebrow || actions

  return (
    <section
      className={clsx(
        'rounded-md border border-neutral-border bg-neutral-surface shadow-panel',
        className,
      )}
      {...props}
    >
      {hasHeader && (
        <header
          className={clsx(
            'flex items-start justify-between gap-4 border-b border-neutral-border',
            density === 'compact' ? 'px-3 py-2' : 'px-4 py-3',
          )}
        >
          <div className="min-w-0">
            {eyebrow && (
              <div className="text-[10px] font-bold uppercase tracking-caps text-neutral-muted">
                {eyebrow}
              </div>
            )}
            {title && (
              <h2 className="truncate text-sm font-semibold text-neutral-primary">
                {title}
              </h2>
            )}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}

      <div className={density === 'compact' ? 'p-3' : 'p-4'}>{children}</div>
    </section>
  )
}
