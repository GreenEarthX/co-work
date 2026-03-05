import { type HTMLAttributes } from 'react'

type BadgeVariant =
  | 'default'
  | 'brand'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'muted'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant
}

const VARIANTS: Record<BadgeVariant, string> = {
  default: 'bg-[#f1f5f9] text-[#475569]',
  brand:   'bg-[#f0fdf9] text-[#0ea5a0]',
  success: 'bg-[#f0fdf4] text-[#16a34a]',
  warning: 'bg-[#fffbeb] text-[#d97706]',
  danger:  'bg-[#fef2f2] text-[#dc2626]',
  info:    'bg-[#f0f9ff] text-[#0369a1]',
  muted:   'bg-[#f8fafc] text-[#94a3b8]',
}

export function Badge({ variant = 'default', className = '', children, ...props }: BadgeProps) {
  return (
    <span
      className={`
        inline-flex items-center px-2 py-0.5 rounded
        text-[0.65rem] font-bold uppercase tracking-wide whitespace-nowrap
        ${VARIANTS[variant]} ${className}
      `}
      {...props}
    >
      {children}
    </span>
  )
}

/** Auto-maps common GEX stage strings to badge variants */
export function StageBadge({ stage }: { stage: string }) {
  const s = stage.toLowerCase()
  let variant: BadgeVariant = 'default'
  if (s.includes('ready') || s.includes('deposited') || s.includes('active')) variant = 'success'
  else if (s.includes('pending')) variant = 'warning'
  else if (s.includes('reject') || s.includes('fail')) variant = 'danger'
  else if (s.includes('market')) variant = 'brand'
  return <Badge variant={variant}>{stage}</Badge>
}
