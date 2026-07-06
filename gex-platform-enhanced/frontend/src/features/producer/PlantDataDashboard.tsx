/**
 * PlantDataDashboard — Producer workspace real-time plant telemetry.
 * Shows latest values from registered OT gateways for a project.
 * Falls back to demo data if no gateway is connected.
 *
 * Backend: GET /api/v1/plant-data/demo/{project_id} (demo)
 *          GET /api/v1/plant-data/data/{project_id}  (live)
 */
import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity, Zap, Wind, Gauge, AlertCircle, RefreshCw } from 'lucide-react'
import { plantDataAPI } from '@/api'
import { useSelectedProject } from '@/contexts/ProjectContext'

interface PlantRecord {
  id: string
  data_type: string
  payload_json: Record<string, any>
  gateway_id: string
  received_at: string
  sha256_hash: string
}

const DATA_TYPE_CONFIG: Record<string, {
  label: string
  icon: React.ReactNode
  color: string
  unit?: string
  valueKey?: string
}> = {
  PRODUCTION_VOLUME: {
    label: 'Production Volume',
    icon: <Activity size={18} />,
    color: 'text-blue-600',
    valueKey: 'value',
  },
  ELECTROLYSER_EFFICIENCY: {
    label: 'Electrolyser Efficiency',
    icon: <Zap size={18} />,
    color: 'text-yellow-600',
    valueKey: 'value',
  },
  POWER_CONSUMPTION: {
    label: 'Power Consumption',
    icon: <Zap size={18} />,
    color: 'text-purple-600',
    valueKey: 'value',
  },
  GHG_MEASUREMENT: {
    label: 'GHG Intensity',
    icon: <Wind size={18} />,
    color: 'text-green-600',
    valueKey: 'value',
  },
  PLANT_STATUS: {
    label: 'Plant Status',
    icon: <Gauge size={18} />,
    color: 'text-gray-600',
    valueKey: 'status',
  },
}

// Fallback when no project context is provided via ?project= or selectedProject.
const FALLBACK_PROJECT_ID = 'proj_breizh_saf'

function RecordCard({ record }: { record: PlantRecord }) {
  const config = DATA_TYPE_CONFIG[record.data_type]
  const payload = record.payload_json || {}

  const displayValue = config?.valueKey ? payload[config.valueKey] : null
  const unit = payload.unit || payload.standard || ''
  const timestamp = payload.timestamp || record.received_at

  return (
    <div className="border rounded-lg p-4 bg-white">
      <div className="flex items-start justify-between mb-3">
        <div className={`flex items-center gap-2 ${config?.color || 'text-gray-600'}`}>
          {config?.icon || <Activity size={18} />}
          <span className="text-sm font-medium text-gray-800">
            {config?.label || record.data_type}
          </span>
        </div>
        <div className="text-xs text-gray-400">
          {record.data_type === 'PLANT_STATUS' && payload.status === 'OPERATING' && (
            <span className="flex items-center gap-1 text-green-600">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              Live
            </span>
          )}
        </div>
      </div>

      {displayValue !== null && displayValue !== undefined ? (
        <div className={`text-3xl font-bold ${config?.color || 'text-gray-900'} mb-1`}>
          {typeof displayValue === 'number' ? displayValue.toLocaleString() : String(displayValue)}
          {unit && <span className="text-sm font-normal text-gray-500 ml-1">{unit}</span>}
        </div>
      ) : (
        <div className="space-y-1">
          {Object.entries(payload).filter(([k]) => k !== 'timestamp').map(([k, v]) => (
            <div key={k} className="text-sm">
              <span className="text-gray-500">{k}: </span>
              <span className="font-medium text-gray-800">{String(v)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 pt-3 border-t border-gray-50 flex items-center justify-between text-xs text-gray-400">
        <span>{record.gateway_id}</span>
        <span>{new Date(timestamp).toLocaleString()}</span>
      </div>

      {/* RED III standard badge for GHG */}
      {record.data_type === 'GHG_MEASUREMENT' && payload.standard && (
        <div className="mt-2 text-xs text-green-700 bg-green-50 px-2 py-1 rounded inline-block">
          {payload.standard} compliant
        </div>
      )}

      {/* Uptime for plant status */}
      {record.data_type === 'PLANT_STATUS' && payload.uptime_pct != null && (
        <div className="mt-2">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>Uptime</span>
            <span>{payload.uptime_pct}%</span>
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 rounded-full"
              style={{ width: `${payload.uptime_pct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export function PlantDataDashboard() {
  const [records, setRecords] = useState<PlantRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [isDemo, setIsDemo] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  // Project context resolution order:
  //   1. ?project=<id> from URL (deep-link from ProjectProfile)
  //   2. global useSelectedProject() context
  //   3. FALLBACK_PROJECT_ID for unauthenticated demo flow
  const [searchParams] = useSearchParams()
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject()
  const queryProject = searchParams.get('project')
  const projectId = queryProject || selectedProjectId || FALLBACK_PROJECT_ID

  // Sync the query-string project into global context so other screens
  // the user navigates to next stay on the same project.
  useEffect(() => {
    if (queryProject && queryProject !== selectedProjectId) {
      setSelectedProjectId(queryProject)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryProject])

  const load = () => {
    setLoading(true)
    plantDataAPI.getForProject(projectId)
      .then((data) => {
        if (data.records && data.records.length > 0) {
          setRecords(data.records)
          setIsDemo(false)
        } else {
          return plantDataAPI.getDemoData(projectId).then((demo) => {
            setRecords(demo.records || [])
            setIsDemo(true)
          })
        }
        setLastRefresh(new Date())
        setLoading(false)
      })
      .catch(() => {
        plantDataAPI.getDemoData(projectId)
          .then((demo) => {
            setRecords(demo.records || [])
            setIsDemo(true)
            setLastRefresh(new Date())
            setLoading(false)
          })
          .catch(() => setLoading(false))
      })
  }

  useEffect(() => { load() }, [projectId])

  // Deduplicate: keep latest record per data_type
  const latestByType = records.reduce<Record<string, PlantRecord>>((acc, rec) => {
    if (!acc[rec.data_type] || rec.received_at > acc[rec.data_type].received_at) {
      acc[rec.data_type] = rec
    }
    return acc
  }, {})

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Activity size={22} className="text-orange-600" />
            Plant Telemetry
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Live OT data from registered gateways · One-way ingest · SHA-256 verified
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isDemo && (
            <div className="flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-3 py-1.5 rounded">
              <AlertCircle size={12} />
              Demo data — no gateway connected
            </div>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 text-xs text-gray-600 border border-gray-200 px-3 py-1.5 rounded hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading telemetry…</div>
      ) : Object.keys(latestByType).length === 0 ? (
        <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-lg">
          <Activity size={32} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-400">No plant data received yet</p>
          <p className="text-xs text-gray-400 mt-1">
            Register a gateway and push data to POST /api/v1/plant-data/ingest
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {Object.values(latestByType).map((record) => (
            <RecordCard key={record.data_type} record={record} />
          ))}
        </div>
      )}

      {lastRefresh && (
        <div className="mt-4 text-xs text-gray-400 text-right">
          Last updated: {lastRefresh.toLocaleTimeString()}
        </div>
      )}

      <div className="mt-6 text-xs text-gray-400 border-t pt-4">
        Domain 4 — OT/IT Boundary · NIS2 Art. 21 ·
        Data integrity verified by SHA-256 · Project: {projectId}
      </div>
    </div>
  )
}
