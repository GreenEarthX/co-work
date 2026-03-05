import { ChevronDown } from 'lucide-react'
import { forwardRef, type SelectHTMLAttributes } from 'react'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  placeholder?: string
  options: { value: string; label: string }[]
  error?: string
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, placeholder, options, error, className = '', ...props }, ref) => (
    <div className="flex flex-col gap-1">
      {label && <label className="label-caps">{label}</label>}
      <div className="relative">
        <select
          ref={ref}
          className={`
            gex-select h-8 w-full pr-8
            ${error ? 'border-[#dc2626]' : ''}
            ${className}
          `}
          {...props}
        >
          {placeholder && (
            <option value="">{placeholder}</option>
          )}
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <ChevronDown
          size={13}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#64748b] pointer-events-none"
        />
      </div>
      {error && <span className="text-xs text-[#dc2626]">{error}</span>}
    </div>
  ),
)
Select.displayName = 'Select'


/** FilterBar — the row of filters exactly as seen on staging */
interface FilterBarProps {
  children: React.ReactNode
}
export function FilterBar({ children }: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      {children}
    </div>
  )
}

/** FilterSelect — a compact filter select matching the staging dropdowns */
interface FilterSelectProps {
  label: string
  options: { value: string; label: string }[]
  value?: string
  onChange?: (value: string) => void
}
export function FilterSelect({ label, options, value = '', onChange }: FilterSelectProps) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        className="gex-select h-8 min-w-[130px] text-[0.8rem]"
      >
        <option value="">{label}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={12}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#64748b] pointer-events-none"
      />
    </div>
  )
}
