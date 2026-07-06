/**
 * Renders peer cursors inside the React Flow viewport so they
 * track pan/zoom automatically. Cursors fade out after 5s idle.
 */
import { useEffect, useState } from "react";
import { ViewportPortal } from "@xyflow/react";
import type { PresencePeer } from "@/hooks/useCanvasPresence";

interface Props {
  peers: PresencePeer[];
}

const IDLE_FADE_MS = 5000;

export function PresenceCursors({ peers }: Props) {
  // Re-render every second so idle fade actually applies.
  const [, setTick] = useState(0);
  useEffect(() => {
    const i = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(i);
  }, []);

  return (
    <ViewportPortal>
      {peers.map((peer) => {
        if (!peer.cursor) return null;
        const age = Date.now() - peer.lastSeen;
        if (age > IDLE_FADE_MS * 2) return null;
        const opacity = age > IDLE_FADE_MS ? Math.max(0, 1 - (age - IDLE_FADE_MS) / IDLE_FADE_MS) : 1;
        return (
          <div
            key={peer.userId}
            style={{
              position: "absolute",
              left: peer.cursor.x,
              top: peer.cursor.y,
              pointerEvents: "none",
              transform: "translate(-2px, -2px)",
              transition: "left 80ms linear, top 80ms linear, opacity 200ms",
              opacity,
              zIndex: 1100,
            }}
          >
            <svg width="22" height="22" viewBox="0 0 22 22" style={{ display: "block" }}>
              <path
                d="M2 2 L20 10 L11 12 L9 20 Z"
                fill={peer.color}
                stroke="white"
                strokeWidth="1.2"
                strokeLinejoin="round"
              />
            </svg>
            <div
              style={{
                marginTop: 2,
                marginLeft: 14,
                padding: "2px 6px",
                borderRadius: 4,
                background: peer.color,
                color: "white",
                fontSize: 11,
                fontWeight: 500,
                whiteSpace: "nowrap",
                boxShadow: "0 1px 3px rgba(0,0,0,0.25)",
              }}
            >
              {peer.name}
            </div>
          </div>
        );
      })}
    </ViewportPortal>
  );
}
