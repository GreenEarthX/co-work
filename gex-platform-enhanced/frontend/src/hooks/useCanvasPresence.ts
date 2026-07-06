/**
 * useCanvasPresence — Phase 1 of canvas multiplayer.
 * Joins a Supabase Realtime channel scoped to a single plant, tracks each
 * connected user's identity, and broadcasts/receives cursor positions in
 * React Flow coordinates so every viewer renders peers correctly under
 * their own pan/zoom.
 */
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { supabase } from "@/lib/backendClient";
import type { RealtimeChannel } from "@supabase/supabase-js";

export interface PresenceUser {
  userId: string;
  name: string;
  email?: string;
  color: string;
}

export interface PresencePeer extends PresenceUser {
  cursor: { x: number; y: number } | null;
  lastSeen: number;
}

const PALETTE = [
  "#ef4444", "#f97316", "#f59e0b", "#84cc16",
  "#10b981", "#06b6d4", "#3b82f6", "#6366f1",
  "#8b5cf6", "#d946ef", "#ec4899", "#14b8a6",
];

export function colorForUser(userId: string): string {
  let h = 0;
  for (let i = 0; i < userId.length; i++) h = (h * 31 + userId.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

const CURSOR_THROTTLE_MS = 33;

export function useCanvasPresence(plantId: string | undefined, me: PresenceUser | null) {
  const [peers, setPeers] = useState<Record<string, PresencePeer>>({});
  const channelRef = useRef<RealtimeChannel | null>(null);
  const lastSentRef = useRef(0);
  const pendingRef = useRef<{ x: number; y: number } | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!plantId || !me) return;
    const channel = supabase.channel(`plant:${plantId}`, {
      config: {
        presence: { key: me.userId },
        broadcast: { self: false },
      },
    });
    channelRef.current = channel;

    const updateFromState = () => {
      const state = channel.presenceState() as Record<string, Array<PresenceUser>>;
      setPeers((prev) => {
        const next: Record<string, PresencePeer> = {};
        for (const [key, metas] of Object.entries(state)) {
          if (key === me.userId) continue;
          const meta = metas[0];
          if (!meta) continue;
          const existing = prev[key];
          next[key] = {
            userId: meta.userId ?? key,
            name: meta.name ?? "Guest",
            email: meta.email,
            color: meta.color ?? colorForUser(key),
            cursor: existing?.cursor ?? null,
            lastSeen: existing?.lastSeen ?? Date.now(),
          };
        }
        return next;
      });
    };

    channel
      .on("presence", { event: "sync" }, updateFromState)
      .on("presence", { event: "join" }, updateFromState)
      .on("presence", { event: "leave" }, updateFromState)
      .on("broadcast", { event: "cursor" }, (payload: { payload: unknown }) => {
        const data = payload.payload as { userId: string; x: number; y: number } | undefined;
        if (!data || data.userId === me.userId) return;
        setPeers((prev) => {
          const existing = prev[data.userId];
          if (!existing) return prev;
          return {
            ...prev,
            [data.userId]: { ...existing, cursor: { x: data.x, y: data.y }, lastSeen: Date.now() },
          };
        });
      })
      .subscribe(async (status: string) => {
        if (status === "SUBSCRIBED") {
          await channel.track(me);
        }
      });

    return () => {
      try { channel.untrack(); } catch { /* noop */ }
      supabase.removeChannel(channel);
      channelRef.current = null;
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plantId, me?.userId]);

  const publishCursor = useCallback((x: number, y: number) => {
    pendingRef.current = { x, y };
    if (rafRef.current != null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      const now = Date.now();
      if (now - lastSentRef.current < CURSOR_THROTTLE_MS) return;
      const ch = channelRef.current;
      const point = pendingRef.current;
      if (!ch || !point || !me) return;
      lastSentRef.current = now;
      ch.send({
        type: "broadcast",
        event: "cursor",
        payload: { userId: me.userId, x: point.x, y: point.y },
      });
    });
  }, [me]);

  const peerList = useMemo(() => Object.values(peers), [peers]);
  return { peers: peerList, publishCursor };
}
