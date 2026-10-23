// Screen: Information lineage panel (/finance/lineage)
/**
 * LineagePanel — the recorded trail of one of the company's trades, from the
 * listing to settlement, read from the hash-chained event ledger through
 * GET /api/v1/market/trail/{correlation_id}. One correlation id runs through
 * every step (gap register G-03).
 *
 * Until 2026-10-23 this screen showed a hard-coded ETFuels chain with invented
 * hashes and "VERIFIED" badges (gap register G-04). A node is now marked
 * verified only when the ledger holds it with a hash.
 */
import { useEffect, useMemo, useState } from 'react'
import { GitBranch, ChevronDown, ChevronUp } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { LineageTrail, type LineageLayer, type LineageNode } from '@/components/primitives'
import { marketAPI, type MarketContract, type TrailEvent } from '@/api'

// Where each step sits: the claim itself, the trade on it, the money and title.
const LAYER: Record<string, LineageLayer> = {
  token: 'TOKEN', capacity: 'TOKEN',
  offer: 'TRADE', rfq: 'TRADE', match: 'TRADE', contract: 'TRADE',
  settlement: 'BRIDGE', attribution: 'BRIDGE',
}

function toNode(e: TrailEvent): LineageNode {
  const kind = (e.aggregate_type ?? e.event_type.split('.')[0]).toLowerCase()
  const state = e.new_state ?? e.event_type.split('.').slice(1).join(' ')
  return {
    id: e.id,
    label: e.event_type.replace('.', ' · ').replace(/_/g, ' '),
    layer: LAYER[kind] ?? 'TRADE',
    state: state.toUpperCase(),
    timestamp: e.timestamp?.slice(0, 19).replace('T', ' ') ?? undefined,
    actor: e.metadata?.user_id,
    hash: e.event_hash?.slice(0, 8) ?? undefined,
    verified: Boolean(e.event_hash),
  }
}

function show(v: unknown): string {
  if (v == null) return '—'
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}

export function LineagePanel() {
  const [contracts, setContracts] = useState<MarketContract[]>([])
  const [chain, setChain] = useState<string>('')
  const [events, setEvents] = useState<TrailEvent[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    marketAPI.myContracts()
      .then(({ contracts }) => {
        setContracts(contracts)
        const first = contracts.find(c => c.correlation_id)
        if (first?.correlation_id) setChain(first.correlation_id)
        else setLoading(false)
      })
      .catch(e => { setError((e as Error).message); setLoading(false) })
  }, [])

  useEffect(() => {
    if (!chain) return
    setLoading(true)
    marketAPI.trail(chain)
      .then(({ events }) => { setEvents(events); setError(null) })
      .catch(e => setError((e as Error).message))
      .finally(() => setLoading(false))
  }, [chain])

  const nodes = useMemo(() => events.map(toNode), [events])
  const verifiedCount = nodes.filter(n => n.verified).length
  const contract = contracts.find(c => c.correlation_id === chain)

  return (
    <div className="space-y-4 max-w-5xl mx-auto pb-8">
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="flex items-start justify-between gap-4 px-6 py-4 bg-gradient-to-r from-gray-900 to-gray-800">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <GitBranch className="w-4 h-4 text-gray-400" />
              <span className="text-xs font-bold uppercase tracking-widest text-gray-400">Trade Lineage</span>
            </div>
            <h1 className="text-2xl font-black text-white">
              {contract ? `${contract.molecule} · ${contract.volume_mtpd} MTPD · €${contract.price_eur_kg}/kg` : 'No trade yet'}
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Listing → match → both acceptances → contract → settlement → title, under one chain id
            </p>
          </div>
          {contracts.length > 0 && (
            <div className="mt-2">
              <label htmlFor="lineage-chain" className="sr-only">Trade</label>
              <select id="lineage-chain" value={chain} onChange={e => setChain(e.target.value)}
                      className="rounded-lg bg-gray-700 px-3 py-1.5 text-xs font-bold text-white">
                {contracts.filter(c => c.correlation_id).map(c => (
                  <option key={c.id} value={c.correlation_id!}>{c.correlation_id} · {c.molecule}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      {!loading && !error && contracts.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-600 shadow-sm">
          Your company has no contract yet. A trail is recorded from the moment a listing opens; it appears
          here once a match both parties accepted has become a contract.
        </div>
      )}

      {nodes.length > 0 && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
              <div className="text-2xl font-black tabular-nums text-gray-900">{nodes.length}</div>
              <div className="text-xs font-semibold text-gray-500 mt-1">Recorded steps</div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
              <div className={`text-2xl font-black tabular-nums ${verifiedCount === nodes.length ? 'text-green-600' : 'text-amber-600'}`}>
                {verifiedCount}
              </div>
              <div className="text-xs font-semibold text-gray-500 mt-1">Hash-chained</div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
              <div className="text-2xl font-black tabular-nums text-gray-900">{new Set(nodes.map(n => n.layer)).size}</div>
              <div className="text-xs font-semibold text-gray-500 mt-1">Layers Spanned</div>
            </div>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 flex items-center gap-2">
              <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">Provenance Chain</h3>
              <InfoTooltip text="Every step of this trade as recorded in the platform's event ledger. Each entry carries the hash that chains it to the one before; a step without a hash is shown unverified." />
            </div>
            <div className="px-6 py-4">
              <LineageTrail nodes={nodes} highlight_id={expanded ?? undefined} />
            </div>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50">
              <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">Step Details</h3>
            </div>
            <div className="divide-y divide-gray-100">
              {events.map(e => {
                const isOpen = expanded === e.id
                return (
                  <div key={e.id}>
                    <button type="button" onClick={() => setExpanded(isOpen ? null : e.id)}
                            className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full shrink-0 ${e.event_hash ? 'bg-green-500' : 'bg-amber-400'}`} />
                        <div className="text-left">
                          <div className="text-sm font-semibold text-gray-800">{e.event_type}</div>
                          <div className="text-xs text-gray-500">
                            {e.previous_state && e.new_state ? `${e.previous_state} → ${e.new_state} · ` : ''}
                            {e.timestamp?.slice(0, 19).replace('T', ' ')}
                          </div>
                        </div>
                      </div>
                      {isOpen ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                    </button>
                    {isOpen && (
                      <div className="px-4 pb-4 pt-1 bg-gray-50/50">
                        <div className="grid grid-cols-2 gap-2">
                          {Object.entries(e.data ?? {}).map(([k, v]) => (
                            <div key={k} className="flex justify-between gap-2 text-xs px-2 py-1.5 rounded bg-white border border-gray-100">
                              <span className="text-gray-500">{k.replace(/_/g, ' ')}</span>
                              <span className="font-semibold text-gray-800 tabular-nums truncate">{show(v)}</span>
                            </div>
                          ))}
                        </div>
                        <div className="flex items-center gap-3 mt-2 text-[10px] text-gray-400">
                          {e.metadata?.user_id && <span>by {e.metadata.user_id}</span>}
                          {e.event_hash && <span className="font-mono">#{e.event_hash.slice(0, 16)}</span>}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
