/**
 * AuditLogPanel — Chronological history of ownership and lifecycle events.
 */
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import {
  Clock,
  Crown,
  FileUp,
  Building2,
  ArrowRightLeft,
  ShieldCheck,
  UserPlus,
  Pencil,
  ShoppingCart,
  PlusCircle,
} from "lucide-react";
import { getAuditLog, getTeamMembers, type AuditLogEntry } from "./OwnershipRolesPanel";

const CATEGORY_CONFIG: Record<AuditLogEntry["category"], { icon: typeof Clock; color: string; bg: string }> = {
  role_assignment: { icon: UserPlus, color: "text-primary", bg: "bg-primary/10" },
  role_change: { icon: ArrowRightLeft, color: "text-warning", bg: "bg-warning/10" },
  status_transition: { icon: ShieldCheck, color: "text-success", bg: "bg-success/10" },
  ownership_type: { icon: Building2, color: "text-accent-foreground", bg: "bg-accent" },
  certification: { icon: FileUp, color: "text-primary", bg: "bg-primary/10" },
  system: { icon: Crown, color: "text-muted-foreground", bg: "bg-muted" },
  field_edit: { icon: Pencil, color: "text-primary", bg: "bg-primary/10" },
  procurement: { icon: ShoppingCart, color: "text-success", bg: "bg-success/10" },
  lifecycle: { icon: PlusCircle, color: "text-accent-foreground", bg: "bg-accent" },
};

interface Props {
  componentId: string;
}

const AuditLogPanel = ({ componentId }: Props) => {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (!detail || detail.componentId === componentId) setTick((t) => t + 1);
    };
    window.addEventListener("gex:audit-log-updated", handler);
    return () => window.removeEventListener("gex:audit-log-updated", handler);
  }, [componentId]);
  const entries = useMemo(() => getAuditLog(componentId), [componentId, tick]);
  const team = useMemo(() => getTeamMembers(), []);

  const getPerformerName = (userId: string) => {
    if (userId === "system") return "System";
    return team.find((m) => m.user_id === userId)?.name ?? userId;
  };

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-muted/40 px-4 py-8 text-center">
        <Clock className="h-5 w-5 text-muted-foreground mx-auto mb-2" />
        <p className="text-xs text-muted-foreground">No audit events recorded yet.</p>
        <p className="text-[10px] text-muted-foreground mt-1">
          Role assignments, status changes, and other actions will appear here.
        </p>
      </div>
    );
  }

  // Reverse chronological
  const sorted = [...entries].reverse();

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
          {entries.length} event{entries.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="relative">
        {/* Timeline line */}
        <div className="absolute left-[15px] top-3 bottom-3 w-px bg-border" />

        {sorted.map((entry, i) => {
          const config = CATEGORY_CONFIG[entry.category] || CATEGORY_CONFIG.system;
          const Icon = config.icon;
          const date = new Date(entry.timestamp);

          return (
            <div key={i} className="relative flex gap-3 pb-3">
              {/* Timeline dot */}
              <div className={`relative z-10 h-[30px] w-[30px] rounded-full ${config.bg} flex items-center justify-center shrink-0`}>
                <Icon className={`h-3.5 w-3.5 ${config.color}`} />
              </div>

              <div className="flex-1 min-w-0 pt-0.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-medium text-foreground">{entry.action}</span>
                  <Badge variant="outline" className="text-[8px] h-3.5 px-1 shrink-0">
                    {entry.category.replace("_", " ")}
                  </Badge>
                </div>

                {(entry.old_value || entry.new_value) && (
                  <div className="flex items-center gap-1.5 mt-1 text-[10px]">
                    {entry.old_value && (
                      <span className="text-muted-foreground line-through">{entry.old_value}</span>
                    )}
                    {entry.old_value && entry.new_value && (
                      <span className="text-muted-foreground">→</span>
                    )}
                    {entry.new_value && (
                      <span className="text-foreground font-medium">{entry.new_value}</span>
                    )}
                  </div>
                )}

                {entry.details && (
                  <p className="text-[10px] text-muted-foreground mt-0.5 italic">{entry.details}</p>
                )}

                <div className="flex items-center gap-2 mt-1 text-[9px] text-muted-foreground">
                  <span>{getPerformerName(entry.performed_by)}</span>
                  <span>·</span>
                  <span>{date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default AuditLogPanel;
