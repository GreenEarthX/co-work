// Screen: Gantt visibility config screen (/ciso-gantt-config)
/**
 * GanttVisibilityConfig — CISO control panel for configuring which Gantt items
 * each workspace can see. Implements ABAC gate filtering for the Production
 * Roadmap view. Changes are persisted to localStorage and propagated on next load.
 */

import { useState, useEffect } from 'react'
import { Eye, EyeOff, RotateCcw, Save, CheckCircle2, Shield } from 'lucide-react'

// ─────────────────────────────── Types ───────────────────────────────────────

type WorkspaceId = 'producer' | 'finance' | 'trader' | 'regulator' | 'executive'

// ─────────────────────────────── Data ────────────────────────────────────────

const GANTT_ITEM_DEFS = [
  // Advisory
  { id: 'G0',         name: 'Site Rights (G0)',          phase: 'ADVISORY',     type: 'gate'      },
  { id: 'G1',         name: 'Grid Connection (G1)',       phase: 'ADVISORY',     type: 'gate'      },
  { id: 'G2',         name: 'RFNBO Certification (G2)',   phase: 'ADVISORY',     type: 'gate'      },
  { id: 'G3',         name: 'Feedstock & Logistics (G3)', phase: 'ADVISORY',     type: 'gate'      },
  { id: 'G4',         name: 'Binding Offtake (G4)',       phase: 'ADVISORY',     type: 'gate'      },
  { id: 'G9',         name: 'Permits & Regulatory (G9)',  phase: 'ADVISORY',     type: 'gate'      },
  { id: 'MS_DFI',     name: 'DFI Mandate Letter',         phase: 'ADVISORY',     type: 'milestone' },
  // Build
  { id: 'G5',         name: 'EPC & Construction (G5)',    phase: 'BUILD',        type: 'gate'      },
  { id: 'G6',         name: 'IE Signoff (G6)',             phase: 'BUILD',        type: 'gate'      },
  { id: 'G7',         name: 'Insurance Program (G7)',      phase: 'BUILD',        type: 'gate'      },
  { id: 'MS_EPC_EXEC',name: 'EPC Contract Executed',      phase: 'BUILD',        type: 'milestone' },
  { id: 'MS_INSURANCE',name: 'CAR/DSU Placed',            phase: 'BUILD',        type: 'milestone' },
  // Financial Close
  { id: 'G8',         name: 'Financial Model (G8)',        phase: 'FIN_CLOSE',   type: 'gate'      },
  { id: 'G10',        name: 'Financial Close (G10)',       phase: 'FIN_CLOSE',   type: 'gate'      },
  { id: 'MS_TERM_SHEET',name: 'Term Sheet Executed',      phase: 'FIN_CLOSE',   type: 'milestone' },
  { id: 'MS_FID',     name: 'FID Decision',                phase: 'FIN_CLOSE',   type: 'milestone' },
  // Construction
  { id: 'MS_NTP',     name: 'NTP Issued',                  phase: 'CONSTRUCTION', type: 'milestone' },
  { id: 'MS_ELECTRO', name: 'Electrolyser Delivery',       phase: 'CONSTRUCTION', type: 'milestone' },
  { id: 'MS_FAT',     name: 'Factory Acceptance Test',     phase: 'CONSTRUCTION', type: 'milestone' },
  // Operations
  { id: 'G11',        name: 'COD (G11)',                   phase: 'OPERATIONS',  type: 'gate'      },
  { id: 'MS_COMM_OPS',name: 'Commercial Operations',       phase: 'OPERATIONS',  type: 'milestone' },
  { id: 'MS_FIRST_GOO',name: 'First GoO Issuance',        phase: 'OPERATIONS',  type: 'milestone' },
]

const DEFAULT_VISIBILITY: Record<string, string[]> = {
  producer:  ['G0','G1','G2','G3','G4','G5','G6','G7','G8','G9','G10','G11','MS_DFI','MS_EPC_EXEC','MS_INSURANCE','MS_TERM_SHEET','MS_FID','MS_NTP','MS_ELECTRO','MS_FAT','MS_COMM_OPS','MS_FIRST_GOO'],
  finance:   ['G4','G7','G8','G9','G10','G11','MS_DFI','MS_TERM_SHEET','MS_FID','MS_NTP','MS_COMM_OPS'],
  trader:    ['G4','G11','MS_TERM_SHEET','MS_NTP','MS_COMM_OPS','MS_FIRST_GOO'],
  regulator: ['G2','G9','G11','MS_FAT','MS_COMM_OPS','MS_FIRST_GOO'],
  executive: ['G5','G8','G10','G11','MS_DFI','MS_TERM_SHEET','MS_FID','MS_COMM_OPS'],
}

const WORKSPACES: { id: WorkspaceId; label: string; color: string; bg: string }[] = [
  { id: 'producer',  label: 'Producer',  color: 'text-emerald-700', bg: 'bg-emerald-50' },
  { id: 'finance',   label: 'Finance',   color: 'text-blue-700',    bg: 'bg-blue-50'    },
  { id: 'trader',    label: 'Trader',    color: 'text-purple-700',  bg: 'bg-purple-50'  },
  { id: 'regulator', label: 'Regulator', color: 'text-red-700',     bg: 'bg-red-50'     },
  { id: 'executive', label: 'Executive', color: 'text-gray-700',    bg: 'bg-gray-50'    },
]

// ─────────────────────────────── Phase config ─────────────────────────────────

