/**
 * ExportValidationDialog — Pre-export checklist with inline role assignment,
 * quick-validate, blocking rules, and dual sign-off.
 */
import { useCallback, useMemo, useState } from "react";
import type { Node } from "@xyflow/react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Crown,
  Lock,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
  Zap,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/Select";
import { toast } from "@/hooks/use-toast";

import {
  getComponentOwnership,
  getTeamMembers,
  lockComponent,
  type ComponentOwnership,
  type ValidationStatus,
  VALIDATION_STATUS_CONFIG,
} from "./OwnershipRolesPanel";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  nodes: Node[];
  plantName: string;
  onExportComplete: () => void;
}

interface ComponentCheck {
  nodeId: string;
  label: string;
  type: string;
  status: ValidationStatus;
  accountableName: string;
  accountableId: string | null;
  responsibleName: string;
  responsibleId: string | null;
  hasAccountable: boolean;
  hasResponsible: boolean;
  ready: boolean;
}

const STATUS_ICON: Record<ValidationStatus, typeof CheckCircle2> = {
  Draft: AlertTriangle,
  "Under Review": ShieldAlert,
  Validated: ShieldCheck,
};

/** Save ownership directly (bypass React state — we reload on each render) */
function saveOwnershipDirect(componentId: string, updates: Partial<ComponentOwnership>) {
  const STORAGE_KEY = "gex_component_ownership";
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const all: Record<string, ComponentOwnership> = raw ? JSON.parse(raw) : {};
    const existing = all[componentId] || {
      component_id: componentId,
      accountable: null,
      responsible: null,
      editors: [],
      viewers: [],
      ownership_type: "Internal",
      ownership_type_log: [],
      certification_file_name: null,
      certification_uploaded_at: null,
      validation_status: "Draft" as ValidationStatus,
      validation_status_log: [],
      last_validated_at: null,
      last_validated_by: null,
      submitted_for_review_by: null,
      audit_log: [],
    };
    all[componentId] = { ...existing, ...updates };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch { /* ignore */ }
}

