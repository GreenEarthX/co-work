import { forwardRef, type InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', ...props }, ref) => (
    <div className="flex flex-col gap-1">
      {label && (
        <label className="label-caps">{label}</label>
      )}
      <input
        ref={ref}
        className={`
          h-8 px-2.5 rounded border text-sm font-medium
          bg-white border-[#e2e8f0] text-[#0f172a]
          placeholder:text-[#94a3b8] placeholder:font-normal
          focus:outline-none focus:border-[#0ea5a0] focus:ring-2 focus:ring-[#0ea5a0]/20
          disabled:opacity-50 disabled:cursor-not-allowed
          transition-colors duration-150
          ${error ? 'border-[#dc2626] focus:border-[#dc2626] focus:ring-[#dc2626]/20' : ''}
          ${className}
        `}
        {...props}
      />
      {error && (
        <span className="text-xs text-[#dc2626] mt-0.5">{error}</span>
      )}
    </div>
  ),
)
Input.displayName = 'Input'