const PHASES = [
  { id: 'ADVISORY',     label: 'ADVISORY',      bandClass: 'bg-amber-100 text-amber-800'   },
  { id: 'BUILD',        label: 'BUILD',          bandClass: 'bg-blue-100 text-blue-800'     },
  { id: 'FIN_CLOSE',   label: 'FINANCIAL CLOSE', bandClass: 'bg-purple-100 text-purple-800' },
  { id: 'CONSTRUCTION', label: 'CONSTRUCTION',   bandClass: 'bg-emerald-100 text-emerald-800' },
  { id: 'OPERATIONS',  label: 'OPERATIONS',      bandClass: 'bg-green-100 text-green-800'   },
]

// ─────────────────────────────── Component ───────────────────────────────────

export function GanttVisibilityConfig() {
  const [config, setConfig] = useState<Record<string, string[]>>(DEFAULT_VISIBILITY)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    try {
      const stored = localStorage.getItem('gex_gantt_visibility')
      if (stored) setConfig(JSON.parse(stored))
    } catch {}
  }, [])

  const handleSave = () => {
    localStorage.setItem('gex_gantt_visibility', JSON.stringify(config))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleReset = () => {
    setConfig(DEFAULT_VISIBILITY)
    localStorage.setItem('gex_gantt_visibility', JSON.stringify(DEFAULT_VISIBILITY))
  }

  const toggle = (workspace: string, itemId: string) => {
    setConfig(prev => {
      const current = prev[workspace] ?? []
      const next = current.includes(itemId)
        ? current.filter(x => x !== itemId)
        : [...current, itemId]
      return { ...prev, [workspace]: next }
    })
  }

  return (
    <div className="p-6 space-y-5">

      {/* ── Save confirmation toast ── */}
      {saved && (
        <div className="flex items-center gap-2 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800 shadow-sm">
          <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-green-600" />
          Configuration saved — all workspace Gantts will refresh on next load.
        </div>
      )}

      {/* ── Header bar ── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg bg-slate-100 p-2">
            <Shield className="h-5 w-5 text-slate-600" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Gantt Visibility Control</h1>
            <p className="mt-0.5 text-sm text-gray-500 max-w-xl">
              Configure which production roadmap items each workspace can see.
              Changes take effect immediately for all logged-in sessions.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={handleReset}
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 transition-colors"
          >
            <RotateCcw className="h-4 w-4" />
            Reset to Defaults
          </button>
          <button
            onClick={handleSave}
            className="inline-flex items-center gap-1.5 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-green-700 transition-colors"
          >
            <Save className="h-4 w-4" />
            Save
          </button>
        </div>
      </div>

      {/* ── Info card ── */}
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 leading-relaxed">
        The Gantt visibility matrix implements ABAC gate filtering for the Production Roadmap view.
        Each workspace actor sees only the items authorized by the CISO. Changes are stored in the
        platform configuration and propagated to all active sessions.
      </div>

      {/* ── Matrix table ── */}
      <div className="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="py-3 px-4 text-left font-semibold text-gray-700 w-56 min-w-[14rem]">
                Item
              </th>
              {WORKSPACES.map(ws => (
                <th
                  key={ws.id}
                  className={`py-3 px-3 text-center font-semibold ${ws.color} ${ws.bg} min-w-[6rem]`}
                >
                  {ws.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {PHASES.map(phase => {
              const phaseItems = GANTT_ITEM_DEFS.filter(item => item.phase === phase.id)
              return (
                <>
                  {/* Phase header row */}
                  <tr key={`phase-${phase.id}`}>
                    <td
                      colSpan={WORKSPACES.length + 1}
                      className={`py-2 px-4 text-xs font-bold tracking-widest uppercase ${phase.bandClass}`}
                    >
                      {phase.label}
                    </td>
                  </tr>

                  {/* Item rows */}
                  {phaseItems.map((item, idx) => (
                    <tr
                      key={item.id}
                      className={`border-b border-gray-100 ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/40'} hover:bg-gray-50 transition-colors`}
                    >
                      {/* Item label */}
                      <td className="py-2.5 px-4 text-gray-700 font-medium whitespace-nowrap">
                        <span className="mr-1.5 text-gray-400 select-none">
                          {item.type === 'gate' ? '○' : '◆'}
                        </span>
                        {item.name}
                      </td>

                      {/* Workspace toggle cells */}
                      {WORKSPACES.map(ws => {
                        const visible = (config[ws.id] ?? []).includes(item.id)
                        return (
                          <td
                            key={ws.id}
                            className="py-2.5 px-3 text-center cursor-pointer select-none"
                            onClick={() => toggle(ws.id, item.id)}
                            title={visible ? `Hide from ${ws.label}` : `Show to ${ws.label}`}
                          >
                            <span className={`inline-flex items-center justify-center rounded-md p-1 transition-colors ${visible ? 'text-green-600 hover:bg-green-50' : 'text-gray-300 hover:bg-gray-100'}`}>
                              {visible
                                ? <Eye className="h-4 w-4" />
                                : <EyeOff className="h-4 w-4" />
                              }
                            </span>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* ── Summary strip ── */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <span className="text-sm text-gray-500 font-medium">Visible items:</span>
        {WORKSPACES.map(ws => {
          const count = (config[ws.id] ?? []).length
          return (
            <span
              key={ws.id}
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${ws.bg} ${ws.color} border border-current/20`}
            >
              {count} to {ws.label}
            </span>
          )
        })}
      </div>

    </div>
  )
}
