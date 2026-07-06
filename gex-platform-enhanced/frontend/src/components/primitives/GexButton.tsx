import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { clsx } from 'clsx'

export interface GexButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'destructive'
  size?: 'sm' | 'md'
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
}

export function GexButton({
  variant = 'secondary',
  size = 'md',
  leadingIcon,
  trailingIcon,
  children,
  className,
  type = 'button',
  ...props
}: GexButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        'inline-flex items-center justify-center gap-1.5 rounded-md border font-semibold',
        'transition-colors duration-100',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-focus focus-visible:ring-offset-1',
        'disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'h-7 px-2 text-xs' : 'h-8 px-3 text-sm',
        variant === 'primary' &&
          'border-brand-primary bg-brand-primary text-neutral-inverse hover:bg-brand-hover',
        variant === 'secondary' &&
          'border-neutral-border bg-neutral-surface text-neutral-secondary hover:border-neutral-borderStrong hover:bg-neutral-surfaceMuted',
        variant === 'destructive' &&
          'border-status-blocker bg-status-blocker text-neutral-inverse hover:bg-status-blocker-hover',
        className,
      )}
      {...props}
    >
      {leadingIcon && <span className="shrink-0">{leadingIcon}</span>}
      {children && <span className="truncate">{children}</span>}
      {trailingIcon && <span className="shrink-0">{trailingIcon}</span>}
    </button>
  )
}
