import type { HTMLAttributes } from 'react'
import { clsx } from 'clsx'

export type GexStatusKind = 'blocker' | 'warning' | 'success'

export interface GexStatusProps extends HTMLAttributes<HTMLSpanElement> {
  status: GexStatusKind
  label?: string
}

const statusClasses: Record<GexStatusKind, { shell: string; dot: string; label: string }> = {
  blocker: {
    shell: 'border-status-blocker bg-status-blocker-light text-status-blocker',
    dot: 'bg-status-blocker',
    label: 'Blocker',
  },
  warning: {
    shell: 'border-status-warning bg-status-warning-light text-status-warning',
    dot: 'bg-status-warning',
    label: 'Needs action',
  },
  success: {
    shell: 'border-status-success bg-status-success-light text-status-success',
    dot: 'bg-status-success',
    label: 'Verified',
  },
}

export function GexStatus({
  status,
  label,
  className,
  ...props
}: GexStatusProps) {
  const styles = statusClasses[status]

  return (
    <span
      className={clsx(
        'inline-flex h-6 items-center gap-1.5 rounded-md border px-2',
        'text-[10px] font-bold uppercase tracking-caps',
        styles.shell,
        className,
      )}
      {...props}
    >
      <span className={clsx('h-1.5 w-1.5 rounded-full', styles.dot)} />
      {label ?? styles.label}
    </span>
  )
}
