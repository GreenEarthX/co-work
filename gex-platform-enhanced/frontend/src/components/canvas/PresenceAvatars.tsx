/**
 * Small avatar stack indicating who else is currently viewing this plant.
 */
import type { PresencePeer } from "@/hooks/useCanvasPresence";

interface Props {
  peers: PresencePeer[];
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function PresenceAvatars({ peers }: Props) {
  if (peers.length === 0) return null;
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1 shadow-sm">
      <div className="flex -space-x-1.5">
        {peers.slice(0, 5).map((p) => (
          <div
            key={p.userId}
            title={p.name}
            className="flex h-6 w-6 items-center justify-center rounded-full border border-card text-[10px] font-semibold text-white"
            style={{ background: p.color }}
          >
            {initials(p.name)}
          </div>
        ))}
      </div>
      <span className="text-[11px] text-muted-foreground">
        {peers.length === 1 ? "1 person here" : `${peers.length} people here`}
      </span>
    </div>
  );
}
