/**
 * useEventStream — SSE client stub (Sprint 0 contract, deferred implementation).
 *
 * Returns a fixed not-connected state while the backend stream is not yet live.
 * When the backend `GET /api/v1/events/stream/{project_id}` returns a real stream
 * (Sprint 1), replace this stub with an EventSource connection that:
 *   - Passes the JWT via ?token=<jwt> (EventSource cannot set headers)
 *   - Calls queryClient.invalidateQueries on gate.score_changed / evidence.verified
 *   - Updates lastEvent state on any received event
 *   - Closes the connection on unmount or when projectId changes
 *
 * No UI component should claim live updates until isConnected is true.
 */

export interface StreamEvent {
  event_id: string
  event_type: string
  project_id: string
  payload: Record<string, unknown>
  timestamp: string
}

export interface UseEventStreamResult {
  lastEvent: StreamEvent | null
  isConnected: boolean
  eventCount: number
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function useEventStream(_projectId: string | null): UseEventStreamResult {
  // Stub — returns not-connected until Sprint 1 SSE implementation lands.
  return {
    lastEvent: null,
    isConnected: false,
    eventCount: 0,
  }
}