const ExportValidationDialog = ({ open, onOpenChange, nodes, plantName, onExportComplete }: Props) => {
  const [coSignerId, setCoSignerId] = useState("");
  const [exported, setExported] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const team = useMemo(() => getTeamMembers(), []);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  const getMemberName = (userId: string | null) => {
    if (!userId) return "Unassigned";
    return team.find((m) => m.user_id === userId)?.name ?? "Unknown";
  };

  const checks: ComponentCheck[] = useMemo(() => {
    // refreshKey dependency forces recalculation
    void refreshKey;
    return nodes
      .filter((n) => n.type !== "boundary")
      .map((n) => {
        const o = getComponentOwnership(n.id);
        const ready = o.validation_status === "Validated";
        return {
          nodeId: n.id,
          label: (n.data.label as string) || n.id,
          type: (n.type as string) || "unknown",
          status: o.validation_status,
          accountableName: getMemberName(o.accountable?.user_id ?? null),
          accountableId: o.accountable?.user_id ?? null,
          responsibleName: getMemberName(o.responsible?.user_id ?? null),
          responsibleId: o.responsible?.user_id ?? null,
          hasAccountable: !!o.accountable,
          hasResponsible: !!o.responsible,
          ready,
        };
      });
  }, [nodes, team, refreshKey]);

  const allReady = checks.every((c) => c.ready);
  const blockedCount = checks.filter((c) => !c.ready).length;
  const unassignedCount = checks.filter((c) => !c.hasAccountable || !c.hasResponsible).length;

  // CFO/CEO co-signers
  const coSigners = useMemo(
    () => team.filter((m) => m.global_role === "CFO" || m.global_role === "CEO" || m.global_role === "Head of Engineering" || m.global_role === "Manager"),
    [team],
  );

  const handleAssignRole = (nodeId: string, role: "accountable" | "responsible", userId: string) => {
    const now = new Date().toISOString();
    const o = getComponentOwnership(nodeId);
    const oldName = o[role] ? getMemberName(o[role]!.user_id) : "None";
    const newName = getMemberName(userId);
    saveOwnershipDirect(nodeId, {
      [role]: { user_id: userId, assigned_at: now, assigned_by: "system" },
      audit_log: [
        ...(o.audit_log || []),
        {
          timestamp: now,
          performed_by: "system",
          action: `${role.charAt(0).toUpperCase() + role.slice(1)} assigned (from export dialog)`,
          category: "role_assignment" as const,
          old_value: oldName,
          new_value: newName,
        },
      ],
    });
    refresh();
    toast({ title: "Role assigned", description: `${newName} assigned as ${role}.` });
  };

  const handleQuickValidate = (nodeId: string) => {
    const o = getComponentOwnership(nodeId);
    if (!o.accountable || !o.responsible) {
      toast({ title: "Cannot validate", description: "Assign Accountable and Responsible first.", variant: "destructive" });
      return;
    }
    const now = new Date().toISOString();
    saveOwnershipDirect(nodeId, {
      validation_status: "Validated",
      last_validated_at: now,
      last_validated_by: o.accountable.user_id,
      submitted_for_review_by: o.responsible.user_id,
      validation_status_log: [
        ...o.validation_status_log,
        { from: o.validation_status, to: "Validated" as ValidationStatus, changed_at: now, changed_by: "system" },
      ],
      audit_log: [
        ...(o.audit_log || []),
        {
          timestamp: now,
          performed_by: "system",
          action: `Quick-validated from export dialog (${o.validation_status} → Validated)`,
          category: "status_transition" as const,
          old_value: o.validation_status,
          new_value: "Validated",
        },
      ],
    });
    refresh();
    toast({ title: "Component validated", description: `${(nodes.find((n) => n.id === nodeId)?.data?.label as string) || nodeId} is now Validated.` });
  };

  const handleValidateAll = () => {
    let validated = 0;
    for (const c of checks) {
      if (c.ready) continue;
      const o = getComponentOwnership(c.nodeId);
      // Auto-assign if missing
      const hoe = team.find((m) => m.global_role === "Head of Engineering");
      const eng = team.find((m) => m.global_role === "Engineer") || team.find((m) => m.global_role === "Manager");
      if (!o.accountable && hoe) {
        saveOwnershipDirect(c.nodeId, {
          accountable: { user_id: hoe.user_id, assigned_at: new Date().toISOString(), assigned_by: "system" },
        });
      }
      if (!o.responsible && eng) {
        saveOwnershipDirect(c.nodeId, {
          responsible: { user_id: eng.user_id, assigned_at: new Date().toISOString(), assigned_by: "system" },
        });
      }
      // Now validate
      const updated = getComponentOwnership(c.nodeId);
      if (updated.accountable && updated.responsible) {
        const now = new Date().toISOString();
        saveOwnershipDirect(c.nodeId, {
          validation_status: "Validated",
          last_validated_at: now,
          last_validated_by: updated.accountable.user_id,
          submitted_for_review_by: updated.responsible.user_id,
          validation_status_log: [
            ...updated.validation_status_log,
            { from: updated.validation_status, to: "Validated" as ValidationStatus, changed_at: now, changed_by: "system" },
          ],
          audit_log: [
            ...(updated.audit_log || []),
            {
              timestamp: now,
              performed_by: "system",
              action: `Bulk quick-validated from export dialog`,
              category: "status_transition" as const,
              old_value: updated.validation_status,
              new_value: "Validated",
            },
          ],
        });
        validated++;
      }
    }
    refresh();
    toast({ title: "Bulk validation complete", description: `${validated} component${validated !== 1 ? "s" : ""} validated.` });
  };

  const handleExport = () => {
    if (!allReady) return;
    if (!coSignerId) {
      toast({ title: "Co-signer required", description: "Select a co-signer to authorize the export.", variant: "destructive" });
      return;
    }

    for (const c of checks) {
      if (c.status === "Validated") {
        lockComponent(c.nodeId);
      }
    }

    setExported(true);
    toast({ title: "Plant exported", description: `${plantName} has been exported and all components are now locked.` });
    onExportComplete();
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) setExported(false); onOpenChange(v); }}>
      <DialogContent className="max-w-2xl max-h-[85vh] p-0 overflow-hidden flex flex-col">
        <div className="p-5 border-b border-border bg-card/80 backdrop-blur-sm space-y-2">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-primary" />
              Pre-Export Validation
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              All components must be Validated or Locked before {plantName} can be exported. Assign roles and validate directly below.
            </DialogDescription>
          </DialogHeader>

          {/* Summary bar */}
          <div className={`rounded-lg border px-3 py-2 flex items-center justify-between ${
            allReady ? "border-success/40 bg-success/5" : "border-destructive/40 bg-destructive/5"
          }`}>
            <div className="flex items-center gap-2">
              {allReady ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-success" />
                  <span className="text-xs font-medium text-success">All {checks.length} components ready for export</span>
                </>
              ) : (
                <>
                  <AlertTriangle className="h-4 w-4 text-destructive" />
                  <span className="text-xs font-medium text-destructive">
                    {blockedCount} blocking · {unassignedCount} unassigned
                  </span>
                </>
              )}
            </div>
            {!allReady && (
              <Button
                size="sm"
                className="h-7 text-[11px] gap-1.5"
                onClick={handleValidateAll}
              >
                <Zap className="h-3 w-3" />
                Auto-Assign & Validate All
              </Button>
            )}
          </div>
        </div>

        {/* Checklist */}
        <div className="flex-1 min-h-0 overflow-y-auto p-5 space-y-2">
          {checks.map((c) => {
            const sc = VALIDATION_STATUS_CONFIG[c.status];
            const Icon = STATUS_ICON[c.status];
            return (
              <div
                key={c.nodeId}
                className={`rounded-lg border p-3 space-y-2 ${
                  c.ready ? "border-border bg-card" : "border-destructive/40 bg-destructive/5"
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`h-4 w-4 shrink-0 ${c.ready ? "text-success" : "text-destructive"}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-foreground truncate">{c.label}</span>
                      <Badge variant="outline" className="text-[9px] shrink-0">{c.type}</Badge>
                      <Badge variant="outline" className={`text-[9px] shrink-0 ${sc.color} ${sc.border}`}>
                        {sc.label}
                      </Badge>
                    </div>
                    {!c.ready && !c.hasAccountable && !c.hasResponsible && (
                      <p className="text-[10px] text-destructive mt-1">
                        No Accountable or Responsible assigned. Use the dropdowns below to assign.
                      </p>
                    )}
                    {!c.ready && c.hasAccountable && c.hasResponsible && (
                      <p className="text-[10px] text-destructive mt-1">
                        Roles assigned but not yet validated. Click "Quick Validate" to proceed.
                      </p>
                    )}
                  </div>
                  {!c.ready && c.hasAccountable && c.hasResponsible && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-[10px] gap-1 shrink-0 border-success/40 text-success hover:bg-success/10"
                      onClick={() => handleQuickValidate(c.nodeId)}
                    >
                      <ShieldCheck className="h-3 w-3" />
                      Quick Validate
                    </Button>
                  )}
                  {c.ready && (
                    <CheckCircle2 className="h-4 w-4 text-success shrink-0" />
                  )}
                </div>

                {/* Inline role assignment for unassigned components */}
                {!c.ready && (
                  <div className="grid grid-cols-2 gap-2 pl-7">
                    <div className="space-y-1">
                      <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                        <Crown className="h-3 w-3" />
                        <span>Accountable</span>
                      </div>
                      <Select
                        value={c.accountableId ?? ""}
                        onValueChange={(v) => handleAssignRole(c.nodeId, "accountable", v)}
                      >
                        <SelectTrigger className="h-7 text-[11px]">
                          {c.hasAccountable ? (
                            <span className="flex items-center gap-1">
                              <UserCheck className="h-3 w-3 text-success" />
                              {c.accountableName}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">Assign…</span>
                          )}
                        </SelectTrigger>
                        <SelectContent>
                          {team.map((m) => (
                            <SelectItem key={m.user_id} value={m.user_id} className="text-xs">
                              {m.name} · {m.global_role}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                        <UserCheck className="h-3 w-3" />
                        <span>Responsible</span>
                      </div>
                      <Select
                        value={c.responsibleId ?? ""}
                        onValueChange={(v) => handleAssignRole(c.nodeId, "responsible", v)}
                      >
                        <SelectTrigger className="h-7 text-[11px]">
                          {c.hasResponsible ? (
                            <span className="flex items-center gap-1">
                              <UserCheck className="h-3 w-3 text-success" />
                              {c.responsibleName}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">Assign…</span>
                          )}
                        </SelectTrigger>
                        <SelectContent>
                          {team.map((m) => (
                            <SelectItem key={m.user_id} value={m.user_id} className="text-xs">
                              {m.name} · {m.global_role}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                )}

                {/* Show assigned roles for ready components */}
                {c.ready && (
                  <div className="flex gap-4 pl-7">
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                      <Crown className="h-3 w-3" />
                      <span>{c.accountableName}</span>
                    </div>
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                      <UserCheck className="h-3 w-3" />
                      <span>{c.responsibleName}</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Export action with co-sign */}
        <div className="p-4 border-t border-border bg-card/80 backdrop-blur-sm space-y-3">
          {allReady && !exported && (
            <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 space-y-2">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-primary" />
                <span className="text-xs font-semibold text-foreground">Co-Signature Required</span>
              </div>
              <p className="text-[10px] text-muted-foreground">
                Four-eyes principle: a senior team member must co-sign to authorize this export.
              </p>
              <Select value={coSignerId} onValueChange={setCoSignerId}>
                <SelectTrigger className="h-8 text-xs">
                  {coSignerId ? (
                    <span className="flex items-center gap-1.5">
                      <UserCheck className="h-3 w-3 text-success" />
                      {getMemberName(coSignerId)}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">Select co-signer…</span>
                  )}
                </SelectTrigger>
                <SelectContent>
                  {coSigners.length > 0 ? (
                    coSigners.map((m) => (
                      <SelectItem key={m.user_id} value={m.user_id} className="text-xs">
                        {m.name} · {m.global_role}
                      </SelectItem>
                    ))
                  ) : (
                    <div className="px-3 py-2 text-xs text-muted-foreground">
                      No eligible co-signers found. Add team members first.
                    </div>
                  )}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="outline" className="flex-1" onClick={() => { setExported(false); onOpenChange(false); }}>
              {exported ? "Close" : "Cancel"}
            </Button>
            {!exported && (
              <Button
                className="flex-1 gap-1.5"
                disabled={!allReady || !coSignerId}
                onClick={handleExport}
              >
                <Lock className="h-3.5 w-3.5" />
                Export & Lock Plant
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default ExportValidationDialog;
