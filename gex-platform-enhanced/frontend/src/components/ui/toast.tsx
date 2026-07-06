/**
 * Toast primitives stub — lightweight replacements for @radix-ui/react-toast.
 * Used by toaster.tsx and use-toast.ts.
 */
import * as React from "react"

/* ---- types ---- */
export type ToastProps = React.HTMLAttributes<HTMLDivElement> & {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  variant?: "default" | "destructive"
}

export type ToastActionElement = React.ReactElement

/* ---- components ---- */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}

export const Toast = React.forwardRef<HTMLDivElement, ToastProps>(
  ({ className, variant = "default", open = true, children, ...props }, ref) => {
    if (!open) return null
    return (
      <div
        ref={ref}
        className={`pointer-events-auto relative flex items-center justify-between gap-3 overflow-hidden rounded-md border p-4 shadow-lg transition-all ${
          variant === "destructive"
            ? "border-red-200 bg-red-50 text-red-900"
            : "border-gray-200 bg-white text-gray-900"
        } ${className ?? ""}`}
        {...props}
      >
        {children}
      </div>
    )
  },
)
Toast.displayName = "Toast"

export function ToastTitle({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className="text-sm font-semibold" {...props}>{children}</div>
}

export function ToastDescription({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className="text-sm opacity-90" {...props}>{children}</div>
}

export function ToastClose(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className="absolute right-2 top-2 rounded p-1 text-gray-400 hover:text-gray-600" {...props}>
      &times;
    </button>
  )
}

export function ToastViewport(props: React.HTMLAttributes<HTMLOListElement>) {
  return (
    <ol
      className="fixed top-0 right-0 z-[100] flex max-h-screen w-full flex-col-reverse gap-2 p-4 sm:max-w-[420px]"
      {...props}
    />
  )
}

export function ToastAction({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className="text-sm font-medium underline" {...props}>{children}</button>
}
