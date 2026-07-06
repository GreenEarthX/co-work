// Screen: Hook (no screen)
/**
 * useGateAccess — workflow enforcement hook.
 *
 * Gate config source priority:
 *   1. Backend `GET /api/v1/gates/screen-gates` (via useGateConfig) — canonical.
 *   2. Menu-derived PATH_GATE_MAP — development fallback only, used when the
 *      backend is unreachable or hasn't returned yet.
 *
 * Returns:
 *   - isScreenLocked(path)     — true if the screen requires a gate that isn't met
 *   - getGateRequirement(path) — gate ID + name + completion for the lock message
 *   - gateCompletionMap        — gate short ID → completion_pct
 */

import { useMemo } from 'react'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useGateConfig } from '@/hooks/useGateConfig'
import { MENU_TABS } from '@/config/menuArchitecture'
import { getShortGateId } from '@/config/gateAccess'
import type { BankabilityGate } from '@/data/customerProjects'

const GATE_UNLOCK_THRESHOLD = 60 // % completion required to unlock downstream screens

export interface GateRequirement {
  gateShortId: string
  gateName: string
  completionPct: number
  threshold: number
  isLocked: boolean
}

// Local fallback: derive path → gate prerequisite from the menu architecture.
// Used only when the backend screen-gates endpoint is unavailable.
const LOCAL_PATH_GATE_MAP: Record<string, string> = {}
for (const tab of MENU_TABS) {
  for (const item of tab.items) {
    if (item.gate_prerequisite) {
      LOCAL_PATH_GATE_MAP[item.path] = item.gate_prerequisite
    }
  }
}

export function useGateAccess() {
  const { selectedProjectId } = useSelectedProject()
  const { projects } = useVisibleProjects()
  const { screenGateMap } = useGateConfig()

  // Use backend gate map when available; fall back to menu-derived map in dev
  const pathGateMap = screenGateMap ?? LOCAL_PATH_GATE_MAP

  const project = useMemo(
    () => projects.find(p => p.id === selectedProjectId),
    [projects, selectedProjectId],
  )

  const gateCompletionMap = useMemo(() => {
    const map: Record<string, BankabilityGate> = {}
    if (!project?.bankability?.gates) return map
    for (const gate of project.bankability.gates) {
      const shortId = getShortGateId(gate.id)
      map[shortId] = gate
    }
    return map
  }, [project])

  const getGateRequirement = useMemo(() => {
    return (path: string): GateRequirement | null => {
      const gatePrereq = pathGateMap[path]
      if (!gatePrereq) return null

      // Backend returns full IDs like "G5_EPC_RISK_PRICED"; menu uses short "G5"
      const shortId = getShortGateId(gatePrereq)
      const gate = gateCompletionMap[shortId] ?? gateCompletionMap[gatePrereq]

      if (!gate) {
        return {
          gateShortId: shortId,
          gateName: `Gate ${shortId}`,
          completionPct: 0,
          threshold: GATE_UNLOCK_THRESHOLD,
          isLocked: true,
        }
      }

      return {
        gateShortId: shortId,
        gateName: gate.name,
        completionPct: gate.completion_pct,
        threshold: GATE_UNLOCK_THRESHOLD,
        isLocked: gate.completion_pct < GATE_UNLOCK_THRESHOLD,
      }
    }
  }, [gateCompletionMap, pathGateMap])

  const isScreenLocked = useMemo(() => {
    return (path: string): boolean => {
      const req = getGateRequirement(path)
      return req?.isLocked ?? false
    }
  }, [getGateRequirement])

  return {
    isScreenLocked,
    getGateRequirement,
    gateCompletionMap,
    threshold: GATE_UNLOCK_THRESHOLD,
  }
}
