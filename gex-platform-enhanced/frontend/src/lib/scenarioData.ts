/** Scenario data stub — to be populated when scenario engine is wired */

export interface ScenarioData {
  id: string
  name: string
  description?: string
  parameters?: Record<string, unknown>
}

export const scenarios: ScenarioData[] = []
