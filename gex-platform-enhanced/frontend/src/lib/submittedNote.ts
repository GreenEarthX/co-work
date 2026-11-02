/**
 * "· 3 submitted, not independently verified" beside a gate's verified count (JML 2026-10-31).
 * A submitted item is an assertion: shown so a project's progress is honest, never counted in the
 * verified figure and never what satisfies a gate. Empty when there are none or the server predates the field.
 */
export function submittedNote(count?: number | null): string {
  return count && count > 0 ? ` · ${count} submitted, not independently verified` : ''
}
