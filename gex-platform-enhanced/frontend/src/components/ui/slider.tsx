import React, { useCallback } from 'react'
import { clsx } from 'clsx'

interface SliderProps {
  value?: number[]
  defaultValue?: number[]
  min?: number
  max?: number
  step?: number
  onValueChange?: (value: number[]) => void
  className?: string
}

/**
 * Minimal Slider (replaces @radix-ui/react-slider).
 * Single-thumb only, styled with Tailwind to match GEX dark theme.
 */
export function Slider({
  value,
  defaultValue,
  min = 0,
  max = 100,
  step = 1,
  onValueChange,
  className,
}: SliderProps) {
  const current = value?.[0] ?? defaultValue?.[0] ?? min

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onValueChange?.([Number(e.target.value)])
    },
    [onValueChange],
  )

  return (
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={current}
      onChange={handleChange}
      className={clsx(
        'w-full h-2 rounded-lg appearance-none cursor-pointer',
        'bg-gray-700 accent-teal-500',
        className,
      )}
    />
  )
}
