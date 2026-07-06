/**
 * useCanvasLiveSync — Phase 2 of canvas multiplayer.
 *
 * Broadcasts the local canvas state (nodes/edges/plantSettings) to other
 * clients viewing the same plant, so peers see edits appear within ~300ms
 * without waiting for the cloud autosave round-trip. Reception is exposed
 * as `lastRemote` state; the consumer decides when it is safe to apply
 * (e.g. not while currently dragging).
 *
 * This sits alongside `useCanvasPresence` (cursors/avatars) on a separate
 * Realtime channel — `plant:{id}:sync` — to keep the high-frequency cursor
 * stream isolated from the heavier snapshot stream.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { supabase } from "@/lib/backendClient";
import type { RealtimeChannel } from "@supabase/supabase-js";
import type { Node, Edge } from "@xyflow/react";
import type { PlantSettings } from "@/hooks/useCanvasData";

export interface RemoteCanvasSnapshot {
  originId: string;
  originName: string;
  ts: number;
  nodes: Node[];
  edges: Edge[];
  plantSettings?: PlantSettings;
}

const THROTTLE_MS = 300;

export function useCanvasLiveSync(
  plantId: string | undefined,
  me: { userId: string; name: string } | null,
) {
  const [lastRemote, setLastRemote] = useState<RemoteCanvasSnapshot | null>(null);
  const channelRef = useRef<RealtimeChannel | null>(null);
  const lastSentRef = useRef(0);
  const pendingRef = useRef<{ nodes: Node[]; edges: Edge[]; plantSettings?: PlantSettings } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!plantId || !me) return;
    const channel = supabase.channel(`plant:${plantId}:sync`, {
      config: { broadcast: { self: false } },
    });
    channelRef.current = channel;

    channel
      .on("broadcast", { event: "canvas:snapshot" }, (msg: { payload: unknown }) => {
        const data = msg.payload as RemoteCanvasSnapshot | undefined;
        if (!data || data.originId === me.userId) return;
        setLastRemote(data);
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
      channelRef.current = null;
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
      pendingRef.current = null;
    };
  }, [plantId, me?.userId, me?.name]);

  const flush = useCallback(() => {
    timerRef.current = null;
    const pending = pendingRef.current;
    const ch = channelRef.current;
    if (!pending || !ch || !me) return;
    pendingRef.current = null;
    lastSentRef.current = Date.now();
    ch.send({
      type: "broadcast",
      event: "canvas:snapshot",
      payload: {
        originId: me.userId,
        originName: me.name,
        ts: lastSentRef.current,
        nodes: pending.nodes,
        edges: pending.edges,
        plantSettings: pending.plantSettings,
      } satisfies RemoteCanvasSnapshot,
    });
  }, [me]);

  const broadcastSnapshot = useCallback(
    (nodes: Node[], edges: Edge[], plantSettings?: PlantSettings) => {
      pendingRef.current = { nodes, edges, plantSettings };
      if (timerRef.current) return;
      const elapsed = Date.now() - lastSentRef.current;
      const wait = elapsed >= THROTTLE_MS ? 0 : THROTTLE_MS - elapsed;
      timerRef.current = setTimeout(flush, wait);
    },
    [flush],
  );

  return { lastRemote, broadcastSnapshot };
}