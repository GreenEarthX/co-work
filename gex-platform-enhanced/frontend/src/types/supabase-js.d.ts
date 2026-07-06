/** Type stubs for @supabase/supabase-js — GEX uses its own backend */
declare module "@supabase/supabase-js" {
  export type RealtimeChannel = {
    on: (event: string, opts: unknown, callback: (...args: unknown[]) => void) => RealtimeChannel
    subscribe: (callback?: (status: string, err?: Error) => void) => RealtimeChannel
    unsubscribe: () => void
    send: (payload: { type: string; event: string; payload: unknown }) => void
    track: (state: Record<string, unknown>) => void
  }

  export function createClient(url: string, key: string, opts?: unknown): {
    auth: {
      getSession(): Promise<{ data: { session: unknown }; error: unknown }>
    }
    channel(name: string): RealtimeChannel
    removeChannel(ch: RealtimeChannel): void
  }
}
