/**
 * NodeValidationBadge — Tiny status indicator for canvas nodes.
 */
import { memo } from "react";
import { Lock, ShieldCheck, Clock, Pencil } from "lucide-react";
import { getValidationStatus, type ValidationStatus } from "./OwnershipRolesPanel";

const STATUS_CONFIG: Record<ValidationStatus, { icon: typeof Lock; color: string; bg: string; border: string; label: string }> = {
  Draft: { icon: Pencil, color: "text-muted-foreground", bg: "bg-muted", border: "border-border", label: "Draft" },
  "Under Review": { icon: Clock, color: "text-warning", bg: "bg-warning/15", border: "border-warning/40", label: "Review" },
  Validated: { icon: ShieldCheck, color: "text-success", bg: "bg-success/15", border: "border-success/40", label: "Valid" },
};

const NodeValidationBadge = memo(({ nodeId }: { nodeId: string }) => {
  const status = getValidationStatus(nodeId);
  if (status === "Draft") return null;
  const config = STATUS_CONFIG[status];
  if (!config) return null;
  const Icon = config.icon;

  return (
    <div
      className={`absolute -top-1.5 -left-1.5 flex items-center justify-center rounded-full border h-3.5 w-3.5 z-10 ${config.bg} ${config.border}`}
      title={`Status: ${status}`}
    >
      <Icon className={`h-2 w-2 ${config.color}`} />
    </div>
  );
});
NodeValidationBadge.displayName = "NodeValidationBadge";

export default NodeValidationBadge;
