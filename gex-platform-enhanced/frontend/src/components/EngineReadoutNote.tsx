// Screen: Shared component — wherever gate figures are shown
/**
 * Says where a gate figure comes from (2026-10-28). Every figure is the
 * engine's, computed from verified evidence; this names the rules version and
 * the evaluation time, states the scope when a persona sees fewer gates than
 * the overall figure covers, and says "not yet evaluated" when the engine has
 * not judged the project — instead of a number.
 */
import type { CustomerProject } from '@/data/customerProjects'

export function EngineReadoutNote({ bankability, compact = false }: {
  bankability: CustomerProject['bankability']; compact?: boolean
}) {
  const b = bankability
  if (b.evaluated === false) {
    return (
      <span className="font-mono text-[11px] text-amber-700 dark:text-amber-300">
        {b.unavailable ?? 'Not yet evaluated by the GEX engine.'}
      </span>
    )
  }
  const when = b.evaluated_at ? new Date(b.evaluated_at).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : null
  return (
    <span className="font-mono text-[11px] text-[var(--text-muted)]">
      GEX engine{b.rules_version ? ` · rules ${b.rules_version}` : ''}{when ? ` · ${when}` : ''}
      {!compact && b.scope?.note ? ` · ${b.scope.note}` : ''}
    </span>
  )
}
