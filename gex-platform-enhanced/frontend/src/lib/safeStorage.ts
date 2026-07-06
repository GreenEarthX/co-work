/**
 * Safe localStorage wrappers — avoids JSON.parse errors and
 * quota/security exceptions in restricted environments.
 */

export function safeGetItem(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}

export function safeSetItem(key: string, value: string): void {
  try { localStorage.setItem(key, value) } catch { /* ignore */ }
}

export function safeGetJson<T = unknown>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch { return fallback }
}

export function safeSetJson(key: string, value: unknown): void {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* ignore */ }
}
