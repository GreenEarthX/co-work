import { type ButtonHTMLAttributes, forwardRef } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
}

const BASE =
  'inline-flex items-center justify-center gap-1.5 font-bold uppercase tracking-wide transition-colors duration-150 rounded disabled:opacity-40 disabled:cursor-not-allowed select-none cursor-pointer'

const VARIANTS = {
  primary:
    'bg-[#0ea5a0] text-white hover:bg-[#0d9488] active:bg-[#0f766e]',
  secondary:
    'bg-white text-[#0f172a] border border-[#e2e8f0] hover:bg-[#f8fafc] active:bg-[#f1f5f9]',
  ghost:
    'bg-transparent text-[#64748b] hover:bg-[#f1f5f9] hover:text-[#0f172a]',
  danger:
    'bg-[#dc2626] text-white hover:bg-[#b91c1c] active:bg-[#991b1b]',
}

const SIZES = {
  sm: 'h-7  px-3   text-[0.65rem]',
  md: 'h-8  px-3.5 text-[0.7rem]',
  lg: 'h-9  px-4   text-[0.75rem]',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', className = '', ...props }, ref) => (
    <button
      ref={ref}
      className={`${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    />
  ),
)
Button.displayName = 'Button'
