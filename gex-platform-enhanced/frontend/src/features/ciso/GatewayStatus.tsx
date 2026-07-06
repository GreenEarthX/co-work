// Screen: Gateway status screen (/ciso-gateways)
/**
 * GatewayStatus — CISO monitoring view for Domain 4: OT/IT Boundary.
 * Shows all registered OT gateways, their status, last-seen, and allowed data types.
 *
 * Backend: GET /api/v1/ciso/gateways
 */
import { useState, useEffect } from 'react'
import { Radio, Wifi, WifiOff, Activity, Filter } from 'lucide-react'
import { cisoSecurityAPI } from '@/api'

interface Gateway {
  id: string
  name: string
  project_id: string
  location?: string
  allowed_ips: string[]
  allowed_data_types: string[]
  cert_fingerprint?: string
  active: boolean
  last_seen_at?: string
  registered_at: string
  status: 'ONLINE' | 'OFFLINE' | 'UNKNOWN'
}

const DATA_TYPE_LABELS: Record<string, string> = {
  PRODUCTION_VOLUME: 'Production Volume',
  POWER_CONSUMPTION: 'Power Consumption',
  ELECTROLYSER_EFFICIENCY: 'Electrolyser Efficiency',
  QUALITY_CERTIFICATE: 'Quality Certificate',
  METERED_DELIVERY: 'Metered Delivery',
  PLANT_STATUS: 'Plant Status',
  ALARM_EVENT: 'Alarm Event',
  GHG_MEASUREMENT: 'GHG Measurement',
}

export function GatewayStatus() {
  const [gateways, setGateways] = useState<Gateway[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'ALL' | 'ONLINE' | 'OFFLINE'>('ALL')
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    cisoSecurityAPI.listGateways()
      .then((data) => {
        setGateways(data.gateways || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const filtered = gateways.filter((g) =>
    filter === 'ALL' ? true : g.status === filter
  )

  const online = gateways.filter((g) => g.status === 'ONLINE').length
  const offline = gateways.filter((g) => g.status === 'OFFLINE').length

  const lastSeenLabel = (ts?: string) => {
    if (!ts) return 'Never'
    const diff = Date.now() - new Date(ts).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    return new Date(ts).toLocaleDateString()
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Radio size={22} className="text-orange-600" />
          OT Gateway Monitor
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Domain 4 — OT/IT Boundary. GEX never initiates connections to OT.
          Gateways push data one-way via SHA-256 authenticated ingest endpoint.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="border rounded-lg p-4 bg-white">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-blue-500" />
            <span className="text-2xl font-bold text-gray-900">{gateways.length}</span>
          </div>
          <div className="text-xs text-gray-500 mt-1">Total gateways</div>
        </div>
        <div className="border rounded-lg p-4 bg-white">
          <div className="flex items-center gap-2">
            <Wifi size={16} className="text-green-500" />
            <span className="text-2xl font-bold text-green-600">{online}</span>
          </div>
          <div className="text-xs text-gray-500 mt-1">Online</div>
        </div>
        <div className="border rounded-lg p-4 bg-white">
          <div className="flex items-center gap-2">
            <WifiOff size={16} className="text-red-400" />
            <span className="text-2xl font-bold text-red-500">{offline}</span>
          </div>
          <div className="text-xs text-gray-500 mt-1">Offline</div>
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2 mb-4">
        <Filter size={14} className="text-gray-400" />
        {(['ALL', 'ONLINE', 'OFFLINE'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              filter === f
                ? 'bg-orange-600 text-white border-orange-600'
                : 'text-gray-500 border-gray-200 hover:border-orange-400'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading gateways…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-lg">
          <Radio size={32} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-400">No gateways matching filter</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((gw) => (
            <div key={gw.id} className="border rounded-lg bg-white overflow-hidden">
              <div
                className="flex items-center gap-4 p-4 cursor-pointer"
                onClick={() => setExpanded(expanded === gw.id ? null : gw.id)}
              >
                <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                  gw.status === 'ONLINE' ? 'bg-green-500 animate-pulse' : 'bg-red-400'
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm text-gray-900">{gw.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                      gw.status === 'ONLINE'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-red-100 text-red-700'
                    }`}>
                      {gw.status}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {gw.id}
                    {gw.location && ` · ${gw.location}`}
                    {' · '}Project: {gw.project_id}
                  </div>
                </div>
                <div className="text-xs text-gray-400 text-right shrink-0">
                  <div>Last seen</div>
                  <div className="font-medium">{lastSeenLabel(gw.last_seen_at)}</div>
                </div>
              </div>

              {expanded === gw.id && (
                <div className="border-t border-gray-100 p-4 space-y-4 bg-gray-50">
                  <div>
                    <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                      Allowed Data Types
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {gw.allowed_data_types.map((dt) => (
                        <span key={dt} className="text-xs bg-white border border-gray-200 text-gray-700 px-2 py-1 rounded">
                          {DATA_TYPE_LABELS[dt] || dt}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-xs text-gray-600">
                    <div>
                      <span className="font-medium">IP Allowlist:</span>{' '}
                      {gw.allowed_ips.length > 0
                        ? gw.allowed_ips.join(', ')
                        : <span className="text-amber-600">Any IP (dev mode)</span>}
                    </div>
                    <div>
                      <span className="font-medium">mTLS Cert:</span>{' '}
                      {gw.cert_fingerprint
                        ? <code>{gw.cert_fingerprint.slice(0, 16)}…</code>
                        : <span className="text-gray-400">Not configured (dev)</span>}
                    </div>
                    <div>
                      <span className="font-medium">Registered:</span>{' '}
                      {new Date(gw.registered_at).toLocaleDateString()}
                    </div>
                    <div>
                      <span className="font-medium">Active:</span>{' '}
                      <span className={gw.active ? 'text-green-600' : 'text-red-600'}>
                        {gw.active ? 'Yes' : 'Disabled'}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="mt-6 text-xs text-gray-400 border-t pt-4">
        Domain 4 — OT/IT Boundary · NIS2 Art. 21 ·
        FORBIDDEN_COMMAND_TYPES: SETPOINT_CHANGE, VALVE_COMMAND, EMERGENCY_STOP, FIRMWARE_UPDATE, PARAMETER_WRITE ·
        Production: mTLS verified by nginx/envoy at DMZ ingress
      </div>
    </div>
  )
}
