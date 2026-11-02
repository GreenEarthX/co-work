// Screen: Panel on the project report (/project-report)
/**
 * The gate clock (JML 2026-10-31; /api/v1/projects/{id}/gate-clock): when each gate was first
 * seen satisfied, and how many days after the project was created. It is the only measurement of
 * whether the gate structure accelerates anything. First evaluation that saw the gate satisfied,
 * not the day the last document was filed; gates satisfied before the clock began are not shown.
 */
import { useEffect, useState } from 'react'
import { Timer } from 'lucide-react'
import { getAuthHeader } from '@/lib/authToken'

interface ClockGate { gate_id: string; first_satisfied_at: string; days_from_project_start: number | null; state_at_time: string | null }
interface Clock { gates: ClockGate[]; note: string; project_started_at: string | null }

export function GateClockPanel({ projectId, reloadKey = 0 }: { projectId: string; reloadKey?: number }) {
  const [data, setData] = useState<Clock | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/gate-clock`, { headers: getAuthHeader() })
      .then(async r => { if (!r.ok) throw new Error(`The server answered ${r.status}.`); return r.json() })
      .then(d => { if (live) setData(d) })
      .catch(e => { if (live) setError(e.message) })
    return () => { live = false }
  }, [projectId, reloadKey])

  if (error) return <p className="px-5 py-4 text-sm text-gray-400">{error}</p>
  if (!data) return null
  return (
    <div className="rounded-2xl border border-gray-200 bg-white" data-testid="gate-clock">
      <h2 className="flex items-center gap-2 border-b border-gray-100 px-5 py-3 text-sm font-bold text-gray-900">
        <Timer className="h-4 w-4" /> Gate clock — when each gate was first satisfied
      </h2>
      {data.gates.length === 0 ? (
        <p className="px-5 py-3 text-sm text-gray-500">No gate has been seen satisfied yet.</p>
      ) : (
        <ul className="divide-y divide-gray-100">
          {data.gates.map(g => (
            <li key={g.gate_id} className="flex flex-wrap items-baseline gap-x-3 px-5 py-2 text-sm">
              <span className="font-mono font-semibold">{g.gate_id.split('_')[0]}</span>
              <span>{g.first_satisfied_at.slice(0, 10)}</span>
              {g.days_from_project_start !== null && (
                <span className="text-gray-500">day {g.days_from_project_start} of the project</span>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="px-5 py-2 text-[11px] text-gray-400">{data.note}</p>
    </div>
  )
}
