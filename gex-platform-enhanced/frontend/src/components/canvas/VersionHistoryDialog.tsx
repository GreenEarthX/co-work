/**
 * VersionHistoryDialog — Lists timestamped canvas snapshots and lets the
 * user restore a previous saved version of the plant.
 */
import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/Button";
import { History, RotateCcw, Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { VersionEntry, CanvasData } from "@/hooks/useCanvasData";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  listVersions: () => Promise<VersionEntry[]>;
  restoreVersion: (path: string) => Promise<CanvasData | null>;
  onRestored: (data: CanvasData) => void;
}

const formatRelative = (date: Date) => {
  const diffMs = Date.now() - date.getTime();
  const sec = Math.round(diffMs / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} min ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} h ago`;
  const d = Math.round(hr / 24);
  return `${d} d ago`;
};

const VersionHistoryDialog = ({ open, onOpenChange, listVersions, restoreVersion, onRestored }: Props) => {
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    listVersions()
      .then((list) => {
        if (!cancelled) setVersions(list);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, listVersions]);

  const handleRestore = async (entry: VersionEntry) => {
    setRestoring(entry.path);
    try {
      const restored = await restoreVersion(entry.path);
      if (restored) {
        onRestored(restored);
        toast.success(`Restored snapshot from ${entry.createdAt.toLocaleString()}`);
        onOpenChange(false);
      } else {
        toast.error("Could not restore this version");
      }
    } finally {
      setRestoring(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-sm flex items-center gap-2">
            <History className="h-4 w-4 text-primary" />
            Version History
          </DialogTitle>
          <DialogDescription className="text-xs">
            Restore your plant canvas to any previous saved snapshot. Snapshots are taken automatically
            (at most one per minute) and the last {30} are kept.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-80 pr-2 -mr-2">
          {loading ? (
            <div className="flex items-center justify-center py-8 text-xs text-muted-foreground gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading snapshots…
            </div>
          ) : versions.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              No snapshots yet. Make a few changes to start building version history.
            </div>
          ) : (
            <ul className="space-y-1.5">
              {versions.map((v) => (
                <li
                  key={v.path}
                  className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2 text-xs"
                >
                  <div className="flex flex-col min-w-0">
                    <span className="font-medium text-card-foreground truncate">
                      {v.createdAt.toLocaleString()}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {formatRelative(v.createdAt)}
                      {v.size ? ` · ${(v.size / 1024).toFixed(1)} KB` : ""}
                    </span>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-[11px]"
                    disabled={restoring !== null}
                    onClick={() => handleRestore(v)}
                  >
                    {restoring === v.path ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <RotateCcw className="h-3 w-3" />
                    )}
                    Restore
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>

        <DialogFooter>
          <Button variant="ghost" size="sm" className="text-xs" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default VersionHistoryDialog;