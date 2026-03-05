import { type HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  title?: string
  action?: React.ReactNode
  noPadding?: boolean
}

export function Card({ title, action, noPadding, children, className = '', ...props }: CardProps) {
  return (
    <div
      className={`bg-white border border-[#e2e8f0] rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.08)] ${className}`}
      {...props}
    >
      {(title || action) && (
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#e2e8f0]">
          {title && (
            <h2 className="section-title">{title}</h2>
          )}
          {action && <div>{action}</div>}
        </div>
      )}
      <div className={noPadding ? '' : 'p-5'}>{children}</div>
    </div>
  )
}
