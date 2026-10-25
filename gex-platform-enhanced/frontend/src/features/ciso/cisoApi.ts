// Screen: Hook (no screen)
/**
 * cisoApi — calls to /api/v1/ciso, which since 2026-10-25 serves the company's
 * real data or says it is not recorded. The bearer is added by the fetch bridge.
 *
 * `company` names the company to open. The server honours it for GEX staff only
 * (header x-ciso-company); a client CISO naming another company gets a 403, which
 * is surfaced as a message, never replaced by sample data.
 */
export class CisoError extends Error {
  constructor(message: string, readonly status: number) { super(message) }
}

export async function cisoCall<T = any>(path: string, company?: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(company ? { 'x-ciso-company': company } : {}),
      ...(init.headers ?? {}),
    },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = body?.detail
    const message = (detail && typeof detail === 'object' && detail.message)
      || (typeof detail === 'string' && detail) || `The server answered ${res.status}.`
    throw new CisoError(message, res.status)
  }
  return body as T
}

export const NOT_RECORDED = 'Not recorded'
