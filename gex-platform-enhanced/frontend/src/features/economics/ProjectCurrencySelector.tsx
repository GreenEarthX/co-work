// Screen: fragment — the project's working-currency selector (on /economics/:projectId)
//
// OpenPyTEA costs in USD; GEX converts every new TEA run to this currency at a
// fixed dated rate. (A CFO may override the rate within ±5% — that lives on the
// compute request, not here.) Any project user may set the currency; the server
// records who. Doctrine: slate-only, square corners, mono labels, colour = state.
import { useEffect, useState } from 'react'

import {
  getProjectCurrency,
  setProjectCurrency,
  SUPPORTED_CURRENCIES,
  type Currency,
  type ProjectCurrency,
} from '@/lib/projectCurrencyApi'

type Status =
  | { kind: 'idle' }
  | { kind: 'saving' }
  | { kind: 'saved' }
  | { kind: 'error'; message: string }

export default function ProjectCurrencySelector({ projectId }: { projectId: string }) {
  const [current, setCurrent] = useState<ProjectCurrency | null>(null)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })

  useEffect(() => {
    let live = true
    setCurrent(null)
    setStatus({ kind: 'idle' })
    getProjectCurrency(projectId)
      .then((c) => { if (live) setCurrent(c) })
      .catch((e) => { if (live) setStatus({ kind: 'error', message: String(e?.message ?? e) }) })
    return () => { live = false }
  }, [projectId])

  async function change(next: Currency) {
    if (!current || next === current.base_currency) return
    setStatus({ kind: 'saving' })
    try {
      setCurrent(await setProjectCurrency(projectId, next))
      setStatus({ kind: 'saved' })
    } catch (e: any) {
      setStatus({ kind: 'error', message: String(e?.message ?? e) })
    }
  }

  return (
    <div className="border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
            Working currency
          </div>
          <p className="mt-1 max-w-md text-xs text-slate-500">
            OpenPyTEA costs in USD; GEX converts every new TEA run to this currency at
            a fixed dated rate. Changing it applies to the next run, not to figures
            already computed.
          </p>
        </div>
        <select
          value={current?.base_currency ?? 'EUR'}
          disabled={current === null || status.kind === 'saving'}
          onChange={(e) => change(e.target.value as Currency)}
          className="border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-900 disabled:opacity-50"
        >
          {SUPPORTED_CURRENCIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <div className="mt-3 font-mono text-[11px] uppercase tracking-wider">
        {current === null && status.kind !== 'error' && (
          <span className="text-slate-400">loading…</span>
        )}
        {current && status.kind === 'idle' && current.is_default && (
          <span className="text-slate-500">default · not yet set for this project</span>
        )}
        {current && status.kind === 'idle' && !current.is_default && (
          <span className="text-slate-600">
            set to {current.base_currency}
            {current.set_by ? ` · by ${current.set_by}` : ''}
          </span>
        )}
        {status.kind === 'saving' && <span className="text-amber-600">saving…</span>}
        {status.kind === 'saved' && (
          <span className="text-emerald-700">saved · {current?.base_currency}</span>
        )}
        {status.kind === 'error' && <span className="text-red-600">error · {status.message}</span>}
      </div>
    </div>
  )
}
